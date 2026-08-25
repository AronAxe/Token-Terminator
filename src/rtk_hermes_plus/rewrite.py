from __future__ import annotations

import asyncio
import configparser
import os
import re
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .cancellation import CancellationToken
from .config import Config
from .metrics import Metrics

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


PYTEST_COMMAND = re.compile(
    r"(?:^|(?:&&|\|\||;)\s*)(?:(?:uv\s+run\s+)?(?:python(?:3(?:\.\d+)?)?\s+-m\s+)?)pytest(?:\s|$)"
)
QUIET_OPTION = re.compile(r"(?:^|\s)(?:-q{1,}|--quiet)(?:\s|$)")


@dataclass(frozen=True)
class RewriteResult:
    command: str | None
    returncode: int
    elapsed_ms: float
    cache_hit: bool = False


class RewriteCache:
    def __init__(self, max_size: int, ttl_seconds: int):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, tuple[float, RewriteResult]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> RewriteResult | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            created, result = item
            if now - created > self.ttl_seconds:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return RewriteResult(
                result.command, result.returncode, result.elapsed_ms, True
            )

    def put(self, key: str, result: RewriteResult) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), result)
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)


class Rewriter:
    def __init__(self, config: Config, metrics: Metrics):
        self.config = config
        self.metrics = metrics
        self.cache = RewriteCache(config.cache_size, config.cache_ttl_seconds)
        self.rtk_path = shutil.which("rtk")

    @property
    def available(self) -> bool:
        return self.rtk_path is not None

    def _result_from_output(
        self,
        command: str,
        *,
        stdout: str,
        returncode: int,
        elapsed_ms: float,
    ) -> RewriteResult:
        self.metrics.add("rewrite_total_ms", elapsed_ms)
        rewritten = stdout.strip()
        command_out = (
            rewritten
            if returncode in {0, 3} and rewritten and rewritten != command
            else None
        )
        result = RewriteResult(command_out, returncode, elapsed_ms)
        self.cache.put(command, result)
        return result

    def rewrite(self, command: str, *, cwd: Path) -> RewriteResult:
        cached = self.cache.get(command)
        if cached is not None:
            self.metrics.add("rewrite_cache_hits")
            return cached

        started = time.perf_counter()
        self.metrics.add("rewrite_attempted")
        try:
            completed = subprocess.run(
                [self.rtk_path or "rtk", "rewrite", command],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.config.timeout_ms / 1000,
                shell=False,
                check=False,
            )
            elapsed = (time.perf_counter() - started) * 1000
            return self._result_from_output(
                command,
                stdout=completed.stdout,
                returncode=completed.returncode,
                elapsed_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.add("rewrite_total_ms", elapsed)
            self.metrics.add("rewrite_timeouts")
            return RewriteResult(None, -1, elapsed)
        except OSError:
            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.add("rewrite_total_ms", elapsed)
            self.metrics.add("rewrite_errors")
            return RewriteResult(None, -1, elapsed)

    async def rewrite_async(
        self,
        command: str,
        *,
        cwd: Path,
        cancellation: CancellationToken | None = None,
    ) -> RewriteResult:
        """Rewrite through a cancellable asyncio subprocess."""
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        cached = self.cache.get(command)
        if cached is not None:
            self.metrics.add("rewrite_cache_hits")
            return cached

        started = time.perf_counter()
        self.metrics.add("rewrite_attempted")
        process: asyncio.subprocess.Process | None = None
        communicate_task: asyncio.Task[tuple[bytes, bytes]] | None = None
        cancellation_waiter: asyncio.Task[None] | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                self.rtk_path or "rtk",
                "rewrite",
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            communicate_task = asyncio.create_task(process.communicate())
            waiters: set[asyncio.Task] = {communicate_task}
            if cancellation is not None:
                cancellation_waiter = asyncio.create_task(cancellation.wait())
                waiters.add(cancellation_waiter)
            done, _pending = await asyncio.wait(
                waiters,
                timeout=self.config.timeout_ms / 1000,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                with suppress(ProcessLookupError):
                    process.kill()
                await communicate_task
                elapsed = (time.perf_counter() - started) * 1000
                self.metrics.add("rewrite_total_ms", elapsed)
                self.metrics.add("rewrite_timeouts")
                return RewriteResult(None, -1, elapsed)
            if cancellation_waiter is not None and cancellation_waiter in done:
                raise asyncio.CancelledError

            stdout, _stderr = communicate_task.result()
            elapsed = (time.perf_counter() - started) * 1000
            return self._result_from_output(
                command,
                stdout=stdout.decode(errors="replace"),
                returncode=int(process.returncode or 0),
                elapsed_ms=elapsed,
            )
        except asyncio.CancelledError:
            if cancellation is not None:
                cancellation.cancel()
            if process is not None and process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            if communicate_task is not None:
                with suppress(asyncio.CancelledError, ProcessLookupError):
                    await communicate_task
            elif process is not None:
                with suppress(asyncio.CancelledError, ProcessLookupError):
                    await process.wait()
            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.add("rewrite_total_ms", elapsed)
            self.metrics.add("rewrite_cancelled")
            raise
        except OSError:
            elapsed = (time.perf_counter() - started) * 1000
            self.metrics.add("rewrite_total_ms", elapsed)
            self.metrics.add("rewrite_errors")
            return RewriteResult(None, -1, elapsed)
        finally:
            if cancellation_waiter is not None:
                cancellation_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await cancellation_waiter


def terminal_backend(args: dict | None = None) -> str:
    args = args or {}
    for key in ("env_type", "backend"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return (
        (os.getenv("TERMINAL_ENV") or os.getenv("TERMINAL_BACKEND") or "local")
        .strip()
        .lower()
    )


def backend_enabled(backend: str, config: Config) -> bool:
    return "all" in config.enabled_backends or backend in config.enabled_backends


def command_workdir(args: dict | None = None) -> Path:
    args = args or {}
    for key in ("cwd", "workdir"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value).expanduser()
    return Path.cwd()


def command_excluded(command: str, prefixes: tuple[str, ...]) -> bool:
    normalized = command.lstrip().lower()
    return any(normalized.startswith(prefix) for prefix in prefixes)


def is_pytest_command(command: str) -> bool:
    return PYTEST_COMMAND.search(command) is not None


def pytest_config_is_quiet(cwd: Path) -> bool:
    for directory in _candidate_config_dirs(cwd):
        if _pyproject_quiet(directory / "pyproject.toml"):
            return True
        if _ini_quiet(directory / "pytest.ini", "pytest"):
            return True
        if _ini_quiet(directory / "tox.ini", "pytest"):
            return True
        if _ini_quiet(directory / "setup.cfg", "tool:pytest"):
            return True
    return False


def _candidate_config_dirs(cwd: Path):
    current = cwd.resolve()
    for _ in range(8):
        yield current
        if current.parent == current or (current / ".git").exists():
            break
        current = current.parent


def _pyproject_quiet(path: Path) -> bool:
    if tomllib is None or not path.is_file():
        return False
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        addopts = (
            data.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("addopts", "")
        )
    except (OSError, ValueError, TypeError):
        return False
    if isinstance(addopts, list):
        addopts = " ".join(str(item) for item in addopts)
    return bool(QUIET_OPTION.search(str(addopts)))


def _ini_quiet(path: Path, section: str) -> bool:
    if not path.is_file():
        return False
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
        addopts = parser.get(section, "addopts", fallback="")
    except (OSError, configparser.Error):
        return False
    return bool(QUIET_OPTION.search(addopts))
