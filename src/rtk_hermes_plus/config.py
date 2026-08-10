from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MODES = frozenset({"balanced", "aggressive", "terminal", "suggest", "off"})
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _integer(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    parts = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return parts or default


@dataclass(frozen=True)
class Config:
    mode: str = "balanced"
    timeout_ms: int = 500
    enabled_backends: tuple[str, ...] = ("local",)
    cache_ttl_seconds: int = 600
    cache_size: int = 512
    preview_marker: bool = False
    pytest_quiet_guard: bool = True
    native_min_chars: int = 12_000
    native_max_chars: int = 8_000
    recovery_files: int = 20
    recovery_dir: Path = Path.home() / ".hermes" / "rtk-plus" / "recovery"
    excluded_prefixes: tuple[str, ...] = ()

    @property
    def terminal_enabled(self) -> bool:
        return self.mode not in {"off"}

    @property
    def native_enabled(self) -> bool:
        return self.mode in {"balanced", "aggressive"}

    @property
    def aggressive(self) -> bool:
        return self.mode == "aggressive"


def load_config() -> Config:
    mode = os.getenv("RTK_HERMES_PLUS_MODE", "balanced").strip().lower()
    if mode not in MODES:
        mode = "balanced"

    backends = _csv("RTK_HERMES_PLUS_BACKENDS", ("local",))
    if "all" in backends:
        backends = ("all",)

    recovery_raw = os.getenv("RTK_HERMES_PLUS_RECOVERY_DIR")
    recovery_dir = (
        Path(recovery_raw).expanduser()
        if recovery_raw
        else Path.home() / ".hermes" / "rtk-plus" / "recovery"
    )

    return Config(
        mode=mode,
        timeout_ms=_integer("RTK_HERMES_PLUS_TIMEOUT_MS", 500, minimum=50),
        enabled_backends=backends,
        cache_ttl_seconds=_integer("RTK_HERMES_PLUS_CACHE_TTL", 600),
        cache_size=_integer("RTK_HERMES_PLUS_CACHE_SIZE", 512),
        preview_marker=_boolean("RTK_HERMES_PLUS_PREVIEW_MARKER", False),
        pytest_quiet_guard=_boolean("RTK_HERMES_PLUS_PYTEST_GUARD", True),
        native_min_chars=_integer(
            "RTK_HERMES_PLUS_NATIVE_MIN_CHARS", 12_000, minimum=1_000
        ),
        native_max_chars=_integer(
            "RTK_HERMES_PLUS_NATIVE_MAX_CHARS", 8_000, minimum=1_000
        ),
        recovery_files=_integer("RTK_HERMES_PLUS_RECOVERY_FILES", 20),
        recovery_dir=recovery_dir,
        excluded_prefixes=_csv("RTK_HERMES_PLUS_EXCLUDE", ()),
    )
