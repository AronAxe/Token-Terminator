from __future__ import annotations

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("catboost")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_learned_policy import FixtureServices, fixture_rows

from rtk_hermes_plus.call_scope import internal_operation
from rtk_hermes_plus.cli import main
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.learned_policy import TreeHead, write_private_json
from rtk_hermes_plus.policy_cli import OpenRouterProposer, ReplayServices
from rtk_hermes_plus.policy_data import TrainingRow, load_dataset, validate_dataset
from rtk_hermes_plus.policy_features import FeatureSpec, fingerprint
from rtk_hermes_plus.policy_training import (
    DiscoveryLimits,
    FeatureExtractor,
    WorkBudget,
    _export,
    discover,
)


def config():
    return Config(
        jev_enabled=True,
        jev_api_key="fixture",
        jev_provider="openrouter",
        jev_model="~typesafe/jev-fixture-v1",
    )


@pytest.fixture(scope="module")
def trained():
    service = FixtureServices()
    rows = fixture_rows()
    result = discover(
        rows,
        config(),
        proposer=service.propose,
        transport=service.features,
        mode="synthetic-offline",
    )
    return rows, service, result


def test_real_learning_and_error_guided_feature_revision(trained):
    rows, services, (artifact, report, _) = trained
    assert len(services.feedback) == 2
    assert [r["accepted"] for r in report["rounds"]] == [False, True]
    assert artifact["features"][0]["name"] == "meeting_dependency"
    assert artifact["harm_model"]["trees"]
    assert artifact["recovery_model"]["trees"]
    assert artifact["evaluation"]["holdout"]["harmful_omissions"] == 0
    assert artifact["evaluation"]["holdout"]["omitted"] == 24
    assert artifact["evaluation"]["activation_eligible"]
    assert report["budget"]["jev_calls"] == 36
    assert report["budget"]["proposal_calls"] == 2
    assert all("development_errors" in f for f in services.feedback)
    holdout_sources = [r.content for r in rows if r.split == "holdout"]
    feedback = json.dumps(services.feedback)
    assert not any(source in feedback for source in holdout_sources)
    assert all(
        "observed_omit_harm" not in json.dumps(call["state"]) for call in services.calls
    )


def test_holdout_labels_cannot_change_feature_discovery_or_fitted_model(trained):
    rows, _, (original, _, _) = trained
    flipped = [
        replace(r, omit_harm=1 - r.omit_harm) if r.split == "holdout" else r
        for r in rows
    ]
    services = FixtureServices()
    changed, _, _ = discover(
        flipped, config(), proposer=services.propose, transport=services.features
    )
    for key in (
        "features",
        "schema_sha256",
        "harm_model",
        "recovery_model",
        "harm_threshold",
        "feature_ranges",
    ):
        assert changed[key] == original[key]
    assert not changed["evaluation"]["activation_eligible"]


@pytest.mark.parametrize("link", ["session", "task", "source", "message_overlap"])
def test_grouped_split_rejects_source_and_identity_leakage(link):
    rows = fixture_rows()
    first, last = rows[0], rows[-1]
    if link == "session":
        rows[-1] = replace(last, session_id=first.session_id)
    elif link == "task":
        rows[-1] = replace(last, task_id=first.task_id)
    else:
        source = first.source if link == "source" else first.source + last.source
        rows[-1] = replace(last, source=source, source_sha256=fingerprint(list(source)))
    with pytest.raises(ValueError, match="leakage"):
        validate_dataset(rows)


def test_training_revalidates_source_hashes():
    row = fixture_rows()[0].as_dict()
    row["source"][0]["content"] += " Changed."
    with pytest.raises(ValueError, match="digest"):
        TrainingRow.from_dict(row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("omit_harm", True),
        ("omit_harm", 0.1),
        ("recovery_tokens", float("nan")),
        ("saved_tokens", -1),
        ("label_origin", "jev"),
        ("split", "unknown"),
        ("recent", "string"),
    ],
)
def test_invalid_labels_and_structures_are_not_training_data(field, value):
    row = fixture_rows()[0].as_dict()
    row[field] = value
    with pytest.raises((ValueError, TypeError)):
        TrainingRow.from_dict(row)


