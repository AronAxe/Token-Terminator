from rtk_hermes_plus.config import load_config


def test_defaults(monkeypatch, tmp_path):
    for key in tuple(__import__("os").environ):
        if key.startswith("RTK_HERMES_PLUS_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.enabled_backends == ("local",)
    assert cfg.native_enabled is True
    assert cfg.aggressive is False
    assert cfg.recovery_dir == tmp_path / ".hermes" / "rtk-plus" / "recovery"


def test_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "aggressive")
    monkeypatch.setenv("RTK_HERMES_PLUS_TIMEOUT_MS", "750")
    monkeypatch.setenv("RTK_HERMES_PLUS_BACKENDS", "local,ssh")
    monkeypatch.setenv("RTK_HERMES_PLUS_EXCLUDE", "git push, Docker Exec")
    monkeypatch.setenv("RTK_HERMES_PLUS_RECOVERY_DIR", str(tmp_path / "recover"))
    cfg = load_config()
    assert cfg.aggressive is True
    assert cfg.timeout_ms == 750
    assert cfg.enabled_backends == ("local", "ssh")
    assert cfg.excluded_prefixes == ("git push", "docker exec")
    assert cfg.recovery_dir == tmp_path / "recover"


def test_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("RTK_HERMES_PLUS_MODE", "nonsense")
    monkeypatch.setenv("RTK_HERMES_PLUS_TIMEOUT_MS", "many")
    monkeypatch.setenv("RTK_HERMES_PLUS_NATIVE_MIN_CHARS", "tiny")
    cfg = load_config()
    assert cfg.mode == "balanced"
    assert cfg.timeout_ms == 500
    assert cfg.native_min_chars == 12_000


def test_all_backend_collapses(monkeypatch):
    monkeypatch.setenv("RTK_HERMES_PLUS_BACKENDS", "local,all,ssh")
    assert load_config().enabled_backends == ("all",)
