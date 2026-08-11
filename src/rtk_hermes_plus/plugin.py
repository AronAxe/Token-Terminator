from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from ._version import __version__
from .compress import NativeCompressor
from .config import MODES, Config, load_config
from .ledger import ExperimentLedger, dump_compare
from .metrics import Metrics
from .rewrite import (
    Rewriter,
    backend_enabled,
    command_excluded,
    command_workdir,
    is_pytest_command,
    pytest_config_is_quiet,
    terminal_backend,
)

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, config: Config | None = None, *, profile_name: str = "default"):
        self.config = config or load_config()
        self.metrics = Metrics()
        self.rewriter = Rewriter(self.config, self.metrics)
        self.compressor = NativeCompressor(
            self.config, self.metrics, self.rewriter.rtk_path
        )
        self.ledger = ExperimentLedger(
            self.config.ledger_path,
            self.config.state_db_path,
            plugin_version=__version__,
            experiment=self.config.experiment,
            profile=profile_name,
            equivalent_rates={
                "input": self.config.equivalent_input_usd_per_million,
                "output": self.config.equivalent_output_usd_per_million,
                "cache_read": self.config.equivalent_cache_read_usd_per_million,
                "cache_write": self.config.equivalent_cache_write_usd_per_million,
            },
            equivalent_rate_card=self.config.equivalent_rate_card,
            enabled=self.config.ledger_enabled,
        )

    def tool_request_middleware(self, *, tool_name: str, args: dict, **kwargs):
        if tool_name != "terminal" or not isinstance(args, dict):
            return None
        rewritten = self._rewrite_args(args)
        if rewritten is None:
            return None
        self._ensure_ledger_session(kwargs.get("session_id"))
        self.ledger.record_rewrite(
            session_id=str(kwargs.get("session_id") or ""),
            turn_id=str(kwargs.get("turn_id") or ""),
        )
        return {
            "args": rewritten,
            "source": "rtk-hermes-plus",
            "reason": "token reduction",
        }

    def pre_tool_call(self, *, tool_name: str, args: dict, **kwargs) -> None:
        self.observe_tool_call(tool_name=tool_name, args=args, **kwargs)
        if tool_name != "terminal" or not isinstance(args, dict):
            return
        rewritten = self._rewrite_args(args)
        if rewritten is not None:
            args.clear()
            args.update(rewritten)
            self._ensure_ledger_session(kwargs.get("session_id"))
            self.ledger.record_rewrite(
                session_id=str(kwargs.get("session_id") or ""),
                turn_id=str(kwargs.get("turn_id") or ""),
            )

    def observe_tool_call(self, *, tool_name: str, args: dict, **kwargs) -> None:
        if tool_name != "read_file" or not isinstance(args, dict):
            return
        value = args.get("path") or args.get("file_path") or args.get("filename")
        if not isinstance(value, str) or not value.strip():
            return
        if not _is_recovery_path(value, self.config.recovery_dir):
            return
        self._ensure_ledger_session(kwargs.get("session_id"))
        self.ledger.record_recovery_read(
            session_id=str(kwargs.get("session_id") or ""),
            turn_id=str(kwargs.get("turn_id") or ""),
        )

    def transform_tool_result(
        self, *, tool_name: str, args: dict, result: str, **kwargs
    ):
        transformed = self.compressor.transform(
            tool_name=tool_name, args=args, result=result, **kwargs
        )
        if transformed is not None:
            self._ensure_ledger_session(kwargs.get("session_id"))
            self.ledger.record_native(
                session_id=str(kwargs.get("session_id") or ""),
                turn_id=str(kwargs.get("turn_id") or ""),
                raw_chars=len(result),
                output_chars=len(transformed),
            )
        return transformed

    def on_session_start(self, *, session_id: str = "", **_kwargs) -> None:
        self._ensure_ledger_session(session_id)

    def pre_llm_call(
        self,
        *,
        session_id: str = "",
        turn_id: str = "",
        task_id: str = "",
        user_message=None,
        model: str = "",
        platform: str = "",
        **_kwargs,
    ) -> None:
        self.ledger.start_turn(
            session_id=str(session_id or ""),
            turn_id=str(turn_id or ""),
            task_id=str(task_id or ""),
            mode=self.config.mode,
            user_message=user_message,
            model=str(model or ""),
            platform=str(platform or ""),
        )

    def on_session_end(
        self,
        *,
        session_id: str = "",
        turn_id: str = "",
        completed: bool = False,
        failed: bool = False,
        interrupted: bool = False,
        turn_exit_reason: str = "",
        **_kwargs,
    ) -> None:
        self.ledger.finish_turn(
            session_id=str(session_id or ""),
            turn_id=str(turn_id or ""),
            mode=self.config.mode,
            completed=bool(completed),
            failed=bool(failed),
            interrupted=bool(interrupted),
            turn_exit_reason=str(turn_exit_reason or ""),
        )

    def on_session_finalize(self, *, session_id: str = "", **_kwargs) -> None:
        self.ledger.finalize_session(str(session_id or ""), self.config.mode)

    def _ensure_ledger_session(self, session_id) -> None:
        if session_id:
            self.ledger.ensure_session(str(session_id), self.config.mode)

    def _rewrite_args(self, args: dict) -> dict | None:
        if not self.config.terminal_enabled:
            return None
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return None

        stripped = command.lstrip()
        if stripped.startswith(("rtk ", ": RTK && ")):
            return None
        if command_excluded(command, self.config.excluded_prefixes):
            self.metrics.add("rewrite_skipped_excluded")
            return None

        backend = terminal_backend(args)
        if not backend_enabled(backend, self.config):
            self.metrics.add("rewrite_skipped_backend")
            return None

        cwd = command_workdir(args)
        if (
            self.config.pytest_quiet_guard
            and is_pytest_command(command)
            and pytest_config_is_quiet(cwd)
        ):
            self.metrics.add("rewrite_skipped_pytest_quiet_config")
            return None

        result = self.rewriter.rewrite(command, cwd=cwd)
        if result.command is None:
            self.metrics.add("rewrite_passthrough")
            return None

        self.metrics.add("rewrite_candidates")
        if self.config.mode == "suggest":
            self.metrics.add("rewrite_suggested")
            return None

        output = dict(args)
        output["command"] = (
            f": RTK && {result.command}"
            if self.config.preview_marker
            else result.command
        )
        self.metrics.add("rewritten")
        return output

    def command(self, raw_args: str = "") -> str:
        parts = (raw_args or "status").strip().split()
        subcommand = parts[0].lower() if parts else "status"
        if subcommand in {"reset", "reset-stats"}:
            self.metrics.reset()
            return "RTK Hermes Plus metrics reset."
        if subcommand in {"stats", "metrics"}:
            return json.dumps(self.metrics.snapshot(), indent=2, sort_keys=True)
        if subcommand == "compare":
            modes = ("native", "balanced")
            requested = tuple(part.lower() for part in parts[1:3])
            if len(requested) == 2 and all(mode in MODES for mode in requested):
                modes = requested
            return dump_compare(self.ledger.compare(modes))
        if subcommand in {"status", "config"}:
            config = asdict(self.config)
            config = {
                key: str(value) if isinstance(value, Path) else value
                for key, value in config.items()
            }
            return json.dumps(
                {
                    "rtk_available": self.rewriter.available,
                    "config": config,
                    "metrics": self.metrics.snapshot(),
                    "ledger": {
                        "available": self.ledger.available,
                        "error": self.ledger.error,
                        "experiment": self.ledger.experiment,
                        "path": str(self.ledger.path),
                    },
                },
                indent=2,
                sort_keys=True,
            )
        return "Usage: /rtk-plus [status|stats|compare [mode-a mode-b]|reset-stats]"


