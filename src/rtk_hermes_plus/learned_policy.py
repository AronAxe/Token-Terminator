"""Read-only, dependency-free inference for explicitly approved CatBoost policies.

The learner can veto an otherwise permitted omission. It cannot grant omission
permission or relax any context safety invariant. Model files are data, not code.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import tempfile
from pathlib import Path

from .policy_features import FeatureSpec, columns, finite, schema_id, validate_specs

FORMAT = "tt-omission-risk-policy-v1"
MAX_MODEL_BYTES = 2_000_000


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def bad_constant(_):
        raise ValueError("non-finite JSON number")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)


def write_private_json(path, value):
    """Create-only local output; atomic where hard links are supported."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() or path.is_symlink():
        raise ValueError("output already exists; choose a new versioned path")
    text = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    )
    fd, tmp = tempfile.mkstemp(prefix=".tt-policy-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Link is create-only and atomic. Windows may not allow links: use O_EXCL.
        try:
            os.link(tmp, path)
        except (NotImplementedError, OSError):
            out = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(out, "w", encoding="utf-8") as handle:
                handle.write(text)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TreeHead:
    """Small numeric-only oblivious tree evaluator; no pickle/native model loader."""

    def __init__(self, obj, width):
        if not isinstance(obj, dict) or set(obj) != {"scale", "bias", "trees"}:
            raise ValueError("unsupported numeric tree model")
        self.scale = finite(obj["scale"], -1e6, 1e6)
        self.bias = finite(obj["bias"], -1e9, 1e9)
        if not isinstance(obj["trees"], list) or len(obj["trees"]) > 256:
            raise ValueError("tree budget exceeded")
        self.trees = []
        for tree in obj["trees"]:
            if not isinstance(tree, dict) or set(tree) != {"splits", "leaves"}:
                raise ValueError("unsupported tree")
            splits, leaves = tree["splits"], tree["leaves"]
            if not isinstance(splits, list) or len(splits) > 6:
                raise ValueError("tree depth exceeded")
            if not isinstance(leaves, list) or len(leaves) != 2 ** len(splits):
                raise ValueError("invalid leaf layout")
            checked = []
            for split in splits:
                if not isinstance(split, list) or len(split) != 2:
                    raise ValueError("invalid split")
                feature, border = split
                if type(feature) is not int or not 0 <= feature < width:
                    raise ValueError("unknown feature index")
                checked.append((feature, finite(border, 0, 1)))
            self.trees.append(
                (tuple(checked), tuple(finite(v, -1e9, 1e9) for v in leaves))
            )

    def predict(self, values):
        # CatBoost compares float32 feature values against its exported borders.
        values = [struct.unpack("f", struct.pack("f", x))[0] for x in values]
        total = 0.0
        for splits, leaves in self.trees:
            index = sum(
                (values[feature] > border) << bit
                for bit, (feature, border) in enumerate(splits)
            )
            total += leaves[index]
        return total * self.scale + self.bias


class OmissionPolicy:
    def __init__(self, obj):
        if not isinstance(obj, dict) or obj.get("format") != FORMAT:
            raise ValueError("unsupported learned policy format")
        self.specs = validate_specs(FeatureSpec.from_dict(f) for f in obj["features"])
        self.schema_sha256 = schema_id(self.specs)
        if obj.get("schema_sha256") != self.schema_sha256 or obj.get("columns") != list(
            columns(self.specs)
        ):
            raise ValueError("feature schema mismatch")
        self.target_models = obj["target_models"]
        if (
            not isinstance(self.target_models, list)
            or not 1 <= len(self.target_models) <= 16
            or any(
                not isinstance(m, str) or not 1 <= len(m) <= 128
                for m in self.target_models
            )
            or len(set(self.target_models)) != len(self.target_models)
        ):
            raise ValueError("invalid generation target identities")
        self.scorer = obj["scorer"]
        if (
            not isinstance(self.scorer, dict)
            or set(self.scorer) != {"provider", "model"}
            or self.scorer["provider"] not in {"openrouter", "typesafe", "auto"}
            or not isinstance(self.scorer["model"], str)
            or not 1 <= len(self.scorer["model"]) <= 256
        ):
            raise ValueError("invalid scorer identity")
        self.threshold = finite(obj["harm_threshold"], 0.001, 0.25)
        self.fixed_threshold = finite(obj["fixed_threshold"], 0, 1)
        self.recovery_fraction = finite(obj["recovery_fraction"], 0, 1)
        self.harm = TreeHead(obj["harm_model"], len(columns(self.specs)))
        self.recovery = TreeHead(obj["recovery_model"], len(columns(self.specs)))
        ranges = obj["feature_ranges"]
        if not isinstance(ranges, list) or len(ranges) != len(columns(self.specs)):
            raise ValueError("invalid feature domain")
        self.ranges = []
        for bounds in ranges:
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise ValueError("invalid feature domain")
            low, high = [finite(x, 0, 1) for x in bounds]
            if low > high:
                raise ValueError("invalid feature domain")
            self.ranges.append((low, high))
        evaluation = obj["evaluation"]
        if (
            not isinstance(evaluation, dict)
            or type(evaluation.get("activation_eligible")) is not bool
        ):
            raise ValueError("missing held-out evaluation")
        self.activation_eligible = evaluation["activation_eligible"]
        self.data = obj

    def compatible(self, config):
        return (
            self.scorer == {"provider": config.jev_provider, "model": config.jev_model}
            and self.fixed_threshold == config.jev_relevance_threshold
        )

    def assess(self, vector, source_hash, saved_tokens):
        """Return (may_omit, reason). Missing, OOD and mismatched features retain."""
        if (
            vector is None
            or vector.sha256 != source_hash
            or vector.schema_sha256 != self.schema_sha256
        ):
            return False, "missing_or_unbound_features"
        if len(vector.values) != len(self.ranges):
            return False, "feature_width_mismatch"
        values = [finite(x, 0, 1) for x in vector.values]
        if any(
            x < low - 0.03 or x > high + 0.03
            for x, (low, high) in zip(values, self.ranges)
        ):
            return False, "out_of_domain"
        if saved_tokens is None or saved_tokens <= 0:
            return False, "no_measured_saving"
        raw = max(-700, min(700, self.harm.predict(values)))
        risk = 1 / (1 + math.exp(-raw))
        recovery = max(0.0, self.recovery.predict(values))
        if risk >= self.threshold:
            return False, "predicted_omission_harm"
        if recovery >= saved_tokens * self.recovery_fraction:
            return False, "predicted_recovery_cost"
        return True, "permitted_by_learner"


def load_policy(config):
    """Invoked only inside authorized engine work; invalid active policy fails open."""
    if config.learned_policy_mode == "off":
        return None, "off"
    try:
        path = Path(config.learned_policy_path).expanduser()
        expected = config.learned_policy_sha256
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("explicit artifact hash approval required")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_MODEL_BYTES
        ):
            raise ValueError("invalid policy file")
        with path.open("rb") as handle:
            raw = handle.read(MAX_MODEL_BYTES + 1)
        if len(raw) > MAX_MODEL_BYTES or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("policy checksum mismatch")
        policy = OmissionPolicy(strict_json(raw))
        if not policy.compatible(config):
            raise ValueError("scorer or base selection contract changed")
        if config.learned_policy_mode == "active" and not policy.activation_eligible:
            raise ValueError("holdout did not qualify for activation")
        return policy, "loaded"
    except Exception:  # noqa: BLE001 - never log local paths, content, or parser bodies
        return None, "invalid_policy"
