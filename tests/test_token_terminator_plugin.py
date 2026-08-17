from __future__ import annotations

import copy
import json

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.plugin import Runtime, register


class FakeContext:
    profile_name = "test"

    def __init__(self):
        self.tools = []
        self.hooks = []
        self.middleware = []
        self.commands = []
        self.context_engines = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_hook(self, name, callback):
        self.hooks.append((name, callback))

    def register_middleware(self, name, callback):
        self.middleware.append((name, callback))

    def register_command(self, name, **kwargs):
        self.commands.append((name, kwargs))

    def register_context_engine(self, engine):
        self.context_engines.append(engine)


def config(tmp_path, **kwargs):
    values = {
        "db_path": tmp_path / "artifacts.sqlite3",
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
        "min_artifact_chars": 20,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


def test_single_plugin_registration_preserves_lcm_and_uses_one_model_tool(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("TOKEN_TERMINATOR_MODE", "balanced")
    monkeypatch.setenv("TOKEN_TERMINATOR_DB_PATH", str(tmp_path / "artifacts.sqlite3"))
    monkeypatch.setenv(
        "TOKEN_TERMINATOR_LEDGER_PATH", str(tmp_path / "experiments.sqlite3")
    )
    ctx = FakeContext()

    register(ctx)

    assert "llm_request" in [name for name, _ in ctx.middleware]
    hook_names = [name for name, _ in ctx.hooks]
    assert "post_tool_call" in hook_names
    assert "transform_tool_result" in hook_names
    assert "on_session_start" in hook_names
    assert ctx.context_engines == []
    assert [tool["name"] for tool in ctx.tools] == ["token_terminator"]
    assert [name for name, _ in ctx.commands] == ["token-terminator"]
    tool_status = json.loads(ctx.tools[0]["handler"]({"action": "status"}))
    assert tool_status["plugin"] == "token-terminator"
    assert tool_status["vault_available"] is True


def test_request_middleware_returns_only_a_strictly_smaller_copy(tmp_path):
    runtime = Runtime(config(tmp_path))
    output = "large evidence " * 300
    request = {
        "messages": [
            {"role": "user", "content": "question"},
            {"role": "tool", "tool_call_id": "c1", "content": output},
        ]
    }
    original = copy.deepcopy(request)

    first = runtime.llm_request_middleware(
        request=request, session_id="s1", api_request_id="r1"
    )
    second = runtime.llm_request_middleware(
        request=request, session_id="s1", api_request_id="r2"
    )

    assert first is None
    assert second is not None
    assert second["source"] == "token-terminator"
    assert second["metrics"]["saved_chars"] > 0
    assert request == original


def test_observer_captures_original_and_recovery_tool_returns_exact_content(tmp_path):
    runtime = Runtime(config(tmp_path))
    evidence = "private evidence " * 20
    runtime.post_tool_call(
        tool_name="terminal",
        result=evidence,
        args={"command": "redacted-from-provider"},
        session_id="s1",
        tool_call_id="c1",
    )
    assert runtime.store is not None
    artifact_id = runtime.store.search_artifacts("private evidence")[0].artifact_id

    payload = json.loads(runtime.tool("artifact_get", artifact_id=artifact_id))
    assert payload["content"] == evidence
    assert payload["sha256"] == runtime.store.get_artifact(artifact_id).sha256


def test_off_mode_captures_nothing_and_changes_nothing(tmp_path):
    runtime = Runtime(config(tmp_path, mode="off"))
    request = {"messages": [{"role": "tool", "content": "x" * 100}]}

    runtime.post_tool_call(tool_name="terminal", result="private evidence", args={})

    assert runtime.llm_request_middleware(request=request) is None
    assert (
        runtime.transform_tool_result(
            tool_name="search_files", args={}, result="match\n" * 3_000
        )
        is None
    )
    assert runtime.store is not None
    assert runtime.store.counts()["artifacts"] == 0
