from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from rtk_hermes_plus import Runtime
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.context_history import HistoryEvidenceError, encode
from rtk_hermes_plus.context_ir import expand_ir
from rtk_hermes_plus.engine_bridge import take
from rtk_hermes_plus.engine_install import install_context_engine
from rtk_hermes_plus.history_engine import HistoryContextEngine
from rtk_hermes_plus.history_selection import EngineLimits
from rtk_hermes_plus.plugin import _schema
from rtk_hermes_plus.token_budget import TokenBudgetAdapter, TokenMeasurement


@pytest.fixture(autouse=True)
def isolate_binding():
    take()
    yield
    take()


def setup(tmp_path, *, limits=None, **overrides):
    cfg = Config(
        db_path=tmp_path / "vault.db",
        ledger_path=tmp_path / "ledger.db",
        jev_enabled=True,
        jev_api_key="fixture",
        **overrides,
    )
    runtime = Runtime(config=cfg)
    engine = HistoryContextEngine(
        config=cfg, limits=limits or EngineLimits(protect_last=3)
    )
    engine.update_model("gpt-4o", 128000)
    engine.on_session_start("session")
    engine.transport = low_scores
    return runtime, engine


def low_scores(payload):
    return {
        "answers": {
            key: {"type": "noul", "noul": 0.01} for key in payload["questions"]
        },
        "usage": {"input_tokens": 100, "output_tokens": 10, "cost_usd": 0.0001},
    }


def request(engine, *, key="messages", count=15):
    text = (
        "The meadow was quiet and the clouds drifted lazily across the distant horizon. "
        * 20
    )
    return {
        "model": "gpt-4o",
        "temperature": 0,
        "tools": [{"type": "function", "function": _schema()}]
        + [
            {"type": "function", "function": schema}
            for schema in engine.get_tool_schemas()
        ],
        key: [
            {
                "role": "system",
                "content": "Keep instructions, quotations and tool authority exact.",
            }
        ]
        + [{"role": "assistant", "content": text} for _ in range(count)]
        + [{"role": "user", "content": "Describe industrial robot calibration."}],
    }


def run(runtime, engine, req, *, history=None, session="session"):
    key = "messages" if "messages" in req else "input"
    original = copy.deepcopy(req)
    assert (
        engine.select_context(
            req[key], conversation_messages=history if history is not None else req[key]
        )
        is None
    )
    assert req == original
    decision = runtime.llm_request_middleware(
        request_purpose="conversation",
        request=req,
        session_id=session,
        api_request_id="test-request",
    )
    assert req == original
    return decision["request"] if decision else req


