"""Bounded, synthetic end-to-end learning and exact-context regression benchmark.

Fixture JEV/proposal responses exercise real CatBoost training and deployment.
They are not a measurement of live JEV, LLM answer quality, or service economics.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rtk_hermes_plus import Runtime
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.context_history import encode
from rtk_hermes_plus.engine_bridge import take
from rtk_hermes_plus.history_engine import HistoryContextEngine
from rtk_hermes_plus.history_selection import EngineLimits
from rtk_hermes_plus.learned_policy import write_private_json
from rtk_hermes_plus.plugin import _schema
from rtk_hermes_plus.policy_data import TrainingRow
from rtk_hermes_plus.policy_features import fingerprint
from rtk_hermes_plus.policy_training import DiscoveryLimits, discover

QUERY = "Which rendezvous location had been agreed?"
PLACES = ("orchard gateway", "harbor archway", "meadow footbridge", "woodland clearing")
FILLER = "The breeze carried a gentle scent through the leaves as a quiet afternoon unfolded around the hills. "


def fixture_rows():
    rows = []
    for group in range(20):
        for offset in range(8):
            relevant = offset % 4 == 0
            place = PLACES[(group + offset) % len(PLACES)]
            # Word-only provenance variation prevents duplicate-source split leakage;
            # it is independent of outcomes and not a model feature supplied by TT.
            tag = chr(97 + group) * (offset + 2)
            content = (
                (
                    f"They settled on the {place} for their meeting. "
                    if relevant
                    else "A passing thought concerned the drift of a cloud. "
                )
                + FILLER * 12
                + f" The observer called this fragment {tag}."
            )
            source = [{"role": "assistant", "content": content, "ordinal": offset + 1}]
            rows.append(
                TrainingRow.from_dict(
                    {
                        "row_id": f"g{group}-r{offset}",
                        "session_id": f"session-{group}",
                        "task_id": f"task-{group}",
                        "split": "dev" if group < 16 else "holdout",
                        "query": QUERY,
                        "recent": [],
                        "source": source,
                        "source_sha256": fingerprint(source),
                        "omit_harm": int(relevant),
                        "recovery_tokens": 1200 if relevant else 0,
                        "saved_tokens": 250,
                        "label_origin": "synthetic",
                        "target_model": "gpt-4o" if group % 2 == 0 else "gpt-4",
                    }
                )
            )
    return rows


class FixtureServices:
    def __init__(self):
        self.calls = []
        self.feedback = []

    def features(self, payload):
        self.calls.append(copy.deepcopy(payload))
        answers = {}
        for key, question in payload["questions"].items():
            cid = key.split("_", 1)[0]
            source = payload["state"]["candidates"][cid]["content"]
            if "_learned_" not in key:
                value = 0.03  # deliberately weak original three-question gate
            elif "meeting_dependency" in key:
                value = 0.98 if "They settled on" in source else 0.02
            else:
                value = 0.5  # first-round feature does not predict the outcome
            if question["type"] == "score":
                n = len(question["criteria"])
                probabilities = {str(i): 0.0 for i in range(n)}
                probabilities["0"], probabilities[str(n - 1)] = 1 - value, value
                answers[key] = {"type": "score", "probabilities": probabilities}
            else:
                answers[key] = {"type": "noul", "noul": value}
        return {
            "answers": answers,
            "usage": {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0},
        }

    def propose(self, feedback):
        self.feedback.append(copy.deepcopy(feedback))
        name = "background_tone" if len(self.feedback) == 1 else "meeting_dependency"
        question = (
            "How strongly does the region describe background atmosphere?"
            if name == "background_tone"
            else "Does the region express a previous meeting-place decision needed to resolve the current question?"
        )
        return {
            "features": [
                {"name": name, "kind": "noul", "question": question, "criteria": []}
            ],
            "usage": {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0},
        }


def build_request(engine, rows, model):
    evidence = [
        {"role": m["role"], "content": m["content"]} for r in rows for m in r.source
    ]
    return {
        "model": model,
        "tools": [{"type": "function", "function": _schema()}]
        + [{"type": "function", "function": s} for s in engine.get_tool_schemas()],
        "messages": [
            {
                "role": "system",
                "content": "Preserve evidence and report the actual previous decision.",
            }
        ]
        + evidence
        + [
            {
                "role": "assistant",
                "content": "The launch cap is 12.30. Never alter the quoted code: `x = 17`.",
            },
            {"role": "assistant", "content": "Let us return to that question."},
            {"role": "user", "content": QUERY},
        ],
    }


def benchmark(output, repeats=2):
    rows, services = fixture_rows(), FixtureServices()
    with tempfile.TemporaryDirectory(prefix="tt-learned-benchmark-") as work:
        root = Path(work)
        base = Config(
            db_path=root / "training-vault.db",
            jev_enabled=True,
            jev_api_key="fixture",
            jev_provider="openrouter",
            jev_model="~typesafe/jev-fixture-v1",
            context_ir_enabled=True,
        )
        artifact, training, _replay = discover(
            rows,
            base,
            proposer=services.propose,
            transport=services.features,
            limits=DiscoveryLimits(rounds=2),
            mode="synthetic-offline",
        )
        sha = write_private_json(root / "policy.json", artifact)
        test_rows = [r for r in rows if r.split == "holdout"]
        trials = []
        for model in ("gpt-4o", "gpt-4"):
            # Warm tokenizer loading, which is not per-request inference cost.
            import tiktoken

            tiktoken.encoding_for_model(model).encode("warmup")
            for mode in ("off", "shadow", "active"):
                for repeat in range(repeats):
                    directory = root / f"{model}-{mode}-{repeat}"
                    directory.mkdir()
                    config = replace(
                        base,
                        db_path=directory / "vault.db",
                        ledger_path=directory / "ledger.db",
                        learned_policy_mode=mode,
                        learned_policy_path=str(root / "policy.json"),
                        learned_policy_sha256=sha,
                        context_ir_max_messages=64,
                    )
                    runtime = Runtime(config=config)
                    engine = HistoryContextEngine(
                        config=config,
                        limits=EngineLimits(
                            region_chars=2000, protect_last=3, max_batches=4
                        ),
                    )
                    engine.update_model(model, 128000)
                    engine.on_session_start("benchmark")
                    live = FixtureServices()
                    engine.transport = live.features
                    request = build_request(engine, test_rows, model)
                    original = copy.deepcopy(request)
                    started = time.perf_counter()
                    engine.select_context(request["messages"])
                    decision = runtime.llm_request_middleware(
                        request=request,
                        request_purpose="conversation",
                        session_id="benchmark",
                        api_request_id="first",
                    )
                    final = decision["request"] if decision else request
                    elapsed = (time.perf_counter() - started) * 1000
                    calls = len(live.calls)
                    retry = runtime.llm_request_middleware(
                        request=request,
                        request_purpose="conversation",
                        session_id="benchmark",
                        api_request_id="retry",
                    )
                    assert (retry["request"] if retry else request) == final
                    assert len(live.calls) == calls
                    required = [
                        r.source[0]["content"] for r in test_rows if r.omit_harm
                    ]
                    visible = [m.get("content", "") for m in final["messages"]]
                    exact = sum(text in visible for text in required)
                    protected = (
                        final["messages"][0] == request["messages"][0]
                        and final["messages"][-3:] == request["messages"][-3:]
                    )
                    raw_tokens = runtime.token_budget.measure_request(request).tokens
                    final_tokens = runtime.token_budget.measure_request(final).tokens
                    assert (
                        request == original and final_tokens <= raw_tokens and protected
                    )
                    if mode == "active":
                        assert exact == len(required)
                    # Induce exact recovery for one receipt, including a full provider resend.
                    recovery_ms, recovery_tokens, recovered = 0.0, 0, True
                    receipt = next(
                        (
                            m["content"]
                            for m in final["messages"]
                            if m.get("content", "").startswith("[TT history")
                        ),
                        None,
                    )
                    if receipt:
                        aid = receipt.split()[2].rstrip(";")
                        start = time.perf_counter()
                        message = engine._history().read("benchmark", aid)
                        recovered = message in request["messages"]
                        recovered_request = copy.deepcopy(final)
                        recovered_request["messages"].append(
                            {"role": "assistant", "content": encode(message)}
                        )
                        recovery_tokens = runtime.token_budget.measure_request(
                            recovered_request
                        ).tokens
                        recovery_ms = (time.perf_counter() - start) * 1000
                    trials.append(
                        {
                            "model": model,
                            "mode": mode,
                            "raw_tokens": raw_tokens,
                            "final_tokens": final_tokens,
                            "required_exact_spans": len(required),
                            "preserved_exact_spans": exact,
                            "protected": protected,
                            "exact_recovery": recovered,
                            "jev_fixture_calls": calls,
                            "retry_additional_calls": len(live.calls) - calls,
                            "elapsed_ms": round(elapsed, 3),
                            "induced_recovery_resend_tokens": recovery_tokens,
                            "induced_recovery_ms": round(recovery_ms, 3),
                        }
                    )
                    take()
        summary = []
        for model in ("gpt-4o", "gpt-4"):
            for mode in ("off", "shadow", "active"):
                selected = [
                    t for t in trials if t["model"] == model and t["mode"] == mode
                ]
                summary.append(
                    {
                        "model": model,
                        "mode": mode,
                        "final_tokens": selected[0]["final_tokens"],
                        "raw_tokens": selected[0]["raw_tokens"],
                        "preserved_exact_spans": selected[0]["preserved_exact_spans"],
                        "required_exact_spans": selected[0]["required_exact_spans"],
                        "jev_fixture_calls": selected[0]["jev_fixture_calls"],
                        "median_ms": statistics.median(
                            t["elapsed_ms"] for t in selected
                        ),
                    }
                )
        report = {
            "fixture_only": True,
            "paid_calls": 0,
            "learning": training,
            "summary": summary,
            "trials": trials,
            "limitations": "Synthetic weak-gate regression, not representative live JEV quality or calibrated omission risk. Learned layer may only retain more evidence. Saved-token labels in training are fixture costs; final token counts above use actual target tokenizers. No LCM or live-service comparison.",
        }
        Path(output).parent.mkdir(exist_ok=True, parents=True)
        Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("learned-policy-results.json")
    )
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=2)
    args = parser.parse_args()
    report = benchmark(args.output, args.repeats)
    print(
        json.dumps(
            {
                "learning": report["learning"]["evaluation"],
                "summary": report["summary"],
            },
            indent=2,
        )
    )
