from __future__ import annotations

import copy
import json
import math
import sys
from dataclasses import replace

import pytest
from test_history_engine import request, run, setup

from rtk_hermes_plus.config import load_config
from rtk_hermes_plus.context_history import digest
from rtk_hermes_plus.engine_bridge import current, take
from rtk_hermes_plus.jev_context import JevSemanticReducer, _Candidate
from rtk_hermes_plus.learned_policy import (
    FORMAT,
    OmissionPolicy,
    TreeHead,
    load_policy,
    strict_json,
    write_private_json,
)
from rtk_hermes_plus.policy_features import (
    FeatureSpec,
    FeatureVector,
    columns,
    schema_id,
    validate_specs,
)

SPEC = FeatureSpec(
    "dependency",
    "noul",
    "Does this region carry an earlier decision needed for the current question?",
)


def fixture_policy(config, *, risk=0.001, recovery=0):
    return {
        "format": FORMAT,
        "features": [SPEC.as_dict()],
        "schema_sha256": schema_id((SPEC,)),
        "columns": list(columns((SPEC,))),
        "target_models": ["gpt-4o", "gpt-4"],
        "scorer": {"provider": config.jev_provider, "model": config.jev_model},
        "harm_threshold": 0.1,
        "fixed_threshold": config.jev_relevance_threshold,
        "recovery_fraction": 0.5,
        "feature_ranges": [[0, 1]] * 4,
        "harm_model": {"scale": 1, "bias": math.log(risk / (1 - risk)), "trees": []},
        "recovery_model": {"scale": 1, "bias": recovery, "trees": []},
        "evaluation": {"activation_eligible": True},
    }


def configured(
    tmp_path, mode="active", *, risk=0.001, recovery=0, provider="openrouter"
):
    runtime, engine = setup(tmp_path, jev_provider=provider, context_ir_enabled=True)
    artifact = fixture_policy(engine.config, risk=risk, recovery=recovery)
    path = tmp_path / "policy.json"
    sha = write_private_json(path, artifact)
    config = replace(
        engine.config,
        learned_policy_mode=mode,
        learned_policy_path=str(path),
        learned_policy_sha256=sha,
    )
    engine.config = config
    runtime.config = config
    return runtime, engine, artifact


@pytest.fixture(autouse=True)
def binding_and_environment(monkeypatch):
    take()
    monkeypatch.delenv("TOKEN_TERMINATOR_CHAT_TARGET_POLICY", raising=False)
    yield
    take()


def complete_scores(payload):
    return {
        "answers": {
            name: {"type": "noul", "noul": 0.01} for name in payload["questions"]
        }
    }


@pytest.mark.parametrize(
    "value", [None, "0.5", True, -1, 2, float("nan"), float("inf")]
)
def test_noul_features_never_impute_invalid_values(value):
    with pytest.raises(ValueError):
        SPEC.values({"type": "noul", "noul": value})


@pytest.mark.parametrize(
    "probabilities",
    [
        {"0": 0.2},
        {"0": 0.5, "1": 0.7},
        {"0": True, "1": 0.0},
        {"0": float("nan"), "1": 1.0},
        {"0": 0.0, "1": 1.0, "2": 0.0},
    ],
)
def test_score_distribution_must_be_complete_and_normalized(probabilities):
    spec = FeatureSpec(
        "intensity",
        "score",
        "How strongly is this dependency expressed?",
        ("absent", "present"),
    )
    with pytest.raises(ValueError):
        spec.values({"type": "score", "probabilities": probabilities})


def test_score_features_keep_mean_and_spread():
    spec = FeatureSpec(
        "intensity",
        "score",
        "How strongly is this dependency expressed?",
        ("absent", "weak", "strong"),
    )
    mean, spread = spec.values(
        {"type": "score", "probabilities": {"0": 0.25, "1": 0.5, "2": 0.25}}
    )
    assert mean == 0.5 and spread == pytest.approx(math.sqrt(0.5) / 2)
    assert columns((spec,))[-2:] == ("intensity.mean", "intensity.spread")
    assert schema_id((spec,)) != schema_id(
        (replace(spec, question=spec.question + " In detail."),)
    )


@pytest.mark.parametrize(
    "name",
    ["guard", "relevance", "salience", "__import__", "../../file", "foo.bar", "x" * 33],
)
def test_feature_names_cannot_replace_base_guard_or_execute_code(name):
    with pytest.raises(ValueError):
        FeatureSpec(name, "noul", "Is there a dependency in this source?")


def test_features_bounded_and_unique():
    with pytest.raises(ValueError):
        validate_specs((SPEC, SPEC))
    with pytest.raises(ValueError):
        validate_specs(tuple(replace(SPEC, name=f"f{i}") for i in range(7)))


