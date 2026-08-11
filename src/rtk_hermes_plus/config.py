from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

MODES = frozenset({"balanced", "aggressive", "native", "terminal", "suggest", "off"})
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


def _decimal(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    parts = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return parts or default


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except ImportError:
        configured = os.getenv("HERMES_HOME", "").strip()
        if configured:
            return Path(configured).expanduser()
        if sys.platform == "win32":
            local_appdata = os.getenv("LOCALAPPDATA", "").strip()
            base = (
                Path(local_appdata)
                if local_appdata
                else Path.home() / "AppData" / "Local"
            )
            return base / "hermes"
        return Path.home() / ".hermes"


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
    ledger_enabled: bool = True
    ledger_path: Path = Path.home() / ".hermes" / "rtk-plus" / "experiments.sqlite3"
    state_db_path: Path = Path.home() / ".hermes" / "state.db"
    experiment: str = "default"
    equivalent_input_usd_per_million: float = 0.0
    equivalent_output_usd_per_million: float = 0.0
    equivalent_cache_read_usd_per_million: float = 0.0
    equivalent_cache_write_usd_per_million: float = 0.0
    equivalent_rate_card: str = ""
    excluded_prefixes: tuple[str, ...] = ()

    @property
    def terminal_enabled(self) -> bool:
        return self.mode not in {"native", "off"}

    @property
    def native_enabled(self) -> bool:
        return self.mode in {"balanced", "aggressive", "native"}

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

    hermes_home = _hermes_home()
    recovery_raw = os.getenv("RTK_HERMES_PLUS_RECOVERY_DIR")
    recovery_dir = (
        Path(recovery_raw).expanduser()
        if recovery_raw
        else hermes_home / "rtk-plus" / "recovery"
    )
    ledger_raw = os.getenv("RTK_HERMES_PLUS_LEDGER_PATH")
    state_db_raw = os.getenv("RTK_HERMES_PLUS_STATE_DB")
    experiment = os.getenv("RTK_HERMES_PLUS_EXPERIMENT", "default").strip()
    experiment = experiment[:80] or "default"

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
        ledger_enabled=_boolean("RTK_HERMES_PLUS_LEDGER", True),
        ledger_path=(
            Path(ledger_raw).expanduser()
            if ledger_raw
            else hermes_home / "rtk-plus" / "experiments.sqlite3"
        ),
        state_db_path=(
            Path(state_db_raw).expanduser()
            if state_db_raw
            else hermes_home / "state.db"
        ),
        experiment=experiment,
        equivalent_input_usd_per_million=_decimal("RTK_HERMES_PLUS_EQ_INPUT_USD_PER_M"),
        equivalent_output_usd_per_million=_decimal(
            "RTK_HERMES_PLUS_EQ_OUTPUT_USD_PER_M"
        ),
        equivalent_cache_read_usd_per_million=_decimal(
            "RTK_HERMES_PLUS_EQ_CACHE_READ_USD_PER_M"
        ),
        equivalent_cache_write_usd_per_million=_decimal(
            "RTK_HERMES_PLUS_EQ_CACHE_WRITE_USD_PER_M"
        ),
        equivalent_rate_card=os.getenv("RTK_HERMES_PLUS_EQ_RATE_CARD", "").strip()[
            :120
        ],
        excluded_prefixes=_csv("RTK_HERMES_PLUS_EXCLUDE", ()),
    )
