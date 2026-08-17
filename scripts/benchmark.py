"""Deterministic Token Terminator structural-savings benchmark.

This measures the exact provider-visible payload reduction with o200k_base. It
makes no provider calls and does not claim answer-quality or end-to-end causal
session effects.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import tiktoken

from rtk_hermes_plus.compiler import RequestCompiler
from rtk_hermes_plus.compress import NativeCompressor
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.graph import WorkingStateGraph
from rtk_hermes_plus.metrics import Metrics
from rtk_hermes_plus.rewrite import Rewriter
from rtk_hermes_plus.storage import TokenTerminatorStore


def serialized(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def measurement(name: str, raw: str, output: str, encoding) -> dict:
    raw_tokens = len(encoding.encode(raw))
    output_tokens = len(encoding.encode(output))
    return {
        "name": name,
        "raw_chars": len(raw),
        "output_chars": len(output),
        "saved_chars": len(raw) - len(output),
        "char_reduction_pct": round((len(raw) - len(output)) / len(raw) * 100, 2),
        "raw_tokens": raw_tokens,
        "output_tokens": output_tokens,
        "saved_tokens": raw_tokens - output_tokens,
        "token_reduction_pct": round(
            (raw_tokens - output_tokens) / raw_tokens * 100, 2
        ),
    }


def _run(command: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stderr}"
        )
    return completed.stdout


def terminal_rewrite_case(root: Path, config: Config, encoding) -> dict:
    """Exercise the real RTK rewrite and compact-result path in a disposable repo."""
    repo = root / "terminal-fixture"
    repo.mkdir()
    _run(["git", "init", "-q"], cwd=repo)
    _run(["git", "config", "user.email", "benchmark@example.invalid"], cwd=repo)
    _run(["git", "config", "user.name", "Token Terminator Benchmark"], cwd=repo)
    fixture = repo / "benchmark_fixture.txt"
    fixture.write_text(
        "".join(f"original value {index:05d}\n" for index in range(8_000)),
        encoding="utf-8",
    )
    _run(["git", "add", "benchmark_fixture.txt"], cwd=repo)
    _run(["git", "commit", "-q", "-m", "benchmark baseline"], cwd=repo)
    fixture.write_text(
        "".join(
            f"changed value {index:05d}: repeated diagnostic evidence {index % 11}\n"
            for index in range(8_000)
        ),
        encoding="utf-8",
    )

    raw_command = "git diff --no-color -- benchmark_fixture.txt"
    raw_result = _run(
        ["git", "diff", "--no-color", "--", "benchmark_fixture.txt"], cwd=repo
    )
    rewriter = Rewriter(config, Metrics())
    if not rewriter.available:
        raise AssertionError("RTK executable is required for the terminal benchmark")
    rewritten = rewriter.rewrite(raw_command, cwd=repo)
    if not rewritten.command:
        raise AssertionError("RTK did not rewrite the terminal benchmark command")
    compact_result = _run(
        [
            str(rewriter.rtk_path),
            "git",
            "diff",
            "--no-color",
            "--",
            "benchmark_fixture.txt",
        ],
        cwd=repo,
    )
    result = measurement(
        "rtk_terminal_rewrite",
        serialized({"command": raw_command, "result": raw_result}),
        serialized({"command": rewritten.command, "result": compact_result}),
        encoding,
    )
    if result["saved_tokens"] <= 0:
        raise AssertionError(
            "RTK terminal benchmark did not reduce provider-visible tokens"
        )
    result["rewritten_command"] = rewritten.command
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic provider-visible structural benchmarks."
    )
    parser.add_argument(
        "--skip-rtk",
        action="store_true",
        help="skip the external RTK binary case (used by hermetic CI)",
    )
    args = parser.parse_args(argv)
    encoding = tiktoken.get_encoding("o200k_base")
    with tempfile.TemporaryDirectory(prefix="token-terminator-benchmark-") as temp_dir:
        root = Path(temp_dir)
        config = Config(
            mode="balanced",
            db_path=root / "artifacts.sqlite3",
            ledger_path=root / "experiments.sqlite3",
            state_db_path=root / "state.db",
            native_min_chars=1_000,
            native_max_chars=4_000,
            min_artifact_chars=1_000,
            graph_context_chars=0,
        )
        store = TokenTerminatorStore(config.db_path)
        graph = WorkingStateGraph(store)
        compiler = RequestCompiler(store, graph, config)
        compressor = NativeCompressor(config, Metrics(), None, store)
        cases = []
        if not args.skip_rtk:
            cases.append(terminal_rewrite_case(root, config, encoding))

        native_raw = "\n".join(
            f"src/module_{index % 40}.py:{index}: repeated match payload value={index % 7}"
            for index in range(12_000)
        )
        native_output = compressor.transform(
            tool_name="search_files",
            args={"pattern": "payload"},
            result=native_raw,
            session_id="benchmark",
            tool_call_id="native-1",
        )
        if native_output is None:
            raise AssertionError("native benchmark did not compress")
        native_artifact = store.search_artifacts("module_0.py", limit=1)[0]
        if store.get_artifact(native_artifact.artifact_id).content != native_raw:
            raise AssertionError("native benchmark recovery mismatch")
        cases.append(
            measurement("native_search_result", native_raw, native_output, encoding)
        )

        artifact = "\n".join(
            f"diagnostic line {index}: detailed state and repeated evidence"
            for index in range(6_000)
        )
        request = {
            "model": "benchmark-model",
            "messages": [
                {"role": "system", "content": "Stable instructions."},
                {"role": "user", "content": "Inspect the evidence."},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "terminal", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": artifact},
            ],
        }
        original = copy.deepcopy(request)
        first = compiler.compile(request, session_id="benchmark", request_id="lease-1")
        second = compiler.compile(request, session_id="benchmark", request_id="lease-2")
        if first.request != original or second.saved_chars <= 0 or request != original:
            raise AssertionError("lease benchmark violated immutability or reduction")
        if store.get_artifact(second.artifact_ids[0]).content != artifact:
            raise AssertionError("receipt benchmark recovery mismatch")
        cases.append(
            measurement(
                "repeated_artifact_second_exposure",
                serialized(original),
                serialized(second.request),
                encoding,
            )
        )

        duplicate_request = copy.deepcopy(original)
        duplicate_request["messages"].insert(
            -2,
            {"role": "tool", "tool_call_id": "older-call", "content": artifact},
        )
        duplicate_result = compiler.compile(
            duplicate_request,
            session_id="duplicate-benchmark",
            request_id="duplicate-1",
        )
        if (
            duplicate_result.saved_chars <= 0
            or duplicate_result.duplicates_collapsed != 1
        ):
            raise AssertionError(
                "duplicate benchmark did not collapse repeated evidence"
            )
        cases.append(
            measurement(
                "same_request_duplicate_artifact",
                serialized(duplicate_request),
                serialized(duplicate_result.request),
                encoding,
            )
        )

        graph.apply(
            [
                {
                    "op": "NODE_CREATE",
                    "node_id": "B1",
                    "kind": "observation",
                    "label": "The exact evidence remains recoverable from the private vault.",
                    "confidence": 1.0,
                    "priority": 1.0,
                },
                {
                    "op": "NODE_CREATE",
                    "node_id": "B2",
                    "kind": "constraint",
                    "label": "Never enlarge the final provider request.",
                    "confidence": 1.0,
                    "priority": 1.0,
                },
                {
                    "op": "EDGE_CREATE",
                    "edge_id": "BE1",
                    "kind": "supports",
                    "source": "B1",
                    "target": "B2",
                    "confidence": 0.9,
                },
            ],
            session_id="benchmark",
        )
        working_compiler = RequestCompiler(
            store,
            graph,
            replace(config, graph_context_chars=1_200),
        )
        guard_request = {
            "messages": [{"role": "user", "content": "What is the next safe step?"}]
        }
        guard_result = working_compiler.compile(
            guard_request,
            session_id="working-state-guard",
            request_id="guard-1",
        )
        if (
            guard_result.request != guard_request
            or guard_result.saved_chars != 0
            or guard_result.graph_context_injected
        ):
            raise AssertionError(
                "working-state guard enlarged or changed a small request"
            )
        cases.append(
            measurement(
                "working_state_guard_no_bloat",
                serialized(guard_request),
                serialized(guard_result.request),
                encoding,
            )
        )

        combined_request = copy.deepcopy(original)
        first_combined = working_compiler.compile(
            combined_request,
            session_id="combined-benchmark",
            request_id="combined-1",
        )
        combined_result = working_compiler.compile(
            combined_request,
            session_id="combined-benchmark",
            request_id="combined-2",
        )
        combined_payload = serialized(combined_result.request)
        if (
            first_combined.request != combined_request
            or combined_result.saved_chars <= 0
            or not combined_result.graph_context_injected
            or "<working_state>" not in combined_payload
            or combined_request != original
        ):
            raise AssertionError("combined working-state benchmark contract failed")
        cases.append(
            measurement(
                "receipt_plus_working_state_combined",
                serialized(combined_request),
                combined_payload,
                encoding,
            )
        )

        small_request = {"messages": [{"role": "user", "content": "short question"}]}
        small_result = compiler.compile(
            small_request,
            session_id="small-benchmark",
            request_id="small-1",
        )
        if small_result.request != small_request or small_result.saved_chars != 0:
            raise AssertionError("small request was changed")
        cases.append(
            measurement(
                "small_request_fail_open",
                serialized(small_request),
                serialized(small_result.request),
                encoding,
            )
        )

        floors = {
            "rtk_terminal_rewrite": 90.0,
            "native_search_result": 90.0,
            "repeated_artifact_second_exposure": 90.0,
            "same_request_duplicate_artifact": 40.0,
            "working_state_guard_no_bloat": 0.0,
            "receipt_plus_working_state_combined": 90.0,
            "small_request_fail_open": 0.0,
        }
        for case in cases:
            floor = floors[case["name"]]
            if case["token_reduction_pct"] < floor:
                raise AssertionError(
                    f"{case['name']} fell below its {floor:.1f}% token-reduction floor"
                )

        totals = {
            "raw_tokens": sum(case["raw_tokens"] for case in cases),
            "output_tokens": sum(case["output_tokens"] for case in cases),
        }
        totals["saved_tokens"] = totals["raw_tokens"] - totals["output_tokens"]
        totals["token_reduction_pct"] = round(
            totals["saved_tokens"] / totals["raw_tokens"] * 100,
            2,
        )
        print(
            json.dumps(
                {
                    "benchmark": "token-terminator-structural-v1",
                    "tokenizer": "o200k_base",
                    "provider_calls": 0,
                    "claims": "provider-visible structural reduction only",
                    "cases": cases,
                    "totals": totals,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
