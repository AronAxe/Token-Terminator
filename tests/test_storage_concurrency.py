from __future__ import annotations

import multiprocessing
import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from rtk_hermes_plus import storage as storage_module
from rtk_hermes_plus.storage import TokenTerminatorStore


def _write_artifacts(path: str, worker: int, iterations: int, variants: int) -> int:
    store = TokenTerminatorStore(path)
    for index in range(iterations):
        store.put_artifact(
            f"shared artifact {index % variants}",
            tool_name="stress_tool",
            args={"variant": index % variants},
            session_id=f"worker-{worker}",
            tool_call_id=f"call-{worker}-{index}",
        )
    return iterations


def _claim_exposure(path: str, artifact_id: str, request_id: str) -> bool:
    store = TokenTerminatorStore(path)
    return store.claim_exposure(
        session_id="shared-session",
        artifact_id=artifact_id,
        request_id=request_id,
        inline_limit=1,
    )


def test_artifact_vault_uses_wal_mode(tmp_path):
    store = TokenTerminatorStore(tmp_path / "wal.db")

    assert store.journal_mode == "wal"
    with store.connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1


def test_wal_initialization_retries_a_transient_lock(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    connect_attempts = 0
    locked_attempts = 0

    class LockedOnceConnection:
        def __init__(self, connection):
            self._connection = connection

        def execute(self, statement, *args, **kwargs):
            nonlocal locked_attempts
            if statement == "PRAGMA journal_mode=WAL" and locked_attempts == 0:
                locked_attempts += 1
                raise sqlite3.OperationalError("database is locked")
            return self._connection.execute(statement, *args, **kwargs)

        def close(self):
            self._connection.close()

        def __getattr__(self, name):
            return getattr(self._connection, name)

    def connect(*args, **kwargs):
        nonlocal connect_attempts
        connect_attempts += 1
        connection = real_connect(*args, **kwargs)
        if connect_attempts == 1:
            return LockedOnceConnection(connection)
        return connection

    monkeypatch.setattr(storage_module.sqlite3, "connect", connect)

    store = TokenTerminatorStore(tmp_path / "wal-retry.db")

    assert locked_attempts == 1
    assert store.journal_mode == "wal"


def test_concurrent_agent_threads_preserve_dedup_and_observations(tmp_path):
    path = str(tmp_path / "threads.db")
    workers = 8
    iterations = 40
    variants = 7

    with ThreadPoolExecutor(max_workers=workers) as executor:
        completed = list(
            executor.map(
                _write_artifacts,
                [path] * workers,
                range(workers),
                [iterations] * workers,
                [variants] * workers,
            )
        )

    store = TokenTerminatorStore(path)
    counts = store.counts()
    assert completed == [iterations] * workers
    assert counts["artifacts"] == variants
    assert counts["artifact_observations"] == workers * iterations
    with store.connection() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_agent_processes_preserve_dedup_and_observations(tmp_path):
    path = str(Path(tmp_path) / "processes.db")
    workers = 4
    iterations = 25
    variants = 5
    context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as executor:
        futures = [
            executor.submit(_write_artifacts, path, worker, iterations, variants)
            for worker in range(workers)
        ]
        completed = [future.result() for future in futures]

    store = TokenTerminatorStore(path)
    counts = store.counts()
    assert completed == [iterations] * workers
    assert counts["artifacts"] == variants
    assert counts["artifact_observations"] == workers * iterations
    with store.connection() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_agent_processes_claim_only_one_inline_lease(tmp_path):
    path = str(Path(tmp_path) / "leases.db")
    store = TokenTerminatorStore(path)
    artifact_id = store.put_artifact("shared evidence").artifact_id
    workers = 6
    context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as executor:
        futures = [
            executor.submit(_claim_exposure, path, artifact_id, f"request-{index}")
            for index in range(workers)
        ]
        decisions = [future.result() for future in futures]

    assert sum(decisions) == 1
    with store.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM artifact_exposures WHERE inline=1"
            ).fetchone()[0]
            == 1
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