@pytest.mark.parametrize("provider", ["openrouter", "typesafe"])
def test_extra_measurements_share_existing_batch_and_exact_source(provider, tmp_path):
    runtime, engine, _ = configured(tmp_path, provider=provider)
    payloads = []

    def transport(payload):
        payloads.append(copy.deepcopy(payload))
        return complete_scores(payload)

    scorer = JevSemanticReducer(
        runtime.store, engine.config, feature_specs=(SPEC,), transport=transport
    )
    candidates = [
        _Candidate(
            {}, "content", "exact " + str(i), "history", i, "history_region", f"c{i}"
        )
        for i in range(4)
    ]
    result = scorer.score_batch("exact current question", candidates)
    assert len(payloads) == 1 and len(payloads[0]["questions"]) == 16
    assert len(result.features) == 4
    assert [v.sha256 for v in result.features] == [
        digest(c.content) for c in candidates
    ]
    assert payloads[0]["state"]["candidates"]["c0"]["content"] == "exact 0"


@pytest.mark.parametrize(
    "kind",
    [
        "bad_hash",
        "no_hash",
        "wrong_model",
        "wrong_provider",
        "wrong_schema",
        "failed_holdout",
        "bad_tree",
        "missing_file",
    ],
)
def test_invalid_active_model_fails_open(tmp_path, kind):
    runtime, engine, artifact = configured(tmp_path)
    config = engine.config
    if kind == "bad_hash":
        config = replace(config, learned_policy_sha256="0" * 64)
    elif kind == "no_hash":
        config = replace(config, learned_policy_sha256="")
    elif kind == "missing_file":
        config = replace(config, learned_policy_path=str(tmp_path / "missing.json"))
    else:
        if kind == "wrong_model":
            artifact["scorer"]["model"] = "another-model"
        elif kind == "wrong_provider":
            artifact["scorer"]["provider"] = "typesafe"
        elif kind == "wrong_schema":
            artifact["schema_sha256"] = "0" * 64
        elif kind == "failed_holdout":
            artifact["evaluation"]["activation_eligible"] = False
        elif kind == "bad_tree":
            artifact["harm_model"]["trees"] = [
                {"splits": [[99, 0.5]], "leaves": [0, 1]}
            ]
        path = tmp_path / "changed.json"
        sha = write_private_json(path, artifact)
        config = replace(
            config, learned_policy_path=str(path), learned_policy_sha256=sha
        )
    engine.config = runtime.config = config
    engine.transport = complete_scores
    req = request(engine)
    assert run(runtime, engine, req) == req
    assert engine.get_status()["context_engine"]["learned_state"] == "invalid_policy"


@pytest.mark.parametrize("risk,recovery", [(0.95, 0), (0.001, 1_000_000)])
def test_learned_harm_or_recovery_veto_preserves_exact_history(
    tmp_path, risk, recovery
):
    runtime, engine, _ = configured(tmp_path, risk=risk, recovery=recovery)
    engine.transport = complete_scores
    req = request(engine)
    final = run(runtime, engine, req)
    assert final == req
    status = engine.get_status()["context_engine"]
    assert status["learned_retained_messages"] > 0
    assert status["omitted_messages"] == 0


def test_active_policy_never_overrides_fixed_guards(tmp_path):
    runtime, engine, _ = configured(tmp_path)

    def guarded(payload):
        return {
            "answers": {
                name: {"type": "noul", "noul": 0.9 if name.endswith("_guard") else 0.01}
                for name in payload["questions"]
            }
        }

    engine.transport = guarded
    req = request(engine)
    assert run(runtime, engine, req) == req


@pytest.mark.parametrize(
    "text",
    [
        "Never omit the earlier decision.",
        'The quote was "keep it".',
        "The value is 12.30.",
        "```python\nx = 17\n```",
        "A system instruction stays exact.",
    ],
)
def test_active_policy_retains_protected_sources(tmp_path, text):
    runtime, engine, _ = configured(tmp_path)
    engine.transport = complete_scores
    req = request(engine)
    req["messages"][1]["content"] = text * 40
    final = run(runtime, engine, req)
    assert req["messages"][1] in final["messages"]
    assert (
        final["messages"][0] == req["messages"][0]
        and final["messages"][-1] == req["messages"][-1]
    )


def test_missing_extra_features_retain_not_impute_and_do_not_cache(tmp_path):
    runtime, engine, _ = configured(tmp_path)
    calls = []

    def missing(payload):
        calls.append(payload)
        return {
            "answers": {
                name: {"type": "noul", "noul": 0.01}
                for name in payload["questions"]
                if "_learned_" not in name
            }
        }

    engine.transport = missing
    req = request(engine)
    assert run(runtime, engine, req) == req
    before = len(calls)
    runtime.llm_request_middleware(
        request=req, request_purpose="conversation", session_id="session"
    )
    assert len(calls) > before


