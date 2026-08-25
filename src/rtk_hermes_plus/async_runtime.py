from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Executor
from contextlib import suppress
from functools import partial
from typing import Any, TypeVar

from .cancellation import CancellationToken
from .compress import compact_text
from .plugin import Runtime

_T = TypeVar("_T")


class AsyncRuntime:
    """Non-blocking façade over :class:`Runtime` for async agent frameworks.

    CPU-bound and SQLite-backed sync operations run in an executor. Cancelling
    the awaiting task propagates immediately to the caller; already-running
    sync work remains atomic and may finish in its worker thread. RTK command
    rewrites use a native asyncio subprocess path and are killed and reaped on
    cancellation.
    """

    def __init__(self, runtime: Runtime, *, executor: Executor | None = None) -> None:
        self.runtime = runtime
        self.executor = executor

    def _raise_if_cancelled(self, cancellation: CancellationToken | None) -> None:
        if cancellation is not None and cancellation.cancelled:
            self.runtime.metrics.add("async_cancelled")
            raise asyncio.CancelledError

    async def _run_sync(
        self,
        function: Callable[..., _T],
        /,
        *args: Any,
        cancellation: CancellationToken | None = None,
        **kwargs: Any,
    ) -> _T:
        self._raise_if_cancelled(cancellation)
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(self.executor, partial(function, *args, **kwargs))
        cancellation_waiter: asyncio.Task[None] | None = None
        try:
            if cancellation is None:
                return await future
            cancellation_waiter = asyncio.create_task(cancellation.wait())
            done, _pending = await asyncio.wait(
                (future, cancellation_waiter),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if future in done:
                return future.result()
            if cancellation_waiter in done:
                future.cancel()
                raise asyncio.CancelledError
            raise RuntimeError("async runtime wait completed without a result")
        except asyncio.CancelledError:
            if cancellation is not None:
                cancellation.cancel()
            future.cancel()
            self.runtime.metrics.add("async_cancelled")
            raise
        finally:
            if cancellation_waiter is not None:
                cancellation_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await cancellation_waiter

    async def tool_request_middleware(
        self,
        *,
        tool_name: str,
        args: dict,
        cancellation: CancellationToken | None = None,
        **kwargs: Any,
    ) -> dict | None:
        self._raise_if_cancelled(cancellation)
        if tool_name != "terminal" or not isinstance(args, dict):
            return None
        prepared = await self._run_sync(
            self.runtime._prepare_rewrite,
            args,
            cancellation=cancellation,
        )
        if prepared is None:
            return None
        command, cwd = prepared
        try:
            result = await self.runtime.rewriter.rewrite_async(
                command,
                cwd=cwd,
                cancellation=cancellation,
            )
        except asyncio.CancelledError:
            if cancellation is not None:
                cancellation.cancel()
            self.runtime.metrics.add("async_cancelled")
            raise
        rewritten = self.runtime._apply_rewrite_result(args, result)
        if rewritten is None:
            return None
        await self._run_sync(
            self.runtime._record_rewrite,
            session_id=str(kwargs.get("session_id") or ""),
            turn_id=str(kwargs.get("turn_id") or ""),
            cancellation=cancellation,
        )
        return {
            "args": rewritten,
            "source": "token-terminator",
            "reason": "strict token reduction",
        }

    async def observe_tool_call(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> None:
        await self._run_sync(
            self.runtime.observe_tool_call, cancellation=cancellation, **kwargs
        )

    async def transform_tool_result(
        self,
        *,
        tool_name: str,
        args: dict,
        result: str,
        cancellation: CancellationToken | None = None,
        **kwargs: Any,
    ) -> Any:
        self._raise_if_cancelled(cancellation)
        compressor = self.runtime.compressor
        if not compressor._eligible(tool_name=tool_name, args=args, result=result):
            return None
        compressor.metrics.add("native_attempted")
        compact = None
        try:
            if tool_name == "read_file":
                compact = await compressor._rtk_read_async(
                    args,
                    cancellation=cancellation,
                )
        except asyncio.CancelledError:
            if cancellation is not None:
                cancellation.cancel()
            self.runtime.metrics.add("async_cancelled")
            raise
        if compact is None:
            compact = await self._run_sync(
                compact_text,
                result,
                compressor.config.native_max_chars,
                cancellation=cancellation,
            )
        transformed = await self._run_sync(
            compressor._finalize_transform,
            tool_name=tool_name,
            args=args,
            result=result,
            compact=compact,
            session_id=str(kwargs.get("session_id") or ""),
            tool_call_id=str(kwargs.get("tool_call_id") or ""),
            cancellation=cancellation,
        )
        if transformed is not None:
            await self._run_sync(
                self.runtime._record_native,
                session_id=str(kwargs.get("session_id") or ""),
                turn_id=str(kwargs.get("turn_id") or ""),
                raw_chars=len(result),
                output_chars=len(transformed),
                cancellation=cancellation,
            )
        return transformed

    async def post_tool_call(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> None:
        await self._run_sync(
            self.runtime.post_tool_call, cancellation=cancellation, **kwargs
        )

    async def llm_request_middleware(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> dict | None:
        return await self._run_sync(
            self.runtime.llm_request_middleware, cancellation=cancellation, **kwargs
        )

    async def on_session_start(
        self,
        *,
        session_id: str,
        cancellation: CancellationToken | None = None,
    ) -> None:
        await self._run_sync(
            self.runtime.on_session_start,
            session_id=session_id,
            cancellation=cancellation,
        )

    async def pre_llm_call(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> None:
        await self._run_sync(
            self.runtime.pre_llm_call, cancellation=cancellation, **kwargs
        )

    async def on_session_end(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> None:
        await self._run_sync(
            self.runtime.on_session_end, cancellation=cancellation, **kwargs
        )

    async def on_session_finalize(
        self,
        *,
        session_id: str,
        cancellation: CancellationToken | None = None,
    ) -> None:
        await self._run_sync(
            self.runtime.on_session_finalize,
            session_id=session_id,
            cancellation=cancellation,
        )

    async def tool(
        self, *, cancellation: CancellationToken | None = None, **kwargs: Any
    ) -> str:
        return await self._run_sync(
            self.runtime.tool, cancellation=cancellation, **kwargs
        )

    async def status(
        self, *, cancellation: CancellationToken | None = None
    ) -> dict[str, Any]:
        return await self._run_sync(self.runtime.status, cancellation=cancellation)