_runtime: Runtime | None = None


def register(ctx) -> None:
    global _runtime
    runtime = Runtime(profile_name=getattr(ctx, "profile_name", "default"))
    _runtime = runtime

    if runtime.config.mode == "off":
        logger.info("RTK Hermes Plus transformations disabled; ledger remains active")

    register_command = getattr(ctx, "register_command", None)
    if callable(register_command):
        register_command(
            "rtk-plus",
            handler=runtime.command,
            description="RTK token savings, configuration, and metrics",
        )

    tool_observer_registered = False
    if runtime.config.terminal_enabled:
        if runtime.rewriter.available:
            register_middleware = getattr(ctx, "register_middleware", None)
            if callable(register_middleware):
                register_middleware("tool_request", runtime.tool_request_middleware)
                ctx.register_hook("pre_tool_call", runtime.observe_tool_call)
                tool_observer_registered = True
            else:
                ctx.register_hook("pre_tool_call", runtime.pre_tool_call)
                tool_observer_registered = True
        else:
            logger.warning("rtk binary not found; terminal rewriting disabled")

    if runtime.config.native_enabled:
        ctx.register_hook("transform_tool_result", runtime.transform_tool_result)

    if runtime.ledger.available:
        if not tool_observer_registered:
            ctx.register_hook("pre_tool_call", runtime.observe_tool_call)
        ctx.register_hook("on_session_start", runtime.on_session_start)
        ctx.register_hook("pre_llm_call", runtime.pre_llm_call)
        ctx.register_hook("on_session_end", runtime.on_session_end)
        ctx.register_hook("on_session_finalize", runtime.on_session_finalize)


def _is_recovery_path(value: str, recovery_dir: Path) -> bool:
    try:
        path = Path(value).expanduser().resolve(strict=False)
        root = recovery_dir.expanduser().resolve(strict=False)
        return path == root or root in path.parents
    except (OSError, RuntimeError, ValueError):
        return False