def test_retry_cache_and_internal_calls_preserve_binding(tmp_path):
    runtime, engine, _ = configured(tmp_path)
    calls = []
    req = request(engine)

    def transport(payload):
        calls.append(payload)
        binding = current()
        assert (
            runtime.llm_request_middleware(
                request=req, request_purpose="conversation", session_id="session"
            )
            is None
        )
        engine.select_context(req["messages"])
        assert current() is binding
        return complete_scores(payload)

    engine.transport = transport
    first = run(runtime, engine, req)
    assert first != req
    count = len(calls)
    pending = current()
    assert (
        runtime.llm_request_middleware(
            request=req, request_purpose="feature_proposal", session_id="session"
        )
        is None
    )
    assert current() is pending
    result = runtime.llm_request_middleware(
        request=req,
        request_purpose="conversation",
        session_id="session",
        api_request_id="retry",
    )
    assert result["request"] == first and len(calls) == count


@pytest.mark.parametrize(
    "purpose",
    [
        "embedding",
        "rerank",
        "classifier",
        "helper",
        "feature_proposal",
        "policy_training",
        "tokenizer",
    ],
)
def test_helpers_bypass_before_policy_loading(tmp_path, monkeypatch, purpose):
    runtime, engine, _ = configured(tmp_path)
    req = request(engine)
    engine.select_context(req["messages"])
    touched = []

    def forbidden(*args):
        touched.append(True)
        raise AssertionError("helper reached policy loading")

    monkeypatch.setattr("rtk_hermes_plus.learned_policy.load_policy", forbidden)
    original = copy.deepcopy(req)
    assert (
        runtime.llm_request_middleware(
            request=req, request_purpose=purpose, session_id="session"
        )
        is None
    )
    assert req == original and not touched


def test_roomy_jev_chat_target_does_not_load_or_score_policy(tmp_path, monkeypatch):
    runtime, engine, _ = configured(tmp_path)
    touched = []

    def forbidden(*args):
        touched.append(True)
        raise AssertionError("roomy preserve target attempted semantic learning")

    monkeypatch.setattr("rtk_hermes_plus.learned_policy.load_policy", forbidden)
    req = request(engine)
    engine.select_context(req["messages"])
    result = runtime.llm_request_middleware(
        request=req,
        request_purpose="conversation",
        target_model_family="jev",
        session_id="session",
    )
    assert (result["request"] if result else req) == req
    assert not touched


def test_shadow_is_identical_to_fixed_mode_and_accounts_extra_work(tmp_path):
    runtime, engine, _ = configured(tmp_path, "shadow", risk=0.99)
    engine.transport = complete_scores
    req = request(engine)
    shadow = run(runtime, engine, req)
    status = engine.get_status()["context_engine"]
    assert status["learned_policy_shadow"]["learned_retained_messages"] > 0
    shadow_calls = status["jev_calls"]
    engine.config = runtime.config = replace(engine.config, learned_policy_mode="off")
    engine._score_cache.clear()
    fixed = run(runtime, engine, req)
    assert (
        shadow == fixed
        and shadow_calls == 2 * engine.get_status()["context_engine"]["jev_calls"]
    )


def test_shadow_failure_does_not_change_baseline(tmp_path):
    runtime, engine, _ = configured(tmp_path, "shadow")
    engine.config = runtime.config = replace(
        engine.config, learned_policy_sha256="0" * 64
    )
    engine.transport = complete_scores
    req = request(engine)
    shadow = run(runtime, engine, req)
    assert shadow != req
    assert (
        engine.get_status()["context_engine"]["learned_policy_shadow"]["learned_state"]
        == "invalid_policy"
    )


@pytest.mark.parametrize("change", ["source", "schema", "range", "missing", "savings"])
def test_unbound_or_out_of_domain_prediction_abstains(tmp_path, change):
    _, _engine, artifact = configured(tmp_path)
    artifact["feature_ranges"] = [[0, 0.1]] * 4
    policy = OmissionPolicy(artifact)
    vector = FeatureVector(0, "a" * 64, policy.schema_sha256, (0.01,) * 4)
    if change == "source":
        vector = replace(vector, sha256="b" * 64)
    elif change == "schema":
        vector = replace(vector, schema_sha256="b" * 64)
    elif change == "range":
        vector = replace(vector, values=(0.01, 0.01, 0.01, 0.9))
    elif change == "missing":
        vector = None
    assert not policy.assess(vector, "a" * 64, 0 if change == "savings" else 100)[0]


