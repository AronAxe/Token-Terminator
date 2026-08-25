from __future__ import annotations

import asyncio
import threading


class CancellationToken:
    """Thread-safe cancellation signal for async runtime adapters.

    Cancelling a token stops cancellable async work such as RTK subprocesses.
    SQLite and compiler operations already running in a worker thread remain
    atomic and may finish after the awaiting task has been cancelled.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()
        self._waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = (
            set()
        )

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @staticmethod
    def _resolve_waiter(waiter: asyncio.Future[None]) -> None:
        if not waiter.done():
            waiter.set_result(None)

    def cancel(self) -> None:
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            waiters = tuple(self._waiters)
            self._waiters.clear()
        for loop, waiter in waiters:
            try:
                loop.call_soon_threadsafe(self._resolve_waiter, waiter)
            except RuntimeError:
                # The owning loop closed while cancellation crossed threads.
                # No active coroutine remains to wake in that loop.
                continue

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        entry = (loop, waiter)
        with self._lock:
            if self._cancelled:
                return
            self._waiters.add(entry)
        try:
            await waiter
        finally:
            with self._lock:
                self._waiters.discard(entry)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError
