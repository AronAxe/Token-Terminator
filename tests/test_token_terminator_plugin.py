from __future__ import annotations

import copy
import json

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.context_compactor import CompactionResult
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
    assert not any(key.startswith("_tt_") for key in second["request"])
    serialized = json.dumps(
        second["request"], ensure_ascii=False, sort_keys=True, default=str
    )
    assert "_tt_vaulted" not in serialized
    assert "_tt_collapsed" not in serialized
    assert request == original

    assert runtime.store is not None
    counts = runtime.store.counts()
    assert counts["requests"] == 2
    assert counts["end_to_end_requests"] == 2
    assert counts["compiler_only_requests"] == 0
    assert (
        counts["measured_compiler_saved_chars"]
        + counts["measured_compactor_saved_chars"]
        == counts["end_to_end_saved_chars"]
    )
    assert (
        counts["measured_raw_chars"] - counts["measured_final_chars"]
        == counts["end_to_end_saved_chars"]
    )


def test_responses_payload_is_provider_safe_and_caller_immutable(tmp_path):
    runtime = Runtime(config(tmp_path))
    request = {
        "input": [
            {"type": "message", "role": "user", "content": "Turn 1"},
            {"type": "function_call", "call_id": "c1", "name": "search_files"},
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "large response evidence " * 300,
            },
            {"type": "message", "role": "user", "content": "Turn 2"},
            {"type": "message", "role": "user", "content": "Turn 3"},
        ]
    }
    original = copy.deepcopy(request)

    first = runtime.llm_request_middleware(
        request=request, session_id="responses", api_request_id="r1"
    )
    second = runtime.llm_request_middleware(
        request=request, session_id="responses", api_request_id="r2"
    )

    assert first is not None or second is not None
    final = second or first
    assert final is not None
    serialized = json.dumps(
        final["request"], ensure_ascii=False, sort_keys=True, default=str
    )
    assert "_tt_vaulted" not in serialized
    assert "_tt_collapsed" not in serialized
    assert request == original


def test_compactor_failure_is_counted_and_keeps_the_usable_request(
    tmp_path, monkeypatch
):
    runtime = Runtime(config(tmp_path))
    request = {"messages": [{"role": "user", "content": "unchanged"}]}
    original = copy.deepcopy(request)
    assert runtime.context_compactor is not None

    def fail_compaction(_request, *, session_id=""):
        return CompactionResult(
            request={"messages": [{"role": "user", "content": "broken"}]},
            raw_chars=100,
            compacted_chars=1,
            saved_chars=99,
            failed_open=True,
            error="injected failure",
        )

    monkeypatch.setattr(runtime.context_compactor, "compact", fail_compaction)
    result = runtime.llm_request_middleware(
        request=request, session_id="failure", api_request_id="r1"
    )

    assert result is None
    assert request == original
    assert runtime.store is not None
    counts = runtime.store.counts()
    assert counts["requests"] == 1
    assert counts["compactor_failed_open_requests"] == 1
    assert counts["end_to_end_requests"] == 1


def test_invalid_request_fails_open_without_creating_telemetry(tmp_path):
    runtime = Runtime(config(tmp_path))

    result = runtime.llm_request_middleware(
        request="not-a-provider-request", session_id="failure"
    )

    assert result is None
    assert runtime.store is not None
    counts = runtime.store.counts()
    assert counts["requests"] == 0
    assert counts["end_to_end_requests"] == 0


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