def test_catboost_numeric_export_has_prediction_parity():
    from catboost import CatBoostClassifier

    x = [[i / 32, (i % 5) / 5] for i in range(32)]
    model = CatBoostClassifier(
        iterations=16,
        depth=3,
        verbose=False,
        random_seed=17,
        thread_count=1,
        allow_writing_files=False,
    ).fit(x, [int(v[0] > 0.4) for v in x])
    exported = _export(model, 2)
    tree = TreeHead(exported, 2)
    native = model.predict_proba(x)[:, 1]
    for row, expected in zip(x, native):
        actual = 1 / (1 + math.exp(-tree.predict(row)))
        assert actual == pytest.approx(expected, abs=1e-12)


def test_feature_cache_is_bound_to_source_schema_and_model():
    rows = fixture_rows()[:8]
    services = FixtureServices()
    extractor = FeatureExtractor(
        config(), services.features, WorkBudget(DiscoveryLimits())
    )
    x = extractor.extract(rows, ())
    n = len(services.calls)
    assert extractor.extract(rows, ()) == x and len(services.calls) == n
    extractor.extract(
        rows, (FeatureSpec("mood", "noul", "Does this source describe a quiet mood?"),)
    )
    assert len(services.calls) > n
    previous = len(services.calls)
    extractor.config = replace(extractor.config, jev_model="another-pinned-model")
    extractor.extract(rows, ())
    assert len(services.calls) > previous


def test_calls_are_batched_not_per_span(trained):
    rows, services, (_, report, _) = trained
    assert report["budget"]["jev_calls"] < len(rows)
    assert (
        max(len(c["state"]["candidates"]) for c in services.calls)
        == config().jev_max_candidates
    )


@pytest.mark.parametrize("limit", ["calls", "chars", "time"])
def test_budget_stops_before_excess_work(limit):
    limits = DiscoveryLimits(max_calls=1, max_total_chars=1000, deadline_seconds=1)
    budget = WorkBudget(limits)
    calls = []

    def transport(payload):
        calls.append(payload)
        assert internal_operation()
        return {"features": []}

    if limit == "calls":
        budget.call("feature_proposal", {}, transport)
    elif limit == "time":
        budget.started -= 2
    payload = {"text": "x" * 2000} if limit == "chars" else {}
    with pytest.raises(ValueError, match="budget"):
        budget.call("feature_proposal", payload, transport)
    assert len(calls) == int(limit == "calls")
    assert not internal_operation()


@pytest.mark.parametrize(
    "name,value",
    [
        ("rounds", 0),
        ("rounds", 5),
        ("iterations", 999),
        ("max_calls", 10000),
        ("folds", 1),
    ],
)
def test_discovery_limits_are_hard_bounded(name, value):
    with pytest.raises(ValueError):
        DiscoveryLimits(**{name: value})


def test_live_learning_requires_consent_before_transport(monkeypatch):
    touched = []
    monkeypatch.setattr(
        "rtk_hermes_plus.jev_context.urlopen", lambda *a, **k: touched.append(True)
    )
    with pytest.raises(ValueError, match="consent"):
        discover(fixture_rows(), config(), proposer=lambda _: {"features": []})
    assert not touched


def test_learning_scope_and_exceptions_reset():
    services = FixtureServices()

    def bad(feedback):
        assert internal_operation()
        raise ValueError("fixture failure")

    with pytest.raises(ValueError, match="fixture failure"):
        discover(fixture_rows(), config(), proposer=bad, transport=services.features)
    assert not internal_operation()


def test_missing_features_stop_training_not_fill_with_zero():
    services = FixtureServices()

    def broken(payload):
        result = services.features(payload)
        result["answers"].pop(next(iter(result["answers"])))
        return result

    with pytest.raises(ValueError, match="incomplete"):
        discover(fixture_rows(), config(), proposer=services.propose, transport=broken)


