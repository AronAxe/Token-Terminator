import os
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    not os.getenv("HERMES_AGENT_SOURCE"),
    reason="set HERMES_AGENT_SOURCE for live Hermes test",
)
def test_current_hermes_tool_request_middleware_contract(monkeypatch, tmp_path):
    source = Path(os.environ["HERMES_AGENT_SOURCE"]).resolve()
    sys.path.insert(0, str(source))
    try:
        from hermes_cli.middleware import apply_tool_request_middleware
        from hermes_cli.plugins import get_plugin_manager

        from rtk_hermes_plus.config import Config
        from rtk_hermes_plus.plugin import Runtime
        from rtk_hermes_plus.rewrite import RewriteResult

        runtime = Runtime(
            Config(
                mode="terminal",
                ledger_path=tmp_path / "experiments.sqlite3",
                state_db_path=tmp_path / "state.db",
                db_path=tmp_path / "artifacts.sqlite3",
            )
        )
        monkeypatch.setattr(runtime.rewriter, "rtk_path", "/fake/rtk")
        monkeypatch.setattr(
            runtime.rewriter,
            "rewrite",
            lambda *_args, **_kwargs: RewriteResult("rtk git status", 3, 1.0),
        )
        manager = get_plugin_manager()
        manager._middleware.setdefault("tool_request", []).append(
            runtime.tool_request_middleware
        )
        result = apply_tool_request_middleware("terminal", {"command": "git status"})
        assert result.payload["command"] == "rtk git status"
        assert result.original_payload["command"] == "git status"
        assert result.trace[-1]["source"] == "token-terminator"
    finally:
        sys.path.remove(str(source))


@pytest.mark.skipif(
    not os.getenv("RTK_INTEGRATION_BIN"),
    reason="set RTK_INTEGRATION_BIN for live RTK test",
)
def test_current_rtk_rewrites_terminal_and_pytest_guard_blocks_known_bad_case(tmp_path):
    from rtk_hermes_plus.config import Config
    from rtk_hermes_plus.plugin import Runtime

    rtk = str(Path(os.environ["RTK_INTEGRATION_BIN"]).resolve())
    runtime = Runtime(
        Config(
            mode="terminal",
            timeout_ms=1_000,
            ledger_path=tmp_path / "experiments.sqlite3",
            state_db_path=tmp_path / "state.db",
            db_path=tmp_path / "artifacts.sqlite3",
        )
    )
    runtime.rewriter.rtk_path = rtk

    git_result = runtime.tool_request_middleware(
        tool_name="terminal",
        args={"command": "git status", "cwd": str(Path(__file__).resolve().parents[1])},
    )
    assert git_result is not None
    assert git_result["args"]["command"] == "rtk git status"

    quiet_project = tmp_path / "quiet-project"
    quiet_project.mkdir()
    (quiet_project / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n', encoding="utf-8"
    )
    pytest_result = runtime.tool_request_middleware(
        tool_name="terminal",
        args={"command": "pytest", "cwd": str(quiet_project)},
    )
    assert pytest_result is None
    assert runtime.metrics.snapshot()["rewrite_skipped_pytest_quiet_config"] == 1
