from pathlib import Path

from rtk_hermes_plus.config import load_config


def test_defaults(monkeypatch, tmp_path):
    for key in tuple(__import__("os").environ):
        if key.startswith("RTK_HERMES_PLUS_"):
            monkeypatch.delenv(key, raising=False)
    # Path.home() follows platform-specific rules. In particular, changing HOME
    # does not redefine the Windows profile directory, so patch the API we use.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.enabled_backends == ("local",)
    assert cfg.native_enabled is True
    assert cfg.aggressive is False
    assert cfg.recovery_dir == tmp_path / ".hermes" / "rtk-plus" / "recovery"
    assert cfg.ledger_path == tmp_path / ".hermes" / "rtk-plus" / "experiments.sqlite3"
    assert cfg.state_db_path == tmp_path / ".hermes" / "state.db"


def test_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "aggressive")
    monkeypatch.setenv("RTK_HERMES_PLUS_TIMEOUT_MS", "750")
    monkeypatch.setenv("RTK_HERMES_PLUS_BACKENDS", "local,ssh")
    monkeypatch.setenv("RTK_HERMES_PLUS_EXCLUDE", "git push, Docker Exec")
    monkeypatch.setenv("RTK_HERMES_PLUS_RECOVERY_DIR", str(tmp_path / "recover"))
    monkeypatch.setenv("RTK_HERMES_PLUS_LEDGER_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("RTK_HERMES_PLUS_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("RTK_HERMES_PLUS_EXPERIMENT", "discord-test")
    monkeypatch.setenv("RTK_HERMES_PLUS_EQ_INPUT_USD_PER_M", "2.5")
    monkeypatch.setenv("RTK_HERMES_PLUS_EQ_RATE_CARD", "example-2026-08")
    cfg = load_config()
    assert cfg.aggressive is True
    assert cfg.timeout_ms == 750
    assert cfg.enabled_backends == ("local", "ssh")
    assert cfg.excluded_prefixes == ("git push", "docker exec")
    assert cfg.recovery_dir == tmp_path / "recover"
    assert cfg.ledger_path == tmp_path / "ledger.db"
    assert cfg.state_db_path == tmp_path / "state.db"
    assert cfg.experiment == "discord-test"
    assert cfg.equivalent_input_usd_per_million == 2.5
    assert cfg.equivalent_rate_card == "example-2026-08"


def test_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "nonsense")
    monkeypatch.setenv("RTK_HERMES_PLUS_TIMEOUT_MS", "many")
    monkeypatch.setenv("RTK_HERMES_PLUS_NATIVE_MIN_CHARS", "tiny")
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.timeout_ms == 500
    assert cfg.native_min_chars == 12_000


def test_native_mode_enables_only_native_compression(monkeypatch):
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "native")
    cfg = load_config()
    assert cfg.mode == "native"
    assert cfg.native_enabled is True
    assert cfg.terminal_enabled is False
    assert cfg.aggressive is False


def test_all_backend_collapses(monkeypatch):
    monkeypatch.setenv("RTK_HERMES_PLUS_BACKENDS", "local,all,ssh")
    assert load_config().enabled_backends == ("all",)
