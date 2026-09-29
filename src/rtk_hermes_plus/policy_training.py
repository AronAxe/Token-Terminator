"""Offline, grouped development loop; a final holdout is evaluated only after freeze.

CatBoost is an optional TRAINING dependency. Deployment uses numeric JSON trees.
This module never mines history, installs a policy, or starts an automatic job.
"""

from __future__ import annotations

import copy
import math
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from .call_scope import internal_call
from .context_history import digest, encode
from .jev_context import JevSemanticReducer, _Candidate
from .learned_policy import FORMAT, OmissionPolicy, TreeHead, strict_json
from .policy_data import TrainingRow, validate_dataset
from .policy_features import (
    FeatureSpec,
    columns,
    fingerprint,
    schema_id,
    validate_specs,
)


@dataclass(frozen=True)
class DiscoveryLimits:
    rounds: int = 2
    folds: int = 3
    iterations: int = 64
    max_calls: int = 64
    max_total_chars: int = 2_000_000
    deadline_seconds: int = 300

    def __post_init__(self):
        for name, lo, hi in (
            ("rounds", 1, 4),
            ("folds", 2, 5),
            ("iterations", 8, 256),
            ("max_calls", 1, 512),
            ("max_total_chars", 1000, 8_000_000),
            ("deadline_seconds", 1, 1800),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("discovery budget outside supported bounds")


class WorkBudget:
    def __init__(self, limits):
        self.limits = limits
        self.started = time.perf_counter()
        self.calls = 0
        self.chars = 0
        self.events = []
        self.replay = {}  # numeric answers + request digest only; no source text

    def check(self):
        if time.perf_counter() - self.started >= self.limits.deadline_seconds:
            raise ValueError("discovery wall-time budget exhausted")

    @internal_call()
    def call(self, kind, payload, transport):
        self.check()
        prepare = getattr(transport, "prepare", None)
        wire = prepare(copy.deepcopy(payload)) if callable(prepare) else payload
        size = len(encode(wire))
        if (
            self.calls >= self.limits.max_calls
            or self.chars + size > self.limits.max_total_chars
        ):
            raise ValueError("discovery request budget exhausted")
        self.calls += 1
        self.chars += size
        started = time.perf_counter()
        response = (
            transport.send(wire)
            if callable(prepare)
            else transport(copy.deepcopy(payload))
        )
        self.check()
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        cost = (
            usage.get("cost_usd", usage.get("cost"))
            if isinstance(usage, dict)
            else None
        )
        if type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0:
            cost = None
        event = {
            "kind": kind,
            "chars": size,
            "cost_usd": cost,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        for name in ("input_tokens", "output_tokens"):
            value = usage.get(name) if isinstance(usage, dict) else None
            event[name] = value if type(value) is int and value >= 0 else None
        self.events.append(event)
        if kind == "jev_features" and isinstance(response, dict):
            # Retain only numeric/schema-valid answers, not arbitrary provider metadata.
            safe = {}
            for key, answer in response.get("answers", {}).items():
                if not isinstance(answer, dict):
                    continue
                if answer.get("type") == "noul":
                    safe[key] = {"type": "noul", "noul": answer.get("noul")}
                elif answer.get("type") == "score":
                    safe[key] = {
                        "type": "score",
                        "probabilities": answer.get("probabilities"),
                    }
            self.replay[fingerprint(payload)] = {
                "answers": safe,
                "usage": {
                    k: event[k] for k in ("input_tokens", "output_tokens", "cost_usd")
                },
            }
        return response

    def report(self):
        costs = [e["cost_usd"] for e in self.events]
        return {
            "calls": self.calls,
            "budgeted_request_chars": self.chars,
            "jev_calls": sum(e["kind"] == "jev_features" for e in self.events),
            "proposal_calls": sum(e["kind"] == "feature_proposal" for e in self.events),
            "reported_cost_usd": sum(costs)
            if costs and all(c is not None for c in costs)
            else None,
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 3),
            "events": self.events,
        }


class FeatureExtractor:
    def __init__(self, config, transport, budget):
        self.config = replace(config, jev_enabled=True, context_ir_enabled=True)
        self.transport = transport
        self.budget = budget
        self.cache = {}
        self.cache_hits = 0

    def extract(self, rows, specs):
        specs = validate_specs(specs)
        schema = schema_id(specs)
        by_query = defaultdict(list)
        output = {}
        for row in rows:
            cache_key = fingerprint(
                {
                    "state": row.state_id,
                    "schema": schema,
                    "provider": self.config.jev_provider,
                    "model": self.config.jev_model,
                }
            )
            if cache_key in self.cache:
                output[row.row_id] = self.cache[cache_key]
                self.cache_hits += 1
            else:
                by_query[row.scoring_query].append((row, cache_key))
        scorer = JevSemanticReducer(None, self.config, feature_specs=specs)
        base_transport = self.transport or scorer._call
        scorer.transport = lambda payload: self.budget.call(
            "jev_features", payload, base_transport
        )
        # For live calls use a separate unwrapped client; never recursively call self.
        if self.transport is None:
            direct = JevSemanticReducer(None, self.config)
            scorer.transport = lambda payload: self.budget.call(
                "jev_features", payload, direct._call
            )
        for query, group in by_query.items():
            position = 0
            while position < len(group):
                batch, batch_rows = [], []
                while (
                    position < len(group)
                    and len(batch) < self.config.jev_max_candidates
                ):
                    row, cache_key = group[position]
                    if len(row.content) > self.config.jev_max_candidate_chars:
                        raise ValueError(
                            "training source exceeds exact candidate bound"
                        )
                    c = _Candidate(
                        {},
                        "content",
                        row.content,
                        "history",
                        len(batch),
                        "history_region",
                        f"c{len(batch)}",
                    )
                    if (
                        len(encode(scorer._payload(query, batch + [c])))
                        > self.config.jev_max_state_chars
                    ):
                        if not batch:
                            raise ValueError(
                                "training request exceeds body bound; never truncate"
                            )
                        break
                    batch.append(c)
                    batch_rows.append((row, cache_key))
                    position += 1
                result = scorer.score_batch(query, batch)
                if result.failed_open or len(result.features) != len(batch):
                    raise ValueError(
                        "feature extraction failed; no incomplete training matrix"
                    )
                vectors = {v.ordinal: v for v in result.features}
                for c, (row, key) in zip(batch, batch_rows):
                    v = vectors[c.ordinal]
                    if v.sha256 != digest(row.content) or v.schema_sha256 != schema:
                        raise ValueError("feature/evidence binding failed")
                    self.cache[key] = output[row.row_id] = v.values
        return [output[r.row_id] for r in rows]


def _constant_head(value):
    return {"scale": 1.0, "bias": float(value), "trees": []}


def _export(model, width):
    with tempfile.TemporaryDirectory(prefix="tt-fit-") as directory:
        path = Path(directory) / "model.json"
        model.save_model(str(path), format="json")
        raw = strict_json(path.read_text())
    scale, bias = raw["scale_and_bias"]
    if len(bias) != 1:
        raise ValueError("only scalar numeric heads can be deployed")
    trees = []
    for tree in raw["oblivious_trees"]:
        splits = tree.get("splits") or []
        if any(s["split_type"] != "FloatFeature" for s in splits):
            raise ValueError("only numeric tree splits can be deployed")
        trees.append(
            {
                "splits": [[s["float_feature_index"], s["border"]] for s in splits],
                "leaves": tree["leaf_values"],
            }
        )
    result = {"scale": scale, "bias": bias[0], "trees": trees}
    TreeHead(result, width)  # validate before any artifact is emitted
    return result


def fit_heads(matrix, rows, iterations=64):
    """Learn omission harm and recovery-token cost from observed labels, not JEV labels."""
    import numpy as np
    from catboost import CatBoostClassifier, CatBoostRegressor

    x = np.asarray(matrix, dtype=float)
    y = np.asarray([r.omit_harm for r in rows], dtype=int)
    recovery = np.asarray([r.recovery_tokens for r in rows], dtype=float)
    if x.ndim != 2 or not len(x) or not np.all(np.isfinite(x)):
        raise ValueError("invalid feature matrix")
    common = {
        "iterations": iterations,
        "depth": 3,
        "learning_rate": 0.12,
        "verbose": False,
        "random_seed": 17,
        "thread_count": 1,
        "allow_writing_files": False,
    }
    constant = bool(np.all(np.ptp(x, axis=0) == 0))
    if constant or len(set(y)) == 1:
        p = (float(y.sum()) + 0.5) / (len(y) + 1)
        harm = _constant_head(math.log(p / (1 - p)))
    else:
        classifier = CatBoostClassifier(loss_function="Logloss", **common).fit(x, y)
        harm = _export(classifier, x.shape[1])
    if constant or len(set(recovery)) == 1:
        cost = _constant_head(float(recovery.mean()))
    else:
        cost = _export(
            CatBoostRegressor(loss_function="RMSE", **common).fit(x, recovery),
            x.shape[1],
        )
    return harm, cost


def probabilities(head, matrix):
    tree = TreeHead(head, len(matrix[0]))
    return [1 / (1 + math.exp(-max(-700, min(700, tree.predict(x))))) for x in matrix]


def cross_validate(matrix, rows, dev_groups, limits):
    """Every validation prediction uses a model fitted without its whole linked group."""
    assignments = {}
    groups = sorted(
        dev_groups, key=lambda g: fingerprint(sorted(r.state_id for r in g))
    )
    for i, group in enumerate(groups):
        for row in group:
            assignments[row.row_id] = i % limits.folds
    harm, recovery = [None] * len(rows), [None] * len(rows)
    for fold in range(limits.folds):
        train = [i for i, r in enumerate(rows) if assignments[r.row_id] != fold]
        test = [i for i, r in enumerate(rows) if assignments[r.row_id] == fold]
        h, c = fit_heads(
            [matrix[i] for i in train], [rows[i] for i in train], limits.iterations
        )
        predicted = probabilities(h, [matrix[i] for i in test])
        tree = TreeHead(c, len(matrix[0]))
        for i, p in zip(test, predicted):
            harm[i], recovery[i] = p, max(0, tree.predict(matrix[i]))
    return harm, recovery


def decisions(rows, matrix, probabilities_, recovery, threshold, fixed_threshold):
    return [
        not row.protected
        and max(x[:3]) < fixed_threshold
        and p < threshold
        and cost < row.saved_tokens * 0.5
        for row, x, p, cost in zip(rows, matrix, probabilities_, recovery)
    ]


def metrics(rows, omitted, predicted=None):
    harm = sum(row.omit_harm for row, omit in zip(rows, omitted) if omit)
    net = sum(
        row.saved_tokens - row.recovery_tokens
        for row, omit in zip(rows, omitted)
        if omit
    )
    return {
        "rows": len(rows),
        "omitted": sum(omitted),
        "harmful_omissions": harm,
        "label_preservation_rate": 1
        - harm / max(1, sum(row.omit_harm for row in rows)),
        "gross_saved_tokens": sum(
            row.saved_tokens for row, omit in zip(rows, omitted) if omit
        ),
        "recovery_tokens": sum(
            row.recovery_tokens for row, omit in zip(rows, omitted) if omit
        ),
        "recovery_adjusted_saved_tokens": net,
        "utility": net - harm * 20000,
        "brier": sum((p - row.omit_harm) ** 2 for row, p in zip(rows, predicted))
        / len(rows)
        if predicted is not None
        else None,
    }


def choose_threshold(rows, matrix, h, c, fixed_threshold):
    trials = []
    for threshold in (0.001, 0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25):
        result = metrics(
            rows, decisions(rows, matrix, h, c, threshold, fixed_threshold), h
        )
        trials.append(
            ((-result["harmful_omissions"], result["utility"]), threshold, result)
        )
    _, threshold, result = max(trials, key=lambda t: t[0])
    return threshold, result


def feedback(rows, specs, result, predicted):
    worst = sorted(
        range(len(rows)),
        key=lambda i: abs(rows[i].omit_harm - predicted[i]),
        reverse=True,
    )[:6]
    # No holdout row, identifier, label, or statistic enters this proposal payload.
    return {
        "task": "Design measurements of whether omitting this exact history region would harm answering the query, or cause recovery. Return JSON {features:[{name,kind,question,criteria}]}. At most six extra Noul or Score questions. Retain/revise/drop existing features or add new ones. Do not propose outcome-label, dataset-ID, or train/test-membership features. The base relevance/guard/salience features and safety limits are immutable.",
        "current_features": [f.as_dict() for f in specs],
        "development_metrics": result,
        "development_errors": [
            {
                "query": rows[i].query,
                "target_model": rows[i].target_model,
                "recent": list(rows[i].recent),
                "source": list(rows[i].source),
                "observed_omit_harm": rows[i].omit_harm,
                "observed_recovery_tokens": rows[i].recovery_tokens,
                "predicted_harm": predicted[i],
            }
            for i in worst
        ],
    }


@internal_call()
def discover(
    rows,
    config,
    *,
    proposer,
    transport=None,
    limits=None,
    mode="provided",
    allow_external_data=False,
):
    """Run bounded feature discovery and final evaluation. Does NOT deploy anything."""
    if (
        transport is None
        or getattr(proposer, "uses_network", False)
        or getattr(transport, "uses_network", False)
    ) and not allow_external_data:
        raise ValueError("explicit external-data consent is required for live learning")
    limits = limits or DiscoveryLimits()
    rows = tuple(TrainingRow.from_dict(r.as_dict()) for r in rows)
    dev_groups, test_groups = validate_dataset(rows, limits.folds)
    dev = tuple(r for group in dev_groups for r in group)
    holdout = tuple(r for group in test_groups for r in group)
    budget = WorkBudget(limits)
    extractor = FeatureExtractor(config, transport, budget)
    specs = ()
    x = extractor.extract(dev, specs)
    h, c = cross_validate(x, dev, dev_groups, limits)
    threshold, current_metrics = choose_threshold(
        dev, x, h, c, config.jev_relevance_threshold
    )
    initial = dict(current_metrics)
    history, proposals = [], []
    for round_index in range(limits.rounds):
        budget.check()
        proposal = budget.call(
            "feature_proposal", feedback(dev, specs, current_metrics, h), proposer
        )
        if not isinstance(proposal, dict) or not isinstance(
            proposal.get("features"), list
        ):
            raise TypeError("malformed feature proposal")
        candidate_specs = validate_specs(
            FeatureSpec.from_dict(f) for f in proposal["features"]
        )
        proposals.append({"features": [f.as_dict() for f in candidate_specs]})
        candidate_x = extractor.extract(dev, candidate_specs)
        ph, pc = cross_validate(candidate_x, dev, dev_groups, limits)
        candidate_threshold, score = choose_threshold(
            dev, candidate_x, ph, pc, config.jev_relevance_threshold
        )
        key = lambda m: (-m["harmful_omissions"], m["utility"], -m["brier"])
        accepted = key(score) > key(current_metrics)
        history.append(
            {
                "round": round_index + 1,
                "schema_sha256": schema_id(candidate_specs),
                "features": len(candidate_specs),
                "accepted": accepted,
                "development": score,
            }
        )
        if accepted:
            specs, x, h, c, threshold, current_metrics = (
                candidate_specs,
                candidate_x,
                ph,
                pc,
                candidate_threshold,
                score,
            )
    # Freeze features, threshold and models BEFORE holdout outcome assessment.
    budget.check()
    harm_model, recovery_model = fit_heads(x, dev, limits.iterations)
    ranges = [[min(v[i] for v in x), max(v[i] for v in x)] for i in range(len(x[0]))]
    artifact = {
        "format": FORMAT,
        "features": [f.as_dict() for f in specs],
        "schema_sha256": schema_id(specs),
        "columns": list(columns(specs)),
        "target_models": sorted({r.target_model for r in dev}),
        "scorer": {"provider": config.jev_provider, "model": config.jev_model},
        "harm_model": harm_model,
        "recovery_model": recovery_model,
        "harm_threshold": threshold,
        "fixed_threshold": config.jev_relevance_threshold,
        "recovery_fraction": 0.5,
        "feature_ranges": ranges,
        "evaluation": {"activation_eligible": False},
    }
    frozen_id = fingerprint(artifact)
    test_x = extractor.extract(holdout, specs)
    policy = OmissionPolicy(artifact)
    from .policy_features import FeatureVector

    predicted = probabilities(harm_model, test_x)
    omitted = []
    for row, values in zip(holdout, test_x):
        vector = FeatureVector(0, digest(row.content), schema_id(specs), tuple(values))
        allowed, _ = policy.assess(vector, digest(row.content), row.saved_tokens)
        omitted.append(
            allowed
            and not row.protected
            and max(values[:3]) < config.jev_relevance_threshold
        )
    final = metrics(holdout, omitted, predicted)
    fixed = metrics(
        holdout,
        [
            not row.protected and max(v[:3]) < config.jev_relevance_threshold
            for row, v in zip(holdout, test_x)
        ],
    )
    artifact["evaluation"] = {
        "activation_eligible": current_metrics["harmful_omissions"] == 0
        and final["harmful_omissions"] == 0
        and final["recovery_adjusted_saved_tokens"] > 0,
        "development": current_metrics,
        "holdout": final,
        "holdout_by_target": {
            model: metrics(
                [r for r in holdout if r.target_model == model],
                [omit for r, omit in zip(holdout, omitted) if r.target_model == model],
            )
            for model in artifact["target_models"]
        },
        "holdout_fixed_gate": fixed,
        "dev_groups": len(dev_groups),
        "holdout_groups": len(test_groups),
        "dataset_sha256": fingerprint([r.as_dict() for r in rows]),
        "frozen_before_holdout_sha256": frozen_id,
        "label_origins": sorted({r.label_origin for r in rows}),
        "transport_mode": mode,
        "limitations": "Omission-label evaluation, not live LLM answer validation. Reused holdouts across separate runs are not automatically detectable. No learned policy may override the fixed safety envelope.",
    }
    OmissionPolicy(artifact)
    report = {
        "initial_development": initial,
        "rounds": history,
        "evaluation": artifact["evaluation"],
        "budget": budget.report(),
        "cache_hits": extractor.cache_hits,
    }
    return artifact, report, {"responses": budget.replay, "proposals": proposals}
