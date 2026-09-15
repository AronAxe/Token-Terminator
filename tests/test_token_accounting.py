from __future__ import annotations

import json

from rtk_hermes_plus import Runtime
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.token_budget import TokenBudgetAdapter, TokenMeasurement


def _config(tmp_path, **kwargs):
    values = {
        "mode": "balanced",
        "ledger_enabled": False,
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
        "db_path": tmp_path / "artifacts.sqlite3",
        "min_artifact_chars": 20,
        "native_min_chars": 1_000,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


class _DeterministicBudget:
    usable_context_tokens = None

    def __init__(self):
        self.text_models: list[str] = []

    def measure_request(self, request, *, model=""):
        request_model = request.get("model", "") if isinstance(request, dict) else ""
        active_model = str(request_model or model or "")
        encoded = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return TokenMeasurement(len(encoded), "test-tokenizer", active_model)

    def measure_text(self, text, *, model=""):
        self.text_models.append(str(model or ""))
        return TokenMeasurement(max(1, len(text) // 3), "test-tokenizer", str(model or ""))

    def status(self):
        return {"enabled": True, "backend": "test-tokenizer"}


def _install_budget(runtime, budget):
    runtime.token_budget = budget
    runtime._sync_token_budget()


def test_request_token_savings_are_persisted_and_reported(tmp_path):
    runtime = Runtime(_config(tmp_path))
    budget = _DeterministicBudget()
    _install_budget(runtime, budget)

    output = "large evidence " * 300
    request = {
        "model": "openai/gpt-5",
        "messages": [
            {"role": "user", "content": "question"},
            {"role": "tool", "tool_call_id": "c1", "content": output},
        ],
    }

    runtime.llm_request_middleware(
        request=request,
        session_id="session-a",
        api_request_id="request-1",
    )
    decision = runtime.llm_request_middleware(
        request=request,
        session_id="session-a",
        api_request_id="request-2",
    )

    assert decision is not None
    assert decision["metrics"]["token_savings_source"] == "exact-tokenizer"
    assert decision["metrics"]["saved_tokens"] > 0
    assert decision["metrics"]["token_measurement_persisted"] is True

    summary = runtime.status()["token_accounting"]
    assert summary["eligible_requests"] == 2
    assert summary["measured_requests"] == 2
    assert summary["coverage_pct"] == 100.0
    assert summary["measured_saved_tokens"] > 0
    assert summary["best_available_saved_tokens"] == summary["measured_saved_tokens"]
    assert summary["source"] == "exact-tokenizer"
    assert summary["backends"] == ["test-tokenizer"]

    assert runtime.store is not None
    with runtime.store.connection() as conn:
        rows = conn.execute(
            "SELECT request_id, raw_tokens, final_tokens, saved_tokens, model "
            "FROM request_token_metrics ORDER BY request_id"
        ).fetchall()
    assert [row["request_id"] for row in rows] == ["request-1", "request-2"]
    assert rows[1]["saved_tokens"] == rows[1]["raw_tokens"] - rows[1]["final_tokens"]
    assert rows[1]["model"] == "openai/gpt-5"


def test_native_measurement_reuses_active_session_model(tmp_path):
    runtime = Runtime(_config(tmp_path))
    budget = _DeterministicBudget()
    _install_budget(runtime, budget)

    runtime.pre_llm_call(
        session_id="session-a",
        turn_id="turn-a",
        model="openai/gpt-5",
        user_message="hello",
    )
    runtime._record_native(
        session_id="session-a",
        turn_id="turn-a",
        raw_chars=600,
        output_chars=100,
        raw_text="raw " * 150,
        output_text="compact " * 12,
    )

    assert budget.text_models[-2:] == ["openai/gpt-5", "openai/gpt-5"]


def test_provider_qualified_openai_model_uses_tiktoken_automatically(monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    budget = TokenBudgetAdapter()

    measured = budget.measure_text("hello world", model="openai/gpt-4o")

    assert measured.available is True
    assert measured.tokens is not None and measured.tokens > 0
    assert measured.backend.startswith("tiktoken:")