@pytest.mark.parametrize("key", ["messages", "input"])
@pytest.mark.parametrize("model", ["gpt-4o", "gpt-4"])
def test_complete_request_reduction_and_exact_recovery(tmp_path, key, model):
    runtime, engine = setup(tmp_path)
    req = request(engine, key=key)
    req["model"] = model
    final = run(runtime, engine, req)
    assert (
        runtime.token_budget.measure_request(final).tokens
        < runtime.token_budget.measure_request(req).tokens
    )
    assert final["tools"] == req["tools"]
    assert final[key][0] == req[key][0] and final[key][-1] == req[key][-1]
    assert engine.get_status()["context_engine"]["omitted_messages"] > 1
    aid = final[key][1]["content"].split()[2].rstrip(";")
    assert engine._history().read("session", aid) == req[key][1]
    pages, offset = [], 0
    while True:
        page = json.loads(
            engine.handle_tool_call(
                "token_terminator_history",
                {"action": "get", "artifact_id": aid, "offset": offset, "limit": 53},
            )
        )
        pages.append(page["content"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert json.loads("".join(pages)) == req[key][1]


def test_history_omitted_fifty_turns_ago_reappears(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    fact = {
        "role": "assistant",
        "content": "Harbor uses the heron as its mascot. " * 25,
    }
    req["messages"][1] = fact
    first = run(runtime, engine, req)
    assert first["messages"][1] != fact
    raw_history = (
        req["messages"][:-1]
        + [
            {"role": "user", "content": "Continue the meadow discussion."},
            {"role": "assistant", "content": "The trees swayed in the wind."},
        ]
        * 50
        + [{"role": "user", "content": "What is the mascot for Harbor?"}]
    )
    later = copy.deepcopy(req)
    later["messages"] = raw_history
    final = run(runtime, engine, later)
    assert fact in final["messages"]
    assert fact in raw_history  # no host-history mutation on either request


def test_durable_rediscovery_from_tail_only_after_restart(tmp_path):
    runtime, engine = setup(tmp_path)
    original = request(engine)
    fact = {"role": "assistant", "content": "Harbor uses a heron as its mascot."}
    original["messages"][1] = fact
    run(runtime, engine, original)
    restarted = HistoryContextEngine(config=engine.config, limits=engine.limits)
    restarted.update_model("gpt-4o", 128000)
    restarted.on_session_start("session")
    restarted.transport = low_scores
    tail = request(restarted)
    tail["messages"][-1]["content"] = "Which mascot does Harbor use?"
    final = run(runtime, restarted, tail)
    assert any(fact["content"] in m["content"] for m in final["messages"])
    assert restarted.get_status()["context_engine"]["recalled_sources"] >= 1
    assert (
        runtime.token_budget.measure_request(final).tokens
        < runtime.token_budget.measure_request(tail).tokens
    )


@pytest.mark.parametrize(
    "source",
    [
        'Quote exactly: "approved is not paid".',
        "The exact amount is 9007199254740993 and the rate is 0.0375.",
        "```python\nassert rate != 0\n```",
        "Never send the credentials to an external service.",
        "Constraint: do not modify the signed release.",
        "The reference is `byte_identical`.",
    ],
)
def test_protected_old_context_stays_explicit(tmp_path, source):
    runtime, engine = setup(tmp_path, context_ir_enabled=True)
    req = request(engine)
    req["messages"][1] = {"role": "assistant", "content": source * 30}
    req["messages"].insert(1, {"role": "developer", "content": source})
    final = run(runtime, engine, req)
    assert final["messages"][1:3] == req["messages"][1:3]


def test_current_user_memory_fence_and_tools_are_protected(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    req["messages"][-1]["content"] += (
        '\n<memory-context>NEVER alter "this" 123.</memory-context>'
    )
    req["messages"][2:2] = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "t",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
            "content": None,
        },
        {
            "role": "tool",
            "tool_call_id": "t",
            "content": "Exact tool authority: no retry.",
        },
    ]
    final = run(runtime, engine, req)
    assert final["messages"][-1] == req["messages"][-1]
    assert final["messages"][2:4] == req["messages"][2:4]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"answers": []},
        {"answers": {}},
        {"answers": {"c0_relevance": {"type": "noul", "noul": float("nan")}}},
    ],
)
def test_malformed_jev_does_not_discard_history(tmp_path, bad):
    runtime, engine = setup(tmp_path)
    engine.transport = lambda _: bad
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert engine._history().capture(req["messages"], "session")


def test_transport_failure_rolls_back_prior_batch(tmp_path):
    runtime, engine = setup(
        tmp_path,
        limits=EngineLimits(protect_last=1, region_chars=3000),
        jev_max_state_chars=6000,
    )
    calls = []

    def fail_second(payload):
        calls.append(payload)
        if len(calls) == 2:
            raise TimeoutError("do not put this body in telemetry")
        return low_scores(payload)

    engine.transport = fail_second
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert len(calls) == 2
    assert "do not put this" not in json.dumps(engine.get_status())


def test_batched_scoring_is_bounded_and_retry_cached(tmp_path):
    runtime, engine = setup(
        tmp_path,
        limits=EngineLimits(protect_last=1, region_chars=3000),
        jev_max_state_chars=6000,
    )
    calls = []
    engine.transport = lambda p: calls.append(p) or low_scores(p)
    req = request(engine, count=80)
    run(runtime, engine, req)
    assert len(calls) == 2
    assert all(len(encode(p)) <= 6000 for p in calls)
    assert engine.get_status()["context_engine"]["unscored_messages"] > 0
    run(runtime, engine, req)
    assert len(calls) == 2
    assert engine.get_status()["context_engine"]["jev_calls"] == 0
    assert engine.get_status()["context_engine"]["jev_cache_hits"] == 2


