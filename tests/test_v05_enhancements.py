from __future__ import annotations

import json
import re

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.enhancements import TokenAwareRequestCompiler
from rtk_hermes_plus.graph import WorkingStateGraph
from rtk_hermes_plus.plugin import Runtime
from rtk_hermes_plus.storage import TokenTerminatorStore
from rtk_hermes_plus.token_budget import TokenBudgetAdapter, TokenMeasurement


def _config(tmp_path, **kwargs):
    values = {
        "mode": "balanced",
        "ledger_enabled": False,
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
        "db_path": tmp_path / "artifacts.sqlite3",
        "min_artifact_chars": 10,
        "native_min_chars": 1_000,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


def test_temporal_terminal_delta_preserves_exact_current_output(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS", "1")
    runtime = Runtime(_config(tmp_path))
    args = {"command": "tree src", "cwd": str(tmp_path)}
    first = "\n".join(f"src/file_{index}.py" for index in range(300))

    assert (
        runtime.transform_tool_result(
            tool_name="terminal",
            args=args,
            result=first,
            session_id="session-a",
            tool_call_id="call-1",
        )
        is None
    )

    unchanged = runtime.transform_tool_result(
        tool_name="terminal",
        args=args,
        result=first,
        session_id="session-a",
        tool_call_id="call-2",
    )
    assert unchanged is not None
    assert "no output changes" in unchanged
    assert len(unchanged) < len(first)

    changed_lines = first.splitlines()
    changed_lines[150] = "src/new_file.py"
    changed = "\n".join(changed_lines)
    delta = runtime.transform_tool_result(
        tool_name="terminal",
        args=args,
        result=changed,
        session_id="session-a",
        tool_call_id="call-3",
    )
    assert delta is not None
    assert "src/new_file.py" in delta
    assert len(delta) < len(changed)

    match = re.search(r"current=(a_[0-9a-f]+)", delta)
    assert match is not None
    exact = json.loads(runtime.tool("artifact_get", artifact_id=match.group(1), limit=20_000))
    assert exact["content"] == changed


def test_multiresolution_recovery_keeps_exact_artifact_authoritative(tmp_path):
    runtime = Runtime(_config(tmp_path))
    assert runtime.store is not None
    content = json.dumps(
        {
            "service": "payments",
            "status": "warning",
            "needle": "find me",
            "items": list(range(50)),
        }
    )
    stored = runtime.store.put_artifact(content, tool_name="process")

    peek = json.loads(
        runtime.tool("artifact_peek", artifact_id=stored.artifact_id, limit=1_000)
    )
    assert peek["lossy"] is True
    assert peek["structure"]["type"] == "object"
    assert peek["exact_recovery"] == "token_terminator action=artifact_get"

    found = json.loads(
        runtime.tool(
            "artifact_find",
            artifact_id=stored.artifact_id,
            query="needle",
            limit=10,
        )
    )
    assert found["total_matches"] == 1

    exact = json.loads(
        runtime.tool("artifact_get", artifact_id=stored.artifact_id, limit=20_000)
    )
    assert exact["content"] == content


def test_token_budget_uses_configured_tiktoken_and_reserves_headroom(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", "cl100k_base")
    monkeypatch.setenv("TOKEN_TERMINATOR_CONTEXT_LIMIT_TOKENS", "1000")
    monkeypatch.setenv("TOKEN_TERMINATOR_OUTPUT_RESERVE_TOKENS", "100")
    monkeypatch.setenv("TOKEN_TERMINATOR_TOKEN_SAFETY_MARGIN", "50")
    budget = TokenBudgetAdapter()

    measured = budget.measure_text("hello world")
    assert measured.tokens is not None
    assert measured.tokens > 0
    assert measured.backend == "tiktoken:encoding:cl100k_base"
    assert budget.usable_context_tokens == 850


class _RejectReceiptsBudget:
    def measure_request(self, request):
        encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
        tokens = 10_000 if "Token Terminator artifact" in encoded else 100
        return TokenMeasurement(tokens=tokens, backend="test")


def test_token_gate_rolls_back_lease_claim_when_receipt_expands_tokens(tmp_path):
    config = _config(tmp_path, inline_lease_exposures=1)
    store = TokenTerminatorStore(config.db_path)
    compiler = TokenAwareRequestCompiler(
        store,
        WorkingStateGraph(store),
        config,
        token_budget=_RejectReceiptsBudget(),
    )
    evidence = "x" * 4_000
    request = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "process", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": evidence},
        ]
    }

    result = compiler.compile(
        request,
        session_id="session-a",
        request_id="request-a",
        record_metric=False,
    )
    assert result.saved_chars == 0
    assert result.request == request
    with store.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM artifact_exposures WHERE request_id='request-a'"
        ).fetchone()[0]
    assert count == 0
