from __future__ import annotations

import asyncio
import copy
import json
import sys
from contextvars import ContextVar
from types import SimpleNamespace

import pytest
from test_history_engine import low_scores, request, setup

from rtk_hermes_plus import AsyncRuntime
from rtk_hermes_plus.call_scope import conservative_chat_target, internal_call
from rtk_hermes_plus.context_ir import expand_ir
from rtk_hermes_plus.engine_bridge import current, take
from rtk_hermes_plus.token_budget import TokenBudgetAdapter, TokenMeasurement


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    take()
    monkeypatch.delenv("TOKEN_TERMINATOR_CHAT_TARGET_POLICY", raising=False)
    yield
    take()


def call(runtime, req, **context):
    return runtime.llm_request_middleware(
        request=req, session_id="session", api_request_id="attempt", **context
    )


def bind(engine, req):
    engine.select_context(req["messages"])


def host_context(**extra):
    return dict(
        middleware_schema_version="hermes.middleware.v1",
        session_id="session",
        turn_id="turn",
        api_request_id="attempt",
        api_call_count=1,
        api_mode="chat_completions",
        **extra,
    )


@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize(
    "purpose",
    [
        "embedding",
        "rerank",
        "classifier",
        "helper",
        "tokenize",
        "count_tokens",
        "vision",
        "title",
        "compression",
        "unknown_service",
    ],
)
def test_internal_chat_shaped_calls_bypass_before_any_work(
    tmp_path, monkeypatch, bound, purpose
):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    if bound:
        bind(engine, req)
    pending = current()
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("internal call reached reduction work")

    for obj, name in (
        (runtime, "_middleware_pipeline"),
        (engine, "reduce_request"),
        (runtime.token_budget, "measure_request"),
        (runtime.store, "put_artifact"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    original = copy.deepcopy(req)
    assert call(runtime, req, request_purpose=purpose) is None
    assert req == original and current() is pending and not touched
    assert runtime._last_call_scope == "non_conversational_or_unknown_purpose"


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "embedding-model", "input": "Do NOT alter this text.\nA  12.30"},
        {"model": "embedding-model", "input": ["query", "document"]},
        {"model": "reranker", "query": "query", "documents": ["first", "second"]},
        {"model": "jev-latest", "state": {"verbatim": "value"}, "questions": {}},
        {"messages": [{"role": "user", "content": "text"}], "input": "embedding"},
    ],
)
def test_service_payloads_cannot_be_opted_in_by_chat_label(tmp_path, payload):
    runtime, engine = setup(tmp_path)
    bind(engine, request(engine))
    original = copy.deepcopy(payload)
    assert call(runtime, payload, request_purpose="conversation") is None
    assert payload == original


@pytest.mark.parametrize(
    "extra",
    [
        {"aux_task": "rerank"},
        {"auxiliary_task": "classify"},
        {"model_role": "helper"},
        {"call_role": "auxiliary:classifier"},
        {"operation": "chat.completions.create", "endpoint": "/v1/rerank"},
        {"operation": {}},
        {"operation": "embeddings.create"},
        {"operation": "/v1/rerank"},
        {"api_mode": "count_tokens"},
        {"is_internal": True},
        {"parent_session_id": "parent"},
        {"purpose": "embedding"},
        {"request_purpose": []},
        {"api_mode": {}},
    ],
)
def test_explicit_negatives_override_hermes_main_hook(tmp_path, extra):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    bind(engine, req)
    context = host_context()
    context.update(extra)
    assert runtime.hermes_llm_request_middleware(request=req, **context) is None
    assert engine.get_status()["context_engine"]["state"] == "awaiting_final_request"


