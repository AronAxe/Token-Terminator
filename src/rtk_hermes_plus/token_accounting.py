from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .storage import TokenTerminatorStore
from .token_budget import TokenMeasurement


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequestTokenAccounting:
    """Persist tokenizer-measured end-to-end request savings in the main vault.

    Character metrics remain authoritative for fail-open reduction invariants.
    This table adds a tokenizer-measured view of the provider-bound payload so
    status/reporting can prefer real tokenizer deltas whenever a tokenizer is
    available and fall back explicitly when it is not.
    """

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
                    CREATE TABLE IF NOT EXISTS request_token_metrics (
                        session_id TEXT NOT NULL DEFAULT '',
                        request_id TEXT NOT NULL DEFAULT '',
                        model TEXT NOT NULL DEFAULT '',
                        tokenizer_backend TEXT NOT NULL DEFAULT '',
                        raw_tokens INTEGER NOT NULL,
                        final_tokens INTEGER NOT NULL,
                        saved_tokens INTEGER NOT NULL,
                        measured_at TEXT NOT NULL,
                        PRIMARY KEY(session_id, request_id)
                    )
                    """
                )
            self.available = True
        except Exception as exc:  # noqa: BLE001 - telemetry must fail open
            self.error = str(exc)

    def record(
        self,
        *,
        session_id: str,
        request_id: str,
        raw: TokenMeasurement,
        final: TokenMeasurement,
    ) -> bool:
        if (
            not self.available
            or self.store is None
            or not raw.available
            or not final.available
        ):
            return False
        raw_tokens = int(raw.tokens or 0)
        final_tokens = int(final.tokens or 0)
        if min(raw_tokens, final_tokens) < 0 or final_tokens > raw_tokens:
            return False
        backend = (
            raw.backend
            if raw.backend == final.backend
            else f"{raw.backend}|{final.backend}"
        )
        model = str(final.model or raw.model or "")
        try:
            with self.store.connection(write=True) as conn:
                conn.execute(
                    """
                    INSERT INTO request_token_metrics(
                        session_id, request_id, model, tokenizer_backend,
                        raw_tokens, final_tokens, saved_tokens, measured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, request_id) DO UPDATE SET
                        model=excluded.model,
                        tokenizer_backend=excluded.tokenizer_backend,
                        raw_tokens=excluded.raw_tokens,
                        final_tokens=excluded.final_tokens,
                        saved_tokens=excluded.saved_tokens,
                        measured_at=excluded.measured_at
                    """,
                    (
                        str(session_id or ""),
                        str(request_id or ""),
                        model,
                        backend,
                        raw_tokens,
                        final_tokens,
                        raw_tokens - final_tokens,
                        _utc_now(),
                    ),
                )
            return True
        except Exception as exc:  # noqa: BLE001 - telemetry must fail open
            self.error = str(exc)
            return False

    def summary(self) -> dict[str, Any]:
        if not self.available or self.store is None:
            return {
                "available": False,
                "error": self.error or "token accounting unavailable",
                "measured_requests": 0,
                "eligible_requests": 0,
                "coverage_pct": 0.0,
                "measured_raw_tokens": 0,
                "measured_final_tokens": 0,
                "measured_saved_tokens": 0,
                "fallback_saved_chars": 0,
                "fallback_estimated_saved_tokens": 0,
                "best_available_saved_tokens": 0,
                "source": "unavailable",
                "backends": [],
            }
        try:
            with self.store.connection() as conn:
                eligible = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM request_metrics "
                        "WHERE end_to_end_measured=1"
                    ).fetchone()[0]
                )
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n,
                           COALESCE(SUM(raw_tokens), 0) AS raw_tokens,
                           COALESCE(SUM(final_tokens), 0) AS final_tokens,
                           COALESCE(SUM(saved_tokens), 0) AS saved_tokens
                    FROM request_token_metrics
                    """
                ).fetchone()
                measured = int(row["n"])
                fallback_chars = int(
                    conn.execute(
                        """
                        SELECT COALESCE(SUM(r.end_to_end_saved_chars), 0)
                        FROM request_metrics r
                        LEFT JOIN request_token_metrics t
                          ON t.session_id=r.session_id AND t.request_id=r.request_id
                        WHERE r.end_to_end_measured=1 AND t.request_id IS NULL
                        """
                    ).fetchone()[0]
                )
                backends = [
                    str(item[0])
                    for item in conn.execute(
                        "SELECT DISTINCT tokenizer_backend "
                        "FROM request_token_metrics "
                        "WHERE tokenizer_backend != '' ORDER BY tokenizer_backend"
                    ).fetchall()
                ]
        except Exception as exc:  # noqa: BLE001 - status must fail open
            self.error = str(exc)
            return {
                "available": False,
                "error": self.error,
                "measured_requests": 0,
                "eligible_requests": 0,
                "coverage_pct": 0.0,
                "measured_raw_tokens": 0,
                "measured_final_tokens": 0,
                "measured_saved_tokens": 0,
                "fallback_saved_chars": 0,
                "fallback_estimated_saved_tokens": 0,
                "best_available_saved_tokens": 0,
                "source": "unavailable",
                "backends": [],
            }

        fallback_tokens = round(fallback_chars / 4)
        measured_saved = int(row["saved_tokens"])
        if eligible and measured >= eligible:
            source = "exact-tokenizer"
        elif measured:
            source = "mixed-exact-and-chars/4-fallback"
        else:
            source = "chars/4-fallback"
        return {
            "available": True,
            "error": self.error,
            "measured_requests": measured,
            "eligible_requests": eligible,
            "coverage_pct": round((measured / eligible * 100), 2) if eligible else 0.0,
            "measured_raw_tokens": int(row["raw_tokens"]),
            "measured_final_tokens": int(row["final_tokens"]),
            "measured_saved_tokens": measured_saved,
            "fallback_saved_chars": fallback_chars,
            "fallback_estimated_saved_tokens": fallback_tokens,
            "best_available_saved_tokens": measured_saved + fallback_tokens,
            "source": source,
            "backends": backends,
        }
