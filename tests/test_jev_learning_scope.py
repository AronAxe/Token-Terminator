"""External learning work is not a conversational request to compress.

Offline scope contracts only. No learner, model fitting or paid calls are run.
"""

from __future__ import annotations

import copy
import json

import pytest
from test_history_engine import low_scores, request, setup
from test_jev_roles import invoke, typed_decision

from rtk_hermes_plus.engine_bridge import current, take


@pytest.fixture(autouse=True)
def isolated_binding(monkeypatch):
    take()
    monkeypatch.delenv("TOKEN_TERMINATOR_CHAT_TARGET_POLICY", raising=False)
    yield
    take()


def feature_request(provider):
    payload = typed_decision(provider)
    payload["state"] = {
        "source_id": "row-17",
        "source_text": "Keep 12.30 exactly.\n  Preserve this indentation.\n",
        "feature_schema": "rubric-v2",
        "prior_probabilities": [0.001, 0.099, 0.2, 0.3, 0.4],
    }
    payload["questions"] = {
        "intensity": {
            "type": "score",
            "instructions": "How strongly does the source state an exact constraint?",
            "criteria": ["Absent", "Indirect", "Explicit", "Repeated", "Dominant"],
        },
        "exact_value": {
            "type": "noul",
            "instructions": "Does the source require preserving 12.30 exactly?",
        },
    }
    return payload


def forbid_reduction(monkeypatch, runtime, engine):
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("learning work reached conversational reduction")

    for obj, name in (
        (runtime, "_middleware_pipeline"),
        (engine, "reduce_request"),
        (runtime.token_budget, "measure_request"),
        (runtime.store, "put_artifact"),
        (runtime.jev_reducer, "_call"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    return touched


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize(
    "purpose",
    [
        "semantic_feature_extraction",
        "feature_proposal",
        "feature_evaluation",
        "policy_training",
    ],
)
def test_learning_helpers_bypass_before_work(tmp_path, monkeypatch, native, purpose):
    runtime, engine = setup(tmp_path)
    payload = request(engine)
    engine.select_context(payload["messages"])
    pending = current()
    before = copy.deepcopy(payload)
    touched = forbid_reduction(monkeypatch, runtime, engine)
    assert invoke(runtime, payload, native, request_purpose=purpose) is None
    assert payload == before and current() is pending and not touched
    assert runtime._last_call_scope == "non_conversational_or_unknown_purpose"


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("with_messages", [False, True])
def test_feature_state_and_rubrics_are_not_rewritten(
    tmp_path, monkeypatch, provider, native, with_messages
):
    runtime, engine = setup(tmp_path, jev_provider=provider)
    main = request(engine)
    engine.select_context(main["messages"])
    pending = current()
    payload = feature_request(provider)
    if with_messages:
        payload["messages"] = copy.deepcopy(main["messages"])
    before = json.dumps(payload, ensure_ascii=False)
    touched = forbid_reduction(monkeypatch, runtime, engine)
    assert (
        invoke(
            runtime,
            payload,
            native,
            request_purpose="conversation",
            target_model_family="jev",
        )
        is None
    )
    assert json.dumps(payload, ensure_ascii=False) == before
    assert current() is pending and not touched
    assert runtime._last_call_scope == "service_envelope"


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
def test_learning_work_between_main_retries_preserves_binding_and_cache(
    tmp_path, provider
):
    runtime, engine = setup(tmp_path, jev_provider=provider)
    main = request(engine)
    before = copy.deepcopy(main)
    engine.select_context(main["messages"])
    pending = current()
    calls = []

    def transport(payload):
        calls.append(copy.deepcopy(payload))
        return low_scores(payload)

    engine.transport = transport
    first = invoke(runtime, main, True)
    assert first and calls
    assert first["metrics"]["context_engine"]["omitted_messages"] > 0
    count = len(calls)
    features = feature_request(provider)
    features_before = copy.deepcopy(features)
    assert (
        invoke(runtime, features, True, request_purpose="semantic_feature_extraction")
        is None
    )
    assert invoke(runtime, main, True, request_purpose="feature_proposal") is None
    assert invoke(runtime, main, True, request_purpose="feature_evaluation") is None
    assert current() is pending
    retry = invoke(runtime, main, True)
    assert retry and retry["request"] == first["request"]
    assert len(calls) == count
    assert main == before and features == features_before
