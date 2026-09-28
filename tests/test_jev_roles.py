"""JEV's controller/verifier roles are decisions, not conversational generation.

Offline contract tests; no assertion about live JEV accuracy or chat capability.
"""

from __future__ import annotations

import copy
import json

import pytest
from test_history_engine import low_scores, request, setup

from rtk_hermes_plus.engine_bridge import current, take


@pytest.fixture(autouse=True)
def isolated_binding(monkeypatch):
    take()
    monkeypatch.delenv("TOKEN_TERMINATOR_CHAT_TARGET_POLICY", raising=False)
    yield
    take()


def invoke(runtime, payload, native, **extra):
    context = {
        "session_id": "session",
        "api_request_id": "decision-attempt",
        **extra,
    }
    if native:
        context.update(
            middleware_schema_version="hermes.middleware.v1",
            turn_id="turn",
            api_call_count=1,
            api_mode="chat_completions",
        )
        return runtime.hermes_llm_request_middleware(request=payload, **context)
    return runtime.llm_request_middleware(request=payload, **context)


def typed_decision(provider):
    # TypeSafe /v1/systemone and OpenRouter Decisions use state + typed questions.
    # Choices/scores use criteria, not free-form generative response schemas.
    return {
        "model": "jev-latest" if provider == "typesafe" else "typesafe/jev-latest",
        "state": {
            "request": "Inspect, but do NOT deploy. Preserve 12.30 exactly.\n",
            "skills": [{"id": "review", "body": "Read-only review.\n  No edits."}],
            "source": "The permitted amount is 12.30, not 12.3.",
            "draft": "The permitted amount is 12.30.",
        },
        "questions": {
            "route": {
                "type": "choice",
                "instructions": "Which permitted handler fits the request?",
                "criteria": {
                    "review": "Read-only analysis",
                    "escalate": "Human review",
                },
            },
            "priority": {
                "type": "score",
                "instructions": "How urgent is the request?",
                "criteria": ["Routine", "Time-sensitive", "Immediate review"],
            },
            "supported": {
                "type": "noul",
                "instructions": "Is the draft's amount supported by the source?",
            },
        },
    }


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize(
    "purpose",
    [
        "workflow_selection",
        "skill_selection",
        "intent_routing",
        "priority_assessment",
        "context_validation",
        "citation_verification",
        "guardrail",
        "requirement_check",
        "retry_escalation",
    ],
)
def test_controller_and_verifier_roles_bypass_before_work(
    tmp_path, monkeypatch, native, purpose
):
    runtime, engine = setup(tmp_path)
    payload = request(engine)
    engine.select_context(payload["messages"])
    pending = current()
    original = copy.deepcopy(payload)
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("decision task reached conversational reduction")

    for obj, name in (
        (runtime, "_middleware_pipeline"),
        (engine, "reduce_request"),
        (runtime.token_budget, "measure_request"),
        (runtime.store, "put_artifact"),
        (runtime.jev_reducer, "_call"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    assert invoke(runtime, payload, native, request_purpose=purpose) is None
    assert payload == original and current() is pending and not touched
    assert runtime._last_call_scope == "non_conversational_or_unknown_purpose"


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("with_messages", [False, True])
def test_typed_jev_decisions_override_misleading_chat_authorization(
    tmp_path, monkeypatch, provider, native, with_messages
):
    runtime, engine = setup(tmp_path, jev_provider=provider)
    main = request(engine)
    engine.select_context(main["messages"])
    pending = current()
    payload = typed_decision(provider)
    if with_messages:
        payload["messages"] = copy.deepcopy(main["messages"])
    before = json.dumps(payload, ensure_ascii=False)
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("typed decision reached target policy")

    for obj, name in (
        (engine, "reduce_request"),
        (runtime, "_middleware_pipeline"),
        (runtime.token_budget, "measure_request"),
        (runtime.store, "put_artifact"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    assert (
        invoke(
            runtime,
            payload,
            native,
            request_purpose="conversation",
            target_model_family="jev",
            chat_target_policy="preserve",
        )
        is None
    )
    assert json.dumps(payload, ensure_ascii=False) == before
    assert current() is pending and not touched
    assert runtime._last_call_scope == "service_envelope"


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
def test_decision_support_does_not_disable_the_separate_answering_llm(
    tmp_path, provider
):
    runtime, engine = setup(tmp_path, jev_provider=provider)
    main = request(engine)
    original = copy.deepcopy(main)
    engine.select_context(main["messages"])
    batches = []

    def transport(payload):
        batches.append(copy.deepcopy(payload))
        return low_scores(payload)

    engine.transport = transport
    decision = typed_decision(provider)
    before = copy.deepcopy(decision)
    assert invoke(runtime, decision, True, request_purpose="intent_routing") is None
    generated = invoke(runtime, main, True)
    assert generated and batches
    assert main == original and decision == before
    assert generated["metrics"]["context_engine"]["omitted_messages"] > 0
    assert runtime.token_budget.measure_request(generated["request"]).tokens < (
        runtime.token_budget.measure_request(main).tokens
    )
    assert all("state" in batch and "questions" in batch for batch in batches)
    assert all(
        question["type"] == "noul"
        for batch in batches
        for question in batch["questions"].values()
    )
    # A verifier between physical attempts must not consume the main binding/cache.
    assert (
        invoke(runtime, decision, True, request_purpose="citation_verification") is None
    )
    count = len(batches)
    retry = invoke(runtime, main, True)
    assert retry["request"] == generated["request"] and len(batches) == count