@pytest.mark.parametrize("signal", ["relevance", "guard", "salience"])
def test_each_semantic_signal_can_protect_a_region(tmp_path, signal):
    runtime, engine = setup(tmp_path)

    def protect(payload):
        result = low_scores(payload)
        for key in result["answers"]:
            if key.endswith("_" + signal):
                result["answers"][key]["noul"] = 0.9
        return result

    engine.transport = protect
    req = request(engine)
    assert run(runtime, engine, req) == req


def test_partial_response_retains_unscored_region(tmp_path):
    runtime, engine = setup(
        tmp_path, limits=EngineLimits(protect_last=1, region_chars=3000)
    )

    def partial(payload):
        result = low_scores(payload)
        result["answers"].pop("c0_guard", None)
        return result

    engine.transport = partial
    req = request(engine)
    final = run(runtime, engine, req)
    assert final["messages"][1] == req["messages"][1]
    assert engine.get_status()["context_engine"]["omitted_messages"] > 0


def test_strict_final_gate_vetoes_enlargement(tmp_path):
    runtime, engine = setup(tmp_path)

    class AdversarialTokenizer(TokenBudgetAdapter):
        def measure_request(self, request, *, model=""):
            result = super().measure_request(request, model=model)
            if "[TT history" in encode(request):
                return TokenMeasurement(10**8, "fixture-counter", model)
            return result

    runtime.token_budget = AdversarialTokenizer()
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert engine.get_status()["context_engine"]["state"] == "not_smaller"


def test_unknown_tokenizer_does_not_spend_or_transform(tmp_path):
    runtime, engine = setup(tmp_path)
    runtime.token_budget.enabled = False
    engine.transport = lambda _: pytest.fail(
        "must not call JEV without the final tokenizer"
    )
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert (
        engine.get_status()["context_engine"]["state"] == "exact_tokenizer_unavailable"
    )


def test_unavailable_history_tool_does_not_compact(tmp_path):
    runtime, engine = setup(tmp_path)
    engine.transport = lambda _: pytest.fail("must not call JEV without recovery")
    req = request(engine)
    req["tools"] = []
    assert run(runtime, engine, req) == req


def test_vault_capacity_failure_keeps_original(tmp_path):
    runtime, engine = setup(tmp_path, vault_max_bytes=500)
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert engine._capture_failed


