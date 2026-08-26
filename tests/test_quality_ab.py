from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


def load_quality_ab():
    path = Path(__file__).resolve().parents[1] / "scripts" / "quality_ab.py"
    spec = importlib.util.spec_from_file_location("quality_ab", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_suite(tmp_path: Path, *, repetitions: int = 2, bootstrap_samples: int = 500):
    workspace = tmp_path / "cases" / "case-1"
    workspace.mkdir(parents=True)
    (workspace / "prompt.txt").write_text(
        'Read evidence.txt and return {"answer": {"code": "..."}}.',
        encoding="utf-8",
    )
    (workspace / "evidence.txt").write_text("evidence\n" * 1600, encoding="utf-8")
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps(
            {
                "experiment_id": "quality-test",
                "repetitions": repetitions,
                "noninferiority_margin": 0.05,
                "bootstrap_samples": bootstrap_samples,
                "tasks": [
                    {
                        "id": "case-1",
                        "category": "needle",
                        "workspace": "cases/case-1",
                        "prompt": "cases/case-1/prompt.txt",
                        "min_evidence_chars": 12000,
                        "assertions": [{"path": "answer.code", "equals": "K-204"}],
                        "forbidden": [{"path": "answer.code", "values": ["K-240"]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def result(pair_id, arm, *, passed=True, score=1.0, input_tokens=1000):
    return {
        "pair_id": pair_id,
        "arm": arm,
        "contaminated": False,
        "grade": {"passed": passed, "score": score},
        "usage": {"input_tokens": input_tokens, "total_tokens": input_tokens + 50},
    }


def test_validate_and_plan_preserve_identical_prompt_hashes(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(make_suite(tmp_path))

    plan = quality.build_plan(suite, seed=7)

    assert suite["target_pairs"] == 2
    assert len(plan) == 4
    by_pair = {}
    for trial in plan:
        by_pair.setdefault(trial.pair_id, []).append(trial)
    assert all(
        {trial.arm for trial in pair} == {"control", "treatment"}
        for pair in by_pair.values()
    )
    assert all(
        len({trial.prompt_sha256 for trial in pair}) == 1 for pair in by_pair.values()
    )
    assert all(
        sorted(trial.order for trial in pair) == [1, 2] for pair in by_pair.values()
    )


def test_arm_order_is_stable_when_repetitions_extend(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(make_suite(tmp_path, repetitions=3))
    first = {
        (trial.pair_id, trial.arm): trial.order
        for trial in quality.build_plan(suite, seed=17)
    }
    extended = {**suite, "repetitions": 6}
    second = {
        (trial.pair_id, trial.arm): trial.order
        for trial in quality.build_plan(extended, seed=17)
    }

    assert all(second[key] == order for key, order in first.items())


def test_grade_response_requires_all_exact_fields_and_rejects_decoy(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(make_suite(tmp_path))
    task = suite["tasks"][0]

    good = quality.grade_response('{"answer":{"code":"K-204"}}', task)
    decoy = quality.grade_response('{"answer":{"code":"K-240"}}', task)
    malformed = quality.grade_response("not json", task)

    assert good["passed"] is True
    assert decoy["passed"] is False
    assert decoy["forbidden_hits"]
    assert malformed["malformed"] is True


def test_json_extractor_accepts_fences_but_rejects_conversational_wrappers(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(make_suite(tmp_path))

    fenced = quality.extract_json_object('```json\n{"answer": 7}\n```')
    conversational = quality.grade_response(
        'Here is the requested object:\n{"answer":{"code":"K-204"}}',
        suite["tasks"][0],
    )

    assert fenced == {"answer": 7}
    assert conversational["passed"] is False
    assert conversational["malformed"] is True


def test_committed_suite_is_valid_and_self_consistent():
    quality = load_quality_ab()
    root = Path(__file__).resolve().parents[1]
    suite = quality.validate_suite(root / "benchmarks" / "quality_ab" / "suite.json")
    categories = {}

    for task in suite["tasks"]:
        categories[task["category"]] = categories.get(task["category"], 0) + 1
        payload = {}
        for assertion in task["assertions"]:
            current = payload
            parts = assertion["path"].split(".")
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = assertion["equals"]
        for forbidden in task.get("forbidden", []):
            matching = [
                assertion["equals"]
                for assertion in task["assertions"]
                if assertion["path"] == forbidden["path"]
            ]
            assert not any(value in forbidden["values"] for value in matching)
        assert quality.grade_response(json.dumps(payload), task)["passed"] is True

    assert len(suite["tasks"]) == 12
    assert suite["target_pairs"] == 36
    assert suite["minimum_decision_pairs"] == 72
    assert sorted(categories.values()) == [2, 2, 2, 2, 2, 2]
    by_id = {task["id"]: task for task in suite["tasks"]}
    case_12 = by_id["case_12_long_list_compliance_firewall_rules"]
    assert case_12["assertions"][0]["equals"] == "PCI-DSS v4.0 Requirement 1.3"
    case_12_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(case_12["_workspace"]).iterdir()
        if path.is_file()
    )
    assert "PCI-DSS v4.0" in case_12_text
    case_09 = by_id["case_09_subtle_config_envoy_cors_misconfig"]
    case_09_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path(case_09["_workspace"]).iterdir()
        if path.is_file()
    )
    assert "regex: 'https://.*\\.corp\\.internal'" in case_09_text


def test_run_trial_changes_only_arm_environment_not_prompt(tmp_path, monkeypatch):
    quality = load_quality_ab()
    suite = quality.validate_suite(make_suite(tmp_path, repetitions=1))
    plan = quality.build_plan(suite, seed=3)
    calls = []
    state_db = tmp_path / "state.db"
    with sqlite3.connect(state_db) as connection, connection:
        connection.execute(
            """CREATE TABLE sessions(
                   id TEXT PRIMARY KEY, model TEXT, billing_provider TEXT,
                   input_tokens INTEGER, output_tokens INTEGER,
                   cache_read_tokens INTEGER, cache_write_tokens INTEGER,
                   reasoning_tokens INTEGER, api_call_count INTEGER,
                   tool_call_count INTEGER, estimated_cost_usd REAL,
                   actual_cost_usd REAL, cost_status TEXT, cost_source TEXT)"""
        )

    class FakePopen:
        pid = 100
        returncode = 0

        def __init__(self, command, **kwargs):
            arm = kwargs["env"]["TOKEN_TERMINATOR_MODE"]
            self.session_id = f"fake-{arm}"
            assert not Path(kwargs["cwd"], "agent-scratch.txt").exists()
            with sqlite3.connect(state_db) as connection, connection:
                connection.execute(
                    "INSERT INTO sessions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        self.session_id,
                        "gpt-test",
                        "provider-test",
                        100,
                        20,
                        0,
                        0,
                        0,
                        1,
                        1,
                        0.0,
                        0.0,
                        "included",
                        "oauth",
                    ),
                )
            Path(kwargs["cwd"], "agent-scratch.txt").write_text(
                "arm-local", encoding="utf-8"
            )
            query_file = Path(command[command.index("--query-file") + 1])
            assert query_file.is_absolute()
            workspace = Path(command[command.index("--in") + 1])
            assert workspace.is_absolute()
            calls.append(
                {
                    "command": list(command),
                    "env": dict(kwargs["env"]),
                    "cwd": Path(kwargs["cwd"]),
                    "prompt": query_file.read_text(encoding="utf-8"),
                }
            )

        def communicate(self, timeout=None):
            return (
                '{"answer":{"code":"K-204"}}',
                f"session_id: {self.session_id}\n",
            )

    monkeypatch.setattr(quality.subprocess, "Popen", FakePopen)
    rows = []
    for trial in plan:
        rows.append(
            quality.run_trial(
                trial,
                hermes="hermes",
                model="gpt-test",
                provider="provider-test",
                reasoning="high",
                experiment_id="quality-test",
                timeout=60,
                state_db=state_db,
                work_root=tmp_path / "workspaces",
            )
        )

    prompts = [call["prompt"] for call in calls]
    assert prompts[0] == prompts[1]
    assert "Evidence workspace (absolute):" in prompts[0]
    normalized_commands = []
    for call in calls:
        command = list(call["command"])
        command[command.index("--query-file") + 1] = "<query-file>"
        command[command.index("--in") + 1] = "<workspace>"
        normalized_commands.append(command)
    assert normalized_commands[0] == normalized_commands[1]
    assert "chat" in normalized_commands[0]
    assert "--reasoning" in normalized_commands[0]
    assert (
        normalized_commands[0][normalized_commands[0].index("--toolsets") + 1] == "file"
    )
    assert "--ignore-rules" in normalized_commands[0]
    budget_index = normalized_commands[0].index("--run-budget") + 1
    assert normalized_commands[0][budget_index] == "48"
    assert {call["env"]["TOKEN_TERMINATOR_MODE"] for call in calls} == {
        "off",
        "balanced",
    }
    assert all(row["grade"]["passed"] for row in rows)
    assert all(not row["contaminated"] for row in rows)
    assert calls[0]["cwd"] == calls[1]["cwd"]
    assert rows[0]["prompt_sha256"] == rows[1]["prompt_sha256"]
    assert rows[0]["source_prompt_sha256"] == rows[1]["source_prompt_sha256"]
    assert not (Path(suite["tasks"][0]["_workspace"]) / "agent-scratch.txt").exists()


def test_timeout_kills_the_complete_process_group(tmp_path, monkeypatch):
    quality = load_quality_ab()
    killed = []

    class TimeoutPopen:
        pid = 321
        returncode = None

        def __init__(self, command, **kwargs):
            self.command = command
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise quality.subprocess.TimeoutExpired(self.command, timeout)
            return ("partial", "timed out")

    monkeypatch.setattr(quality.subprocess, "Popen", TimeoutPopen)
    monkeypatch.setattr(
        quality, "_kill_process_tree", lambda process: killed.append(process.pid)
    )

    result = quality._run_process(
        ["hermes", "-z", "prompt"], cwd=tmp_path, env={}, timeout=1
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert killed == [321]


def test_paired_bootstrap_ci_is_deterministic_for_constant_deltas():
    quality = load_quality_ab()

    assert quality.paired_bootstrap_ci([0.0] * 12, samples=100, seed=1) == (
        0.0,
        0.0,
    )
    assert quality.paired_bootstrap_ci([-1.0] * 12, samples=100, seed=1) == (
        -1.0,
        -1.0,
    )


def test_clean_retry_replaces_contaminated_attempt():
    quality = load_quality_ab()
    contaminated = result("case-1:r1", "control")
    contaminated["contaminated"] = True
    clean = result("case-1:r1", "control", input_tokens=900)
    treatment = result("case-1:r1", "treatment", input_tokens=500)

    assert quality._completed_clean_keys([contaminated]) == set()
    pairs, duplicates = quality._paired_rows([contaminated, clean, treatment])

    assert duplicates == 1
    assert pairs[0][0]["usage"]["input_tokens"] == 900


def test_complete_noninferior_report_requires_quality_and_efficiency(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(
        make_suite(tmp_path, repetitions=72, bootstrap_samples=1000)
    )
    rows = []
    for index in range(72):
        pair = f"case-1:r{index + 1}"
        rows.append(result(pair, "control", input_tokens=1000))
        rows.append(result(pair, "treatment", input_tokens=500))

    report = quality.analyze_results(suite, rows, seed=9)

    assert report["status"] == "complete"
    assert report["primary"]["noninferior"] is True
    assert report["primary"]["bootstrap_unit"] == "task"
    assert report["secondary"]["efficiency_win"] is True
    assert report["secondary"]["input_token_reduction_pct"] == 50.0
    assert report["decision"] == "noninferior_and_more_efficient"


def test_quality_drop_fails_noninferiority_gate(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(
        make_suite(tmp_path, repetitions=72, bootstrap_samples=1000)
    )
    rows = []
    for index in range(72):
        pair = f"case-1:r{index + 1}"
        rows.append(result(pair, "control", input_tokens=1000))
        rows.append(
            result(
                pair,
                "treatment",
                passed=index >= 10,
                score=0.0 if index < 10 else 1.0,
                input_tokens=500,
            )
        )

    report = quality.analyze_results(suite, rows, seed=9)

    assert report["status"] == "complete"
    assert report["primary"]["noninferior"] is False
    assert report["decision"] == "review_or_reject"


def test_both_arms_failing_cannot_pass_noninferiority(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(
        make_suite(tmp_path, repetitions=72, bootstrap_samples=100)
    )
    rows = []
    for index in range(72):
        pair = f"case-1:r{index + 1}"
        rows.append(result(pair, "control", passed=False, score=0.0, input_tokens=1000))
        rows.append(
            result(pair, "treatment", passed=False, score=0.0, input_tokens=500)
        )

    report = quality.analyze_results(suite, rows, seed=9)

    assert report["primary"]["control_pass_rate"] == 0.0
    assert report["primary"]["assay_sensitive"] is False
    assert report["primary"]["noninferior"] is False
    assert report["decision"] == "review_or_reject"


def test_report_stays_provisional_before_precommitted_sample(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(
        make_suite(tmp_path, repetitions=72, bootstrap_samples=100)
    )
    rows = [
        result("case-1:r1", "control", input_tokens=1000),
        result("case-1:r1", "treatment", input_tokens=500),
    ]

    report = quality.analyze_results(suite, rows, seed=9)

    assert report["status"] == "collecting"
    assert report["primary"]["noninferior"] is False
    assert report["decision"] == "not_ready"


def test_first_36_pairs_are_an_answer_quality_checkpoint(tmp_path):
    quality = load_quality_ab()
    suite = quality.validate_suite(
        make_suite(tmp_path, repetitions=36, bootstrap_samples=100)
    )
    suite["minimum_decision_pairs"] = 72
    rows = []
    for index in range(36):
        pair = f"case-1:r{index + 1}"
        rows.append(result(pair, "control", input_tokens=1000))
        rows.append(result(pair, "treatment", input_tokens=500))

    report = quality.analyze_results(suite, rows, seed=9)

    assert report["status"] == "checkpoint_complete"
    assert report["eligible_pairs"] == 36
    assert report["primary"]["control_pass_rate"] == 1.0
    assert report["primary"]["treatment_pass_rate"] == 1.0
    assert report["primary"]["noninferior"] is False
    assert report["decision"] == "not_ready"
