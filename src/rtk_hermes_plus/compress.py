from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from .config import Config
from .metrics import Metrics
from .rewrite import backend_enabled, command_workdir, terminal_backend

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class RecoveryStore:
    def __init__(self, config: Config, metrics: Metrics):
        self.config = config
        self.metrics = metrics

    def write(self, tool_name: str, content: str) -> Path | None:
        try:
            directory = self.config.recovery_dir
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                directory.chmod(0o700)
            except OSError:
                pass
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)[:40] or "tool"
            path = directory / f"{time.time_ns()}_{safe_name}.log"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as handle:
                handle.write(content)
            self._rotate()
            self.metrics.add("recovery_files_written")
            return path
        except OSError:
            self.metrics.add("recovery_errors")
            return None

    def _rotate(self) -> None:
        files = sorted(
            (item for item in self.config.recovery_dir.glob("*.log") if item.is_file()),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        for stale in files[self.config.recovery_files :]:
            try:
                stale.unlink()
            except OSError:
                continue


class NativeCompressor:
    BALANCED_TOOLS = frozenset({"search_files", "process"})
    AGGRESSIVE_TOOLS = frozenset({"read_file"})

    def __init__(self, config: Config, metrics: Metrics, rtk_path: str | None):
        self.config = config
        self.metrics = metrics
        self.rtk_path = rtk_path
        self.recovery = RecoveryStore(config, metrics)

    def transform(
        self, *, tool_name: str, args: dict, result: str, **_kwargs
    ) -> str | None:
        if not self.config.native_enabled or not isinstance(result, str):
            return None
        allowed = self.BALANCED_TOOLS | (
            self.AGGRESSIVE_TOOLS if self.config.aggressive else frozenset()
        )
        if tool_name not in allowed or len(result) < self.config.native_min_chars:
            return None

        backend = terminal_backend(args)
        if not backend_enabled(backend, self.config):
            self.metrics.add("native_skipped_backend")
            return None

        self.metrics.add("native_attempted")
        compact = None
        if tool_name == "read_file":
            compact = self._rtk_read(args)
        if compact is None:
            compact = compact_text(result, self.config.native_max_chars)
        if not compact or len(compact) >= len(result):
            self.metrics.add("native_not_smaller")
            return None

        # The recovery annotation is deliberately small, but it still counts
        # against the context budget. Avoid a nominal "compression" that grows
        # the final tool result after metadata is attached.
        if len(compact) + 256 >= len(result):
            self.metrics.add("native_not_smaller")
            return None

        recovery_path = self.recovery.write(tool_name, result)
        note = _recovery_note(len(result), len(compact), recovery_path)
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


def compact_text(text: str, max_chars: int) -> str:
    clean = ANSI.sub("", text)
    lines = _collapse_consecutive(clean.splitlines())
    collapsed = "\n".join(lines)
    if len(collapsed) <= max_chars:
        return collapsed

    head_budget = int(max_chars * 0.72)
    tail_budget = max_chars - head_budget
    head = _take_head(lines, head_budget)
    tail = _take_tail(lines[len(head) :], tail_budget)
    omitted = max(0, len(lines) - len(head) - len(tail))
    middle = f"… {omitted} lines omitted …"
    return "\n".join([*head, middle, *tail])


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


def _take_head(lines: list[str], budget: int) -> list[str]:
    selected: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + 1
        if selected and used + cost > budget:
            break
        selected.append(line)
        used += cost
    return selected


def _take_tail(lines: list[str], budget: int) -> list[str]:
    selected: list[str] = []
    used = 0
    for line in reversed(lines):
        cost = len(line) + 1
        if selected and used + cost > budget:
            break
        selected.append(line)
        used += cost
    return list(reversed(selected))


def _recovery_note(raw_chars: int, compact_chars: int, path: Path | None) -> str:
    savings = (
        round((raw_chars - compact_chars) / raw_chars * 100, 1) if raw_chars else 0.0
    )
    location = str(path) if path else "unavailable"
    return f"[rtk-plus: {savings}% fewer characters; full output: {location}]"
