from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

MODES = frozenset({"balanced", "aggressive", "native", "terminal", "suggest", "off"})
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _env(name: str, legacy: str | None = None) -> str | None:
    """Read the Token Terminator variable, with one-release RTK compatibility."""
    value = os.getenv(name)
    if value is not None:
        return value
    return os.getenv(legacy) if legacy else None


def _integer(
    name: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int | None = None,
    legacy: str | None = None,
) -> int:
    raw = _env(name, legacy)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    value = max(minimum, value)
    return min(maximum, value) if maximum is not None else value


def _boolean(name: str, default: bool, *, legacy: str | None = None) -> bool:
    raw = _env(name, legacy)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def _decimal(name: str, default: float = 0.0, *, legacy: str | None = None) -> float:
    raw = _env(name, legacy)
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _probability(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return default


def _csv(
    name: str,
    default: tuple[str, ...],
    *,
    legacy: str | None = None,
) -> tuple[str, ...]:
    raw = _env(name, legacy)
    if raw is None:
        return default
    parts = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return parts or default


def _hermes_home() -> Path:
    configured = os.getenv("HERMES_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except ImportError:
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
    rtk_path: Path | None = None
    cache_ttl_seconds: int = 600
    cache_size: int = 512
    preview_marker: bool = False
    pytest_quiet_guard: bool = True
    native_min_chars: int = 12_000
    native_max_chars: int = 8_000
    ledger_enabled: bool = True
    ledger_path: Path = (
        Path.home() / ".hermes" / "token-terminator" / "experiments.sqlite3"
    )
    state_db_path: Path = Path.home() / ".hermes" / "state.db"
    experiment: str = "default"
    equivalent_input_usd_per_million: float = 0.0
    equivalent_output_usd_per_million: float = 0.0
    equivalent_cache_read_usd_per_million: float = 0.0
    equivalent_cache_write_usd_per_million: float = 0.0
    equivalent_rate_card: str = ""
    excluded_prefixes: tuple[str, ...] = ()

    # Request compiler, content-addressed vault, and bounded working-state graph.
    db_path: Path = Path.home() / ".hermes" / "token-terminator" / "artifacts.sqlite3"
    enabled: bool = True
    min_artifact_chars: int = 8_000
    max_artifact_chars: int = 2_000_000
    vault_max_bytes: int = 536_870_912
    vault_high_water_pct: int = 90
    vault_low_water_pct: int = 80
    inline_lease_exposures: int = 1
    # Context compaction: aggressive vaulting of old tool results and turn collapsing.
    context_compaction_enabled: bool = True
    context_min_vault_chars: int = 4_000
    context_collapse_after_turns: int = 6
    context_inline_recent_turns: int = 5

    # Optional external semantic context gate. Jev augments, never replaces,
    # the deterministic compiler/compactor/vault pipeline.
    jev_enabled: bool = False
    jev_provider: str = "auto"
    jev_api_key: str = ""
    jev_model: str = "~typesafe/jev-latest"
    jev_timeout_ms: int = 1500
    jev_relevance_threshold: float = 0.15
    jev_min_message_chars: int = 600
    jev_max_candidates: int = 12
    jev_max_candidate_chars: int = 12_000
    jev_max_state_chars: int = 60_000

    # Disabled by default. This is a bounded working-state selector, not the
    # principal's broader graph-reasoning architecture.
    graph_context_chars: int = 0
    max_artifact_page_chars: int = 20_000
    max_search_results: int = 50

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(MODES))}")
        for name in ("ledger_path", "state_db_path", "db_path"):
            object.__setattr__(self, name, Path(getattr(self, name)).expanduser())
        if self.rtk_path is not None:
            object.__setattr__(self, "rtk_path", Path(self.rtk_path).expanduser())
        for name in (
            "inline_lease_exposures",
            "graph_context_chars",
            "context_collapse_after_turns",
            "context_inline_recent_turns",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "min_artifact_chars",
            "max_artifact_chars",
            "vault_max_bytes",
            "max_artifact_page_chars",
            "max_search_results",
            "jev_timeout_ms",
            "jev_min_message_chars",
            "jev_max_candidates",
            "jev_max_candidate_chars",
            "jev_max_state_chars",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.min_artifact_chars > self.max_artifact_chars:
            raise ValueError("min_artifact_chars must not exceed max_artifact_chars")
        if not 0.0 <= self.jev_relevance_threshold <= 1.0:
            raise ValueError("jev_relevance_threshold must be between 0 and 1")
        if not 0 <= self.vault_low_water_pct < self.vault_high_water_pct <= 100:
            raise ValueError("vault watermarks must satisfy 0 <= low < high <= 100")
        if (
            self.context_collapse_after_turns > 0
            and self.context_collapse_after_turns < self.context_inline_recent_turns
        ):
            raise ValueError(
                "context_collapse_after_turns must be 0 or at least "
                "context_inline_recent_turns"
            )

    @property
    def terminal_enabled(self) -> bool:
        return self.enabled and self.mode not in {"native", "off"}

    @property
    def native_enabled(self) -> bool:
        return self.enabled and self.mode in {"balanced", "aggressive", "native"}

    @property
    def compiler_enabled(self) -> bool:
        return self.enabled and self.mode in {"balanced", "aggressive"}

    @property
    def evidence_capture_enabled(self) -> bool:
        return self.compiler_enabled

    @property
    def aggressive(self) -> bool:
        return self.mode == "aggressive"

    @classmethod
    def from_env(cls) -> Config:
        return load_config()


def load_config() -> Config:
    mode = (
        (_env("TOKEN_TERMINATOR_MODE", "RTK_HERMES_PLUS_MODE") or "balanced")
        .strip()
        .lower()
    )
    if mode not in MODES:
        mode = "balanced"

    backends = _csv(
        "TOKEN_TERMINATOR_BACKENDS",
        ("local",),
        legacy="RTK_HERMES_PLUS_BACKENDS",
    )
    if "all" in backends:
        backends = ("all",)

    hermes_home = _hermes_home()
    data_dir = hermes_home / "token-terminator"

    ledger_raw = _env("TOKEN_TERMINATOR_LEDGER_PATH", "RTK_HERMES_PLUS_LEDGER_PATH")
    state_db_raw = _env("TOKEN_TERMINATOR_STATE_DB", "RTK_HERMES_PLUS_STATE_DB")
    db_raw = _env("TOKEN_TERMINATOR_DB_PATH")
    experiment = (
        _env("TOKEN_TERMINATOR_EXPERIMENT", "RTK_HERMES_PLUS_EXPERIMENT") or "default"
    ).strip()
    experiment = experiment[:80] or "default"
    min_artifact_chars = _integer(
        "TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS",
        8_000,
        minimum=1,
    )
    max_artifact_chars = _integer(
        "TOKEN_TERMINATOR_MAX_ARTIFACT_CHARS",
        2_000_000,
        minimum=1,
        maximum=50_000_000,
    )
    # Environment configuration must not prevent the plugin from loading.
    # Keep direct Config construction strict, but clamp an inconsistent pair
    # supplied by environment variables to the safest usable boundary.
    min_artifact_chars = min(min_artifact_chars, max_artifact_chars)

    rtk_raw = _env("TOKEN_TERMINATOR_RTK_PATH")
    jev_provider = (_env("TOKEN_TERMINATOR_JEV_PROVIDER") or "auto").strip().lower()
    if jev_provider not in {"auto", "openrouter", "typesafe"}:
        jev_provider = "auto"

    openrouter_jev_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    # TOKEN_TERMINATOR_JEV_API_KEY was introduced in v0.8.0 as a direct
    # TypeSafe credential. Keep it as a temporary compatibility alias.
    typesafe_jev_key = (
        os.getenv("TYPESAFE_API_KEY", "")
        or _env("TOKEN_TERMINATOR_JEV_API_KEY")
        or ""
    ).strip()

    if jev_provider == "auto":
        if openrouter_jev_key:
            jev_provider = "openrouter"
        elif typesafe_jev_key:
            jev_provider = "typesafe"

    if jev_provider == "typesafe":
        jev_api_key = typesafe_jev_key
        default_jev_model = "jev-latest"
    else:
        jev_api_key = openrouter_jev_key
        default_jev_model = "~typesafe/jev-latest"

    jev_model = (_env("TOKEN_TERMINATOR_JEV_MODEL") or default_jev_model).strip()
    if jev_provider == "openrouter":
        if jev_model == "jev-latest":
            jev_model = "~typesafe/jev-latest"
        elif jev_model.startswith("jev-"):
            jev_model = f"typesafe/{jev_model}"
    elif jev_provider == "typesafe":
        if jev_model.startswith("~typesafe/"):
            jev_model = jev_model.removeprefix("~typesafe/")
        elif jev_model.startswith("typesafe/"):
            jev_model = jev_model.removeprefix("typesafe/")
    jev_model = jev_model[:120] or default_jev_model
    context_inline_recent_turns = _integer(
        "TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS", 5, minimum=0
    )
    context_collapse_after_turns = _integer(
        "TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS", 6, minimum=0
    )
    if (
        context_collapse_after_turns > 0
        and context_collapse_after_turns < context_inline_recent_turns
    ):
        context_collapse_after_turns = context_inline_recent_turns
    vault_high_water_pct = _integer(
        "TOKEN_TERMINATOR_VAULT_HIGH_WATER_PCT", 90, minimum=1, maximum=100
    )
    vault_low_water_pct = _integer(
        "TOKEN_TERMINATOR_VAULT_LOW_WATER_PCT", 80, minimum=0, maximum=99
    )
    if vault_low_water_pct >= vault_high_water_pct:
        vault_low_water_pct = max(0, vault_high_water_pct - 10)

    config = Config(
        mode=mode,
        enabled=_boolean("TOKEN_TERMINATOR_ENABLED", True),
        timeout_ms=_integer(
            "TOKEN_TERMINATOR_TIMEOUT_MS",
            500,
            minimum=50,
            legacy="RTK_HERMES_PLUS_TIMEOUT_MS",
        ),
        enabled_backends=backends,
        rtk_path=Path(rtk_raw).expanduser() if rtk_raw else None,
        cache_ttl_seconds=_integer(
            "TOKEN_TERMINATOR_CACHE_TTL",
            600,
            legacy="RTK_HERMES_PLUS_CACHE_TTL",
        ),
        cache_size=_integer(
            "TOKEN_TERMINATOR_CACHE_SIZE",
            512,
            legacy="RTK_HERMES_PLUS_CACHE_SIZE",
        ),
        preview_marker=_boolean(
            "TOKEN_TERMINATOR_PREVIEW_MARKER",
            False,
            legacy="RTK_HERMES_PLUS_PREVIEW_MARKER",
        ),
        pytest_quiet_guard=_boolean(
            "TOKEN_TERMINATOR_PYTEST_GUARD",
            True,
            legacy="RTK_HERMES_PLUS_PYTEST_GUARD",
        ),
        native_min_chars=_integer(
            "TOKEN_TERMINATOR_NATIVE_MIN_CHARS",
            12_000,
            minimum=1_000,
            legacy="RTK_HERMES_PLUS_NATIVE_MIN_CHARS",
        ),
        native_max_chars=_integer(
            "TOKEN_TERMINATOR_NATIVE_MAX_CHARS",
            8_000,
            minimum=1_000,
            legacy="RTK_HERMES_PLUS_NATIVE_MAX_CHARS",
        ),
        ledger_enabled=_boolean(
            "TOKEN_TERMINATOR_LEDGER",
            True,
            legacy="RTK_HERMES_PLUS_LEDGER",
        ),
        ledger_path=Path(ledger_raw).expanduser()
        if ledger_raw
        else data_dir / "experiments.sqlite3",
        state_db_path=Path(state_db_raw).expanduser()
        if state_db_raw
        else hermes_home / "state.db",
        experiment=experiment,
        equivalent_input_usd_per_million=_decimal(
            "TOKEN_TERMINATOR_EQ_INPUT_USD_PER_M",
            legacy="RTK_HERMES_PLUS_EQ_INPUT_USD_PER_M",
        ),
        equivalent_output_usd_per_million=_decimal(
            "TOKEN_TERMINATOR_EQ_OUTPUT_USD_PER_M",
            legacy="RTK_HERMES_PLUS_EQ_OUTPUT_USD_PER_M",
        ),
        equivalent_cache_read_usd_per_million=_decimal(
            "TOKEN_TERMINATOR_EQ_CACHE_READ_USD_PER_M",
            legacy="RTK_HERMES_PLUS_EQ_CACHE_READ_USD_PER_M",
        ),
        equivalent_cache_write_usd_per_million=_decimal(
            "TOKEN_TERMINATOR_EQ_CACHE_WRITE_USD_PER_M",
            legacy="RTK_HERMES_PLUS_EQ_CACHE_WRITE_USD_PER_M",
        ),
        equivalent_rate_card=(
            _env("TOKEN_TERMINATOR_EQ_RATE_CARD", "RTK_HERMES_PLUS_EQ_RATE_CARD") or ""
        ).strip()[:120],
        excluded_prefixes=_csv(
            "TOKEN_TERMINATOR_EXCLUDE",
            (),
            legacy="RTK_HERMES_PLUS_EXCLUDE",
        ),
        db_path=Path(db_raw).expanduser() if db_raw else data_dir / "artifacts.sqlite3",
        min_artifact_chars=min_artifact_chars,
        max_artifact_chars=max_artifact_chars,
        vault_max_bytes=_integer(
            "TOKEN_TERMINATOR_VAULT_MAX_BYTES",
            536_870_912,
            minimum=1,
            maximum=100_000_000_000,
        ),
        vault_high_water_pct=vault_high_water_pct,
        vault_low_water_pct=vault_low_water_pct,
        inline_lease_exposures=_integer(
            "TOKEN_TERMINATOR_INLINE_LEASES",
            1,
            minimum=0,
            maximum=100,
        ),
        graph_context_chars=_integer(
            "TOKEN_TERMINATOR_WORKING_GRAPH_CHARS",
            0,
            minimum=0,
        ),
        max_artifact_page_chars=_integer(
            "TOKEN_TERMINATOR_MAX_PAGE_CHARS",
            20_000,
            minimum=1,
        ),
        max_search_results=_integer(
            "TOKEN_TERMINATOR_MAX_SEARCH_RESULTS",
            50,
            minimum=1,
            maximum=500,
        ),
        context_compaction_enabled=_boolean(
            "TOKEN_TERMINATOR_CONTEXT_COMPACTION",
            True,
        ),
        context_min_vault_chars=_integer(
            "TOKEN_TERMINATOR_CONTEXT_MIN_VAULT_CHARS",
            4_000,
            minimum=100,
        ),
        context_collapse_after_turns=context_collapse_after_turns,
        context_inline_recent_turns=context_inline_recent_turns,
        jev_enabled=_boolean("TOKEN_TERMINATOR_JEV", False),
        jev_provider=jev_provider,
        jev_api_key=jev_api_key,
        jev_model=jev_model,
        jev_timeout_ms=_integer(
            "TOKEN_TERMINATOR_JEV_TIMEOUT_MS",
            1500,
            minimum=100,
            maximum=30_000,
        ),
        jev_relevance_threshold=_probability(
            "TOKEN_TERMINATOR_JEV_RELEVANCE_THRESHOLD",
            0.15,
        ),
        jev_min_message_chars=_integer(
            "TOKEN_TERMINATOR_JEV_MIN_MESSAGE_CHARS",
            600,
            minimum=100,
        ),
        jev_max_candidates=_integer(
            "TOKEN_TERMINATOR_JEV_MAX_CANDIDATES",
            12,
            minimum=1,
            maximum=64,
        ),
        jev_max_candidate_chars=_integer(
            "TOKEN_TERMINATOR_JEV_MAX_CANDIDATE_CHARS",
            12_000,
            minimum=500,
            maximum=500_000,
        ),
        jev_max_state_chars=_integer(
            "TOKEN_TERMINATOR_JEV_MAX_STATE_CHARS",
            60_000,
            minimum=1_000,
            maximum=2_000_000,
        ),
    )
    return config
