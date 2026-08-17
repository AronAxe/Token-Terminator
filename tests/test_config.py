from rtk_hermes_plus.config import load_config


def test_defaults(monkeypatch, tmp_path):
    for key in tuple(__import__("os").environ):
        if key.startswith(("TOKEN_TERMINATOR_", "RTK_HERMES_PLUS_")):
            monkeypatch.delenv(key, raising=False)
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.enabled_backends == ("local",)
    assert cfg.native_enabled is True
    assert cfg.aggressive is False

    assert cfg.ledger_path == hermes_home / "token-terminator" / "experiments.sqlite3"
    assert cfg.db_path == hermes_home / "token-terminator" / "artifacts.sqlite3"
    assert cfg.state_db_path == hermes_home / "state.db"


def test_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("TOKEN_TERMINATOR_MODE", "aggressive")
    monkeypatch.setenv("TOKEN_TERMINATOR_TIMEOUT_MS", "750")
    monkeypatch.setenv("TOKEN_TERMINATOR_BACKENDS", "local,ssh")
    monkeypatch.setenv("TOKEN_TERMINATOR_EXCLUDE", "git push, Docker Exec")

    monkeypatch.setenv("TOKEN_TERMINATOR_LEDGER_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("TOKEN_TERMINATOR_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("TOKEN_TERMINATOR_EXPERIMENT", "discord-test")
    monkeypatch.setenv("TOKEN_TERMINATOR_EQ_INPUT_USD_PER_M", "2.5")
    monkeypatch.setenv("TOKEN_TERMINATOR_EQ_RATE_CARD", "example-2026-08")
    cfg = load_config()
    assert cfg.aggressive is True
    assert cfg.timeout_ms == 750
    assert cfg.enabled_backends == ("local", "ssh")
    assert cfg.excluded_prefixes == ("git push", "docker exec")

    assert cfg.ledger_path == tmp_path / "ledger.db"
    assert cfg.state_db_path == tmp_path / "state.db"
    assert cfg.experiment == "discord-test"
    assert cfg.equivalent_input_usd_per_million == 2.5
    assert cfg.equivalent_rate_card == "example-2026-08"


def test_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_MODE", "nonsense")
    monkeypatch.setenv("TOKEN_TERMINATOR_TIMEOUT_MS", "many")
    monkeypatch.setenv("TOKEN_TERMINATOR_NATIVE_MIN_CHARS", "tiny")
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.timeout_ms == 500
    assert cfg.native_min_chars == 12_000


def test_environment_artifact_minimum_is_clamped_to_maximum(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS", "3000000")
    monkeypatch.setenv("TOKEN_TERMINATOR_MAX_ARTIFACT_CHARS", "2000000")

    cfg = load_config()

    assert cfg.min_artifact_chars == 2_000_000
    assert cfg.max_artifact_chars == 2_000_000


def test_native_mode_enables_only_native_compression(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_MODE", "native")
    cfg = load_config()
    assert cfg.mode == "native"
    assert cfg.native_enabled is True
    assert cfg.terminal_enabled is False
    assert cfg.aggressive is False


def test_all_backend_collapses(monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_BACKENDS", "local,all,ssh")
    assert load_config().enabled_backends == ("all",)


def test_legacy_rtk_environment_remains_a_compatibility_fallback(monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_MODE", raising=False)
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "native")
    assert load_config().mode == "native"
