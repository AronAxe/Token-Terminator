from __future__ import annotations

import asyncio
import threading

import pytest

from rtk_hermes_plus import AsyncRuntime, CancellationToken, Runtime
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.metrics import Metrics
from rtk_hermes_plus.rewrite import Rewriter, RewriteResult


def _runtime(tmp_path, **overrides) -> Runtime:
    values = {
        "mode": "balanced",
        "db_path": tmp_path / "artifacts.sqlite3",
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
        "ledger_enabled": False,
        "context_compaction_enabled": False,
        "min_artifact_chars": 20,
        "inline_lease_exposures": 0,
    }
    values.update(overrides)
    return Runtime(Config(**values), profile_name="async-test")


def test_async_runtime_compiles_without_mutating_caller_request(tmp_path):
    runtime = _runtime(tmp_path)
    async_runtime = AsyncRuntime(runtime)
    request = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "search_files", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "evidence " * 40},
        ]
    }
    original = {"messages": [dict(message) for message in request["messages"]]}

    result = asyncio.run(
        async_runtime.llm_request_middleware(
            request=request,
            session_id="session-1",
            request_id="request-1",
        )
    )

    assert result is not None
    assert result["request"] is not request
    assert request == original
    assert runtime.store is not None
    assert runtime.store.counts()["artifacts"] == 1


def test_async_runtime_rewrites_terminal_request(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path, mode="terminal")
    async_runtime = AsyncRuntime(runtime)

    async def rewrite_async(command, **_kwargs):
        assert command == "git status"
        return RewriteResult("rtk git status", 0, 1.0)

    monkeypatch.setattr(runtime.rewriter, "rewrite_async", rewrite_async)

    result = asyncio.run(
        async_runtime.tool_request_middleware(
            tool_name="terminal",
            args={"command": "git status", "cwd": str(tmp_path)},
            session_id="session-1",
            turn_id="turn-1",
        )
    )

    assert result is not None
    assert result["args"]["command"] == "rtk git status"
    assert result["source"] == "token-terminator"


def test_async_runtime_compresses_and_vaults_native_result(tmp_path):
    runtime = _runtime(
        tmp_path,
        native_min_chars=20,
        native_max_chars=80,
    )
    async_runtime = AsyncRuntime(runtime)
    original = "repeated evidence line\n" * 100

    transformed = asyncio.run(
        async_runtime.transform_tool_result(
            tool_name="search_files",
            args={"pattern": "evidence"},
            result=original,
            session_id="session-1",
            tool_call_id="call-1",
        )
    )

    assert transformed is not None
    assert len(transformed) < len(original)
    assert "full artifact=" in transformed
    assert runtime.store is not None
    assert runtime.store.counts()["artifacts"] == 1


def test_async_runtime_offloads_sync_work_from_event_loop(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    async_runtime = AsyncRuntime(runtime)
    started = threading.Event()
    release = threading.Event()

    def blocking_status():
        started.set()
        release.wait()
        return {"ready": True}

    monkeypatch.setattr(runtime, "status", blocking_status)

    async def exercise():
        task = asyncio.create_task(async_runtime.status())
        await asyncio.to_thread(started.wait)
        release.set()
        return await task

    assert asyncio.run(exercise()) == {"ready": True}


def test_cancellation_token_stops_waiting_for_sync_work(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    async_runtime = AsyncRuntime(runtime)
    cancellation = CancellationToken()
    started = threading.Event()
    release = threading.Event()

    def blocking_status():
        started.set()
        release.wait()
        return {"late": True}

    monkeypatch.setattr(runtime, "status", blocking_status)

    async def exercise():
        task = asyncio.create_task(async_runtime.status(cancellation=cancellation))
        await asyncio.to_thread(started.wait)
        cancellation.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()

    asyncio.run(exercise())
    assert runtime.metrics.snapshot()["async_cancelled"] == 1


def test_pre_cancelled_token_does_not_start_work(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)
    async_runtime = AsyncRuntime(runtime)
    cancellation = CancellationToken()
    cancellation.cancel()
    called = False

    def status():
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(runtime, "status", status)

    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            await async_runtime.status(cancellation=cancellation)

    asyncio.run(exercise())
    assert called is False
    assert runtime.metrics.snapshot()["async_cancelled"] == 1


def test_cancellation_token_can_be_triggered_from_another_thread():
    cancellation = CancellationToken()

    async def exercise():
        waiter = asyncio.create_task(cancellation.wait())
        thread = threading.Thread(target=cancellation.cancel)
        thread.start()
        await waiter
        thread.join()

    asyncio.run(exercise())
    assert cancellation.cancelled is True


class _FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.killed = False

    async def communicate(self):
        self.started.set()
        await self.finished.wait()
        return b"rtk git status", b""

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.finished.set()

    async def wait(self) -> int:
        await self.finished.wait()
        return int(self.returncode or 0)


def test_async_rewriter_kills_and_reaps_on_token_cancellation(tmp_path, monkeypatch):
    rewriter = Rewriter(
        Config(mode="terminal", timeout_ms=10_000),
        Metrics(),
    )
    rewriter.rtk_path = "rtk"
    process = _FakeProcess()

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    async def exercise():
        cancellation = CancellationToken()
        task = asyncio.create_task(
            rewriter.rewrite_async(
                "git status",
                cwd=tmp_path,
                cancellation=cancellation,
            )
        )
        await process.started.wait()
        cancellation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert process.killed is True
    assert rewriter.metrics.snapshot()["rewrite_cancelled"] == 1


def test_async_rewriter_kills_and_reaps_on_task_cancellation(tmp_path, monkeypatch):
    rewriter = Rewriter(
        Config(mode="terminal", timeout_ms=10_000),
        Metrics(),
    )
    rewriter.rtk_path = "rtk"
    process = _FakeProcess()

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    async def exercise():
        task = asyncio.create_task(rewriter.rewrite_async("git status", cwd=tmp_path))
        await process.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert process.killed is True
    assert rewriter.metrics.snapshot()["rewrite_cancelled"] == 1


def test_async_native_read_kills_rtk_before_vault_write(tmp_path, monkeypatch):
    runtime = _runtime(
        tmp_path,
        mode="aggressive",
        native_min_chars=20,
    )
    runtime.compressor.rtk_path = "rtk"
    async_runtime = AsyncRuntime(runtime)
    process = _FakeProcess()

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)

    async def exercise():
        cancellation = CancellationToken()
        task = asyncio.create_task(
            async_runtime.transform_tool_result(
                tool_name="read_file",
                args={"path": "large.py"},
                result="evidence " * 100,
                cancellation=cancellation,
            )
        )
        await process.started.wait()
        cancellation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert process.killed is True
    assert runtime.metrics.snapshot()["native_rtk_cancelled"] == 1
    assert runtime.metrics.snapshot()["async_cancelled"] == 1
    assert runtime.store is not None
    assert runtime.store.counts()["artifacts"] == 0
