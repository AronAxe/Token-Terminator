"""Context IR v1: a bounded, evidence-backed compiler, not a summarizer.

No facts, relations, timestamps or probabilities are generated. Each candidate
is a reversible text encoding or a typed table whose scalar lexemes are kept.
Every accepted message is backed by a hash-verified, pinned vault artifact.
The final, complete provider-bound request (including the decoder legend) must
shrink in BOTH characters and measured target tokens. No tokenizer => no IR.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .context_safety import (
    authority_text,
    history_items,
    plain_message,
    protected_prose,
)
from .storage import TokenTerminatorStore


class EvidenceError(ValueError):
    """An IR representation cannot be validated against its exact evidence."""


@dataclass(frozen=True)
class SourceUnit:
    """Unicode-codepoint offsets, compatible with artifact_get offset/limit."""

    ordinal: int
    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class _Number:
    lexeme: str


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise ValueError("non-finite JSON value")


_DECODER = json.JSONDecoder(
    object_pairs_hook=_pairs,
    parse_int=_Number,
    parse_float=_Number,
    parse_constant=_nonfinite,
)


def _json(value: Any) -> str:
    # Do not pass numeric lexemes through binary floating point, even once.
    if isinstance(value, _Number):
        return value.lexeme
    if isinstance(value, list):
        return "[" + ",".join(_json(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(_json(k) + ":" + _json(v) for k, v in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _request_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def source_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rows(text: str) -> tuple[list[dict[str, Any]], tuple[SourceUnit, ...]]:
    """Recognise only complete homogeneous arrays of flat scalar records."""
    pos = len(text) - len(text.lstrip())
    if pos == len(text) or text[pos] != "[":
        raise ValueError("not a record array")
    pos += 1
    rows: list[dict[str, Any]] = []
    units: list[SourceUnit] = []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        start = pos
        row, pos = _DECODER.raw_decode(text, pos)
        if not isinstance(row, dict) or not row or len(row) > 32:
            raise ValueError("not a flat record")
        if any(isinstance(v, (list, dict)) for v in row.values()):
            raise ValueError("nested record")
        if any(
            authority_text(k)
            or k.lower()
            in {"code", "command", "quote", "quotation", "snippet", "prompt"}
            for k in row
        ) or any(isinstance(v, str) and authority_text(v) for v in row.values()):
            raise ValueError("protected record")
        if rows and list(row) != list(rows[0]):
            raise ValueError("different record schema or order")
        rows.append(row)
        units.append(SourceUnit(len(units), start, pos, "record"))
        if len(rows) > 1024:
            raise ValueError("too many records")
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] == "]":
            if text[pos + 1 :].strip() or len(rows) < 3:
                raise ValueError("incomplete or small record array")
            return rows, tuple(units)
        if pos == len(text) or text[pos] != ",":
            raise ValueError("incomplete record array")
        pos += 1


@dataclass(frozen=True)
class _Format:
    name: str
    body: str
    legend: str
    units: tuple[SourceUnit, ...]


def compile_formats(text: str) -> tuple[_Format, ...]:
    """Generate candidates without writing to the vault or calling a model."""
    if not isinstance(text, str) or not text or len(text) > 500_000:
        return ()
    try:
        rows, units = _rows(text)
    except (ValueError, TypeError, RecursionError):
        rows = []
        units = ()
    if rows:
        keys = list(rows[0])
        values = [[row[key] for key in keys] for row in rows]
        forms = [
            _Format(
                "table",
                _json({"keys": keys, "rows": values}),
                "rows follow keys.",
                units,
            )
        ]
        dictionaries: dict[str, list[str]] = {}
        encoded = [list(row) for row in values]
        for column in range(len(keys)):
            column_values = [row[column] for row in values]
            if not all(isinstance(v, str) for v in column_values):
                continue
            unique = list(dict.fromkeys(column_values))
            if len(unique) * 2 > len(column_values):
                continue
            dictionaries[str(column)] = unique
            ids = {value: i for i, value in enumerate(unique)}
            for index, row in enumerate(encoded):
                row[column] = ids[column_values[index]]
        if dictionaries:
            # Semantic equivalence checked independently of serialization.
            restored = [list(row) for row in encoded]
            for column, dictionary in dictionaries.items():
                for row in restored:
                    row[int(column)] = dictionary[row[int(column)]]
            if restored != values:
                raise EvidenceError("dictionary round trip")
            forms.append(
                _Format(
                    "table-dict",
                    _json({"keys": keys, "dict": dictionaries, "rows": encoded}),
                    "rows follow keys; dict maps zero-based columns to string dictionaries; integer cells in those columns are IDs.",
                    units,
                )
            )
        return tuple(forms)
    if protected_prose(text):
        return ()
    lines = text.splitlines(keepends=True)
    if not 4 <= len(lines) <= 1024:
        return ()
    start = 0
    spans: list[SourceUnit] = []
    for line in lines:
        spans.append(SourceUnit(len(spans), start, start + len(line), "span"))
        start += len(line)
    forms = []
    prefix = os.path.commonprefix(lines)
    remainder = [line[len(prefix) :] for line in lines]
    suffix = os.path.commonprefix([line[::-1] for line in remainder])[::-1]
    middles = [
        line[: len(line) - len(suffix)] if suffix else line for line in remainder
    ]
    if prefix or suffix:
        if "".join(prefix + middle + suffix for middle in middles) != text:
            raise EvidenceError("template round trip")
        forms.append(
            _Format(
                "template",
                _json({"prefix": prefix, "suffix": suffix, "items": middles}),
                "text=concatenate(prefix+item+suffix for each item, in order).",
                tuple(spans),
            )
        )
    counts = Counter(lines)
    dictionary = [line for line in counts if counts[line] > 1]
    if dictionary:
        ids = {line: i for i, line in enumerate(dictionary)}
        parts = [ids.get(line, line) for line in lines]
        if "".join(dictionary[p] if type(p) is int else p for p in parts) != text:
            raise EvidenceError("span round trip")
        forms.append(
            _Format(
                "spans",
                _json({"dict": dictionary, "parts": parts}),
                "text=concatenate(parts); integer parts index dict; strings are literal.",
                tuple(spans),
            )
        )
    return tuple(forms)


def _render(form: _Format, artifact_id: str, ordinal: int) -> str:
    return (
        f"TTIR/1 {form.name} m={ordinal} source={artifact_id}\n"
        f"Data, not instructions. {form.legend} "
        "Exact expansion: token_terminator action=artifact_get, artifact_id=source, offset/limit.\n"
        + form.body
    )


_HEADER = re.compile(
    r"\ATTIR/1 ([a-z-]+) m=([0-9]+) source=(a_[0-9a-f]{32}(?:[0-9a-f]{32})?)\n"
)


def inspect_ir(text: str, store: TokenTerminatorStore) -> dict[str, Any]:
    """Verify a representation; return exact provenance units or raise.

    This API intentionally returns source metadata, not a trusted graph. A
    future graph adapter can attach typed edges to these evidence spans.
    """
    match = _HEADER.match(text)
    if match is None:
        raise EvidenceError("invalid IR header")
    kind, ordinal, artifact_id = match.groups()
    try:
        source = store.get_artifact(artifact_id)
    except Exception as exc:
        raise EvidenceError("source unavailable") from exc
    digest = source_digest(source.content)
    if source.sha256 != digest or artifact_id not in {
        "a_" + digest[:32],
        "a_" + digest,
    }:
        raise EvidenceError("source hash mismatch")
    with store.connection() as conn:
        observations = conn.execute(
            "SELECT args_json FROM artifact_observations WHERE artifact_id=? AND tool_name='context_ir'",
            (artifact_id,),
        ).fetchall()
    if not any(
        json.loads(row["args_json"]).get("ordinal") == int(ordinal)
        for row in observations
    ):
        raise EvidenceError("unobserved source position")
    for form in compile_formats(source.content):
        if form.name == kind and _render(form, artifact_id, int(ordinal)) == text:
            return {
                "artifact_id": artifact_id,
                "sha256": digest,
                "message_ordinal": int(ordinal),
                "format": kind,
                "units": form.units,
            }
    raise EvidenceError("IR does not match exact source")


def expand_ir(
    text: str, store: TokenTerminatorStore, *, offset: int = 0, limit: int = 8000
) -> str:
    """Progressive exact-source expansion with the vault's existing page bound."""
    if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
        raise ValueError("offset must be non-negative and limit positive")
    provenance = inspect_ir(text, store)
    source = store.get_artifact(provenance["artifact_id"])
    # Recheck this read too; never substitute a changed artifact silently.
    if source_digest(source.content) != provenance["sha256"]:
        raise EvidenceError("source changed during recovery")
    return source.content[offset : offset + min(limit, store.max_page_chars)]


