from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass

from rtk_hermes_plus import jev_context
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.jev_context import JevSemanticReducer
from rtk_hermes_plus.storage import TokenTerminatorStore


def _config(tmp_path, **overrides):
    values = {
        "db_path": tmp_path / "artifacts.db",
        "jev_enabled": True,
        "jev_api_key": "test-secret-never-print",
        "jev_min_message_chars": 40,
        "jev_relevance_threshold": 0.15,
        "jev_max_candidates": 8,
        "jev_max_candidate_chars": 20_000,
        "jev_max_state_chars": 80_000,
    }
    values.update(overrides)
    return Config(**values)


def _request():
    return {
        "model": "example-model",
        "messages": [
            {"role": "system", "content": "Private stable system instruction"},
            {
                "role": "user",
                "content": "Irrelevant weather discussion. " * 30,
            },
            {
                "role": "assistant",
                "content": "A project constraint that still matters. " * 30,
            },
            {
                "role": "user",
                "content": "Continue with the project constraint we discussed.",
            },
        ],
    }


def _semantic_transport(payload):
    answers = {}
    candidates = payload["state"]["candidates"]
    for cid, candidate in candidates.items():
        content = candidate["content"]
        keep = "project constraint" in content
        answers[f"{cid}_relevance"] = {
            "type": "noul",
            "noul": 0.95 if keep else 0.01,
        }
        answers[f"{cid}_guard"] = {
            "type": "noul",
            "noul": 0.95 if keep else 0.01,
        }
    return {
        "model": "jev-test",
        "answers": answers,
        "usage": {"input_tokens": 321, "output_tokens": 4},
    }


def test_jev_compacts_only_low_relevance_prior_plain_text(tmp_path):
    config = _config(tmp_path)
    store = TokenTerminatorStore(config.db_path)
    reducer = JevSemanticReducer(store, config, transport=_semantic_transport)
    request = _request()
    original = copy.deepcopy(request)

    result = reducer.reduce(request, session_id="s1", model="example-model")

    assert result.failed_open is False
    assert result.saved_chars > 0
    assert result.compacted_messages == 1
    assert result.input_tokens == 321
    assert request == original

    messages = result.request["messages"]
    assert messages[0]["content"] == "Private stable system instruction"
    assert messages[1]["content"].startswith("[Token Terminator artifact ")
    assert messages[2]["content"] == original["messages"][2]["content"]
    assert messages[3]["content"] == original["messages"][3]["content"]

    artifact_id = re.search(r"\ba_[0-9a-f]{32,64}\b", messages[1]["content"]).group(0)
    assert store.get_artifact(artifact_id).content == original["messages"][1]["content"]


def test_jev_is_disabled_without_explicit_switch_or_key(tmp_path):
    no_switch = _config(tmp_path, jev_enabled=False)
    no_key = _config(tmp_path, jev_api_key="")
    store = TokenTerminatorStore(no_switch.db_path)
    calls = []

    def transport(payload):
        calls.append(payload)
        raise AssertionError("transport must not be called")

    first = JevSemanticReducer(store, no_switch, transport=transport)
    second = JevSemanticReducer(store, no_key, transport=transport)

    assert first.reduce(_request()).saved_chars == 0
    assert second.reduce(_request()).saved_chars == 0
    assert calls == []


def test_status_never_exposes_api_key(tmp_path):
    config = _config(tmp_path)
    store = TokenTerminatorStore(config.db_path)
    reducer = JevSemanticReducer(store, config, transport=_semantic_transport)

    status = reducer.status()

    assert status["enabled"] is True
    assert status["configured"] is True
    assert config.jev_api_key not in repr(status)


def test_jev_transport_error_fails_open_without_mutating_request(tmp_path):
    config = _config(tmp_path)
    store = TokenTerminatorStore(config.db_path)

    def explode(_payload):
        raise RuntimeError("network unavailable")

    reducer = JevSemanticReducer(store, config, transport=explode)
    request = _request()
    original = copy.deepcopy(request)

    result = reducer.reduce(request, session_id="s1")

    assert result.failed_open is True
    assert result.saved_chars == 0
    assert result.request == original
    assert request == original


@dataclass
class _Measurement:
    tokens: int
    available: bool = True


