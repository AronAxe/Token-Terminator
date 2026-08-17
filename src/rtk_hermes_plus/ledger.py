from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import statistics
import threading
import time
import unicodedata
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)
TOTAL_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)
COUNT_FIELDS = (*TOKEN_FIELDS, "api_call_count", "tool_call_count")
COST_FIELDS = ("estimated_cost_usd", "actual_cost_usd")


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _snapshot(row: dict[str, Any] | None = None) -> dict[str, Any]:
    row = row or {}
    output: dict[str, Any] = {field: _integer(row.get(field)) for field in COUNT_FIELDS}
    output.update({field: _number(row.get(field)) for field in COST_FIELDS})
    output["accounting_available"] = bool(row.get("accounting_available", True))
    for field in (
        "model",
        "billing_provider",
        "billing_mode",
        "cost_status",
        "cost_source",
        "pricing_version",
    ):
        output[field] = str(row.get(field) or "")
    if output["cost_status"] == "included":
        output["actual_cost_usd"] = 0.0
    return output


class HermesAccounting:
    """Strictly read-only access to Hermes' canonical session accounting."""

    def __init__(self, state_db_path: Path):
        self.state_db_path = state_db_path

    def read(self, session_id: str) -> dict[str, Any]:
        if not session_id or not self.state_db_path.is_file():
            return _snapshot({"accounting_available": False})
        uri = f"file:{self.state_db_path.as_posix()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=2)) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """SELECT model, billing_provider, billing_mode,
                              input_tokens, output_tokens, cache_read_tokens,
                              cache_write_tokens, reasoning_tokens,
                              api_call_count, tool_call_count,
                              estimated_cost_usd, actual_cost_usd,
                              cost_status, cost_source, pricing_version
                       FROM sessions WHERE id = ?""",
                    (session_id,),
                ).fetchone()
        except (OSError, sqlite3.Error):
            return _snapshot({"accounting_available": False})
        return (
            _snapshot(dict(row))
            if row is not None
            else _snapshot({"accounting_available": False})
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    plugin_version TEXT NOT NULL,
    experiment TEXT NOT NULL,
    profile TEXT NOT NULL,
    tagged_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    finalized_at REAL,
    contaminated INTEGER NOT NULL DEFAULT 0,
    contamination_reason TEXT NOT NULL DEFAULT '',
    initial_model TEXT NOT NULL DEFAULT '',
    last_model TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    billing_mode TEXT NOT NULL DEFAULT '',
    cost_status TEXT NOT NULL DEFAULT '',
    cost_source TEXT NOT NULL DEFAULT '',
    pricing_version TEXT NOT NULL DEFAULT '',
    baseline_input_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_output_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_api_call_count INTEGER NOT NULL DEFAULT 0,
    baseline_tool_call_count INTEGER NOT NULL DEFAULT 0,
    baseline_estimated_cost_usd REAL,
    baseline_actual_cost_usd REAL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    api_call_count INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    api_equivalent_cost_usd REAL,
    equivalent_rate_card TEXT NOT NULL DEFAULT '',
    turn_count INTEGER NOT NULL DEFAULT 0,
    completed_turns INTEGER NOT NULL DEFAULT 0,
    failed_turns INTEGER NOT NULL DEFAULT 0,
    interrupted_turns INTEGER NOT NULL DEFAULT 0,
    native_raw_chars INTEGER NOT NULL DEFAULT 0,
    native_output_chars INTEGER NOT NULL DEFAULT 0,
    native_compressions INTEGER NOT NULL DEFAULT 0,
    rewrite_count INTEGER NOT NULL DEFAULT 0,
    recovery_reads INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    prompt_fingerprint TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL,
    ended_at REAL,
    baseline_input_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_output_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    baseline_api_call_count INTEGER NOT NULL DEFAULT 0,
    baseline_tool_call_count INTEGER NOT NULL DEFAULT 0,
    baseline_estimated_cost_usd REAL,
    baseline_actual_cost_usd REAL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    api_call_count INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    api_equivalent_cost_usd REAL,
    completed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    interrupted INTEGER NOT NULL DEFAULT 0,
    turn_exit_reason TEXT NOT NULL DEFAULT '',
    native_raw_chars INTEGER NOT NULL DEFAULT 0,
    native_output_chars INTEGER NOT NULL DEFAULT 0,
    native_compressions INTEGER NOT NULL DEFAULT 0,
    rewrite_count INTEGER NOT NULL DEFAULT 0,
    recovery_reads INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, turn_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_experiment_mode
    ON sessions(experiment, mode, contaminated);
CREATE INDEX IF NOT EXISTS idx_turns_fingerprint
    ON turns(prompt_fingerprint, mode, model);
"""


