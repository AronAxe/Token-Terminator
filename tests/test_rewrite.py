import subprocess
import time
from unittest.mock import patch

import pytest

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.metrics import Metrics
from rtk_hermes_plus.rewrite import (
    RewriteCache,
    Rewriter,
    RewriteResult,
    backend_enabled,
    command_excluded,
    command_workdir,
    is_pytest_command,
    pytest_config_is_quiet,
    terminal_backend,
)


def test_cache_hit_and_expiry(monkeypatch):
    cache = RewriteCache(max_size=2, ttl_seconds=10)
    cache.put("git status", RewriteResult("rtk git status", 3, 2.0))
    hit = cache.get("git status")
    assert hit and hit.cache_hit and hit.command == "rtk git status"

    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + 20)
    assert cache.get("git status") is None


def test_cache_evicts_oldest():
    cache = RewriteCache(max_size=2, ttl_seconds=60)
    for value in ("a", "b", "c"):
        cache.put(value, RewriteResult(value, 0, 1.0))
    assert cache.get("a") is None
    assert cache.get("b") is not None
    assert cache.get("c") is not None


def test_rewriter_accepts_exit_zero_and_three(tmp_path):
    metrics = Metrics()
    rewriter = Rewriter(Config(), metrics)
    rewriter.rtk_path = "/fake/rtk"
    for rc in (0, 3):
        rewriter.cache = RewriteCache(10, 60)
        completed = subprocess.CompletedProcess(
            [], rc, stdout="rtk git status\n", stderr=""
        )
        with patch("subprocess.run", return_value=completed) as run:
            result = rewriter.rewrite("git status", cwd=tmp_path)
        assert result.command == "rtk git status"
        run.assert_called_once()


def test_rewriter_caches_positive_and_negative_results(tmp_path):
    metrics = Metrics()
    rewriter = Rewriter(Config(), metrics)
    rewriter.rtk_path = "/fake/rtk"
    completed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
    with patch("subprocess.run", return_value=completed) as run:
        assert rewriter.rewrite("echo hi", cwd=tmp_path).command is None
        assert rewriter.rewrite("echo hi", cwd=tmp_path).command is None
    run.assert_called_once()
    assert metrics.snapshot()["rewrite_cache_hits"] == 1


def test_rewriter_timeout_is_fail_open(tmp_path):
    rewriter = Rewriter(Config(timeout_ms=50), Metrics())
    rewriter.rtk_path = "/fake/rtk"
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("rtk", 0.05)):
        result = rewriter.rewrite("git status", cwd=tmp_path)
    assert result.command is None
    assert result.returncode == -1


@pytest.mark.parametrize(
    "command",
    [
        "pytest",
        "pytest -q",
        "python -m pytest tests",
        "python3 -m pytest",
        "uv run pytest",
    ],
)
def test_pytest_command_detection(command):
    assert is_pytest_command(command)


def test_pytest_config_detection_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q --disable-warnings"\n',
        encoding="utf-8",
    )
    child = tmp_path / "src"
    child.mkdir()
    assert pytest_config_is_quiet(child)


@pytest.mark.parametrize(
    ("filename", "section"),
    [("pytest.ini", "pytest"), ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")],
)
def test_pytest_config_detection_ini(tmp_path, filename, section):
    (tmp_path / filename).write_text(
        f"[{section}]\naddopts = --quiet\n", encoding="utf-8"
    )
    assert pytest_config_is_quiet(tmp_path)


def test_pytest_config_without_quiet_is_safe(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -x\n", encoding="utf-8")
    assert not pytest_config_is_quiet(tmp_path)


def test_backend_and_workdir_helpers(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_ENV", "ssh")
    assert terminal_backend({}) == "ssh"
    assert terminal_backend({"env_type": "docker"}) == "docker"
    assert backend_enabled("local", Config())
    assert not backend_enabled("ssh", Config())
    assert backend_enabled("ssh", Config(enabled_backends=("all",)))
    assert command_workdir({"cwd": str(tmp_path)}) == tmp_path


def test_command_exclusions_are_prefix_based():
    assert command_excluded("  Git Push origin main", ("git push",))
    assert not command_excluded("git status", ("git push",))
