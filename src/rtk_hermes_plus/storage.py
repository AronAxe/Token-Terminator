from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


# Additive telemetry columns deliberately remain within schema version 2. Older
# 0.3.0 code names every column it writes, so it safely ignores these defaulted
# columns. Keeping user_version=2 makes package rollback possible without also
# requiring a destructive database downgrade.
_END_TO_END_COLUMNS = (
    "final_chars",
    "compactor_saved_chars",
    "end_to_end_saved_chars",
    "vaulted_results",
    "collapsed_turns",
    "compactor_failed_open",
    "end_to_end_measured",
)


@dataclass(frozen=True)
class ArtifactPut:
    artifact_id: str
    created: bool
    sha256: str


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    sha256: str
    content: str
    char_count: int
    byte_count: int
    tool_name: str
    args: dict[str, Any]
    created_at: str
    observation_count: int


@dataclass(frozen=True)
class ArtifactSummary:
    artifact_id: str
    sha256: str
    char_count: int
    byte_count: int
    tool_name: str
    created_at: str
    observation_count: int


class VaultCapacityError(RuntimeError):
    """The configured private artifact-vault capacity would be exceeded."""


class TokenTerminatorStore:
    """Private SQLite vault for artifacts, working state, leases, and metrics.

    Connections are short-lived and transactions use ``BEGIN IMMEDIATE`` for
    deterministic write serialization across Hermes tool workers.
    """

    SCHEMA_VERSION = 2

    def __init__(
        self,
        path: str | Path,
        *,
        max_artifact_chars: int = 2_000_000,
        max_vault_bytes: int = 536_870_912,
        max_page_chars: int = 20_000,
    ):
        self.path = Path(path).expanduser()
        self.max_artifact_chars = max(1, int(max_artifact_chars))
        self.max_vault_bytes = max(1, int(max_vault_bytes))
        self.max_page_chars = max(1, int(max_page_chars))
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix":
            os.chmod(self.path.parent, 0o700)
        self._initialize()
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self._new_connection()
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connection(write=True) as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {version} is newer than supported {self.SCHEMA_VERSION}"
                )
            # sqlite3.executescript() commits a pending transaction before it
            # runs. Execute this static DDL one statement at a time so schema
            # creation and migration remain inside BEGIN IMMEDIATE.
            schema_sql = """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    char_count INTEGER NOT NULL,
                    byte_count INTEGER NOT NULL,
                    tool_name TEXT NOT NULL DEFAULT '',
                    args_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifact_observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                    session_id TEXT NOT NULL DEFAULT '',
                    tool_call_id TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL DEFAULT '',
                    args_json TEXT NOT NULL DEFAULT '{}',
                    observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifact_observations_artifact
                    ON artifact_observations(artifact_id);

                CREATE TABLE IF NOT EXISTS artifact_exposures (
                    session_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                    request_id TEXT NOT NULL,
                    inline INTEGER NOT NULL CHECK(inline IN (0, 1)),
                    exposed_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, artifact_id, request_id)
                );

                CREATE TABLE IF NOT EXISTS graph_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL DEFAULT '',
                    op TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence REAL,
                    priority REAL,
                    uncertainty REAL,
                    activation REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_seq INTEGER NOT NULL,
                    updated_seq INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    confidence REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_seq INTEGER NOT NULL,
                    updated_seq INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS request_metrics (
                    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL DEFAULT '',
                    request_mode TEXT NOT NULL,
                    raw_chars INTEGER NOT NULL,
                    compiled_chars INTEGER NOT NULL,
                    saved_chars INTEGER NOT NULL,
                    artifact_count INTEGER NOT NULL,
                    receipts INTEGER NOT NULL,
                    duplicates_collapsed INTEGER NOT NULL,
                    tool_schema_chars INTEGER NOT NULL,
                    failed_open INTEGER NOT NULL CHECK(failed_open IN (0, 1)),
                    created_at TEXT NOT NULL,
                    final_chars INTEGER NOT NULL DEFAULT 0,
                    compactor_saved_chars INTEGER NOT NULL DEFAULT 0,
                    end_to_end_saved_chars INTEGER NOT NULL DEFAULT 0,
                    vaulted_results INTEGER NOT NULL DEFAULT 0,
                    collapsed_turns INTEGER NOT NULL DEFAULT 0,
                    compactor_failed_open INTEGER NOT NULL DEFAULT 0,
                    end_to_end_measured INTEGER NOT NULL DEFAULT 0
                );
                """
            for statement in schema_sql.split(";"):
                if statement.strip():
                    conn.execute(statement)
            if version < self.SCHEMA_VERSION:
                observation_columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(artifact_observations)")
                }
                if "tool_name" not in observation_columns:
                    conn.execute(
                        "ALTER TABLE artifact_observations ADD COLUMN tool_name TEXT NOT NULL DEFAULT ''"
                    )
                if "args_json" not in observation_columns:
                    conn.execute(
                        "ALTER TABLE artifact_observations ADD COLUMN args_json TEXT NOT NULL DEFAULT '{}'"
                    )
                conn.execute(
                    """
                    DELETE FROM artifact_observations
                    WHERE observation_id NOT IN (
                        SELECT MIN(observation_id) FROM artifact_observations
                        GROUP BY artifact_id, session_id, tool_call_id, tool_name, args_json
                    )
                    """
                )
                conn.execute("DROP INDEX IF EXISTS idx_artifact_observation_identity")
                conn.execute(
                    """
                    CREATE UNIQUE INDEX idx_artifact_observation_identity
                    ON artifact_observations(
                        artifact_id, session_id, tool_call_id, tool_name, args_json
                    )
                    """
                )
                conn.execute(
                    """
                    DELETE FROM request_metrics
                    WHERE metric_id NOT IN (
                        SELECT MAX(metric_id) FROM request_metrics GROUP BY session_id, request_id
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_request_metric_identity
                    ON request_metrics(session_id, request_id)
                    """
                )
                conn.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")

            # Compatibility-preserving additive migration for existing schema-2
            # databases. Legacy rows stay explicitly unmeasured; legacy code can
            # continue opening the database because user_version remains 2.
            metric_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(request_metrics)")
            }
            for column in _END_TO_END_COLUMNS:
                if column not in metric_columns:
                    conn.execute(
                        f"ALTER TABLE request_metrics "
                        f"ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                    )
            # The original 0.3.0 writer only updates legacy columns. If it
            # touches a row measured by this release, invalidate the newer
            # fields rather than retaining telemetry that no longer describes
            # the legacy values. The current writer restores a fresh final
            # measurement later in the same transaction.
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS invalidate_request_metric_end_to_end
                AFTER UPDATE OF
                    request_mode, raw_chars, compiled_chars, saved_chars,
                    artifact_count, receipts, duplicates_collapsed,
                    tool_schema_chars, failed_open, created_at
                ON request_metrics
                WHEN OLD.end_to_end_measured = 1
                BEGIN
                    UPDATE request_metrics SET
                        final_chars = 0,
                        compactor_saved_chars = 0,
                        end_to_end_saved_chars = 0,
                        vaulted_results = 0,
                        collapsed_turns = 0,
                        compactor_failed_open = 0,
                        end_to_end_measured = 0
                    WHERE metric_id = NEW.metric_id;
                END
                """
            )

    @staticmethod
    def _artifact_id(sha256: str) -> str:
        return f"a_{sha256[:32]}"

    def put_artifact(
        self,
        content: str,
        *,
        tool_name: str = "",
        args: dict[str, Any] | None = None,
        session_id: str = "",
        tool_call_id: str = "",
    ) -> ArtifactPut:
        if not isinstance(content, str):
            raise TypeError("artifact content must be a string")
        if len(content) > self.max_artifact_chars:
            raise VaultCapacityError(
                f"artifact has {len(content)} characters; limit is {self.max_artifact_chars}"
            )
        encoded = content.encode("utf-8")
        sha256 = hashlib.sha256(encoded).hexdigest()
        artifact_id = self._artifact_id(sha256)
        now = _utc_now()
        with self.connection(write=True) as conn:
            collision = conn.execute(
                "SELECT sha256 FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if collision is not None and collision["sha256"] != sha256:
                artifact_id = f"a_{sha256}"
            existing = conn.execute(
                "SELECT artifact_id FROM artifacts WHERE sha256=?", (sha256,)
            ).fetchone()
            created = existing is None
            if existing is None:
                current_bytes = int(
                    conn.execute(
                        "SELECT COALESCE(SUM(byte_count), 0) FROM artifacts"
                    ).fetchone()[0]
                )
                if current_bytes + len(encoded) > self.max_vault_bytes:
                    raise VaultCapacityError(
                        f"artifact vault capacity would exceed {self.max_vault_bytes} bytes"
                    )
                conn.execute(
                    """
                    INSERT INTO artifacts(
                        artifact_id, sha256, content, char_count, byte_count,
                        tool_name, args_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        sha256,
                        content,
                        len(content),
                        len(encoded),
                        str(tool_name or ""),
                        _json(args or {}),
                        now,
                    ),
                )
            else:
                artifact_id = existing["artifact_id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO artifact_observations(
                    artifact_id, session_id, tool_call_id, tool_name, args_json, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    str(session_id or ""),
                    str(tool_call_id or ""),
                    str(tool_name or ""),
                    _json(args or {}),
                    now,
                ),
            )
        return ArtifactPut(artifact_id=artifact_id, created=created, sha256=sha256)

    def get_artifact(self, artifact_id: str) -> Artifact:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT a.*,
                       (SELECT COUNT(*) FROM artifact_observations o
                        WHERE o.artifact_id=a.artifact_id) AS observation_count
                FROM artifacts a WHERE a.artifact_id=?
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown artifact: {artifact_id}")
        return Artifact(
            artifact_id=row["artifact_id"],
            sha256=row["sha256"],
            content=row["content"],
            char_count=row["char_count"],
            byte_count=row["byte_count"],
            tool_name=row["tool_name"],
            args=json.loads(row["args_json"]),
            created_at=row["created_at"],
            observation_count=row["observation_count"],
        )

    def read_artifact(
        self, artifact_id: str, *, offset: int = 0, limit: int = 20_000
    ) -> dict:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be non-negative and limit must be positive")
        limit = min(int(limit), self.max_page_chars)
        artifact = self.get_artifact(artifact_id)
        content = artifact.content[offset : offset + limit]
        next_offset = offset + len(content)
        return {
            "artifact_id": artifact.artifact_id,
            "content": content,
            "offset": offset,
            "next_offset": next_offset if next_offset < artifact.char_count else None,
            "total_chars": artifact.char_count,
            "sha256": artifact.sha256,
            "tool_name": artifact.tool_name,
        }

    def search_artifacts(self, query: str, *, limit: int = 10) -> list[ArtifactSummary]:
        limit = max(1, min(int(limit), 500))
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT a.artifact_id, a.sha256, a.char_count, a.byte_count,
                       a.tool_name, a.created_at,
                       COUNT(o.observation_id) AS observation_count
                FROM artifacts a
                LEFT JOIN artifact_observations o ON o.artifact_id=a.artifact_id
                WHERE instr(lower(a.content), ?) > 0
                   OR instr(lower(a.tool_name), ?) > 0
                   OR EXISTS (
                       SELECT 1 FROM artifact_observations matched
                       WHERE matched.artifact_id=a.artifact_id
                         AND instr(lower(matched.tool_name), ?) > 0
                   )
                GROUP BY a.artifact_id
                ORDER BY a.created_at DESC, a.artifact_id
                LIMIT ?
                """,
                (needle, needle, needle, limit),
            ).fetchall()
        return [
            ArtifactSummary(
                artifact_id=row["artifact_id"],
                sha256=row["sha256"],
                char_count=row["char_count"],
                byte_count=row["byte_count"],
                tool_name=row["tool_name"],
                created_at=row["created_at"],
                observation_count=row["observation_count"],
            )
            for row in rows
        ]

    def claim_exposure(
        self,
        *,
        session_id: str,
        artifact_id: str,
        request_id: str,
        inline_limit: int,
    ) -> bool:
        """Idempotently decide whether an artifact is inline for this request."""
        session_id = str(session_id or "")
        request_id = str(request_id or "")
        with self.connection(write=True) as conn:
            existing = conn.execute(
                """
                SELECT inline FROM artifact_exposures
                WHERE session_id=? AND artifact_id=? AND request_id=?
                """,
                (session_id, artifact_id, request_id),
            ).fetchone()
            if existing is not None:
                return bool(existing["inline"])
            used = conn.execute(
                """
                SELECT COUNT(*) AS n FROM artifact_exposures
                WHERE session_id=? AND artifact_id=? AND inline=1
                """,
                (session_id, artifact_id),
            ).fetchone()["n"]
            inline = int(used < max(0, int(inline_limit)))
            if not inline:
                return False
            conn.execute(
                """
                INSERT INTO artifact_exposures(
                    session_id, artifact_id, request_id, inline, exposed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, artifact_id, request_id, inline, _utc_now()),
            )
        return bool(inline)

    def exposure_available(
        self,
        *,
        session_id: str,
        artifact_id: str,
        request_id: str,
        inline_limit: int,
    ) -> bool:
        """Read whether this request may expose the artifact inline.

        The subsequent claim remains authoritative. This read-only preflight
        permits the compiler to prove the complete candidate is smaller before
        it makes a durable exposure claim; a concurrent claim can only turn an
        inline candidate into a receipt.
        """
        session_id = str(session_id or "")
        request_id = str(request_id or "")
        with self.connection() as conn:
            existing = conn.execute(
                """
                SELECT inline FROM artifact_exposures
                WHERE session_id=? AND artifact_id=? AND request_id=?
                """,
                (session_id, artifact_id, request_id),
            ).fetchone()
            if existing is not None:
                return bool(existing["inline"])
            used = conn.execute(
                """
                SELECT COUNT(*) AS n FROM artifact_exposures
                WHERE session_id=? AND artifact_id=? AND inline=1
                """,
                (session_id, artifact_id),
            ).fetchone()["n"]
        return bool(used < max(0, int(inline_limit)))

    def record_request_metric(self, **metric: Any) -> None:
        """Persist one compiler/final-payload measurement without double-counting."""
        raw_chars = int(metric.get("raw_chars") or 0)
        compiled_chars = int(metric.get("compiled_chars") or 0)
        measured = int(bool(metric.get("end_to_end_measured")))
        final_chars = int(metric.get("final_chars") or 0) if measured else 0
        compiler_saved_chars = (
            int(metric.get("saved_chars") or 0)
            if "saved_chars" in metric
            else raw_chars - compiled_chars
        )
        if min(raw_chars, compiled_chars, compiler_saved_chars) < 0:
            raise ValueError("request metric character counts must be non-negative")
        if (
            compiled_chars > raw_chars
            or compiler_saved_chars != raw_chars - compiled_chars
        ):
            raise ValueError("request metric compiler savings algebra is inconsistent")
        if measured and (final_chars < 0 or final_chars > compiled_chars):
            raise ValueError(
                "request metric final characters exceed compiled characters"
            )
        compactor_saved = compiled_chars - final_chars if measured else 0
        end_to_end_saved = raw_chars - final_chars if measured else 0
        session_id = str(metric.get("session_id") or "")
        request_id = str(metric.get("request_id") or "")
        now = _utc_now()
        with self.connection(write=True) as conn:
            conn.execute(
                """
                INSERT INTO request_metrics(
                    session_id, request_id, request_mode, raw_chars, compiled_chars,
                    saved_chars, artifact_count, receipts, duplicates_collapsed,
                    tool_schema_chars, failed_open, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, request_id) DO UPDATE SET
                    request_mode=excluded.request_mode,
                    raw_chars=excluded.raw_chars,
                    compiled_chars=excluded.compiled_chars,
                    saved_chars=excluded.saved_chars,
                    artifact_count=excluded.artifact_count,
                    receipts=excluded.receipts,
                    duplicates_collapsed=excluded.duplicates_collapsed,
                    tool_schema_chars=excluded.tool_schema_chars,
                    failed_open=excluded.failed_open,
                    created_at=excluded.created_at
                WHERE request_metrics.end_to_end_measured = 0 OR ? = 1
                """,
                (
                    session_id,
                    request_id,
                    str(metric.get("request_mode") or "unknown"),
                    raw_chars,
                    compiled_chars,
                    compiler_saved_chars,
                    int(metric.get("artifact_count") or 0),
                    int(metric.get("receipts") or 0),
                    int(metric.get("duplicates_collapsed") or 0),
                    int(metric.get("tool_schema_chars") or 0),
                    int(bool(metric.get("failed_open"))),
                    now,
                    measured,
                ),
            )
            if measured:
                conn.execute(
                    """
                    UPDATE request_metrics SET
                        final_chars=?,
                        compactor_saved_chars=?,
                        end_to_end_saved_chars=?,
                        vaulted_results=?,
                        collapsed_turns=?,
                        compactor_failed_open=?,
                        end_to_end_measured=1
                    WHERE session_id=? AND request_id=?
                    """,
                    (
                        final_chars,
                        compactor_saved,
                        end_to_end_saved,
                        int(metric.get("vaulted_results") or 0),
                        int(metric.get("collapsed_turns") or 0),
                        int(bool(metric.get("compactor_failed_open"))),
                        session_id,
                        request_id,
                    ),
                )

    COUNT_KEYS = (
        "artifacts",
        "artifact_observations",
        "graph_events",
        "active_nodes",
        "active_edges",
        "requests",
        "saved_chars",
        "compiler_saved_chars",
        "failed_open_requests",
        "end_to_end_requests",
        "compiler_only_requests",
        "measured_raw_chars",
        "measured_compiled_chars",
        "measured_final_chars",
        "measured_compiler_saved_chars",
        "measured_compactor_saved_chars",
        "end_to_end_saved_chars",
        "vaulted_results",
        "collapsed_turns",
        "compactor_failed_open_requests",
        "any_failed_open_requests",
    )

    def counts(self) -> dict[str, int]:
        queries = {
            "artifacts": "SELECT COUNT(*) FROM artifacts",
            "artifact_observations": "SELECT COUNT(*) FROM artifact_observations",
            "graph_events": "SELECT COUNT(*) FROM graph_events",
            "active_nodes": "SELECT COUNT(*) FROM graph_nodes WHERE status='active'",
            "active_edges": "SELECT COUNT(*) FROM graph_edges WHERE status='active'",
            "requests": "SELECT COUNT(*) FROM request_metrics",
            "saved_chars": "SELECT COALESCE(SUM(saved_chars), 0) FROM request_metrics",
            "compiler_saved_chars": "SELECT COALESCE(SUM(saved_chars), 0) FROM request_metrics",
            "failed_open_requests": "SELECT COUNT(*) FROM request_metrics WHERE failed_open=1",
            "end_to_end_requests": "SELECT COUNT(*) FROM request_metrics WHERE end_to_end_measured=1",
            "compiler_only_requests": "SELECT COUNT(*) FROM request_metrics WHERE end_to_end_measured=0",
            "measured_raw_chars": "SELECT COALESCE(SUM(raw_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "measured_compiled_chars": "SELECT COALESCE(SUM(compiled_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "measured_final_chars": "SELECT COALESCE(SUM(final_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "measured_compiler_saved_chars": "SELECT COALESCE(SUM(saved_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "measured_compactor_saved_chars": "SELECT COALESCE(SUM(compactor_saved_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "end_to_end_saved_chars": "SELECT COALESCE(SUM(end_to_end_saved_chars), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "vaulted_results": "SELECT COALESCE(SUM(vaulted_results), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "collapsed_turns": "SELECT COALESCE(SUM(collapsed_turns), 0) FROM request_metrics WHERE end_to_end_measured=1",
            "compactor_failed_open_requests": "SELECT COUNT(*) FROM request_metrics WHERE compactor_failed_open=1",
            "any_failed_open_requests": "SELECT COUNT(*) FROM request_metrics WHERE failed_open=1 OR compactor_failed_open=1",
        }
        with self.connection() as conn:
            return {
                name: int(conn.execute(sql).fetchone()[0])
                for name, sql in queries.items()
            }