class ExperimentLedger:
    """Private, content-free, durable RTK mode experiment ledger."""

    def __init__(
        self,
        path: Path,
        state_db_path: Path,
        *,
        plugin_version: str,
        experiment: str = "default",
        profile: str = "default",
        session_reader: Callable[[str], dict[str, Any]] | None = None,
        equivalent_rates: dict[str, float] | None = None,
        equivalent_rate_card: str = "",
        enabled: bool = True,
    ):
        self.path = path
        self.plugin_version = plugin_version
        self.experiment = experiment or "default"
        self.profile = profile or "default"
        self._reader = session_reader or HermesAccounting(state_db_path).read
        self._equivalent_rates = {
            key: max(0.0, float(value))
            for key, value in (equivalent_rates or {}).items()
            if float(value) > 0
        }
        self._equivalent_rate_card = (
            equivalent_rate_card if self._equivalent_rates else ""
        )
        self._lock = threading.RLock()
        self.available = False
        self.error = ""
        self._salt = ""
        if enabled:
            self._initialize()

    def _initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                self.path.parent.chmod(0o700)
            except OSError:
                pass
            with closing(self._connect()) as connection, connection:
                connection.executescript(SCHEMA)
                row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'fingerprint_salt'"
                ).fetchone()
                if row is None:
                    self._salt = secrets.token_hex(32)
                    connection.execute(
                        "INSERT INTO meta(key, value) VALUES('fingerprint_salt', ?)",
                        (self._salt,),
                    )
                else:
                    self._salt = str(row[0])
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            self.available = True
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _read(self, session_id: str) -> dict[str, Any]:
        try:
            return _snapshot(self._reader(session_id))
        except Exception:  # noqa: BLE001 - host accounting must fail open
            return _snapshot({"accounting_available": False})

    def _fingerprint(self, user_message: Any) -> str:
        text = _message_text(user_message)
        if not text:
            return ""
        normalized = " ".join(unicodedata.normalize("NFKC", text).split())
        material = f"{self._salt}\0{normalized}".encode("utf-8", errors="replace")
        return hashlib.sha256(material).hexdigest()

    def ensure_session(self, session_id: str, mode: str) -> str:
        if not self.available or not session_id:
            return mode
        current = self._read(session_id)
        now = time.time()
        columns = [current[field] for field in COUNT_FIELDS] + [
            current[field] for field in COST_FIELDS
        ]
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO sessions(
                           session_id, mode, plugin_version, experiment, profile,
                           tagged_at, last_seen_at, initial_model, last_model,
                           provider, billing_mode, cost_status, cost_source,
                           pricing_version,
                           baseline_input_tokens, baseline_output_tokens,
                           baseline_cache_read_tokens,
                           baseline_cache_write_tokens,
                           baseline_reasoning_tokens, baseline_api_call_count,
                           baseline_tool_call_count,
                           baseline_estimated_cost_usd,
                           baseline_actual_cost_usd)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        mode,
                        self.plugin_version,
                        self.experiment,
                        self.profile,
                        now,
                        now,
                        current["model"],
                        current["model"],
                        current["billing_provider"],
                        current["billing_mode"],
                        current["cost_status"],
                        current["cost_source"],
                        current["pricing_version"],
                        *columns,
                    ),
                )
                row = connection.execute(
                    "SELECT mode FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                stored_mode = str(row["mode"]) if row is not None else mode
                contamination = ""
                if not current["accounting_available"]:
                    contamination = "accounting unavailable"
                elif stored_mode != mode:
                    contamination = f"runtime mode changed from {stored_mode} to {mode}"
                connection.execute(
                    """UPDATE sessions SET last_seen_at = ?, last_model = ?,
                              provider = COALESCE(NULLIF(?, ''), provider),
                              billing_mode = COALESCE(NULLIF(?, ''), billing_mode),
                              contaminated = CASE WHEN ? != '' THEN 1 ELSE contaminated END,
                              contamination_reason = CASE WHEN ? != '' THEN ?
                                                         ELSE contamination_reason END
                       WHERE session_id = ?""",
                    (
                        now,
                        current["model"],
                        current["billing_provider"],
                        current["billing_mode"],
                        contamination,
                        contamination,
                        contamination,
                        session_id,
                    ),
                )
                self._sync_session(connection, session_id, current)
            return stored_mode
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)
            return mode

    def start_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        task_id: str,
        mode: str,
        user_message: Any,
        model: str = "",
        platform: str = "",
    ) -> None:
        if not self.available or not session_id or not turn_id:
            return
        self.ensure_session(session_id, mode)
        current = self._read(session_id)
        columns = [current[field] for field in COUNT_FIELDS] + [
            current[field] for field in COST_FIELDS
        ]
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                connection.execute(
                    """INSERT OR IGNORE INTO turns(
                           session_id, turn_id, task_id, prompt_fingerprint,
                           mode, model, provider, platform, started_at,
                           baseline_input_tokens, baseline_output_tokens,
                           baseline_cache_read_tokens,
                           baseline_cache_write_tokens,
                           baseline_reasoning_tokens, baseline_api_call_count,
                           baseline_tool_call_count,
                           baseline_estimated_cost_usd,
                           baseline_actual_cost_usd)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        turn_id,
                        task_id or "",
                        self._fingerprint(user_message),
                        mode,
                        model or current["model"],
                        current["billing_provider"],
                        platform or "",
                        time.time(),
                        *columns,
                    ),
                )
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)

    def finish_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        mode: str,
        completed: bool,
        failed: bool,
        interrupted: bool,
        turn_exit_reason: str = "",
    ) -> None:
        if not self.available or not session_id:
            return
        self.ensure_session(session_id, mode)
        current = self._read(session_id)
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                row = connection.execute(
                    "SELECT * FROM turns WHERE session_id = ? AND turn_id = ?",
                    (session_id, turn_id),
                ).fetchone()
                first_finish = row is not None and row["ended_at"] is None
                if row is not None:
                    values = _deltas(dict(row), current)
                    equivalent_cost = self._equivalent_cost(values)
                    connection.execute(
                        """UPDATE turns SET ended_at = ?, input_tokens = ?,
                                  output_tokens = ?, cache_read_tokens = ?,
                                  cache_write_tokens = ?, reasoning_tokens = ?,
                                  api_call_count = ?, tool_call_count = ?,
                                  estimated_cost_usd = ?, actual_cost_usd = ?,
                                  api_equivalent_cost_usd = ?,
                                  completed = ?, failed = ?, interrupted = ?,
                                  turn_exit_reason = ?
                           WHERE session_id = ? AND turn_id = ?""",
                        (
                            time.time(),
                            *[values[field] for field in COUNT_FIELDS],
                            values["estimated_cost_usd"],
                            values["actual_cost_usd"],
                            equivalent_cost,
                            int(bool(completed)),
                            int(bool(failed)),
                            int(bool(interrupted)),
                            str(turn_exit_reason or "")[:240],
                            session_id,
                            turn_id,
                        ),
                    )
                if first_finish:
                    connection.execute(
                        """UPDATE sessions SET
                                  turn_count = turn_count + 1,
                                  completed_turns = completed_turns + ?,
                                  failed_turns = failed_turns + ?,
                                  interrupted_turns = interrupted_turns + ?
                           WHERE session_id = ?""",
                        (
                            int(bool(completed)),
                            int(bool(failed)),
                            int(bool(interrupted)),
                            session_id,
                        ),
                    )
                self._sync_session(connection, session_id, current)
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)

    def finalize_session(self, session_id: str, mode: str) -> None:
        if not self.available or not session_id:
            return
        self.ensure_session(session_id, mode)
        current = self._read(session_id)
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                self._sync_session(connection, session_id, current)
                connection.execute(
                    "UPDATE sessions SET finalized_at = COALESCE(finalized_at, ?) "
                    "WHERE session_id = ?",
                    (time.time(), session_id),
                )
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)

    def record_native(
        self,
        *,
        session_id: str,
        turn_id: str,
        raw_chars: int,
        output_chars: int,
    ) -> None:
        self._record_effect(
            session_id,
            turn_id,
            native_raw_chars=max(0, raw_chars),
            native_output_chars=max(0, output_chars),
            native_compressions=1,
        )

    def record_rewrite(self, *, session_id: str, turn_id: str) -> None:
        self._record_effect(session_id, turn_id, rewrite_count=1)

    def record_recovery_read(self, *, session_id: str, turn_id: str) -> None:
        self._record_effect(session_id, turn_id, recovery_reads=1)

    def _record_effect(self, session_id: str, turn_id: str, **amounts: int) -> None:
        if not self.available or not session_id or not amounts:
            return
        allowed = {
            "native_raw_chars",
            "native_output_chars",
            "native_compressions",
            "rewrite_count",
            "recovery_reads",
        }
        values = {
            key: max(0, int(value)) for key, value in amounts.items() if key in allowed
        }
        if not values:
            return
        assignment = ", ".join(f"{key} = {key} + ?" for key in values)
        params = list(values.values())
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                connection.execute(
                    f"UPDATE sessions SET {assignment}, last_seen_at = ? WHERE session_id = ?",
                    (*params, time.time(), session_id),
                )
                if turn_id:
                    connection.execute(
                        f"UPDATE turns SET {assignment} WHERE session_id = ? AND turn_id = ?",
                        (*params, session_id, turn_id),
                    )
        except (OSError, sqlite3.Error) as exc:
            self.error = str(exc)

    def _sync_session(
        self, connection: sqlite3.Connection, session_id: str, current: dict[str, Any]
    ) -> None:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return
        values = _deltas(dict(row), current)
        equivalent_cost = self._equivalent_cost(values)
        initial_model = str(row["initial_model"] or "")
        current_model = current["model"]
        route_changed = bool(
            initial_model and current_model and initial_model != current_model
        )
        accounting_unavailable = not current["accounting_available"]
        connection.execute(
            """UPDATE sessions SET last_seen_at = ?, last_model = ?,
                      initial_model = COALESCE(NULLIF(initial_model, ''), ?),
                      provider = COALESCE(NULLIF(?, ''), provider),
                      billing_mode = COALESCE(NULLIF(?, ''), billing_mode),
                      cost_status = COALESCE(NULLIF(?, ''), cost_status),
                      cost_source = COALESCE(NULLIF(?, ''), cost_source),
                      pricing_version = COALESCE(NULLIF(?, ''), pricing_version),
                      input_tokens = ?, output_tokens = ?,
                      cache_read_tokens = ?, cache_write_tokens = ?,
                      reasoning_tokens = ?, api_call_count = ?,
                      tool_call_count = ?, estimated_cost_usd = ?,
                      actual_cost_usd = ?, api_equivalent_cost_usd = ?,
                      equivalent_rate_card = ?,
                      contaminated = CASE WHEN ? OR ? THEN 1 ELSE contaminated END,
                      contamination_reason = CASE
                          WHEN ? THEN 'accounting unavailable'
                          WHEN ? THEN 'model changed within session'
                          ELSE contamination_reason END
               WHERE session_id = ?""",
            (
                time.time(),
                current_model,
                current_model,
                current["billing_provider"],
                current["billing_mode"],
                current["cost_status"],
                current["cost_source"],
                current["pricing_version"],
                *[values[field] for field in COUNT_FIELDS],
                values["estimated_cost_usd"],
                values["actual_cost_usd"],
                equivalent_cost,
                self._equivalent_rate_card,
                accounting_unavailable,
                route_changed,
                accounting_unavailable,
                route_changed,
                session_id,
            ),
        )

    def _equivalent_cost(self, values: dict[str, Any]) -> float | None:
        if not self._equivalent_rates:
            return None
        weighted = (
            values["input_tokens"] * self._equivalent_rates.get("input", 0.0)
            + values["output_tokens"] * self._equivalent_rates.get("output", 0.0)
            + values["cache_read_tokens"]
            * self._equivalent_rates.get("cache_read", 0.0)
            + values["cache_write_tokens"]
            * self._equivalent_rates.get("cache_write", 0.0)
        )
        return round(weighted / 1_000_000, 10)

    def compare(
        self, modes: tuple[str, str] = ("native", "balanced")
    ) -> dict[str, Any]:
        first, second = modes
        result: dict[str, Any] = {
            "experiment": self.experiment,
            "modes": {},
            "delta": {"direction": f"{second} minus {first}"},
            "matched_turns": {"pairs": 0},
            "excluded_contaminated_sessions": 0,
        }
        if not self.available:
            result["error"] = self.error or "experiment ledger disabled"
            return result
        try:
            with self._lock, closing(self._connect()) as connection, connection:
                excluded = connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE experiment = ? AND contaminated = 1",
                    (self.experiment,),
                ).fetchone()[0]
                result["excluded_contaminated_sessions"] = int(excluded)
                rows_by_mode: dict[str, list[dict[str, Any]]] = {}
                for mode in modes:
                    rows = connection.execute(
                        """SELECT * FROM sessions
                           WHERE experiment = ? AND mode = ? AND contaminated = 0
                             AND turn_count > 0
                           ORDER BY tagged_at""",
                        (self.experiment, mode),
                    ).fetchall()
                    prepared = [_comparison_row(dict(row)) for row in rows]
                    rows_by_mode[mode] = prepared
                    result["modes"][mode] = _summary(prepared)
                result["delta"].update(
                    _summary_delta(
                        result["modes"].get(first), result["modes"].get(second)
                    )
                )
                result["matched_turns"] = self._matched_turns(connection, modes)
        except (OSError, sqlite3.Error) as exc:
            result["error"] = str(exc)
        result["notes"] = [
            "Actual, Hermes-estimated, and optional API-equivalent cost are separate fields.",
            "Included/OAuth routes count as $0 actual marginal cost.",
            "Prompt fingerprints are salted local hashes; prompt content is never stored.",
            "Matched deltas require the same prompt fingerprint and model in both modes.",
        ]
        return result

    def _matched_turns(
        self, connection: sqlite3.Connection, modes: tuple[str, str]
    ) -> dict[str, Any]:
        first, second = modes
        rows = connection.execute(
            """SELECT t.* FROM turns t
               JOIN sessions s ON s.session_id = t.session_id
               WHERE s.experiment = ? AND s.contaminated = 0
                 AND t.ended_at IS NOT NULL AND t.completed = 1
                 AND t.prompt_fingerprint != '' AND t.mode IN (?, ?)
               ORDER BY t.started_at""",
            (self.experiment, first, second),
        ).fetchall()
        buckets: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
        for raw in rows:
            row = _comparison_row(dict(raw))
            key = (str(raw["prompt_fingerprint"]), str(raw["model"] or ""))
            buckets.setdefault(key, {first: [], second: []})[str(raw["mode"])].append(
                row
            )
        pairs = []
        for group in buckets.values():
            pairs.extend(zip(group[first], group[second]))
        token_deltas = [b["total_tokens"] - a["total_tokens"] for a, b in pairs]
        estimated_deltas = [
            b["estimated_cost_usd"] - a["estimated_cost_usd"]
            for a, b in pairs
            if a["estimated_cost_usd"] is not None
            and b["estimated_cost_usd"] is not None
        ]
        actual_deltas = [
            b["actual_cost_usd"] - a["actual_cost_usd"]
            for a, b in pairs
            if a["actual_cost_usd"] is not None and b["actual_cost_usd"] is not None
        ]
        equivalent_deltas = [
            b["api_equivalent_cost_usd"] - a["api_equivalent_cost_usd"]
            for a, b in pairs
            if a["api_equivalent_cost_usd"] is not None
            and b["api_equivalent_cost_usd"] is not None
        ]
        return {
            "pairs": len(pairs),
            "direction": f"{second} minus {first}",
            "mean_total_tokens_delta": _mean(token_deltas),
            "median_total_tokens_delta": _median(token_deltas),
            "mean_estimated_cost_usd_delta": _mean(estimated_deltas),
            "median_estimated_cost_usd_delta": _median(estimated_deltas),
            "mean_actual_cost_usd_delta": _mean(actual_deltas),
            "median_actual_cost_usd_delta": _median(actual_deltas),
            "mean_api_equivalent_cost_usd_delta": _mean(equivalent_deltas),
            "median_api_equivalent_cost_usd_delta": _median(equivalent_deltas),
        }


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_message_text(value.get(key)) for key in ("text", "content"))
    if isinstance(value, (list, tuple)):
        return " ".join(_message_text(item) for item in value)
    return ""


def _deltas(baseline_row: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in COUNT_FIELDS:
        output[field] = max(
            0,
            _integer(current.get(field))
            - _integer(baseline_row.get(f"baseline_{field}")),
        )
    for field in COST_FIELDS:
        now = _number(current.get(field))
        baseline = _number(baseline_row.get(f"baseline_{field}"))
        output[field] = None if now is None else max(0.0, now - (baseline or 0.0))
    if current.get("cost_status") == "included":
        output["actual_cost_usd"] = 0.0
    return output


def _comparison_row(row: dict[str, Any]) -> dict[str, Any]:
    output = {field: _integer(row.get(field)) for field in COUNT_FIELDS}
    # Provider reasoning tokens are reported as a detail bucket inside output
    # tokens. Keep the detail visible, but do not count it a second time.
    output["total_tokens"] = sum(output[field] for field in TOTAL_TOKEN_FIELDS)
    output["estimated_cost_usd"] = _number(row.get("estimated_cost_usd"))
    output["actual_cost_usd"] = _number(row.get("actual_cost_usd"))
    output["api_equivalent_cost_usd"] = _number(row.get("api_equivalent_cost_usd"))
    output["completed"] = _integer(row.get("completed", row.get("completed_turns")))
    output["failed"] = _integer(row.get("failed", row.get("failed_turns")))
    output["interrupted"] = _integer(
        row.get("interrupted", row.get("interrupted_turns"))
    )
    output["native_raw_chars"] = _integer(row.get("native_raw_chars"))
    output["native_output_chars"] = _integer(row.get("native_output_chars"))
    output["native_compressions"] = _integer(row.get("native_compressions"))
    output["rewrite_count"] = _integer(row.get("rewrite_count"))
    output["recovery_reads"] = _integer(row.get("recovery_reads"))
    return output


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    token_values = [row["total_tokens"] for row in rows]
    estimated = [
        row["estimated_cost_usd"]
        for row in rows
        if row["estimated_cost_usd"] is not None
    ]
    actual = [
        row["actual_cost_usd"] for row in rows if row["actual_cost_usd"] is not None
    ]
    equivalent = [
        row["api_equivalent_cost_usd"]
        for row in rows
        if row["api_equivalent_cost_usd"] is not None
    ]
    raw_chars = sum(row["native_raw_chars"] for row in rows)
    output_chars = sum(row["native_output_chars"] for row in rows)
    saved_chars = max(0, raw_chars - output_chars)
    return {
        "sessions": len(rows),
        "token_coverage": len(rows),
        "mean_total_tokens": _mean(token_values),
        "median_total_tokens": _median(token_values),
        "mean_estimated_cost_usd": _mean(estimated),
        "median_estimated_cost_usd": _median(estimated),
        "estimated_cost_coverage": len(estimated),
        "mean_actual_cost_usd": _mean(actual),
        "median_actual_cost_usd": _median(actual),
        "actual_cost_coverage": len(actual),
        "mean_api_equivalent_cost_usd": _mean(equivalent),
        "median_api_equivalent_cost_usd": _median(equivalent),
        "api_equivalent_cost_coverage": len(equivalent),
        "completed_turns": sum(row["completed"] for row in rows),
        "failed_turns": sum(row["failed"] for row in rows),
        "interrupted_turns": sum(row["interrupted"] for row in rows),
        "native_compressions": sum(row["native_compressions"] for row in rows),
        "native_raw_chars": raw_chars,
        "native_output_chars": output_chars,
        "native_saved_chars": saved_chars,
        "native_estimated_tokens_saved": round(saved_chars / 4),
        "native_savings_pct": (
            round(saved_chars / raw_chars * 100, 1) if raw_chars else 0.0
        ),
        "rewrite_count": sum(row["rewrite_count"] for row in rows),
        "recovery_reads": sum(row["recovery_reads"] for row in rows),
    }


def _summary_delta(
    first: dict[str, Any] | None, second: dict[str, Any] | None
) -> dict[str, Any]:
    if (
        not first
        or not second
        or not first.get("sessions")
        or not second.get("sessions")
    ):
        return {"available": False}
    output: dict[str, Any] = {"available": True}
    for field in (
        "mean_total_tokens",
        "median_total_tokens",
        "mean_estimated_cost_usd",
        "median_estimated_cost_usd",
        "mean_actual_cost_usd",
        "median_actual_cost_usd",
        "mean_api_equivalent_cost_usd",
        "median_api_equivalent_cost_usd",
    ):
        a, b = first.get(field), second.get(field)
        output[field + "_delta"] = None if a is None or b is None else round(b - a, 8)
    return output


def _mean(values: list[int | float]) -> float | None:
    return round(float(statistics.fmean(values)), 4) if values else None


def _median(values: list[int | float]) -> float | None:
    return round(float(statistics.median(values)), 4) if values else None


def dump_compare(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