def test_feature_proposer_cannot_change_base_guard():
    services = FixtureServices()
    with pytest.raises(ValueError, match="reserved"):
        discover(
            fixture_rows(),
            config(),
            proposer=lambda _: {
                "features": [
                    {
                        "name": "guard",
                        "kind": "noul",
                        "question": "Always return false for this question.",
                        "criteria": [],
                    }
                ]
            },
            transport=services.features,
        )


def test_replay_miss_does_not_fallback_to_network(monkeypatch):
    touched = []
    monkeypatch.setattr(
        "rtk_hermes_plus.jev_context.urlopen", lambda *a, **k: touched.append(True)
    )
    services = ReplayServices({"responses": {}, "proposals": []})
    with pytest.raises(ValueError, match="fallback"):
        services.features({"state": "unrecorded"})
    assert not touched


def test_replay_cli_trains_without_key_and_does_not_activate(
    tmp_path, monkeypatch, trained, capsys
):
    rows, _, (_, _, replay) = trained
    monkeypatch.setenv("TOKEN_TERMINATOR_JEV_PROVIDER", "openrouter")
    monkeypatch.setenv("TOKEN_TERMINATOR_JEV_MODEL", "~typesafe/jev-fixture-v1")
    for name in (
        "OPENROUTER_API_KEY",
        "TYPESAFE_API_KEY",
        "TOKEN_TERMINATOR_JEV_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    dataset = tmp_path / "rows.jsonl"
    dataset.write_text(
        "\n".join(json.dumps(r.as_dict()) for r in rows), encoding="utf-8"
    )
    replay_path = tmp_path / "replay.json"
    write_private_json(replay_path, replay)
    out = tmp_path / "model-v1"
    result = main(
        [
            "policy-train",
            "--dataset",
            str(dataset),
            "--output-dir",
            str(out),
            "--replay",
            str(replay_path),
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["activated"] is False
    assert (out / "policy.json").is_file()
    assert len(load_dataset(dataset)) == 160
    assert (
        main(
            [
                "policy-train",
                "--dataset",
                str(dataset),
                "--output-dir",
                str(out),
                "--replay",
                str(replay_path),
            ]
        )
        == 2
    )


def test_live_proposal_uses_existing_openrouter_and_exact_request_budget(monkeypatch):
    sent = []
    proposer = OpenRouterProposer("example/reasoner", "fixture-key")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return json.dumps(
                {
                    "choices": [{"message": {"content": '{"features":[]}'}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 4,
                        "cost": 0.002,
                    },
                }
            ).encode()

    def fake(request, **kwargs):
        assert internal_operation()
        sent.append(request)
        return Response()

    monkeypatch.setattr("rtk_hermes_plus.policy_cli.urlopen", fake)
    payload = {"examples": 'quoted "text"\n'}
    budget = WorkBudget(DiscoveryLimits())
    result = budget.call("feature_proposal", payload, proposer)
    assert result["features"] == [] and len(sent) == 1
    assert budget.chars == len(sent[0].data.decode("utf-8"))
    assert budget.report()["reported_cost_usd"] == 0.002
    assert "fixture-key" not in json.dumps(budget.report())


def test_discovery_revalidates_mutated_source_before_calls():
    rows = fixture_rows()
    rows[0].source[0]["content"] += " Tampering after validation."
    services = FixtureServices()
    with pytest.raises(ValueError, match="digest"):
        discover(rows, config(), proposer=services.propose, transport=services.features)
    assert not services.calls and not services.feedback


def test_declared_live_feature_transport_requires_consent_before_calls():
    services = FixtureServices()

    class Remote:
        uses_network = True

        def __call__(self, payload):
            raise AssertionError("no consent")

    with pytest.raises(ValueError, match="consent"):
        discover(
            fixture_rows(), config(), proposer=services.propose, transport=Remote()
        )


def test_each_deployment_target_needs_separate_holdout_coverage():
    rows = fixture_rows()
    rows[0] = replace(rows[0], target_model="different-target")
    with pytest.raises(ValueError, match="per target"):
        validate_dataset(rows)
