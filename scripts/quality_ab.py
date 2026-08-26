"""Paired Token Terminator answer-quality A/B experiment runner.

The runner gives the same synthetic prompt and evidence workspace to the same
Hermes model twice. Only TOKEN_TERMINATOR_MODE changes: off versus balanced.
It records deterministic grades and provider usage receipts without changing
live Hermes configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTROL = "control"
TREATMENT = "treatment"
ARM_MODES = {CONTROL: "off", TREATMENT: "balanced"}
DEFAULT_SEED = 20260826


class ExperimentError(ValueError):
    """The experiment definition or collected evidence is invalid."""


@dataclass(frozen=True)
class Trial:
    pair_id: str
    task_id: str
    repetition: int
    arm: str
    order: int
    prompt_path: Path
    workspace: Path
    prompt_sha256: str
    workspace_sha256: str
    task: dict[str, Any]


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExperimentError(f"{path} must contain a JSON object")
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _workspace_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _resolve(base: Path, raw: str, *, label: str) -> Path:
    path = (base / raw).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as exc:
        raise ExperimentError(f"{label} escapes the suite directory: {raw}") from exc
    return path


def validate_suite(path: Path) -> dict[str, Any]:
    suite = _read_json(path)
    base = path.parent.resolve()
    experiment_id = str(suite.get("experiment_id") or "").strip()
    if not experiment_id or len(experiment_id) > 80:
        raise ExperimentError("experiment_id must contain 1-80 characters")
    repetitions = int(suite.get("repetitions", 0))
    if repetitions < 1:
        raise ExperimentError("repetitions must be at least 1")
    margin = float(suite.get("noninferiority_margin", 0.05))
    if not 0 < margin < 1:
        raise ExperimentError("noninferiority_margin must be between 0 and 1")
    minimum_control_pass_rate = float(suite.get("minimum_control_pass_rate", 0.8))
    if not 0 < minimum_control_pass_rate <= 1:
        raise ExperimentError("minimum_control_pass_rate must be in (0, 1]")
    tasks = suite.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ExperimentError("tasks must be a non-empty array")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw_task in tasks:
        if not isinstance(raw_task, dict):
            raise ExperimentError("every task must be an object")
        task = dict(raw_task)
        task_id = str(task.get("id") or "").strip()
        if not task_id or task_id in seen:
            raise ExperimentError(f"task id is empty or duplicated: {task_id!r}")
        seen.add(task_id)
        prompt = _resolve(base, str(task.get("prompt") or ""), label="prompt")
        workspace = _resolve(base, str(task.get("workspace") or ""), label="workspace")
        if not prompt.is_file():
            raise ExperimentError(f"task {task_id}: prompt does not exist: {prompt}")
        if not workspace.is_dir():
            raise ExperimentError(
                f"task {task_id}: workspace does not exist: {workspace}"
            )
        try:
            prompt.relative_to(workspace)
        except ValueError as exc:
            raise ExperimentError(
                f"task {task_id}: prompt must be inside its workspace"
            ) from exc
        prompt_text = prompt.read_text(encoding="utf-8")
        if not prompt_text.strip():
            raise ExperimentError(f"task {task_id}: prompt is empty")
        evidence_chars = sum(
            len(candidate.read_text(encoding="utf-8"))
            for candidate in workspace.rglob("*")
            if candidate.is_file() and candidate != prompt
        )
        minimum = int(task.get("min_evidence_chars", 12_000))
        if evidence_chars < minimum:
            raise ExperimentError(
                f"task {task_id}: evidence has {evidence_chars} chars; "
                f"requires at least {minimum}"
            )
        assertions = task.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise ExperimentError(f"task {task_id}: assertions must be non-empty")
        for assertion in assertions:
            if not isinstance(assertion, dict) or not str(assertion.get("path") or ""):
                raise ExperimentError(
                    f"task {task_id}: every assertion needs a field path"
                )
            if "equals" not in assertion:
                raise ExperimentError(
                    f"task {task_id}: assertion {assertion['path']} needs equals"
                )
        forbidden = task.get("forbidden", [])
        if not isinstance(forbidden, list):
            raise ExperimentError(f"task {task_id}: forbidden must be an array")
        task["_prompt_path"] = str(prompt)
        task["_workspace"] = str(workspace)
        task["_prompt_sha256"] = _sha256_text(prompt_text)
        task["_workspace_sha256"] = _workspace_sha256(workspace)
        task["_evidence_chars"] = evidence_chars
        validated.append(task)

    target_pairs = len(validated) * repetitions
    minimum_decision_pairs = int(suite.get("minimum_decision_pairs", target_pairs))
    if minimum_decision_pairs < target_pairs:
        raise ExperimentError("minimum_decision_pairs cannot be below target_pairs")
    return {
        **suite,
        "experiment_id": experiment_id,
        "repetitions": repetitions,
        "noninferiority_margin": margin,
        "minimum_control_pass_rate": minimum_control_pass_rate,
        "tasks": validated,
        "target_pairs": target_pairs,
        "minimum_decision_pairs": minimum_decision_pairs,
    }


def build_plan(suite: dict[str, Any], *, seed: int = DEFAULT_SEED) -> list[Trial]:
    trials: list[Trial] = []
    for task in suite["tasks"]:
        for repetition in range(1, int(suite["repetitions"]) + 1):
            pair_id = f"{task['id']}:r{repetition}"
            arms = [CONTROL, TREATMENT]
            pair_seed = int(
                hashlib.sha256(f"{seed}:{pair_id}".encode()).hexdigest()[:16],
                16,
            )
            random.Random(pair_seed).shuffle(arms)
            for order, arm in enumerate(arms, start=1):
                trials.append(
                    Trial(
                        pair_id=pair_id,
                        task_id=task["id"],
                        repetition=repetition,
                        arm=arm,
                        order=order,
                        prompt_path=Path(task["_prompt_path"]),
                        workspace=Path(task["_workspace"]),
                        prompt_sha256=task["_prompt_sha256"],
                        workspace_sha256=task["_workspace_sha256"],
                        task=task,
                    )
                )
    return trials


def _path_value(value: Any, raw_path: str) -> Any:
    current = value
    for part in raw_path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(raw_path) from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(raw_path)
    return current


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    raise ExperimentError("response is not exactly one JSON object")


def grade_response(text: str, task: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = extract_json_object(text)
    except ExperimentError as exc:
        return {
            "passed": False,
            "score": 0.0,
            "assertions_passed": 0,
            "assertions_total": len(task["assertions"]),
            "malformed": True,
            "forbidden_hits": [],
            "failures": [str(exc)],
        }

    passed = 0
    failures: list[str] = []
    for assertion in task["assertions"]:
        path = str(assertion["path"])
        try:
            actual = _path_value(payload, path)
        except KeyError:
            failures.append(f"missing {path}")
            continue
        expected = assertion["equals"]
        if actual == expected:
            passed += 1
        else:
            failures.append(f"{path}: expected {expected!r}, got {actual!r}")

    forbidden_hits: list[str] = []
    for rule in task.get("forbidden", []):
        if not isinstance(rule, dict):
            continue
        path = str(rule.get("path") or "")
        values = rule.get("values", [])
        if not path or not isinstance(values, list):
            continue
        try:
            actual = _path_value(payload, path)
        except KeyError:
            continue
        if actual in values:
            forbidden_hits.append(f"{path}={actual!r}")

    total = len(task["assertions"])
    return {
        "passed": passed == total and not forbidden_hits,
        "score": round(passed / total, 6) if total else 0.0,
        "assertions_passed": passed,
        "assertions_total": total,
        "malformed": False,
        "forbidden_hits": forbidden_hits,
        "failures": failures,
    }


def _load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExperimentError(f"{path}:{line_number}: invalid JSONL row") from exc
        if not isinstance(row, dict):
            raise ExperimentError(f"{path}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def _completed_clean_keys(rows: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("pair_id")), str(row.get("arm")))
        for row in rows
        if not row.get("contaminated")
    }


def _append_result(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _usage_matches(usage: dict[str, Any], model: str, provider: str) -> bool:
    return usage.get("model") == model and usage.get("provider") == provider


def _session_id(stderr: str) -> str:
    matches = re.findall(r"(?m)^session_id:\s*(\S+)\s*$", stderr)
    return matches[-1] if matches else ""


def _read_session_usage(state_db: Path, session_id: str) -> dict[str, Any]:
    if not state_db.is_file() or not session_id:
        return {}
    for attempt in range(3):
        try:
            with sqlite3.connect(state_db, timeout=2.0) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """SELECT model, billing_provider, input_tokens, output_tokens,
                              cache_read_tokens, cache_write_tokens, reasoning_tokens,
                              api_call_count, tool_call_count, estimated_cost_usd,
                              actual_cost_usd, cost_status, cost_source
                       FROM sessions WHERE id = ?""",
                    (session_id,),
                ).fetchone()
            if row is None:
                return {}
            payload = dict(row)
            payload["provider"] = payload.pop("billing_provider", "")
            payload["total_tokens"] = int(payload.get("input_tokens") or 0) + int(
                payload.get("output_tokens") or 0
            )
            payload["session_id"] = session_id
            return payload
        except sqlite3.OperationalError:
            if attempt == 2:
                return {}
            time.sleep(0.05 * (attempt + 1))
    return {}


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_process(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: int
) -> ProcessResult:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return ProcessResult(process.returncode, stdout, stderr, False)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        return ProcessResult(124, stdout, stderr, True)


def run_trial(
    trial: Trial,
    *,
    hermes: str,
    model: str,
    provider: str,
    reasoning: str,
    experiment_id: str,
    timeout: int,
    state_db: Path,
    work_root: Path,
) -> dict[str, Any]:
    prompt_text = trial.prompt_path.read_text(encoding="utf-8")
    if _sha256_text(prompt_text) != trial.prompt_sha256:
        raise ExperimentError(f"prompt changed after planning: {trial.prompt_path}")
    if _workspace_sha256(trial.workspace) != trial.workspace_sha256:
        raise ExperimentError(f"workspace changed after planning: {trial.workspace}")
    work_root = work_root.resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    pair_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", trial.pair_id).strip("-")
    pair_root = work_root / "active" / pair_slug
    isolated_workspace = pair_root / "workspace"
    query_file = pair_root / "query.txt"
    effective_prompt = (
        prompt_text.rstrip()
        + "\n\n"
        + f"Evidence workspace (absolute): '{isolated_workspace}'. "
        + "Resolve every relative evidence filename in this task against that exact "
        + "directory; do not search outside it."
    )
    effective_prompt_sha256 = _sha256_text(effective_prompt)
    env = os.environ.copy()
    env["TOKEN_TERMINATOR_ENABLED"] = "true"
    env["TOKEN_TERMINATOR_MODE"] = ARM_MODES[trial.arm]
    env["TOKEN_TERMINATOR_EXPERIMENT"] = experiment_id
    started = _utc_now()
    before = time.monotonic()
    if pair_root.exists():
        shutil.rmtree(pair_root)
    pair_root.mkdir(parents=True)
    try:
        shutil.copytree(trial.workspace, isolated_workspace)
        query_file.write_text(effective_prompt, encoding="utf-8")
        command = [
            hermes,
            "chat",
            "--query-file",
            str(query_file),
            "--in",
            str(isolated_workspace),
            "-m",
            model,
            "--provider",
            provider,
            "--reasoning",
            reasoning,
            "--toolsets",
            "file",
            "-Q",
            "--ignore-rules",
            "--source",
            "tool",
            "--max-turns",
            "40",
            "--run-budget",
            str(max(1, int(timeout * 0.8))),
        ]
        completed = _run_process(
            command,
            cwd=isolated_workspace,
            env=env,
            timeout=timeout,
        )
    finally:
        shutil.rmtree(pair_root, ignore_errors=True)
    duration = round(time.monotonic() - before, 3)
    session_id = _session_id(completed.stderr)
    usage = _read_session_usage(state_db, session_id)
    grade = grade_response(completed.stdout, trial.task)
    contamination: list[str] = []
    if completed.exit_code:
        contamination.append(f"exit_code={completed.exit_code}")
    if completed.timed_out:
        contamination.append("timeout")
    if not usage:
        contamination.append("missing_usage")
    elif not _usage_matches(usage, model, provider):
        contamination.append(f"route={usage.get('provider')}/{usage.get('model')}")
    return {
        "schema": 1,
        "experiment_id": experiment_id,
        "pair_id": trial.pair_id,
        "task_id": trial.task_id,
        "category": trial.task.get("category", ""),
        "repetition": trial.repetition,
        "arm": trial.arm,
        "mode": ARM_MODES[trial.arm],
        "order": trial.order,
        "prompt_sha256": effective_prompt_sha256,
        "source_prompt_sha256": trial.prompt_sha256,
        "model": model,
        "provider": provider,
        "reasoning": reasoning,
        "session_id": session_id,
        "started_at": started,
        "duration_seconds": duration,
        "exit_code": completed.exit_code,
        "timed_out": completed.timed_out,
        "contaminated": bool(contamination),
        "contamination_reasons": contamination,
        "grade": grade,
        "usage": usage,
        "response": completed.stdout,
        "stderr": completed.stderr,
    }


def _paired_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[tuple[dict, dict]], int]:
    by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    duplicates = 0
    for row in rows:
        pair = by_pair.setdefault(str(row.get("pair_id") or ""), {})
        arm = str(row.get("arm") or "")
        if arm in pair:
            duplicates += 1
            existing = pair[arm]
            if not existing.get("contaminated") and row.get("contaminated"):
                continue
        pair[arm] = row
    pairs = []
    for pair in by_pair.values():
        if CONTROL in pair and TREATMENT in pair:
            pairs.append((pair[CONTROL], pair[TREATMENT]))
    return pairs, duplicates


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def paired_bootstrap_ci(
    deltas: list[float],
    *,
    samples: int,
    seed: int,
    clusters: list[str] | None = None,
) -> tuple[float, float]:
    if not deltas:
        return (0.0, 0.0)
    if clusters is None:
        clusters = [str(index) for index in range(len(deltas))]
    if len(clusters) != len(deltas):
        raise ExperimentError("bootstrap clusters must align with deltas")
    grouped: dict[str, list[float]] = {}
    for cluster, delta in zip(clusters, deltas, strict=True):
        grouped.setdefault(cluster, []).append(delta)
    cluster_ids = list(grouped)
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        selected = [rng.choice(cluster_ids) for _ in cluster_ids]
        sample = [delta for cluster in selected for delta in grouped[cluster]]
        means.append(statistics.fmean(sample))
    return (_percentile(means, 0.025), _percentile(means, 0.975))


def analyze_results(
    suite: dict[str, Any], rows: list[dict[str, Any]], *, seed: int
) -> dict[str, Any]:
    pairs, duplicates = _paired_rows(rows)
    eligible = [
        (control, treatment)
        for control, treatment in pairs
        if not control.get("contaminated") and not treatment.get("contaminated")
    ]
    pass_deltas = [
        float(bool(treatment["grade"]["passed"]))
        - float(bool(control["grade"]["passed"]))
        for control, treatment in eligible
    ]
    score_deltas = [
        float(treatment["grade"]["score"]) - float(control["grade"]["score"])
        for control, treatment in eligible
    ]
    input_deltas = [
        float(treatment["usage"].get("input_tokens", 0) or 0)
        - float(control["usage"].get("input_tokens", 0) or 0)
        for control, treatment in eligible
    ]
    total_deltas = [
        float(treatment["usage"].get("total_tokens", 0) or 0)
        - float(control["usage"].get("total_tokens", 0) or 0)
        for control, treatment in eligible
    ]
    task_clusters = [
        str(control.get("task_id") or control["pair_id"].rsplit(":r", 1)[0])
        for control, _ in eligible
    ]
    bootstrap_samples = int(suite.get("bootstrap_samples", 20_000))
    lower, upper = paired_bootstrap_ci(
        pass_deltas,
        samples=bootstrap_samples,
        seed=seed + 1,
        clusters=task_clusters,
    )
    input_lower, input_upper = paired_bootstrap_ci(
        input_deltas,
        samples=bootstrap_samples,
        seed=seed + 2,
        clusters=task_clusters,
    )
    target = int(suite["target_pairs"])
    minimum_decision_pairs = int(suite["minimum_decision_pairs"])
    margin = float(suite["noninferiority_margin"])
    minimum_control_pass_rate = float(suite["minimum_control_pass_rate"])
    collection_complete = len(eligible) >= target
    decision_complete = len(eligible) >= minimum_decision_pairs
    control_pass = (
        statistics.fmean(float(bool(c["grade"]["passed"])) for c, _ in eligible)
        if eligible
        else 0.0
    )
    treatment_pass = (
        statistics.fmean(float(bool(t["grade"]["passed"])) for _, t in eligible)
        if eligible
        else 0.0
    )
    assay_sensitive = control_pass >= minimum_control_pass_rate
    control_input = [float(c["usage"].get("input_tokens", 0) or 0) for c, _ in eligible]
    treatment_input = [
        float(t["usage"].get("input_tokens", 0) or 0) for _, t in eligible
    ]
    mean_control_input = statistics.fmean(control_input) if control_input else 0.0
    mean_treatment_input = statistics.fmean(treatment_input) if treatment_input else 0.0
    input_reduction_pct = (
        (mean_control_input - mean_treatment_input) / mean_control_input * 100
        if mean_control_input
        else 0.0
    )
    treatment_wins = sum(1 for delta in pass_deltas if delta > 0)
    control_wins = sum(1 for delta in pass_deltas if delta < 0)
    report = {
        "experiment_id": suite["experiment_id"],
        "status": (
            "complete"
            if decision_complete
            else "checkpoint_complete"
            if collection_complete
            else "collecting"
        ),
        "target_pairs": target,
        "minimum_decision_pairs": minimum_decision_pairs,
        "paired_rows": len(pairs),
        "eligible_pairs": len(eligible),
        "contaminated_pairs": len(pairs) - len(eligible),
        "duplicate_rows": duplicates,
        "primary": {
            "control_pass_rate": round(control_pass, 6),
            "treatment_pass_rate": round(treatment_pass, 6),
            "treatment_minus_control": round(
                statistics.fmean(pass_deltas) if pass_deltas else 0.0, 6
            ),
            "bootstrap_95_ci": [round(lower, 6), round(upper, 6)],
            "bootstrap_unit": "task",
            "noninferiority_margin": margin,
            "minimum_control_pass_rate": minimum_control_pass_rate,
            "assay_sensitive": assay_sensitive,
            "noninferior": decision_complete and assay_sensitive and lower >= -margin,
            "control_wins": control_wins,
            "treatment_wins": treatment_wins,
            "ties": len(pass_deltas) - control_wins - treatment_wins,
        },
        "secondary": {
            "mean_assertion_score_delta": round(
                statistics.fmean(score_deltas) if score_deltas else 0.0, 6
            ),
            "mean_input_token_delta": round(
                statistics.fmean(input_deltas) if input_deltas else 0.0, 3
            ),
            "input_token_delta_bootstrap_95_ci": [
                round(input_lower, 3),
                round(input_upper, 3),
            ],
            "mean_total_token_delta": round(
                statistics.fmean(total_deltas) if total_deltas else 0.0, 3
            ),
            "mean_control_input_tokens": round(mean_control_input, 3),
            "mean_treatment_input_tokens": round(mean_treatment_input, 3),
            "input_token_reduction_pct": round(input_reduction_pct, 3),
            "efficiency_win": decision_complete and input_upper < 0,
        },
    }
    report["decision"] = (
        "noninferior_and_more_efficient"
        if report["primary"]["noninferior"] and report["secondary"]["efficiency_win"]
        else "not_ready"
        if not decision_complete
        else "review_or_reject"
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "plan"):
        command = sub.add_parser(name)
        command.add_argument("--suite", type=Path, required=True)
        command.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run = sub.add_parser("run")
    run.add_argument("--suite", type=Path, required=True)
    run.add_argument("--results", type=Path, required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--provider", required=True)
    run.add_argument("--reasoning", default="high")
    run.add_argument("--hermes", default=shutil.which("hermes") or "hermes")
    run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run.add_argument("--timeout", type=int, default=600)
    run.add_argument("--max-pairs", type=int, default=0)
    run.add_argument(
        "--state-db",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        / "state.db",
    )
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--suite", type=Path, required=True)
    analyze.add_argument("--results", type=Path, required=True)
    analyze.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        suite = validate_suite(args.suite)
        if args.command == "validate":
            print(
                json.dumps(
                    {
                        "experiment_id": suite["experiment_id"],
                        "tasks": len(suite["tasks"]),
                        "repetitions": suite["repetitions"],
                        "target_pairs": suite["target_pairs"],
                        "minimum_decision_pairs": suite["minimum_decision_pairs"],
                        "answer_runs": suite["target_pairs"] * 2,
                        "evidence_chars": sum(
                            task["_evidence_chars"] for task in suite["tasks"]
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "plan":
            plan = build_plan(suite, seed=args.seed)
            print(
                json.dumps(
                    [
                        {
                            "pair_id": trial.pair_id,
                            "task_id": trial.task_id,
                            "repetition": trial.repetition,
                            "arm": trial.arm,
                            "mode": ARM_MODES[trial.arm],
                            "order": trial.order,
                            "prompt_sha256": trial.prompt_sha256,
                        }
                        for trial in plan
                    ],
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "analyze":
            report = analyze_results(suite, _load_results(args.results), seed=args.seed)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        if args.command == "run":
            existing = _load_results(args.results)
            completed = _completed_clean_keys(existing)
            plan = build_plan(suite, seed=args.seed)
            pair_ids = []
            for trial in plan:
                if trial.pair_id not in pair_ids:
                    pair_ids.append(trial.pair_id)
            incomplete = [
                pair_id
                for pair_id in pair_ids
                if any((pair_id, arm) not in completed for arm in ARM_MODES)
            ]
            selected = (
                incomplete[: args.max_pairs] if args.max_pairs > 0 else incomplete
            )
            selected_set = set(selected)
            for trial in plan:
                if trial.pair_id not in selected_set:
                    continue
                key = (trial.pair_id, trial.arm)
                if key in completed:
                    continue
                row = run_trial(
                    trial,
                    hermes=args.hermes,
                    model=args.model,
                    provider=args.provider,
                    reasoning=args.reasoning,
                    experiment_id=suite["experiment_id"],
                    timeout=args.timeout,
                    state_db=args.state_db,
                    work_root=args.results.parent / "workspaces",
                )
                _append_result(args.results, row)
                completed.add(key)
                print(
                    json.dumps(
                        {
                            "pair_id": trial.pair_id,
                            "arm": trial.arm,
                            "passed": row["grade"]["passed"],
                            "contaminated": row["contaminated"],
                            "input_tokens": row["usage"].get("input_tokens"),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            return 0
    except (ExperimentError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
