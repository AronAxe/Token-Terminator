import os
import sqlite3
from contextlib import closing

from rtk_hermes_plus.ledger import ExperimentLedger, HermesAccounting


def snapshot(**overrides):
    values = {
        "model": "test-model",
        "billing_provider": "openai-codex",
        "billing_mode": "subscription_included",
        "cost_status": "included",
        "cost_source": "oauth",
        "pricing_version": "included-route",
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 0,
        "api_call_count": 0,
        "tool_call_count": 0,
        "estimated_cost_usd": 0.0,
        "actual_cost_usd": None,
    }
    values.update(overrides)
    return values


def ledger(tmp_path, current):
    return ExperimentLedger(
        tmp_path / "experiments.sqlite3",
        tmp_path / "state.db",
        plugin_version="test",
        experiment="paired-test",
        session_reader=lambda session_id: current.get(session_id, snapshot()),
    )


def finish_trial(store, current, session_id, mode, values, *, rewrite=False):
    current[session_id] = snapshot()
    store.start_turn(
        session_id=session_id,
        turn_id="turn-1",
        task_id="task-1",
        mode=mode,
        user_message="Implement the same deterministic task",
        model="test-model",
        platform="cli",
    )
    current[session_id] = snapshot(**values)
    store.record_native(
        session_id=session_id,
        turn_id="turn-1",
        raw_chars=100_000,
        output_chars=2_000,
    )
    if rewrite:
        store.record_rewrite(session_id=session_id, turn_id="turn-1")
    store.finish_turn(
        session_id=session_id,
        turn_id="turn-1",
        mode=mode,
        completed=True,
        failed=False,
        interrupted=False,
        turn_exit_reason="text_response(stop)",
    )


def test_compare_reports_session_and_matched_turn_deltas(tmp_path):
    current = {}
    store = ledger(tmp_path, current)
    finish_trial(
        store,
        current,
        "native-session",
        "native",
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_tokens": 50,
            "api_call_count": 1,
            "tool_call_count": 2,
        },
    )
    finish_trial(
        store,
        current,
        "balanced-session",
        "balanced",
        {
            "input_tokens": 130,
            "output_tokens": 25,
            "cache_read_tokens": 60,
            "api_call_count": 2,
            "tool_call_count": 3,
        },
        rewrite=True,
    )

    result = store.compare()
    assert result["modes"]["native"]["median_total_tokens"] == 170.0
    assert result["modes"]["balanced"]["median_total_tokens"] == 215.0
    assert result["delta"]["median_total_tokens_delta"] == 45.0
    assert result["matched_turns"]["pairs"] == 1
    assert result["matched_turns"]["median_total_tokens_delta"] == 45.0
    assert result["modes"]["native"]["mean_actual_cost_usd"] == 0.0
    assert result["modes"]["balanced"]["rewrite_count"] == 1


def test_resumed_session_uses_accounting_baseline(tmp_path):
    current = {"resumed": snapshot(input_tokens=1_000, output_tokens=200)}
    store = ledger(tmp_path, current)
    store.start_turn(
        session_id="resumed",
        turn_id="turn-1",
        task_id="task-1",
        mode="native",
        user_message="Continue",
    )
    current["resumed"] = snapshot(input_tokens=1_100, output_tokens=225)
    store.finish_turn(
        session_id="resumed",
        turn_id="turn-1",
        mode="native",
        completed=True,
        failed=False,
        interrupted=False,
    )
    result = store.compare()
    assert result["modes"]["native"]["median_total_tokens"] == 125.0


def test_mode_change_contaminates_and_excludes_session(tmp_path):
    current = {"mixed": snapshot()}
    store = ledger(tmp_path, current)
    store.ensure_session("mixed", "native")
    store.ensure_session("mixed", "balanced")
    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            "SELECT contaminated, contamination_reason FROM sessions WHERE session_id = 'mixed'"
        ).fetchone()
    assert row[0] == 1
    assert "runtime mode changed" in row[1]
    assert store.compare()["excluded_contaminated_sessions"] == 1