class _RejectingTokenBudget:
    def measure_request(self, request, model=""):
        # The candidate passes the character gate, but this fake exact tokenizer
        # makes the reduced form one token larger. It must therefore be vetoed.
        first = request["messages"][1]["content"]
        if first.startswith("[Token Terminator artifact "):
            return _Measurement(101)
        return _Measurement(100)


def test_exact_tokenizer_can_veto_jev_reduction(tmp_path):
    config = _config(tmp_path)
    store = TokenTerminatorStore(config.db_path)
    reducer = JevSemanticReducer(
        store,
        config,
        transport=_semantic_transport,
        token_budget=_RejectingTokenBudget(),
    )
    request = _request()

    result = reducer.reduce(request, session_id="s1", model="example-model")

    assert result.failed_open is False
    assert result.saved_chars == 0
    assert result.request == request


def test_fenced_current_turn_memory_is_scored_without_touching_user_request(tmp_path):
    config = _config(tmp_path, jev_min_message_chars=40)
    store = TokenTerminatorStore(config.db_path)

    def transport(payload):
        assert payload["state"]["current_request"] == "What should I do next?"
        memory_ids = [
            cid
            for cid, item in payload["state"]["candidates"].items()
            if item["kind"] == "memory"
        ]
        assert len(memory_ids) == 1
        answers = {key: {"type": "noul", "noul": 0.01} for key in payload["questions"]}
        return {
            "model": "jev-test",
            "answers": answers,
            "usage": {"input_tokens": 50, "output_tokens": len(answers)},
        }

    reducer = JevSemanticReducer(store, config, transport=transport)
    memory = "HINDSIGHT FACT " + ("old unrelated detail " * 80)
    request = {
        "model": "example-model",
        "messages": [
            {"role": "system", "content": "Stable system prompt"},
            {
                "role": "user",
                "content": (
                    "What should I do next?\n\n"
                    "<memory-context>\n"
                    "[System note: recalled memory background]\n\n"
                    f"{memory}\n"
                    "</memory-context>"
                ),
            },
        ],
    }

    result = reducer.reduce(request, session_id="s1")

    assert result.saved_chars > 0
    output = result.request["messages"][-1]["content"]
    assert output.startswith("What should I do next?")
    assert "<memory-context>" in output
    assert "[Token Terminator artifact " in output
    assert memory not in output

    artifact_id = re.search(r"\ba_[0-9a-f]{32,64}\b", output).group(0)
    recovered = store.get_artifact(artifact_id).content
    assert recovered.startswith("<memory-context>")
    assert memory in recovered



def test_jev_http_transport_uses_selected_provider_endpoint(tmp_path, monkeypatch):
    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "model": "jev-test",
                    "answers": {"q": {"type": "noul", "noul": 0.5}},
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return Response()

    monkeypatch.setattr(jev_context, "urlopen", fake_urlopen)

    openrouter = Config(
        db_path=tmp_path / "openrouter.db",
        jev_enabled=True,
        jev_provider="openrouter",
        jev_api_key="or-key",
        jev_model="~typesafe/jev-latest",
    )
    openrouter_reducer = JevSemanticReducer(
        TokenTerminatorStore(openrouter.db_path),
        openrouter,
    )
    openrouter_reducer._call(
        {
            "model": openrouter.jev_model,
            "state": "state",
            "questions": {"q": {"type": "noul", "instructions": "question"}},
        }
    )

    request, _ = captured[-1]
    assert request.full_url == "https://openrouter.ai/api/alpha/decisions"
    assert request.get_header("Authorization") == "Bearer or-key"
    assert request.get_header("X-title") == "Token Terminator"

    typesafe = Config(
        db_path=tmp_path / "typesafe.db",
        jev_enabled=True,
        jev_provider="typesafe",
        jev_api_key="ts-key",
        jev_model="jev-latest",
    )
    typesafe_reducer = JevSemanticReducer(
        TokenTerminatorStore(typesafe.db_path),
        typesafe,
    )
    typesafe_reducer._call(
        {
            "model": typesafe.jev_model,
            "state": "state",
            "questions": {"q": {"type": "noul", "instructions": "question"}},
        }
    )

    request, _ = captured[-1]
    assert request.full_url == "https://api.typesafe.ai/v1/systemone"
    assert request.get_header("Authorization") == "Bearer ts-key"
    assert request.get_header("X-title") is None
