"""New-model regression: no override, no substituted model name, real BPE."""

import copy
import json
from types import SimpleNamespace

import pytest
import tiktoken

from rtk_hermes_plus.token_budget import TokenBudgetAdapter, _compat_encoding


@pytest.mark.parametrize(
    "model",
    [
        "gpt-6.1-sol",
        "gpt-6.1-sol-900k",
        "openai/gpt-6.1-sol-900k",
        "openai:gpt-6.1-sol-900k",
        "openai-codex/gpt-6.1-sol-900k",
        "openai-codex:gpt-6.1-sol-900k",
        "openrouter/openai/gpt-6.1-sol-900k",
        "openai/gpt-6.1-sol",
        "openai:gpt-6.1-sol",
        "openai-codex/gpt-6.1-sol",
        "openrouter/openai/gpt-6.1-sol",
    ],
)
def test_sol_request_has_measured_tokens_without_override(monkeypatch, model):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    monkeypatch.setenv("TOKEN_TERMINATOR_TOKEN_BUDGET", "true")
    request = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Exact 12.30; cafÃ©; æ—¥æœ¬èªž; ðŸ§ª"}
        ],
    }
    before = copy.deepcopy(request)
    result = TokenBudgetAdapter().measure_request(request)
    canonical = json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert result.tokens == len(
        tiktoken.get_encoding("o200k_base").encode(canonical, disallowed_special=())
    )
    assert result.model == model
    assert result.available
    assert request == before


@pytest.mark.parametrize(
    "model",
    [
        "vendor/gpt-6.1-sol",
        "gpt-6.1-sol-FAKE",
        "gpt-6.2-sol",
        "gpt-60",
        "claude-opus",
        "unknown",
        "gpt-6.1-terra",
    ],
)
def test_new_mapping_does_not_guess_other_models(model):
    assert _compat_encoding(model) == ""


def test_namespace_cache_does_not_leak_compatibility(monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    adapter = TokenBudgetAdapter()
    # Deliberately emulate the upstream version missing this model.
    adapter._tiktoken_attempted = True

    def unknown(_):
        raise KeyError("missing")

    adapter._tiktoken = SimpleNamespace(
        encoding_for_model=unknown, get_encoding=tiktoken.get_encoding
    )
    assert adapter.measure_text("x", model="openai/gpt-6.1-sol").available
    assert not adapter.measure_text("x", model="other/gpt-6.1-sol").available


def test_upstream_mapping_takes_precedence(monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    adapter = TokenBudgetAdapter()
    adapter._tiktoken_attempted = True
    selected = tiktoken.get_encoding("cl100k_base")
    adapter._tiktoken = SimpleNamespace(encoding_for_model=lambda _: selected)
    encoding, label = adapter._tiktoken_encoding("gpt-6.1-sol")
    assert encoding is selected
    assert label == "tiktoken:model:gpt-6.1-sol"


@pytest.mark.parametrize(
    "model",
    [
        "gpt-6.1-sol",
        "gpt-6.1-sol-900k",
        "openai/gpt-6.1-sol-900k",
        "openai-codex/gpt-6.1-sol-900k",
        "openai-codex:gpt-6.1-sol-900k",
        "openrouter/openai/gpt-6.1-sol-900k",
    ],
)
@pytest.mark.parametrize("key", ["messages", "input"])
def test_sol_context_engine_reaches_selection_and_strict_gate(
    tmp_path, monkeypatch, model, key
):
    from test_history_engine import low_scores, request, run, setup

    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    runtime, engine = setup(tmp_path)
    window = 900000 if model.endswith("-900k") else 1050000
    engine.update_model(model, window)
    req = request(engine, key=key)
    req["model"] = model
    original = copy.deepcopy(req)
    calls = []

    def score(payload):
        calls.append(1)
        return low_scores(payload)

    engine.transport = score
    final = run(runtime, engine, req)
    assert calls, "Sol must not return early as unknown tokenizer before JEV"
    assert engine.get_status()["context_engine"]["omitted_messages"] > 0
    assert final[key][0] == original[key][0]
    assert final[key][-1] == original[key][-1]
    aid = final[key][1]["content"].split()[2].rstrip(";")
    assert engine._history().read("session", aid) == original[key][1]
    counter = TokenBudgetAdapter()
    assert counter.measure_request(final).tokens < counter.measure_request(req).tokens
    assert req == original
    assert final["model"] == model
    assert engine.context_length == window


def test_recorded_provider_corpus_matches_local_content_counter():
    from pathlib import Path

    report = json.loads(
        (Path(__file__).parent / "fixtures/gpt61-token-counts.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["model"] == "gpt-6.1-sol"
    assert report["generation_calls"] == 0
    assert len(report["results"]) == 5
    encoding = tiktoken.get_encoding("o200k_base")
    for row in report["results"]:
        assert row["http_status"] == 200
        assert (
            len(encoding.encode(row["text"], disallowed_special=()))
            == row["o200k_base"]
        )
        assert row["provider_tokens"] - row["o200k_base"] == 6
    assert any(r["o200k_base"] != r["cl100k_base"] for r in report["results"])