def test_ledger_is_durable_and_stores_no_prompt_content(tmp_path):
    current = {}
    first = ledger(tmp_path, current)
    secret_prompt = "private phrase that must never enter sqlite"
    current["s"] = snapshot()
    first.start_turn(
        session_id="s",
        turn_id="t",
        task_id="task",
        mode="native",
        user_message=secret_prompt,
    )
    current["s"] = snapshot(input_tokens=10)
    first.finish_turn(
        session_id="s",
        turn_id="t",
        mode="native",
        completed=True,
        failed=False,
        interrupted=False,
    )
    second = ledger(tmp_path, current)
    assert second.compare()["modes"]["native"]["sessions"] == 1
    with closing(sqlite3.connect(second.path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    payload = b"".join(
        path.read_bytes()
        for path in (
            second.path,
            second.path.with_name(second.path.name + "-wal"),
            second.path.with_name(second.path.name + "-shm"),
        )
        if path.is_file()
    )
    assert secret_prompt.encode() not in payload
    if os.name != "nt":
        assert second.path.stat().st_mode & 0o777 == 0o600


def test_ledger_operations_leave_no_open_database_handle(tmp_path):
    current = {"s": snapshot()}
    store = ledger(tmp_path, current)
    store.ensure_session("s", "native")
    store.compare()

    moved = tmp_path / "experiments-moved.sqlite3"
    store.path.replace(moved)
    assert moved.is_file()


def test_hermes_accounting_reads_canonical_columns(tmp_path):
    state_db = tmp_path / "state.db"
    with closing(sqlite3.connect(state_db)) as connection, connection:
        connection.execute(
            """CREATE TABLE sessions(
                   id TEXT PRIMARY KEY, model TEXT, billing_provider TEXT,
                   billing_mode TEXT, input_tokens INTEGER, output_tokens INTEGER,
                   cache_read_tokens INTEGER, cache_write_tokens INTEGER,
                   reasoning_tokens INTEGER, api_call_count INTEGER,
                   tool_call_count INTEGER, estimated_cost_usd REAL,
                   actual_cost_usd REAL, cost_status TEXT, cost_source TEXT,
                   pricing_version TEXT)"""
        )
        connection.execute(
            "INSERT INTO sessions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "s1",
                "model",
                "provider",
                "subscription_included",
                10,
                5,
                20,
                0,
                2,
                1,
                3,
                0.0,
                None,
                "included",
                "oauth",
                "included-route",
            ),
        )
    result = HermesAccounting(state_db).read("s1")
    assert result["cache_read_tokens"] == 20
    assert result["actual_cost_usd"] == 0.0

    moved = tmp_path / "state-moved.db"
    state_db.replace(moved)
    assert moved.is_file()


def test_unavailable_hermes_accounting_contaminates_measurement(tmp_path):
    store = ExperimentLedger(
        tmp_path / "experiments.sqlite3",
        tmp_path / "missing-state.db",
        plugin_version="test",
        experiment="paired-test",
    )
    store.start_turn(
        session_id="missing",
        turn_id="t1",
        task_id="task",
        mode="native",
        user_message="measurement must not become zero usage",
    )
    store.finish_turn(
        session_id="missing",
        turn_id="t1",
        mode="native",
        completed=True,
        failed=False,
        interrupted=False,
    )

    result = store.compare()
    assert result["excluded_contaminated_sessions"] == 1
    assert result["modes"]["native"]["sessions"] == 0
    with closing(sqlite3.connect(store.path)) as connection:
        row = connection.execute(
            "SELECT contamination_reason FROM sessions WHERE session_id='missing'"
        ).fetchone()
    assert row[0] == "accounting unavailable"


def test_optional_api_equivalent_cost_stays_separate_from_actual(tmp_path):
    current = {"s": snapshot()}
    store = ExperimentLedger(
        tmp_path / "experiments.sqlite3",
        tmp_path / "state.db",
        plugin_version="test",
        experiment="paired-test",
        session_reader=lambda session_id: current[session_id],
        equivalent_rates={"input": 2.0, "output": 10.0, "cache_read": 0.2},
        equivalent_rate_card="example",
    )
    store.start_turn(
        session_id="s",
        turn_id="t",
        task_id="task",
        mode="native",
        user_message="priced task",
    )
    current["s"] = snapshot(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=2_000_000,
    )
    store.finish_turn(
        session_id="s",
        turn_id="t",
        mode="native",
        completed=True,
        failed=False,
        interrupted=False,
    )
    result = store.compare()["modes"]["native"]
    assert result["mean_actual_cost_usd"] == 0.0
    assert result["mean_api_equivalent_cost_usd"] == 3.4


def test_reasoning_detail_is_not_double_counted_as_output(tmp_path):
    current = {}
    store = ledger(tmp_path, current)
    finish_trial(
        store,
        current,
        "reasoning-session",
        "native",
        {
            "input_tokens": 100,
            "output_tokens": 50,
            "reasoning_tokens": 40,
        },
    )
    result = store.compare()["modes"]["native"]
    assert result["median_total_tokens"] == 150.0
