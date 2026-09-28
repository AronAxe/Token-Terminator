"""Offline, bounded context-lifecycle comparison with independent golden checks.

Normal middleware uses the released defaults for turn-age collapse. TT ContextEngine
owns history and disables only that lossy age-collapse path. Fixture JEV probabilities
are NOT real classifier accuracy, economics, or live-model answer-quality evidence.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from benchmark_context_ir import cases, solve, visible_evidence

from rtk_hermes_plus import Runtime, __version__
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.context_ir import expand_ir
from rtk_hermes_plus.history_engine import HistoryContextEngine
from rtk_hermes_plus.history_selection import EngineLimits
from rtk_hermes_plus.plugin import _schema

HERMES_COMMIT = "801a9022a742562a3c4578c0d8dd12cfd393fc47"
ARMS = (
    "tt_middleware_default",
    "tt_middleware_jev_ir",
    "tt_middleware_jev_ir_no_age_collapse",
    "tt_context_engine_jev_ir",
)


def long_history(case):
    history = [
        {
            "role": "system",
            "content": "Use exact source evidence. Preserve all constraints and current user wording.",
        },
        {
            "role": "user",
            "content": "Here is source evidence for our later engineering work.",
        },
        {"role": "assistant", "name": "fixture_evidence", "content": case.source},
    ]
    for index in range(50):
        label = chr(97 + index // 26) + chr(97 + index % 26)
        history.extend(
            [
                {
                    "role": "user",
                    "content": f"Discuss the meadow scene labeled {label}.",
                },
                {
                    "role": "assistant",
                    "content": (
                        f"The meadow scene labeled {label} had gentle breezes and drifting clouds above the hills. "
                        * 18
                    ),
                },
            ]
        )
    history.append({"role": "user", "content": case.question})
    return history


def fixture(case, calls):
    def transport(payload):
        calls.append(payload)
        answers = {}
        for key in payload["questions"]:
            cid, kind = key.rsplit("_", 1)
            candidate = payload["state"]["candidates"][cid]
            content = candidate["content"]
            relevant = content == case.source
            if candidate.get("kind") == "history_region":
                relevant = any(
                    row["content"] == case.source for row in json.loads(content)
                )
            value = (
                {"relevance": 0.95, "guard": 0.5, "salience": case.salience}[kind]
                if relevant
                else 0.01
            )
            answers[key] = {"type": "noul", "noul": value}
        return {"answers": answers}

    return transport


def recovery_probe(final, runtime, engine):
    """One explicit page fetch + one measured re-send; NOT a hidden quality oracle."""
    for message in final["messages"]:
        content = str(message.get("content") or "")
        match = re.search(r"\ba_[0-9a-f]{32}(?:[0-9a-f]{32})?\b", content)
        if not match:
            continue
        aid = match.group()
        is_history = content.startswith("[TT history ")
        name = "token_terminator_history" if is_history else "token_terminator"
        args = {
            "action": "get" if is_history else "artifact_get",
            "artifact_id": aid,
            "limit": 8000,
        }
        start = time.perf_counter()
        response = (
            engine.handle_tool_call(name, args) if is_history else runtime.tool(**args)
        )
        page = json.loads(response)
        if "content" not in page:
            raise AssertionError("recovery probe failed")
        expected = runtime.store.get_artifact(aid).content
        assert expected.startswith(page["content"])
        after = copy.deepcopy(final)
        after["messages"].extend(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "recovery_probe",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "recovery_probe", "content": response},
            ]
        )
        return {
            "available": True,
            "tool_calls": 1,
            "page_chars": len(page["content"]),
            "more_pages": page.get("next_offset") is not None,
            "local_latency_ms": round(1000 * (time.perf_counter() - start), 3),
            "additional_request_tokens": runtime.token_budget.measure_request(
                after
            ).tokens,
            "probe_exact_page": True,
            "scope": "induced probe, not required for the golden answer; a new provider call resends context",
        }
    return {"available": False, "tool_calls": 0, "additional_request_tokens": 0}


def run(models, repeats):
    report = {
        "version": __version__,
        "mode": "fixture-scores",
        "repeats": repeats,
        "hermes_commit": HERMES_COMMIT,
        "paid_api_calls": 0,
        "measurement": "complete canonical provider-request JSON; not hidden provider framing or billed tokens",
        "quality_scope": "independent visible-data golden checks; no live LLM or real JEV evaluation",
        "corpus": "five structured/prose/constraint tasks, source followed by fifty distracting conversation turns",
        "timing": "cold per-arm store; tokenizer warmed; engine capture included; optional retry cache separately measured",
        "config": {
            "jev_max_candidate_chars": 64000,
            "jev_max_state_chars": 200000,
            "engine_max_batches": 2,
            "engine_region_chars": 8000,
            "context_collapse_after_turns_middleware": 6,
        },
        "lcm_tt": {
            "status": "not_reproduced",
            "reason": "Pinned upstream has no bundled LCM implementation; no external LCM repository/commit, configuration or scored transcript was supplied. No simulated LCM result is substituted.",
        },
        "trials": [],
        "summary": [],
        "engine_failures": [],
    }
    for model in models:
        for case in cases():
            for repeat in range(repeats):
                for arm in ARMS:
                    print(
                        f"{model} {case.name} repeat={repeat} {arm}",
                        file=sys.stderr,
                        flush=True,
                    )
                    with tempfile.TemporaryDirectory(
                        prefix="tt-engine-bench-"
                    ) as directory:
                        root = Path(directory)
                        enabled = arm != "tt_middleware_default"
                        cfg = replace(
                            Config(),
                            db_path=root / "vault.db",
                            ledger_path=root / "ledger.db",
                            state_db_path=root / "state.db",
                            ledger_enabled=False,
                            jev_enabled=enabled,
                            context_ir_enabled=enabled,
                            jev_api_key="fixture",
                            jev_max_candidate_chars=64000,
                            jev_max_state_chars=200000,
                            context_collapse_after_turns=0
                            if arm.endswith("no_age_collapse")
                            else 6,
                        )
                        runtime = Runtime(cfg)
                        engine = HistoryContextEngine(config=cfg, limits=EngineLimits())
                        engine.update_model(model, 128000)
                        engine.on_session_start("benchmark")
                        calls = []
                        transport = fixture(case, calls)
                        engine.transport = runtime.jev_reducer.transport = transport
                        is_engine = arm == "tt_context_engine_jev_ir"
                        request = {
                            "model": model,
                            "temperature": 0,
                            "max_tokens": 2048,
                            "messages": long_history(case),
                            "tools": [{"type": "function", "function": _schema()}],
                        }
                        if is_engine:
                            request["tools"] += [
                                {"type": "function", "function": schema}
                                for schema in engine.get_tool_schemas()
                            ]
                        untouched = copy.deepcopy(request)
                        raw = runtime.token_budget.measure_request(request).tokens
                        assert raw is not None, (
                            "benchmark requires the selected model tokenizer"
                        )
                        start = time.perf_counter()
                        if is_engine:
                            engine.select_context(
                                request["messages"],
                                conversation_messages=request["messages"],
                            )
                        decision = runtime.llm_request_middleware(
                            request=request,
                            session_id="benchmark",
                            api_request_id=f"{arm}-{repeat}",
                        )
                        final = decision["request"] if decision else request
                        latency = round(1000 * (time.perf_counter() - start), 3)
                        count = runtime.token_budget.measure_request(final).tokens
                        assert request == untouched
                        evidence = next(
                            (
                                m["content"]
                                for m in final["messages"]
                                if m.get("name") == "fixture_evidence"
                            ),
                            None,
                        )
                        golden = visible_equal = exact = False
                        if evidence is not None:
                            try:
                                decoded = visible_evidence(evidence)
                                visible_equal = decoded == visible_evidence(case.source)
                                golden = solve(case, decoded) == case.expected
                                if evidence.startswith("TTIR/1 "):
                                    recovered = "".join(
                                        expand_ir(
                                            evidence,
                                            runtime.store,
                                            offset=i,
                                            limit=8000,
                                        )
                                        for i in range(0, len(case.source), 8000)
                                    )
                                    exact = recovered == case.source
                                else:
                                    exact = evidence == case.source
                            except (ValueError, TypeError, KeyError):
                                pass
                        protected = (
                            final["messages"][0] == request["messages"][0]
                            and final["messages"][-1] == request["messages"][-1]
                        )
                        entry = {
                            "model": model,
                            "case": case.name,
                            "repeat": repeat,
                            "arm": arm,
                            "raw_tokens": raw,
                            "final_input_tokens": count,
                            "reduction_vs_own_raw_pct": round(
                                100 * (raw - count) / raw, 3
                            ),
                            "local_latency_ms": latency,
                            "jev_fixture_calls": len(calls),
                            "jev_payload_chars": sum(
                                len(json.dumps(p, ensure_ascii=False)) for p in calls
                            ),
                            "jev_cost_usd": None if enabled else 0,
                            "cost_scope": "unmeasured live service; paid calls zero",
                            "golden_answer_visible": golden,
                            "visible_evidence_equal": visible_equal,
                            "exact_target_preserved_or_recoverable": exact,
                            "protected_boundary_pass": protected,
                            "no_enlargement": count <= raw,
                            "recovery_probe": recovery_probe(final, runtime, engine),
                        }
                        if is_engine:
                            entry["engine_status"] = dict(
                                engine.get_status()["context_engine"]
                            )
                            assert len(calls) <= 2
                            previous = len(calls)
                            start = time.perf_counter()
                            engine.select_context(
                                request["messages"],
                                conversation_messages=request["messages"],
                            )
                            runtime.llm_request_middleware(
                                request=request,
                                session_id="benchmark",
                                api_request_id="retry",
                            )
                            entry["identical_retry_local_ms"] = round(
                                1000 * (time.perf_counter() - start), 3
                            )
                            entry["identical_retry_new_jev_calls"] = (
                                len(calls) - previous
                            )
                            if not (
                                golden
                                and visible_equal
                                and exact
                                and protected
                                and count <= raw
                            ):
                                report["engine_failures"].append(
                                    f"{model}/{case.name}/{repeat}"
                                )
                        report["trials"].append(entry)
                        if is_engine:
                            engine.on_turn_complete(request["messages"])
    for model in models:
        for arm in ARMS:
            rows = [
                r for r in report["trials"] if r["model"] == model and r["arm"] == arm
            ]
            report["summary"].append(
                {
                    "model": model,
                    "arm": arm,
                    "evaluations": len(rows),
                    "raw_tokens_five_tasks_once": round(
                        sum(r["raw_tokens"] for r in rows) / repeats
                    ),
                    "final_tokens_five_tasks_once": round(
                        sum(r["final_input_tokens"] for r in rows) / repeats
                    ),
                    "median_local_ms": statistics.median(
                        r["local_latency_ms"] for r in rows
                    ),
                    "golden_passes": sum(r["golden_answer_visible"] for r in rows),
                    "exact_target_passes": sum(
                        r["exact_target_preserved_or_recoverable"] for r in rows
                    ),
                    "no_enlargement_passes": sum(r["no_enlargement"] for r in rows),
                    "jev_fixture_calls_per_trial": sorted(
                        {r["jev_fixture_calls"] for r in rows}
                    ),
                    "median_recovery_probe_resend_tokens": statistics.median(
                        r["recovery_probe"]["additional_request_tokens"] for r in rows
                    ),
                }
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["gpt-4o", "gpt-4"])
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    parser.add_argument(
        "--output", type=Path, default=Path("context-engine-results.json")
    )
    args = parser.parse_args()
    report = run(args.models, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "engine_failures": report["engine_failures"],
            },
            indent=2,
        )
    )
    return bool(report["engine_failures"])


if __name__ == "__main__":
    raise SystemExit(main())
