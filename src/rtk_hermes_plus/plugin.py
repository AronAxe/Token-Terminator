from __future__ import annotations

import json
import logging
from dataclasses import asdict

from .compress import NativeCompressor
from .config import Config, load_config
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
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.metrics = Metrics()
        self.rewriter = Rewriter(self.config, self.metrics)
        self.compressor = NativeCompressor(
            self.config, self.metrics, self.rewriter.rtk_path
        )

    def tool_request_middleware(self, *, tool_name: str, args: dict, **_kwargs):
        if tool_name != "terminal" or not isinstance(args, dict):
            return None
        rewritten = self._rewrite_args(args)
        if rewritten is None:
            return None
        return {
            "args": rewritten,
            "source": "rtk-hermes-plus",
            "reason": "token reduction",
        }

    def pre_tool_call(self, *, tool_name: str, args: dict, **_kwargs) -> None:
        if tool_name != "terminal" or not isinstance(args, dict):
            return
        rewritten = self._rewrite_args(args)
        if rewritten is not None:
            args.clear()
            args.update(rewritten)

    def transform_tool_result(
        self, *, tool_name: str, args: dict, result: str, **kwargs
    ):
        return self.compressor.transform(
            tool_name=tool_name, args=args, result=result, **kwargs
        )

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
        subcommand = (raw_args or "status").strip().split(maxsplit=1)[0].lower()
        if subcommand in {"reset", "reset-stats"}:
            self.metrics.reset()
            return "RTK Hermes Plus metrics reset."
        if subcommand in {"stats", "metrics"}:
            return json.dumps(self.metrics.snapshot(), indent=2, sort_keys=True)
        if subcommand in {"status", "config"}:
            config = asdict(self.config)
            config["recovery_dir"] = str(config["recovery_dir"])
            return json.dumps(
                {
                    "rtk_available": self.rewriter.available,
                    "config": config,
                    "metrics": self.metrics.snapshot(),
                },
                indent=2,
                sort_keys=True,
            )
        return "Usage: /rtk-plus [status|stats|reset-stats]"


_runtime: Runtime | None = None


def register(ctx) -> None:
    global _runtime
    runtime = Runtime()
    _runtime = runtime

    if runtime.config.mode == "off":
        logger.info("RTK Hermes Plus disabled")
        return

    register_command = getattr(ctx, "register_command", None)
    if callable(register_command):
        register_command(
            "rtk-plus",
            handler=runtime.command,
            description="RTK token savings, configuration, and metrics",
        )

    if runtime.config.terminal_enabled:
        if runtime.rewriter.available:
            register_middleware = getattr(ctx, "register_middleware", None)
            if callable(register_middleware):
                register_middleware("tool_request", runtime.tool_request_middleware)
            else:
                ctx.register_hook("pre_tool_call", runtime.pre_tool_call)
        else:
            logger.warning("rtk binary not found; terminal rewriting disabled")

    if runtime.config.native_enabled:
        ctx.register_hook("transform_tool_result", runtime.transform_tool_result)