def test_numeric_model_has_no_pickle_or_catboost_runtime_dependency(
    tmp_path, monkeypatch
):
    _, _, artifact = configured(tmp_path)
    monkeypatch.setitem(sys.modules, "catboost", None)
    policy = OmissionPolicy(artifact)
    vector = FeatureVector(0, "a" * 64, policy.schema_sha256, (0.01,) * 4)
    assert policy.assess(vector, "a" * 64, 100)[0]
    with pytest.raises(ValueError):
        TreeHead({"pickle": "not allowed"}, 4)


def test_strict_json_and_create_only_private_outputs(tmp_path):
    for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
        with pytest.raises(ValueError):
            strict_json(text)
    path = tmp_path / "policy.json"
    write_private_json(path, {"value": 1})
    with pytest.raises(ValueError):
        write_private_json(path, {"value": 2})
    assert json.loads(path.read_text())["value"] == 1


def test_model_symlink_is_rejected(tmp_path):
    _runtime, engine, _ = configured(tmp_path)
    link = tmp_path / "link.json"
    try:
        link.symlink_to(engine.config.learned_policy_path)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert (
        load_policy(replace(engine.config, learned_policy_path=str(link)))[1]
        == "invalid_policy"
    )


def test_new_config_is_opt_in(monkeypatch):
    for suffix in ("MODE", "PATH", "SHA256"):
        monkeypatch.delenv("TOKEN_TERMINATOR_LEARNED_POLICY_" + suffix, raising=False)
    assert load_config().learned_policy_mode == "off"
    monkeypatch.setenv("TOKEN_TERMINATOR_LEARNED_POLICY_MODE", "ACTIVE")
    assert load_config().learned_policy_mode == "active"
    monkeypatch.setenv("TOKEN_TERMINATOR_LEARNED_POLICY_MODE", "typo")
    assert load_config().learned_policy_mode == "off"


def test_untrained_target_is_not_silently_given_another_models_policy(tmp_path):
    runtime, engine, _ = configured(tmp_path)
    req = request(engine)
    req["model"] = "gpt-4.1"
    engine.update_model("gpt-4.1", 128000)
    calls = []
    engine.transport = lambda payload: calls.append(payload) or complete_scores(payload)
    result = run(runtime, engine, req)
    assert result == req
    assert not calls
    assert engine._last_status["learned_state"] == "target_model_mismatch"


@pytest.mark.parametrize("declared", ["typesafe/different-version", 27, {}])
def test_declared_scorer_drift_never_produces_deployment_features(tmp_path, declared):
    runtime, engine, _ = configured(tmp_path)
    config = replace(engine.config, jev_model="~typesafe/jev-pinned-v1")
    scorer = JevSemanticReducer(
        runtime.store,
        config,
        feature_specs=(SPEC,),
        transport=lambda payload: {**complete_scores(payload), "model": declared},
    )
    candidate = _Candidate(
        {}, "content", "An old discussion.", "history", 0, "history_region", "c0"
    )
    scored = scorer.score_batch("Current query", [candidate])
    assert len(scored.attention) == 1
    assert not scored.features


def test_active_learning_never_bypasses_exact_final_token_veto(tmp_path):
    from rtk_hermes_plus.context_history import encode
    from rtk_hermes_plus.token_budget import TokenBudgetAdapter, TokenMeasurement

    runtime, engine, _ = configured(tmp_path)
    engine.transport = complete_scores

    class NoSaving(TokenBudgetAdapter):
        def measure_request(self, request, *, model=""):
            value = super().measure_request(request, model=model)
            if "[TT history" in encode(request):
                return TokenMeasurement(10**8, "fixture-counter", model)
            return value

    runtime.token_budget = NoSaving()
    req = request(engine)
    assert run(runtime, engine, req) == req


def test_active_policy_is_not_loaded_without_a_target_tokenizer(tmp_path, monkeypatch):
    runtime, engine, _ = configured(tmp_path)
    runtime.token_budget.enabled = False
    import rtk_hermes_plus.learned_policy as policy

    monkeypatch.setattr(
        policy, "load_policy", lambda _: pytest.fail("must bypass first")
    )
    engine.transport = lambda _: pytest.fail("must not spend")
    req = request(engine)
    assert run(runtime, engine, req) == req


def test_active_policy_cannot_override_corrupted_exact_evidence(tmp_path):
    runtime, engine, _ = configured(tmp_path)
    engine.transport = complete_scores
    req = request(engine)
    final = run(runtime, engine, req)
    receipt = next(
        m["content"]
        for m in final["messages"]
        if m.get("content", "").startswith("[TT history")
    )
    aid = receipt.split()[2].rstrip(";")
    with runtime.store.connection(write=True) as conn:
        conn.execute(
            "UPDATE artifacts SET content='corrupt' WHERE artifact_id=?", (aid,)
        )
    assert run(runtime, engine, req) == req
    result = json.loads(
        engine.handle_tool_call(
            "token_terminator_history", {"action": "get", "artifact_id": aid}
        )
    )
    assert "error" in result