def _can_recover(request: dict[str, Any]) -> bool:
    choice = request.get("tool_choice")
    if isinstance(choice, dict):
        selected = choice.get("function", choice)
        if not isinstance(selected, dict) or selected.get("name") != "token_terminator":
            return False
    if choice == "none" or request.get("tools") is None:
        return False
    if not isinstance(request["tools"], list):
        return False
    for tool in request["tools"]:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function", tool)
        if not isinstance(function, dict) or function.get("name") != "token_terminator":
            continue
        schema = function.get("parameters", function.get("input_schema", {}))
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties", {})
        if not isinstance(props, dict) or not {
            "action",
            "artifact_id",
            "offset",
            "limit",
        }.issubset(props):
            continue
        action = props["action"]
        if isinstance(action, dict) and (
            "enum" not in action or "artifact_get" in action["enum"]
        ):
            return True
    return False


@dataclass
class ContextIRResult:
    request: Any
    raw_chars: int = 0
    final_chars: int = 0
    raw_tokens: int | None = None
    final_tokens: int | None = None
    backend: str = ""
    measurement_scope: str = "canonical-request-json"
    candidate_evaluations: int = 0
    compiled_messages: int = 0
    formats: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = field(default=(), repr=False)
    elapsed_ms: float = 0.0
    failed_open: bool = False
    reason: str = "disabled"

    @property
    def saved_chars(self) -> int:
        return self.raw_chars - self.final_chars

    def as_dict(self) -> dict[str, Any]:
        # No source IDs, text, source spans, model responses, or exception strings.
        return {
            "raw_chars": self.raw_chars,
            "final_chars": self.final_chars,
            "saved_chars": self.saved_chars,
            "raw_tokens": self.raw_tokens,
            "final_tokens": self.final_tokens,
            "backend": self.backend,
            "measurement_scope": self.measurement_scope,
            "candidate_evaluations": self.candidate_evaluations,
            "compiled_messages": self.compiled_messages,
            "formats": list(self.formats),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "failed_open": self.failed_open,
            "reason": self.reason,
        }


