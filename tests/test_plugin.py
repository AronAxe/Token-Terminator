import json
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.plugin import Runtime
from rtk_hermes_plus.rewrite import RewriteResult


def test_package_metadata_matches_module():
    import rtk_hermes_plus

    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == rtk_hermes_plus.__version__
    assert (
        metadata["project"]["entry-points"]["hermes_agent.plugins"]["rtk-plus"]
        == "rtk_hermes_plus"
    )


def runtime(tmp_path, **kwargs):
    values = {
        "recovery_dir": tmp_path / "recovery",
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
    }
    values.update(kwargs)
    instance = Runtime(Config(**values))
    instance.rewriter.rtk_path = "/fake/rtk"
    instance.compressor.rtk_path = "/fake/rtk"
    return instance


def test_modern_middleware_returns_replacement_without_mutating(tmp_path):
    rt = runtime(tmp_path)
    args = {"command": "git status", "timeout": 30}
    with patch.object(
        rt.rewriter, "rewrite", return_value=RewriteResult("rtk git status", 3, 2.0)
    ):
        result = rt.tool_request_middleware(tool_name="terminal", args=args)
    assert args == {"command": "git status", "timeout": 30}
    assert result["args"] == {"command": "rtk git status", "timeout": 30}
    assert result["source"] == "rtk-hermes-plus"


def test_legacy_hook_mutates_same_dict(tmp_path):
    rt = runtime(tmp_path)
    args = {"command": "git status"}
    with patch.object(
        rt.rewriter, "rewrite", return_value=RewriteResult("rtk git status", 3, 2.0)
    ):
        rt.pre_tool_call(tool_name="terminal", args=args)
    assert args == {"command": "rtk git status"}


def test_suggest_mode_does_not_rewrite(tmp_path):
    rt = runtime(tmp_path, mode="suggest")
    with patch.object(
        rt.rewriter, "rewrite", return_value=RewriteResult("rtk git status", 3, 2.0)
    ):
        assert (
            rt.tool_request_middleware(
                tool_name="terminal", args={"command": "git status"}
            )
            is None
        )
    assert rt.metrics.snapshot()["rewrite_suggested"] == 1


def test_native_mode_does_not_call_terminal_rewriter(tmp_path):
    rt = runtime(tmp_path, mode="native")
    with patch.object(rt.rewriter, "rewrite") as rewrite:
        result = rt.tool_request_middleware(
            tool_name="terminal", args={"command": "git status"}
        )
    assert result is None
    rewrite.assert_not_called()


def test_quiet_pytest_project_is_not_rewritten(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n', encoding="utf-8"
    )
    rt = runtime(tmp_path)
    with patch.object(rt.rewriter, "rewrite") as rewrite:
        result = rt.tool_request_middleware(
            tool_name="terminal", args={"command": "pytest", "cwd": str(tmp_path)}
        )
    assert result is None
    rewrite.assert_not_called()
    assert rt.metrics.snapshot()["rewrite_skipped_pytest_quiet_config"] == 1


def test_remote_backend_is_not_rewritten(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    rt = runtime(tmp_path)
    with patch.object(rt.rewriter, "rewrite") as rewrite:
        assert (
            rt.tool_request_middleware(
                tool_name="terminal", args={"command": "git status"}
            )
            is None
        )
    rewrite.assert_not_called()


def test_non_terminal_and_already_rtk_are_ignored(tmp_path):
    rt = runtime(tmp_path)
    assert rt.tool_request_middleware(tool_name="read_file", args={"path": "x"}) is None
    assert (
        rt.tool_request_middleware(
            tool_name="terminal", args={"command": "rtk git status"}
        )
        is None
    )


def test_status_and_reset_commands(tmp_path):
    rt = runtime(tmp_path)
    rt.metrics.add("rewritten", 3)
    status = json.loads(rt.command("status"))
    assert status["rtk_available"] is True
    assert status["metrics"]["rewritten"] == 3
    assert rt.command("reset-stats") == "RTK Hermes Plus metrics reset."
    assert rt.metrics.snapshot().get("rewritten", 0) == 0


def test_register_prefers_middleware(monkeypatch, tmp_path):
    from rtk_hermes_plus import plugin

    fake_runtime = runtime(tmp_path)
    monkeypatch.setattr(plugin, "Runtime", lambda **_kwargs: fake_runtime)
    ctx = MagicMock()
    plugin.register(ctx)
    ctx.register_middleware.assert_called_once()
    hooks = [call.args[0] for call in ctx.register_hook.call_args_list]
    assert "pre_tool_call" in hooks
    assert "transform_tool_result" in hooks
    assert "pre_llm_call" in hooks
    assert "on_session_end" in hooks


def test_register_falls_back_to_hook(monkeypatch, tmp_path):
    from rtk_hermes_plus import plugin

    fake_runtime = runtime(tmp_path, mode="terminal")
    monkeypatch.setattr(plugin, "Runtime", lambda **_kwargs: fake_runtime)

    class OldContext:
        def __init__(self):
            self.hooks = []

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

        def register_command(self, *_args, **_kwargs):
            pass

    ctx = OldContext()
    plugin.register(ctx)
    assert [name for name, _ in ctx.hooks] == [
        "pre_tool_call",
        "on_session_start",
        "pre_llm_call",
        "on_session_end",
        "on_session_finalize",
    ]


def test_register_native_mode_skips_terminal_middleware(tmp_path, monkeypatch):
    from rtk_hermes_plus import plugin

    fake_runtime = runtime(tmp_path, mode="native")
    monkeypatch.setattr(plugin, "Runtime", lambda **_kwargs: fake_runtime)
    ctx = MagicMock()
    plugin.register(ctx)
    ctx.register_middleware.assert_not_called()
    hooks = [call.args[0] for call in ctx.register_hook.call_args_list]
    assert hooks == [
        "transform_tool_result",
        "pre_tool_call",
        "on_session_start",
        "pre_llm_call",
        "on_session_end",
        "on_session_finalize",
    ]


def test_compare_command_uses_durable_ledger(tmp_path):
    rt = runtime(tmp_path, mode="native")
    payload = json.loads(rt.command("compare"))
    assert payload["experiment"] == "default"
    assert payload["modes"]["native"]["sessions"] == 0
    assert payload["modes"]["balanced"]["sessions"] == 0
