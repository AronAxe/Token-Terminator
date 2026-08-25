from __future__ import annotations

import asyncio
import re
import subprocess
from contextlib import suppress

from .cancellation import CancellationToken
from .config import Config
from .metrics import Metrics
from .rewrite import backend_enabled, command_workdir, terminal_backend
from .storage import TokenTerminatorStore

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class RecoveryStore:
    """Compatibility facade over Token Terminator's content-addressed vault."""

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
        store: TokenTerminatorStore | None = None,
    ):
        self.config = config
        self.metrics = metrics
        self.error = ""
        try:
            self.store = store or TokenTerminatorStore(
                config.db_path,
                max_artifact_chars=config.max_artifact_chars,
                max_vault_bytes=config.vault_max_bytes,
                max_page_chars=config.max_artifact_page_chars,
            )
        except Exception as exc:  # noqa: BLE001 - plugin must remain fail-open
            self.store = None
            self.error = f"{type(exc).__name__}: {exc}"
            self.metrics.add("recovery_errors")

    def write(
        self,
        tool_name: str,
        content: str,
        *,
        args: dict | None = None,
        session_id: str = "",
        tool_call_id: str = "",
    ) -> str | None:
        """Persist and verify exact recovery before returning an artifact ID."""
        if self.store is None:
            self.metrics.add("recovery_errors")
            return None
        try:
            stored = self.store.put_artifact(
                content,
                tool_name=tool_name,
                args=args or {},
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            recovered = self.store.get_artifact(stored.artifact_id)
            if recovered.content != content or recovered.sha256 != stored.sha256:
                self.metrics.add("recovery_errors")
                return None
            self.metrics.add(
                "recovery_artifacts_written"
                if stored.created
                else "recovery_artifacts_reused"
            )
            return stored.artifact_id
        except Exception:  # noqa: BLE001 - recovery failure must degrade to original result
            self.metrics.add("recovery_errors")
            return None


class NativeCompressor:
    BALANCED_TOOLS = frozenset({"search_files", "process"})
    AGGRESSIVE_TOOLS = frozenset({"read_file"})

    def __init__(
        self,
        config: Config,
        metrics: Metrics,
        rtk_path: str | None,
        store: TokenTerminatorStore | None = None,
    ):
        self.config = config
        self.metrics = metrics
        self.rtk_path = rtk_path
        self.recovery = RecoveryStore(config, metrics, store)

    def transform(
        self, *, tool_name: str, args: dict, result: str, **kwargs
    ) -> str | None:
        if not self._eligible(tool_name=tool_name, args=args, result=result):
            return None

        self.metrics.add("native_attempted")
        compact = None
        if tool_name == "read_file":
            compact = self._rtk_read(args)
        if compact is None:
            compact = compact_text(result, self.config.native_max_chars)
        return self._finalize_transform(
            tool_name=tool_name,
            args=args,
            result=result,
            compact=compact,
            **kwargs,
        )

    def _eligible(self, *, tool_name: str, args: dict, result: str) -> bool:
        if not self.config.native_enabled or not isinstance(result, str):
            return False
        allowed = self.BALANCED_TOOLS | (
            self.AGGRESSIVE_TOOLS if self.config.aggressive else frozenset()
        )
        if tool_name not in allowed or len(result) < self.config.native_min_chars:
            return False

        backend = terminal_backend(args)
        if not backend_enabled(backend, self.config):
            self.metrics.add("native_skipped_backend")
            return False
        return True

    def _finalize_transform(
        self,
        *,
        tool_name: str,
        args: dict,
        result: str,
        compact: str | None,
        **kwargs,
    ) -> str | None:
        if not compact or len(compact) >= len(result):
            self.metrics.add("native_not_smaller")
            return None

        # Use the longest possible content-address identifier to reject a
        # metadata-bloated candidate before writing anything to the vault.
        prospective_note = _recovery_note(len(result), len(compact), "a_" + ("0" * 64))
        if len(f"{compact.rstrip()}\n\n{prospective_note}") >= len(result):
            self.metrics.add("native_not_smaller")
            return None

        artifact_id = self.recovery.write(
            tool_name,
            result,
            args=args,
            session_id=str(kwargs.get("session_id") or ""),
            tool_call_id=str(kwargs.get("tool_call_id") or ""),
        )
        if artifact_id is None:
            # Exact recovery is part of the acceptance contract, not optional
            # metadata. Leave the complete native result untouched.
            self.metrics.add("native_recovery_unavailable")
            return None

        note = _recovery_note(len(result), len(compact), artifact_id)
        transformed = f"{compact.rstrip()}\n\n{note}"
        if len(transformed) >= len(result):
            self.metrics.add("native_not_smaller")
            return None
        self.metrics.add("native_compressed")
        self.metrics.add("native_raw_chars", len(result))
        self.metrics.add("native_output_chars", len(transformed))
        return transformed

    def _rtk_read(self, args: dict) -> str | None:
        if not self.rtk_path:
            return None
        path_value = args.get("path") or args.get("file_path") or args.get("filename")
        if not isinstance(path_value, str) or not path_value.strip():
            return None
        cwd = command_workdir(args)
        try:
            completed = subprocess.run(
                [self.rtk_path, "read", path_value, "-l", "aggressive"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.config.timeout_ms / 1000,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return (
            completed.stdout
            if completed.returncode == 0 and completed.stdout.strip()
            else None
        )

    async def _rtk_read_async(
        self,
        args: dict,
        *,
        cancellation: CancellationToken | None = None,
    ) -> str | None:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        if not self.rtk_path:
            return None
        path_value = args.get("path") or args.get("file_path") or args.get("filename")
        if not isinstance(path_value, str) or not path_value.strip():
            return None
        process: asyncio.subprocess.Process | None = None
        communicate_task: asyncio.Task[tuple[bytes, bytes]] | None = None
        cancellation_waiter: asyncio.Task[None] | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                self.rtk_path,
                "read",
                path_value,
                "-l",
                "aggressive",
                cwd=str(command_workdir(args)),
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
                self.metrics.add("native_rtk_timeouts")
                return None
            if cancellation_waiter is not None and cancellation_waiter in done:
                raise asyncio.CancelledError
            stdout, _stderr = communicate_task.result()
            decoded = stdout.decode(errors="replace")
            return decoded if process.returncode == 0 and decoded.strip() else None
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
            self.metrics.add("native_rtk_cancelled")
            raise
        except OSError:
            self.metrics.add("native_rtk_errors")
            return None
        finally:
            if cancellation_waiter is not None:
                cancellation_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await cancellation_waiter


def compact_text(text: str, max_chars: int) -> str:
    max_chars = max(1, int(max_chars))
    clean = ANSI.sub("", text)
    lines = _collapse_consecutive(clean.splitlines())
    collapsed = "\n".join(lines)
    if len(collapsed) <= max_chars:
        return collapsed

    marker = "… lines omitted …"
    if max_chars <= len(marker):
        return marker[:max_chars]
    payload_budget = max_chars - len(marker) - 2
    head_chars = int(payload_budget * 0.72)
    tail_chars = payload_budget - head_chars
    head = collapsed[:head_chars].rstrip("\n")
    tail = collapsed[-tail_chars:].lstrip("\n") if tail_chars else ""
    return "\n".join(part for part in (head, marker, tail) if part)[:max_chars]


def _collapse_consecutive(lines: list[str]) -> list[str]:
    if not lines:
        return []
    output: list[str] = []
    previous = lines[0]
    count = 1
    for line in lines[1:]:
        if line == previous:
            count += 1
            continue
        output.append(_collapsed_line(previous, count))
        previous, count = line, 1
    output.append(_collapsed_line(previous, count))
    return output


def _collapsed_line(line: str, count: int) -> str:
    return f"{line}  [repeated ×{count}]" if count > 2 else "\n".join([line] * count)


def _recovery_note(raw_chars: int, compact_chars: int, artifact_id: str) -> str:
    savings = (
        round((raw_chars - compact_chars) / raw_chars * 100, 1) if raw_chars else 0.0
    )
    return (
        f"[Token Terminator: {savings}% fewer characters; "
        f"full artifact={artifact_id}; recover with token_terminator action=artifact_get]"
    )