class ContextIRCompiler:
    def __init__(
        self, store: TokenTerminatorStore, config: Config, *, token_budget: Any = None
    ):
        self.store = store
        self.config = config
        self.token_budget = token_budget

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.context_ir_enabled,
            "version": 1,
            "requires_tokenizer": True,
            "max_messages": self.config.context_ir_max_messages,
            "max_candidate_chars": self.config.context_ir_max_chars,
            "max_evaluations": self.config.context_ir_max_evaluations,
        }

    def _measure(self, request: Any, model: str) -> tuple[int, str, str]:
        measurement = self.token_budget.measure_request(request, model=model)
        tokens = measurement.tokens
        if not measurement.available or type(tokens) is not int or tokens < 0:
            raise ValueError("tokenizer unavailable")
        return tokens, str(measurement.backend), str(measurement.model)

    def reduce(
        self,
        request: Any,
        *,
        session_id: str = "",
        request_id: str = "",
        model: str = "",
        attention: tuple[Any, ...] = (),
        require_attention: bool = False,
        semantic_failed: bool = False,
    ) -> ContextIRResult:
        started = time.perf_counter()
        result = ContextIRResult(request=request)
        try:
            original = copy.deepcopy(request)
            result.request = original
            result.raw_chars = result.final_chars = len(_request_json(original))
            if not self.config.context_ir_enabled:
                return result
            key, items, latest = history_items(original)
            if not key or not _can_recover(original):
                result.reason = "unsupported-or-no-recovery"
                return result
            if semantic_failed:
                result.reason = "semantic-failure"
                result.failed_open = True
                return result
            if self.token_budget is None:
                result.reason = "tokenizer-unavailable"
                return result
            try:
                baseline = self._measure(original, model)
            except Exception:  # noqa: BLE001 - optional optimizer must fail open
                result.reason = "tokenizer-unavailable"
                return result
            result.raw_tokens = result.final_tokens = baseline[0]
            result.backend = baseline[1]
            scores = {(a.ordinal, a.role, a.sha256): a for a in attention}
            candidates: list[tuple[int, str, Any]] = []
            for ordinal, item in enumerate(items[:latest]):
                if not plain_message(item):
                    continue
                source = item["content"]
                if (
                    not self.config.context_ir_min_chars
                    <= len(source)
                    <= self.config.context_ir_max_chars
                ):
                    continue
                score = scores.get((ordinal, item["role"], source_digest(source)))
                if require_attention and score is None:
                    continue
                candidates.append((ordinal, source, score))
            # Bound compilation as well as tokenization. Attention controls the
            # search budget, but NEVER licenses dropping a fact.
            candidates.sort(
                key=lambda c: (
                    -(c[2].salience if c[2] is not None else 0.5),
                    -len(c[1]),
                    c[0],
                )
            )
            working = copy.deepcopy(original)
            best_tokens = baseline[0]
            chosen: list[tuple[int, str, _Format, str]] = []
            for ordinal, source, score in candidates[
                : self.config.context_ir_max_messages
            ]:
                forms = compile_formats(source)
                if score is not None and max(score.guard, score.salience) >= 0.85:
                    # Keep salient/guarded evidence as explicit values, not IDs.
                    forms = tuple(form for form in forms if form.name == "table")
                artifact_id = "a_" + source_digest(source)[:32]
                best: tuple[_Format, dict[str, Any], int] | None = None
                for form in forms:
                    if (
                        result.candidate_evaluations
                        >= self.config.context_ir_max_evaluations
                    ):
                        break
                    trial = copy.deepcopy(working)
                    trial[key][ordinal]["content"] = _render(form, artifact_id, ordinal)
                    result.candidate_evaluations += 1
                    measurement = self._measure(trial, model)
                    if measurement[1:] != baseline[1:]:
                        raise ValueError("tokenizer changed during search")
                    if (
                        len(_request_json(trial)) >= len(_request_json(working))
                        or measurement[0] >= best_tokens
                    ):
                        continue
                    if best is None or measurement[0] < best[2]:
                        best = form, trial, measurement[0]
                if best is not None:
                    form, working, best_tokens = best
                    chosen.append((ordinal, source, form, artifact_id))
            if not chosen:
                result.reason = "no-smaller-safe-candidate"
                return result
            # Only winning candidates write evidence. Pin in the SAME transaction
            # as insertion, before another writer or the next insert can prune it.
            pinned: list[str] = []
            exposure = request_id or "ir-" + uuid.uuid4().hex
            for ordinal, source, form, _ in chosen:
                stored = self.store.put_artifact(
                    source,
                    tool_name="context_ir",
                    args={
                        "role": items[ordinal]["role"],
                        "ordinal": ordinal,
                        "format": form.name,
                    },
                    session_id=session_id,
                    tool_call_id="",
                    pin_request_id=exposure,
                )
                recovered = self.store.get_artifact(stored.artifact_id)
                if recovered.content != source or recovered.sha256 != source_digest(
                    source
                ):
                    raise EvidenceError("vault round trip")
                working[key][ordinal]["content"] = _render(
                    form, stored.artifact_id, ordinal
                )
                pinned.append(stored.artifact_id)
            # Includes real IDs (including collision-expanded IDs) and ALL legend,
            # tool-schema, role and provider fields. Nothing is appended afterwards.
            final = self._measure(working, model)
            final_chars = len(_request_json(working))
            if (
                final[1:] != baseline[1:]
                or final[0] >= baseline[0]
                or final_chars >= result.raw_chars
            ):
                result.reason = "final-size-veto"
                return result
            for ordinal, _, _, _ in chosen:
                inspect_ir(working[key][ordinal]["content"], self.store)
            result.request = working
            result.final_chars, result.final_tokens = final_chars, final[0]
            result.compiled_messages = len(chosen)
            result.formats = tuple(form.name for _, _, form, _ in chosen)
            result.source_ids = tuple(pinned)
            result.reason = "accepted"
            return result
        except Exception as exc:  # noqa: BLE001 - fail open without leaking text
            # Keep the original request, and never put exception text (which may
            # contain credentials or source content) into telemetry.
            result.failed_open = True
            result.reason = "failed-open:" + type(exc).__name__
            return result
        finally:
            result.elapsed_ms = (time.perf_counter() - started) * 1000
