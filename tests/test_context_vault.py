from __future__ import annotations

import sqlite3

import pytest

from rtk_hermes_plus.storage import TokenTerminatorStore


def test_artifact_round_trip_and_deduplication(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    original = "evidence αβγ\n" * 30

    first = store.put_artifact(
        original,
        tool_name="terminal",
        args={"command": "produce evidence"},
        session_id="session-a",
        tool_call_id="call-1",
    )
    second = store.put_artifact(
        original,
        tool_name="terminal",
        args={"command": "produce evidence again"},
        session_id="session-a",
        tool_call_id="call-2",
    )

    assert first.artifact_id == second.artifact_id
    assert first.created is True
    assert second.created is False
    recovered = store.get_artifact(first.artifact_id)
    assert recovered.content == original
    assert recovered.char_count == len(original)
    assert recovered.byte_count == len(original.encode("utf-8"))
    assert recovered.observation_count == 2


def test_artifact_search_and_bounded_read(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    stored = store.put_artifact("alpha needle omega", tool_name="read_file")

    hits = store.search_artifacts("needle", limit=5)
    assert [hit.artifact_id for hit in hits] == [stored.artifact_id]

    page = store.read_artifact(stored.artifact_id, offset=6, limit=6)
    assert page["content"] == "needle"
    assert page["next_offset"] == 12
    assert page["total_chars"] == len("alpha needle omega")


def test_additive_metrics_migration_remains_schema_2_compatible(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE request_metrics (
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
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX idx_request_metric_identity
            ON request_metrics(session_id, request_id);
            PRAGMA user_version=2;
            """
        )

    store = TokenTerminatorStore(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {row[1] for row in conn.execute("PRAGMA table_info(request_metrics)")}
        assert "end_to_end_measured" in columns
        # Explicit old-column INSERT shape used by the previous package.
        conn.execute(
            """
            INSERT INTO request_metrics(
                session_id, request_id, request_mode, raw_chars, compiled_chars,
                saved_chars, artifact_count, receipts, duplicates_collapsed,
                tool_schema_chars, failed_open, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy", "r1", "messages", 100, 80, 20, 0, 0, 0, 0, 0, "now"),
        )

    store.record_request_metric(
        session_id="new",
        request_id="r2",
        request_mode="messages",
        raw_chars=200,
        compiled_chars=150,
        final_chars=100,
        end_to_end_measured=True,
    )
    counts = store.counts()
    assert counts["requests"] == 2
    assert counts["compiler_only_requests"] == 1
    assert counts["end_to_end_requests"] == 1
    assert counts["measured_compiler_saved_chars"] == 50
    assert counts["measured_compactor_saved_chars"] == 50
    assert counts["end_to_end_saved_chars"] == 100


def test_compiler_only_retry_does_not_downgrade_measured_row(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    store.record_request_metric(
        session_id="session",
        request_id="request",
        request_mode="messages",
        raw_chars=100,
        compiled_chars=80,
        saved_chars=20,
        final_chars=70,
        end_to_end_measured=True,
    )

    store.record_request_metric(
        session_id="session",
        request_id="request",
        request_mode="messages",
        raw_chars=100,
        compiled_chars=80,
        saved_chars=20,
        end_to_end_measured=False,
    )

    with store.connection() as conn:
        row = conn.execute(
            "SELECT final_chars, compactor_saved_chars, "
            "end_to_end_saved_chars, end_to_end_measured "
            "FROM request_metrics WHERE session_id=? AND request_id=?",
            ("session", "request"),
        ).fetchone()
    assert tuple(row) == (70, 10, 30, 1)


def test_legacy_update_invalidates_stale_end_to_end_measurement(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    store.record_request_metric(
        session_id="session",
        request_id="request",
        request_mode="messages",
        raw_chars=100,
        compiled_chars=80,
        saved_chars=20,
        final_chars=70,
        vaulted_results=2,
        collapsed_turns=1,
        end_to_end_measured=True,
    )

    with sqlite3.connect(store.path) as conn:
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
            """,
            ("session", "request", "messages", 120, 110, 10, 0, 0, 0, 0, 0, "later"),
        )

    with store.connection() as conn:
        row = conn.execute(
            "SELECT raw_chars, compiled_chars, saved_chars, final_chars, "
            "compactor_saved_chars, end_to_end_saved_chars, vaulted_results, "
            "collapsed_turns, end_to_end_measured FROM request_metrics"
        ).fetchone()
    assert tuple(row) == (120, 110, 10, 0, 0, 0, 0, 0, 0)


def test_inconsistent_metric_algebra_is_rejected(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")

    with pytest.raises(ValueError, match="compiler savings algebra"):
        store.record_request_metric(
            session_id="session",
            request_id="request",
            request_mode="messages",
            raw_chars=120,
            compiled_chars=110,
            saved_chars=20,
            final_chars=70,
            end_to_end_measured=True,
        )


def test_count_keys_match_counts_result(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")

    assert tuple(store.counts()) == TokenTerminatorStore.COUNT_KEYS
