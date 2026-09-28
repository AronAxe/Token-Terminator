"""Explicit, labelled omission experiments; never silently mine a user's vault."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from .context_history import encode, terms
from .context_safety import protected_prose
from .learned_policy import strict_json
from .policy_features import fingerprint, finite

MAX_ROWS = 512


@dataclass(frozen=True)
class TrainingRow:
    row_id: str
    session_id: str
    task_id: str
    split: str
    query: str
    recent: tuple[dict, ...]
    source: tuple[dict, ...]
    source_sha256: str
    omit_harm: int
    recovery_tokens: float
    saved_tokens: float
    label_origin: str
    target_model: str

    @property
    def scoring_query(self):
        return encode(
            {"current_user": self.query, "recent_exact_context": list(self.recent)}
        )

    @property
    def content(self):
        return encode(list(self.source))

    @property
    def state_id(self):
        return fingerprint({"query": self.scoring_query, "source": self.content})

    @property
    def source_identity(self):
        # Ordinals must not disguise identical source text across splits.
        return fingerprint(
            [{k: m[k] for k in ("role", "content")} for m in self.source]
        )

    @property
    def protected(self):
        return any(
            protected_prose(m["content"]) or (terms(m["content"]) & terms(self.query))
            for m in self.source
        )

    def as_dict(self):
        return {
            "row_id": self.row_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "split": self.split,
            "query": self.query,
            "recent": list(self.recent),
            "source": list(self.source),
            "source_sha256": self.source_sha256,
            "omit_harm": self.omit_harm,
            "recovery_tokens": self.recovery_tokens,
            "saved_tokens": self.saved_tokens,
            "label_origin": self.label_origin,
            "target_model": self.target_model,
        }

    @classmethod
    def from_dict(cls, obj):
        required = {
            "row_id",
            "session_id",
            "task_id",
            "split",
            "query",
            "recent",
            "source",
            "source_sha256",
            "omit_harm",
            "recovery_tokens",
            "saved_tokens",
            "label_origin",
            "target_model",
        }
        if not isinstance(obj, dict) or set(obj) != required:
            raise ValueError("invalid training row schema")
        for name in ("row_id", "session_id", "task_id", "target_model"):
            if not isinstance(obj[name], str) or not 1 <= len(obj[name]) <= 128:
                raise ValueError("missing grouping/row identity")
        if obj["split"] not in {"dev", "holdout"} or obj["label_origin"] not in {
            "human",
            "deterministic",
            "synthetic",
        }:
            raise ValueError(
                "invalid split or label origin; JEV judgments are not outcome labels"
            )
        if not isinstance(obj["query"], str) or not 1 <= len(obj["query"]) <= 8000:
            raise ValueError("invalid training query")
        if not isinstance(obj["source"], list) or not 1 <= len(obj["source"]) <= 16:
            raise ValueError("source must be a bounded exact history region")
        if not isinstance(obj["recent"], list) or len(obj["recent"]) > 64:
            raise ValueError("invalid recent context")
        for messages, source in ((obj["source"], True), (obj["recent"], False)):
            for message in messages:
                expected = (
                    {"role", "content", "ordinal"} if source else {"role", "content"}
                )
                if not isinstance(message, dict) or set(message) != expected:
                    raise ValueError("unexpected source message schema")
                if message["role"] not in {"user", "assistant"} or not isinstance(
                    message["content"], str
                ):
                    raise ValueError(
                        "only exact plain dialogue belongs in training features"
                    )
                if source and (
                    type(message["ordinal"]) is not int or message["ordinal"] < 0
                ):
                    raise ValueError("invalid source ordinal")
        if len(encode(obj["source"])) > 64000 or len(encode(obj["recent"])) > 64000:
            raise ValueError("source bound exceeded")
        if obj["source_sha256"] != fingerprint(obj["source"]):
            raise ValueError("source evidence digest mismatch")
        if type(obj["omit_harm"]) is not int or obj["omit_harm"] not in {0, 1}:
            raise ValueError("omit_harm must be an observed binary outcome")
        return cls(
            obj["row_id"],
            obj["session_id"],
            obj["task_id"],
            obj["split"],
            obj["query"],
            tuple(copy.deepcopy(obj["recent"])),
            tuple(copy.deepcopy(obj["source"])),
            obj["source_sha256"],
            obj["omit_harm"],
            finite(obj["recovery_tokens"], 0, 1_000_000),
            finite(obj["saved_tokens"], 0, 1_000_000),
            obj["label_origin"],
            obj["target_model"],
        )


def validate_dataset(rows, folds=3):
    rows = tuple(rows)
    if not 12 <= len(rows) <= MAX_ROWS or len({r.row_id for r in rows}) != len(rows):
        raise ValueError("dataset requires 12-512 uniquely identified rows")
    # Union session/task/source connections into whole groups, before splitting.
    parents = list(range(len(rows)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen = {}
    for i, row in enumerate(rows):
        keys = [
            ("session", row.session_id),
            ("task", row.task_id),
            ("source", row.source_identity),
        ]
        keys.extend(
            ("message", fingerprint({"role": m["role"], "content": m["content"]}))
            for m in row.source
        )
        for key in keys:
            if key in seen:
                parents[root(i)] = root(seen[key])
            else:
                seen[key] = i
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    if any(len({r.split for r in group}) != 1 for group in groups.values()):
        raise ValueError(
            "session/task/duplicate-source leakage across development and holdout"
        )
    dev_groups = [group for group in groups.values() if group[0].split == "dev"]
    test_groups = [group for group in groups.values() if group[0].split == "holdout"]
    if len(dev_groups) < folds or len(test_groups) < 2:
        raise ValueError(
            "need at least folds independent development groups and two holdout groups"
        )
    for model in {r.target_model for r in rows}:
        for split in ("dev", "holdout"):
            if {
                r.omit_harm
                for r in rows
                if r.split == split and r.target_model == model
            } != {0, 1}:
                raise ValueError(
                    "both observed outcome classes are required per target in each split"
                )
    return dev_groups, test_groups


def load_dataset(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_000_000:
        raise ValueError("dataset must be a bounded local file")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in iter(lambda: handle.readline(200001), ""):
            if len(line) > 200000:
                raise ValueError("dataset line bound exceeded")
            if not line.strip():
                continue
            if len(rows) >= MAX_ROWS or len(line) > 200000:
                raise ValueError("dataset bound exceeded")
            rows.append(TrainingRow.from_dict(strict_json(line)))
    validate_dataset(rows)
    return tuple(rows)
