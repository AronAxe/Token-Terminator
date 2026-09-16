from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .storage import TokenTerminatorStore
from .token_budget import TokenBudgetAdapter

_COMPONENT_ORDER = (
    "instructions",
    "tool_schemas",
    "tool_results",
    "current_user",
    "history",
    "other",
    "request_framing",
)
_INSTRUCTION_KEYS = frozenset({"instructions", "system", "developer"})
_TOOL_SCHEMA_KEYS = frozenset({"tools", "functions"})
_CONVERSATION_KEYS = ("messages", "input")
_TOOL_RESULT_TYPES = frozenset(
    {
        "tool_result",
        "function_call_output",
        "computer_call_output",
        "mcp_call_output",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _role(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("role") or "").strip().lower()


def _type(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("type") or "").strip().lower()


def _is_tool_result(item: Any) -> bool:
    role = _role(item)
    item_type = _type(item)
    if role in {"tool", "function"} or item_type in _TOOL_RESULT_TYPES:
        return True
    if isinstance(item, dict):
        content = item.get("content")
        if isinstance(content, list):
            return any(_type(part) in _TOOL_RESULT_TYPES for part in content)
    return False


def _latest_user_index(items: list[Any]) -> int | None:
    for index in range(len(items) - 1, -1, -1):
        if _role(items[index]) == "user":
            return index
    return None


@dataclass(frozen=True)
class ComponentUsage:
    chars: int
    tokens: int
    exact: bool
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chars": self.chars,
            "tokens": self.tokens,
            "exact": self.exact,
            "source": self.source,
        }


@dataclass(frozen=True)
class AttributionSnapshot:
    total_chars: int
    total_tokens: int
    exact: bool
    tokenizer_backend: str
    model: str
    components: dict[str, ComponentUsage]

    @property
    def source(self) -> str:
        return "exact-tokenizer" if self.exact else "chars/4-fallback"

    def as_dict(self) -> dict[str, Any]:
        denominator = self.total_tokens or 0
        return {
            "total_chars": self.total_chars,
            "total_tokens": self.total_tokens,
            "exact": self.exact,
            "source": self.source,
            "tokenizer_backend": self.tokenizer_backend,
            "model": self.model,
            "components": {
                name: {
                    **usage.as_dict(),
                    "pct": round(usage.tokens / denominator * 100, 2)
                    if denominator
                    else 0.0,
                }
                for name, usage in self.components.items()
            },
        }


class RequestAttributor:
    """Partition a provider request into disjoint token-cost buckets.

    The attribution is diagnostic, not an acceptance gate. It intentionally
    counts the serialized payload nodes in each component and assigns remaining
    request-level JSON framing to ``request_framing``. When the active tokenizer
    is unavailable, every bucket is explicitly labelled as a chars/4 estimate.
    """

    def __init__(self, token_budget: TokenBudgetAdapter):
        self.token_budget = token_budget

    def _usage(self, values: list[Any], *, model: str) -> ComponentUsage:
        if not values:
            return ComponentUsage(0, 0, True, "empty")
        text = "\n".join(_serialize(value) for value in values)
        chars = len(text)
        measured = self.token_budget.measure_text(text, model=model)
        if measured.available:
            return ComponentUsage(
                chars=chars,
                tokens=int(measured.tokens or 0),
                exact=True,
                source=measured.backend,
            )
        return ComponentUsage(
            chars=chars,
            tokens=round(chars / 4),
            exact=False,
            source="chars/4-fallback",
        )

    def measure(self, request: Any, *, model: str = "") -> AttributionSnapshot:
        buckets: dict[str, list[Any]] = {
            name: [] for name in _COMPONENT_ORDER if name != "request_framing"
        }
        active_model = str(model or "")

        if isinstance(request, dict):
            request_model = request.get("model")
            if isinstance(request_model, str) and request_model:
                active_model = request_model

            handled_top: set[str] = set()
            for key in _INSTRUCTION_KEYS:
                if key in request:
                    buckets["instructions"].append({key: request[key]})
                    handled_top.add(key)
            for key in _TOOL_SCHEMA_KEYS:
                if key in request:
                    buckets["tool_schemas"].append({key: request[key]})
                    handled_top.add(key)

            for key in _CONVERSATION_KEYS:
                if key not in request:
                    continue
                value = request[key]
                handled_top.add(key)
                if isinstance(value, str):
                    if key == "input":
                        buckets["current_user"].append(value)
                    else:
                        buckets["history"].append(value)
                    continue
                if not isinstance(value, list):
                    buckets["other"].append({key: value})
                    continue
                latest_user = _latest_user_index(value)
                for index, item in enumerate(value):
                    role = _role(item)
                    if role in {"system", "developer"}:
                        buckets["instructions"].append(item)
                    elif _is_tool_result(item):
                        buckets["tool_results"].append(item)
                    elif latest_user is not None and index == latest_user:
                        buckets["current_user"].append(item)
                    else:
                        buckets["history"].append(item)

            for key, value in request.items():
                if key not in handled_top:
                    buckets["other"].append({key: value})
        else:
            buckets["other"].append(request)

        total_text = _serialize(request)
        total_chars = len(total_text)
        total_measurement = self.token_budget.measure_request(request, model=active_model)
        total_exact = total_measurement.available
        total_tokens = (
            int(total_measurement.tokens or 0)
            if total_exact
            else round(total_chars / 4)
        )

        components = {
            name: self._usage(values, model=active_model)
            for name, values in buckets.items()
        }
        attributed_chars = sum(item.chars for item in components.values())
        attributed_tokens = sum(item.tokens for item in components.values())
        framing_chars = max(0, total_chars - attributed_chars)
        all_exact = total_exact and all(item.exact for item in components.values())
        framing_tokens = (
            max(0, total_tokens - attributed_tokens)
            if all_exact
            else round(framing_chars / 4)
        )
        components["request_framing"] = ComponentUsage(
            chars=framing_chars,
            tokens=framing_tokens,
            exact=all_exact,
            source=total_measurement.backend if all_exact else "chars/4-fallback",
        )

        return AttributionSnapshot(
            total_chars=total_chars,
            total_tokens=total_tokens,
            exact=all_exact,
            tokenizer_backend=(
                total_measurement.backend if total_exact else "chars/4-fallback"
            ),
            model=active_model,
            components={name: components[name] for name in _COMPONENT_ORDER},
        )


class RequestAttributionAccounting:
    """Persist raw/final component attribution without storing prompt content."""

    def __init__(self, store: TokenTerminatorStore | None):
        self.store = store
        self.available = False
        self.error = ""
        if store is not None:
            self._initialize()

    def _initialize(self) -> None:
        assert self.store is not None
        try:
            with self.store.connection(write=True) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS request_component_metrics (
                        session_id TEXT NOT NULL DEFAULT '',
                        request_id TEXT NOT NULL DEFAULT '',
                        component TEXT NOT NULL,
                        raw_chars INTEGER NOT NULL,
                        final_chars INTEGER NOT NULL,
                        raw_tokens INTEGER NOT NULL,
                        final_tokens INTEGER NOT NULL,
                        raw_exact INTEGER NOT NULL,
                        final_exact INTEGER NOT NULL,
                        tokenizer_backend TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        measured_at TEXT NOT NULL,
                        PRIMARY KEY(session_id, request_id, component)
                    )
                    """
                )
            self.available = True
        except Exception as exc:  # noqa: BLE001 - diagnostics must fail open
            self.error = str(exc)

    def record(
        self,
        *,
        session_id: str,
        request_id: str,
        raw: AttributionSnapshot,
        final: AttributionSnapshot,
    ) -> bool:
        if not self.available or self.store is None:
            return False
        try:
            with self.store.connection(write=True) as conn:
                for component in _COMPONENT_ORDER:
                    raw_usage = raw.components[component]
                    final_usage = final.components[component]
                    conn.execute(
                        """
                        INSERT INTO request_component_metrics(
                            session_id, request_id, component,
                            raw_chars, final_chars, raw_tokens, final_tokens,
                            raw_exact, final_exact, tokenizer_backend, model,
                            measured_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, request_id, component) DO UPDATE SET
                            raw_chars=excluded.raw_chars,
                            final_chars=excluded.final_chars,
                            raw_tokens=excluded.raw_tokens,
                            final_tokens=excluded.final_tokens,
                            raw_exact=excluded.raw_exact,
                            final_exact=excluded.final_exact,
                            tokenizer_backend=excluded.tokenizer_backend,
                            model=excluded.model,
                            measured_at=excluded.measured_at
                        """,
                        (
                            str(session_id or ""),
                            str(request_id or ""),
                            component,
                            raw_usage.chars,
                            final_usage.chars,
                            raw_usage.tokens,
                            final_usage.tokens,
                            int(raw_usage.exact),
                            int(final_usage.exact),
                            final.tokenizer_backend or raw.tokenizer_backend,
                            final.model or raw.model,
                            _utc_now(),
                        ),
                    )
            return True
        except Exception as exc:  # noqa: BLE001 - diagnostics must fail open
            self.error = str(exc)
            return False

    def summary(self) -> dict[str, Any]:
        if not self.available or self.store is None:
            return {
                "available": False,
                "error": self.error or "request attribution unavailable",
                "requests": 0,
                "components": {},
            }
        try:
            with self.store.connection() as conn:
                requests = int(
                    conn.execute(
                        "SELECT COUNT(DISTINCT session_id || char(0) || request_id) "
                        "FROM request_component_metrics"
                    ).fetchone()[0]
                )
                rows = conn.execute(
                    """
                    SELECT component,
                           COALESCE(SUM(raw_chars), 0) AS raw_chars,
                           COALESCE(SUM(final_chars), 0) AS final_chars,
                           COALESCE(SUM(raw_tokens), 0) AS raw_tokens,
                           COALESCE(SUM(final_tokens), 0) AS final_tokens,
                           MIN(raw_exact) AS raw_exact,
                           MIN(final_exact) AS final_exact
                    FROM request_component_metrics
                    GROUP BY component
                    """
                ).fetchall()
        except Exception as exc:  # noqa: BLE001 - status must fail open
            self.error = str(exc)
            return {"available": False, "error": self.error, "requests": 0, "components": {}}

        total_raw_tokens = sum(int(row["raw_tokens"]) for row in rows)
        components: dict[str, Any] = {}
        for row in rows:
            raw_tokens = int(row["raw_tokens"])
            final_tokens = int(row["final_tokens"])
            components[str(row["component"])] = {
                "raw_chars": int(row["raw_chars"]),
                "final_chars": int(row["final_chars"]),
                "raw_tokens": raw_tokens,
                "final_tokens": final_tokens,
                "saved_tokens": raw_tokens - final_tokens,
                "raw_pct": round(raw_tokens / total_raw_tokens * 100, 2)
                if total_raw_tokens
                else 0.0,
                "exact": bool(row["raw_exact"] and row["final_exact"]),
            }
        return {
            "available": True,
            "error": self.error,
            "requests": requests,
            "components": {
                name: components[name]
                for name in _COMPONENT_ORDER
                if name in components
            },
        }