def test_unscoped_calls_and_prompt_metadata_do_not_authorize_reduction(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    req["metadata"] = {"request_purpose": "conversation"}
    req["_tt_request_purpose"] = "conversation"
    bind(engine, req)
    original = copy.deepcopy(req)
    assert call(runtime, req) is None
    assert req == original and runtime._last_call_scope == "unscoped_request"
    # Rejected helper neither consumes the binding nor poisons a subsequent retry.
    assert call(runtime, req, request_purpose="conversation") is not None


def test_native_main_hook_and_retry_still_use_engine(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    batches = []
    engine.transport = lambda payload: (batches.append(payload), low_scores(payload))[1]
    bind(engine, req)
    first = runtime.hermes_llm_request_middleware(request=req, **host_context())
    assert first and batches and runtime._last_call_scope == "hermes_main_turn_hook"
    count = len(batches)
    assert call(runtime, req, request_purpose="classifier") is None
    retry = runtime.hermes_llm_request_middleware(request=req, **host_context())
    assert retry["request"] == first["request"]
    assert len(batches) == count
    assert retry["metrics"]["context_engine"]["jev_cache_hits"] > 0


@pytest.mark.parametrize("role", ["auxiliary", "delegated"])
def test_hermes_execution_role_overrides_inherited_main_metadata(
    tmp_path, monkeypatch, role
):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    bind(engine, req)
    if role == "auxiliary":
        task = ContextVar("fixture_aux", default=None)
        task.set({"task": "approval"})
        monkeypatch.setitem(
            sys.modules,
            "agent.auxiliary_client",
            SimpleNamespace(_RELAY_AUX_CALL_CONTEXT=task),
        )
    else:
        lease = SimpleNamespace(parent_session_id="parent")
        monkeypatch.setitem(
            sys.modules,
            "agent.relay_runtime",
            SimpleNamespace(current_turn=lambda: SimpleNamespace(lease=lease)),
        )
    assert runtime.hermes_llm_request_middleware(request=req, **host_context()) is None
    assert runtime._last_call_scope == "hermes_auxiliary_or_delegated_role"


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
def test_internal_jev_transport_never_recurses_even_with_explicit_chat_label(
    tmp_path, provider
):
    runtime, engine = setup(tmp_path, jev_provider=provider)
    req = request(engine)
    inner = []

    def transport(payload):
        inner.append(call(runtime, req, request_purpose="conversation"))
        return low_scores(payload)

    engine.transport = transport
    bind(engine, req)
    assert call(runtime, req, request_purpose="conversation") is not None
    assert inner and all(result is None for result in inner)
    # Also protect internal JEV invoked independently, without an outer runtime guard.
    take()
    runtime.jev_reducer.transport = transport
    runtime.jev_reducer._call({"questions": {}})
    assert inner[-1] is None
    assert call(runtime, req, request_purpose="classifier") is None


def test_tokenizer_callback_is_measurement_not_recursive_generation(
    tmp_path, monkeypatch
):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    measure = runtime.token_budget.measure_request
    inner = []

    def counting(value, **kwargs):
        inner.append(call(runtime, req, request_purpose="conversation"))
        return measure(value, **kwargs)

    monkeypatch.setattr(runtime.token_budget, "measure_request", counting)
    bind(engine, req)
    assert call(runtime, req, request_purpose="conversation") is not None
    assert inner and all(result is None for result in inner)


def test_internal_scope_resets_on_error_and_propagates_to_async_worker(tmp_path):
    runtime, engine = setup(tmp_path)
    req = request(engine)
    facade = AsyncRuntime(runtime)
    with pytest.raises(RuntimeError), internal_call():
        assert (
            asyncio.run(
                facade.llm_request_middleware(
                    request=req, request_purpose="conversation"
                )
            )
            is None
        )
        raise RuntimeError("fixture")
    bind(engine, req)
    assert (
        asyncio.run(
            facade.llm_request_middleware(
                request=req, request_purpose="conversation", session_id="session"
            )
        )
        is not None
    )


class PolicyFixtureCounter(TokenBudgetAdapter):
    """Exercise policy arithmetic only. NOT a claim to know the JEV tokenizer."""

    def measure_request(self, request, *, model=""):
        from rtk_hermes_plus.context_history import encode

        result = super().measure_text(encode(request), model="gpt-4o")
        return TokenMeasurement(
            result.tokens, "fixture-gpt4o-not-jev", model or request.get("model", "")
        )


def jev_case(tmp_path, *, ir=False, bound=True):
    runtime, engine = setup(tmp_path, context_ir_enabled=ir)
    runtime.token_budget = PolicyFixtureCounter()
    runtime.jev_reducer.transport = low_scores
    engine.update_model("typesafe/jev-latest", 128000)
    req = request(engine)
    req["model"] = engine.model
    if bound:
        bind(engine, req)
    return runtime, engine, req


@pytest.mark.parametrize("bound", [False, True])
def test_jev_chat_preserves_all_bounded_history_and_makes_no_semantic_calls(
    tmp_path, bound
):
    runtime, engine, req = jev_case(tmp_path, bound=bound)

    def forbidden(payload):
        pytest.fail("JEV chat with room must not run semantic pruning")

    engine.transport = runtime.jev_reducer.transport = forbidden
    original = copy.deepcopy(req)
    assert call(runtime, req, request_purpose="conversation") is None
    assert req == original
    assert runtime._last_chat_target["jev_calls"] == 0
    assert runtime._last_chat_target["omitted_messages"] == 0


def test_jev_chat_allows_only_reversible_measured_ir(tmp_path):
    runtime, engine, req = jev_case(tmp_path, ir=True)
    source = json.dumps(
        [
            {
                "component": "spectrometer",
                "status": "operational",
                "site": "calibration_laboratory",
            }
            for _ in range(90)
        ]
    )
    req["messages"][1]["content"] = source
    bind(engine, req)
    decision = call(runtime, req, request_purpose="conversation")
    assert decision and decision["metrics"]["saved_tokens"] > 0
    final = decision["request"]
    assert (
        expand_ir(final["messages"][1]["content"], runtime.store, limit=20000) == source
    )
    assert final["messages"][2:] == req["messages"][2:]
    assert decision["metrics"]["chat_target"]["omitted_messages"] == 0
    assert decision["metrics"]["chat_target"]["jev_calls"] == 0


@pytest.mark.parametrize("bound", [False, True])
def test_jev_budget_pressure_omits_only_enough_and_keeps_exact_evidence(
    tmp_path, bound
):
    runtime, _engine, req = jev_case(tmp_path, bound=bound)
    before = runtime.token_budget.measure_request(req).tokens
    adapter = runtime.token_budget
    adapter.context_limit_tokens = (
        before + adapter.output_reserve_tokens + adapter.safety_margin_tokens - 200
    )
    decision = call(runtime, req, request_purpose="conversation")
    assert decision, runtime._last_chat_target
    status = decision["metrics"]["chat_target"]
    assert status["budget_pressure"] and status["omitted_messages"] == 1
    assert decision["metrics"]["final_tokens"] <= status["usable_context_tokens"]
    final = decision["request"]
    assert final["messages"][2:] == req["messages"][2:]
    from rtk_hermes_plus.plugin import _artifact_ids_in_value

    ids = _artifact_ids_in_value(final["messages"][1])
    evidence = runtime.store.get_artifact(ids[0]).content
    if bound:
        assert json.loads(evidence) == req["messages"][1]
    else:
        assert evidence == req["messages"][1]["content"]


def test_jev_unsatisfiable_limit_never_force_cuts_protected_context(tmp_path):
    runtime, engine, req = jev_case(tmp_path)
    adapter = runtime.token_budget
    adapter.context_limit_tokens = (
        adapter.output_reserve_tokens + adapter.safety_margin_tokens + 1
    )
    req["messages"][1]["content"] = (
        'Never change 9007199254740993 or "signed".\n```python\nassert x\n```' * 60
    )
    bind(engine, req)
    original = copy.deepcopy(req)
    assert call(runtime, req, request_purpose="conversation") is None
    assert runtime._last_chat_target["state"] == "context_limit_unresolved"
    assert req == original


def test_jev_pressure_failure_preserves_original_and_retry_cache(tmp_path):
    runtime, engine, req = jev_case(tmp_path)
    adapter = runtime.token_budget
    adapter.context_limit_tokens = (
        runtime.token_budget.measure_request(req).tokens
        + adapter.output_reserve_tokens
        + adapter.safety_margin_tokens
        - 200
    )
    engine.transport = lambda payload: {"malformed": True}
    assert call(runtime, req, request_purpose="conversation") is None
    assert runtime._last_chat_target["state"] == "jev_failed_open"
    calls = []
    engine.transport = lambda payload: (calls.append(payload), low_scores(payload))[1]
    first = call(runtime, req, request_purpose="conversation")
    assert first
    count = len(calls)
    second = call(runtime, req, request_purpose="conversation")
    assert second["request"] == first["request"] and len(calls) == count


def test_jev_unknown_tokenizer_does_not_license_character_only_pruning(tmp_path):
    runtime, engine, req = jev_case(tmp_path)
    runtime.token_budget = TokenBudgetAdapter()  # no fictitious JEV encoding fallback
    assert call(runtime, req, request_purpose="conversation") is None
    assert (
        engine.get_status()["context_engine"]["state"] == "exact_tokenizer_unavailable"
    )


@pytest.mark.parametrize(
    "model,context,expected",
    [
        ("typesafe/jev-latest", {}, True),
        ("~typesafe/jev-latest", {}, True),
        ("typesafe/jev-3.5", {}, True),
        ("jev-latest", {"provider": "typesafe"}, True),
        ("jev-latest", {"base_url": "https://api.typesafe.ai/v1"}, True),
        ("jev-latest", {"provider": "unrelated"}, False),
        ("acme/jev-compatible", {}, False),
        ("acme/jevil", {}, False),
        ("private-alias", {"target_model_family": "jev"}, True),
        ("gpt-4o", {"model": "typesafe/jev-latest"}, False),
        ("typesafe/jev-latest", {"model": "gpt-4o"}, True),
        ("gpt-4o", {"chat_target_policy": "preserve"}, True),
    ],
)
def test_actual_target_role_not_substring_or_stale_session_model(
    model, context, expected
):
    assert conservative_chat_target({"model": model}, context) is expected


def test_provider_fallback_reselects_target_policy_per_attempt(tmp_path):
    runtime, engine = setup(tmp_path)
    runtime.token_budget = PolicyFixtureCounter()
    req = request(engine)
    bind(engine, req)
    normal = call(runtime, req, request_purpose="conversation")
    assert normal and normal["metrics"]["context_engine"]["omitted_messages"] > 0
    fallback = copy.deepcopy(req)
    fallback["model"] = "typesafe/jev-latest"
    assert (
        call(runtime, fallback, request_purpose="conversation", model="gpt-4o") is None
    )
    assert runtime._last_chat_target["omitted_messages"] == 0
    assert (
        runtime._last_chat_target["usable_context_tokens"] is None
    )  # stale GPT window not borrowed
    retry = call(runtime, req, request_purpose="conversation")
    assert retry["request"] == normal["request"]


@pytest.mark.parametrize("bound", [False, True])
def test_salience_alone_vetoes_jev_target_emergency_omission(tmp_path, bound):
    runtime, engine, req = jev_case(tmp_path, bound=bound)
    adapter = runtime.token_budget
    adapter.context_limit_tokens = (
        adapter.measure_request(req).tokens
        + adapter.output_reserve_tokens
        + adapter.safety_margin_tokens
        - 200
    )

    def salient(payload):
        return {
            "answers": {
                q: {"type": "noul", "noul": 0.99 if q.endswith("_salience") else 0.01}
                for q in payload["questions"]
            }
        }

    runtime.jev_reducer.transport = engine.transport = salient
    original = copy.deepcopy(req)
    assert call(runtime, req, request_purpose="conversation") is None
    assert runtime._last_chat_target["state"] == "context_limit_unresolved"
    assert runtime._last_chat_target["omitted_messages"] == 0
    assert req == original


def test_internal_jev_cannot_overwrite_lifecycle_binding_or_capture_helpers(
    tmp_path, monkeypatch
):
    _runtime, engine = setup(tmp_path)
    req = request(engine)
    bind(engine, req)
    pending, generation = current(), engine.generation
    touched = []
    monkeypatch.setattr(engine._history(), "capture", lambda *a: touched.append(True))
    with internal_call():
        engine.select_context([{"role": "user", "content": "classify me"}])
        engine.compress(req["messages"])
        engine.on_turn_complete(req["messages"])
        engine.on_session_end("session", req["messages"])
    assert not touched and current() is pending and engine.generation == generation


def test_input_budget_reserves_requested_output_and_does_not_use_stale_window(tmp_path):
    from rtk_hermes_plus.chat_target import input_budget

    runtime, engine, req = jev_case(tmp_path)
    req["max_completion_tokens"] = 20000
    adapter = runtime.token_budget
    assert input_budget(runtime, req, {}, engine) == (
        128000 - 20000 - adapter.safety_margin_tokens
    )
    req["model"] = "typesafe/jev-newer"
    assert input_budget(runtime, req, {}, engine) is None
    assert input_budget(runtime, req, {"context_length": 40000}, engine) == (
        40000 - 20000 - adapter.safety_margin_tokens
    )