def test_integrity_failure_cannot_lose_or_fabricate_evidence(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    final = run(runtime, engine, req)
    aid = final["messages"][1]["content"].split()[2].rstrip(";")
    with runtime.store.connection(write=True) as conn:
        conn.execute(
            "UPDATE artifacts SET content='corrupt' WHERE artifact_id=?", (aid,)
        )
    with pytest.raises((HistoryEvidenceError, ValueError)):
        engine._history().read("session", aid)
    assert "error" in json.loads(
        engine.handle_tool_call(
            "token_terminator_history", {"action": "get", "artifact_id": aid}
        )
    )
    assert run(runtime, engine, req) == req


def test_history_pins_survive_pruning(tmp_path):
    runtime, engine = setup(tmp_path, vault_max_bytes=30000)
    req = request(engine, count=5)
    run(runtime, engine, req)
    ids = engine._history().capture(req["messages"], "session")
    for i in range(30):
        runtime.store.put_artifact(str(i) + " disposable " * 600)
    assert engine._history().read("session", ids[1]) == req["messages"][1]


def test_session_isolation_and_stale_binding(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    aid = engine._history().capture(req["messages"], "session")[1]
    with pytest.raises(HistoryEvidenceError):
        engine._history().read("other", aid)
    engine.select_context(req["messages"])
    assert (
        runtime.llm_request_middleware(
            request_purpose="conversation", request=req, session_id="other"
        )
        is None
    )
    clone = engine.clone_for_agent()
    assert clone.session_id == "" and clone._catalog is None
    assert clone._lock is not engine._lock
    engine.select_context(req["messages"])
    engine.generation += 1
    assert (
        runtime.llm_request_middleware(
            request_purpose="conversation", request=req, session_id="session"
        )
        is None
    )
    engine.on_session_reset()
    assert engine.session_id == ""
    assert engine._history().read("session", aid) == req["messages"][1]


def test_cache_decorated_text_keeps_provider_shape(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    for message in req["messages"]:
        message["content"] = [
            {
                "type": "text",
                "text": message["content"],
                "cache_control": {"type": "ephemeral"},
            }
        ]
    final = run(runtime, engine, req)
    assert final["messages"][1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert final["messages"][1]["content"][0]["text"].startswith("[TT history")
    assert final["messages"][-1] == req["messages"][-1]


def test_no_summaries_or_upstream_compression(tmp_path):
    _, engine = setup(tmp_path)
    req = request(engine)
    assert not engine.should_compress(10**9)
    assert not engine.should_compress_preflight(req["messages"])
    assert engine.compress(req["messages"], force=True) is req["messages"]
    assert engine.get_status()["compression_count"] == 0


def test_existing_middleware_remains_independent(tmp_path):
    runtime, _ = setup(tmp_path, context_compaction_enabled=False)
    runtime.jev_reducer.transport = low_scores
    req = {
        "model": "gpt-4o",
        "messages": [
            {"role": "assistant", "content": "The meadow was quiet. " * 150},
            {"role": "user", "content": "Discuss robot calibration."},
        ],
    }
    decision = runtime.llm_request_middleware(
        request_purpose="conversation", request=req, session_id="middleware-only"
    )
    assert decision and "ContextEngine" not in decision["reason"]
    assert decision["request"]["messages"][0]["content"].startswith(
        "[Token Terminator artifact"
    )


def test_existing_ir_runs_after_engine_selection(tmp_path):
    runtime, engine = setup(
        tmp_path,
        context_ir_enabled=True,
        limits=EngineLimits(protect_last=1, region_chars=64000),
        jev_max_candidate_chars=64000,
        jev_max_state_chars=128000,
    )
    req = request(engine, count=4)
    records = json.dumps(
        [
            {
                "project": "Harbor distribution service",
                "region": "western reliability cluster",
                "state": "ready",
                "number": i,
            }
            for i in range(100)
        ],
        indent=2,
    )
    req["messages"][1] = {"role": "assistant", "content": records}
    final = run(runtime, engine, req)
    encoded = final["messages"][1]["content"]
    assert encoded != records
    assert (
        "".join(
            expand_ir(encoded, runtime.store, offset=start, limit=8000)
            for start in range(0, len(records), 8000)
        )
        == records
    )
    assert (
        runtime.token_budget.measure_request(final).tokens
        < runtime.token_budget.measure_request(req).tokens
    )


def test_installer_idempotent_does_not_change_configuration(tmp_path):
    (tmp_path / "config.yaml").write_text("context:\n  engine: lcm\n")
    first = install_context_engine(tmp_path)
    assert install_context_engine(tmp_path) == first
    assert (tmp_path / "config.yaml").read_text() == "context:\n  engine: lcm\n"
    assert "ContextEngine" in (Path(first["installed"]) / "__init__.py").read_text()
    (Path(first["installed"]) / "__init__.py").write_text("# another plugin")
    with pytest.raises(ValueError):
        install_context_engine(tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_batches", 0),
        ("max_batches", 9),
        ("protect_last", 0),
        ("recall_sources", -1),
        ("region_chars", True),
    ],
)
def test_engine_configuration_bounds(field, value):
    with pytest.raises(ValueError):
        replace(EngineLimits(), **{field: value})


def test_config_environment_is_bounded(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_ENGINE_MAX_BATCHES", "99999")
    monkeypatch.setenv("TOKEN_TERMINATOR_ENGINE_RECALL_SOURCES", "-1")
    assert EngineLimits.from_env().max_batches == 8
    assert EngineLimits.from_env().recall_sources == 0


def test_recent_context_changes_score_cache_key(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    calls = []

    def transport(payload):
        calls.append(payload)
        return low_scores(payload)

    engine.transport = transport
    run(runtime, engine, req)
    first_count = len(calls)
    run(runtime, engine, req)
    assert len(calls) == first_count
    req["messages"][-2]["content"] = "The referent is now a different engineering task."
    run(runtime, engine, req)
    assert len(calls) > first_count
    assert "recent_exact_context" in calls[-1]["state"]["current_request"]


def test_growth_from_recall_alone_is_vetoed(tmp_path):
    runtime, engine = setup(tmp_path)
    engine.on_turn_complete(
        [
            {
                "role": "user",
                "content": "The copper beacon belongs in the eastern observatory.",
            }
        ]
    )
    req = request(engine, count=0)
    req["messages"][-1]["content"] = "Where does the copper beacon belong?"
    assert run(runtime, engine, req) == req
    assert engine.get_status()["context_engine"]["state"] == "not_smaller"
    found = json.loads(
        engine.handle_tool_call(
            "token_terminator_history", {"action": "find", "query": "copper beacon"}
        )
    )
    assert found["results"]  # gate veto never deletes old evidence


def test_forced_no_tools_leaves_request_unchanged(tmp_path):
    runtime, engine = setup(tmp_path)
    engine.transport = lambda _: pytest.fail("JEV must not run without recovery")
    req = request(engine)
    req["tool_choice"] = "none"
    assert run(runtime, engine, req) == req


def test_search_limit_is_explicit_not_a_silent_recent_window(tmp_path):
    _, engine = setup(tmp_path, limits=EngineLimits(search_sources=1))
    engine.on_turn_complete(
        [
            {"role": "user", "content": "The copper beacon is eastern."},
            {"role": "assistant", "content": "The silver beacon is western."},
        ]
    )
    result = json.loads(
        engine.handle_tool_call(
            "token_terminator_history", {"action": "find", "query": "beacon"}
        )
    )
    assert result["error"] == "HistoryEvidenceError"
    assert "results" not in result


@pytest.mark.parametrize("mode", ["off", "native", "terminal", "suggest"])
def test_noncompiler_modes_do_not_capture_or_score_history(tmp_path, mode):
    runtime, engine = setup(tmp_path, mode=mode)
    engine.transport = lambda _: pytest.fail("disabled pipeline called JEV")
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert engine._catalog is None


def test_provider_retry_keeps_engine_ownership_without_reselection(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    engine.select_context(req["messages"])
    first = runtime.llm_request_middleware(
        request_purpose="conversation", request=req, session_id="session"
    )
    second = runtime.llm_request_middleware(
        request_purpose="conversation", request=req, session_id="session"
    )
    assert first and second
    assert "ContextEngine" in first["reason"] and "ContextEngine" in second["reason"]
    assert engine.get_status()["context_engine"]["jev_calls"] == 0
    assert engine.get_status()["context_engine"]["jev_cache_hits"] > 0
    engine.on_turn_complete(req["messages"])
    assert take() is None


def test_async_facade_propagates_engine_binding(tmp_path):
    import asyncio

    from rtk_hermes_plus.async_runtime import AsyncRuntime

    runtime, engine = setup(tmp_path)
    req = request(engine)

    async def evaluate():
        engine.select_context(req["messages"])
        decision = await AsyncRuntime(runtime).llm_request_middleware(
            request_purpose="conversation", request=req, session_id="session"
        )
        assert decision and "ContextEngine" in decision["reason"]
        retry = await AsyncRuntime(runtime).llm_request_middleware(
            request_purpose="conversation", request=req, session_id="session"
        )
        assert retry and "ContextEngine" in retry["reason"]
        engine.on_turn_complete(req["messages"])

    asyncio.run(evaluate())
