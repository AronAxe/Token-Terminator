from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from .metrics import Metrics
from .rewrite import command_workdir, terminal_backend
from .storage import TokenTerminatorStore

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemporalDeltaReducer:
    """Reduce repeated terminal observations to exact recoverable deltas.

    Commands are never cached or skipped. The terminal command executes first,
    the current raw result is vaulted and verified, and only then may the
    provider-visible result be replaced by a diff against the previous
    observation for the same command/workspace key.
    """

    def __init__(self, store: TokenTerminatorStore | None, metrics: Metrics):
        self.store = store
        self.metrics = metrics
        self.enabled = _env_bool("TOKEN_TERMINATOR_TEMPORAL_DELTA", True)
        self.min_chars = _env_int("TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS", 2_000, minimum=1)
        self.scope = os.getenv("TOKEN_TERMINATOR_TEMPORAL_SCOPE", "session").strip().lower()
        if self.scope not in {"session", "workspace"}:
            self.scope = "session"
        self.available = bool(self.enabled and self.store is not None)
        if self.available:
            self._initialize()

    def _initialize(self) -> None:
        if self.store is None:
            self.available = False
            return
        try:
            with self.store.connection(write=True) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS terminal_snapshots (
                        state_key TEXT PRIMARY KEY,
                        artifact_id TEXT NOT NULL,
                        command TEXT NOT NULL,
                        cwd TEXT NOT NULL,
                        backend TEXT NOT NULL,
                        session_scope TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
        except Exception:  # noqa: BLE001 - optimization must fail open
            self.available = False
            self.metrics.add("temporal_errors")

    def _identity(
        self, args: dict[str, Any], *, session_id: str
    ) -> tuple[str, str, str, str, str] | None:
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return None
        command = command.strip()
        cwd = str(command_workdir(args).expanduser().resolve())
        backend = terminal_backend(args)
        session_scope = session_id if self.scope == "session" else ""
        material = json.dumps(
            {
                "command": command,
                "cwd": cwd,
                "backend": backend,
                "session": session_scope,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        state_key = hashlib.sha256(material).hexdigest()
        return state_key, command, cwd, backend, session_scope

    def _previous(self, state_key: str) -> str | None:
        if self.store is None:
            return None
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT artifact_id FROM terminal_snapshots WHERE state_key=?",
                (state_key,),
            ).fetchone()
        return str(row["artifact_id"]) if row is not None else None

    def _remember(
        self,
        *,
        state_key: str,
        artifact_id: str,
        command: str,
        cwd: str,
        backend: str,
        session_scope: str,
    ) -> None:
        if self.store is None:
            return
        with self.store.connection(write=True) as conn:
            conn.execute(
                """
                INSERT INTO terminal_snapshots(
                    state_key, artifact_id, command, cwd, backend,
                    session_scope, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    artifact_id=excluded.artifact_id,
                    command=excluded.command,
                    cwd=excluded.cwd,
                    backend=excluded.backend,
                    session_scope=excluded.session_scope,
                    updated_at=excluded.updated_at
                """,
                (
                    state_key,
                    artifact_id,
                    command,
                    cwd,
                    backend,
                    session_scope,
                    _utc_now(),
                ),
            )

    @staticmethod
    def _delta(
        previous: str,
        current: str,
        *,
        previous_id: str,
        current_id: str,
        command: str,
    ) -> str:
        if previous == current:
            return (
                "[Token Terminator temporal delta: no output changes since the "
                f"previous execution | current={current_id} | previous={previous_id} | "
                "recover exact current output with token_terminator "
                "action=artifact_get]"
            )

        label = command.replace("\n", " ")[:80] or "terminal"
        diff = "\n".join(
            difflib.unified_diff(
                previous.splitlines(),
                current.splitlines(),
                fromfile=f"{label} :: {previous_id}",
                tofile=f"{label} :: {current_id}",
                lineterm="",
                n=3,
            )
        )
        header = (
            f"[Token Terminator temporal delta | current={current_id} | "
            f"previous={previous_id} | exact current output: token_terminator "
            "action=artifact_get]"
        )
        return f"{header}\n{diff}" if diff else header

    def transform(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        session_id: str = "",
        tool_call_id: str = "",
        **_kwargs: Any,
    ) -> str | None:
        if (
            not self.available
            or self.store is None
            or tool_name != "terminal"
            or not isinstance(args, dict)
            or not isinstance(result, str)
            or len(result) < self.min_chars
        ):
            return None

        identity = self._identity(args, session_id=str(session_id or ""))
        if identity is None:
            return None
        state_key, command, cwd, backend, session_scope = identity
        self.metrics.add("temporal_attempted")

        try:
            stored = self.store.put_artifact(
                result,
                tool_name="terminal",
                args=args,
                session_id=str(session_id or ""),
                tool_call_id=str(tool_call_id or ""),
            )
            current = self.store.get_artifact(stored.artifact_id)
            if current.content != result or current.sha256 != stored.sha256:
                self.metrics.add("temporal_errors")
                return None

            previous_id = self._previous(state_key)
            candidate: str | None = None
            if previous_id:
                try:
                    previous = self.store.get_artifact(previous_id)
                    candidate = self._delta(
                        previous.content,
                        result,
                        previous_id=previous.artifact_id,
                        current_id=current.artifact_id,
                        command=command,
                    )
                except KeyError:
                    previous_id = None

            self._remember(
                state_key=state_key,
                artifact_id=current.artifact_id,
                command=command,
                cwd=cwd,
                backend=backend,
                session_scope=session_scope,
            )

            if previous_id is None:
                self.metrics.add("temporal_baselines")
                return None
            if not candidate or len(candidate) >= len(result):
                self.metrics.add("temporal_not_smaller")
                return None

            self.metrics.add("temporal_reduced")
            self.metrics.add("temporal_raw_chars", len(result))
            self.metrics.add("temporal_output_chars", len(candidate))
            return candidate
        except Exception:  # noqa: BLE001 - terminal evidence must fail open
            self.metrics.add("temporal_errors")
            return None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "min_chars": self.min_chars,
            "scope": self.scope,
        }
