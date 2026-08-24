from __future__ import annotations

import copy
import json

from rtk_hermes_plus.compiler import RequestCompiler
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.graph import WorkingStateGraph
from rtk_hermes_plus.storage import TokenTerminatorStore


def make_compiler(tmp_path, *, threshold=40, leases=1):
    config = Config(
        db_path=tmp_path / "context.db",
        min_artifact_chars=threshold,
        inline_lease_exposures=leases,
        graph_context_chars=1200,
    )
    store = TokenTerminatorStore(config.db_path)
    return RequestCompiler(store, WorkingStateGraph(store), config), store


def chat_request(output: str):
    return {
        "model": "example-model",
        "messages": [
            {"role": "system", "content": "Stable system instructions"},
            {"role": "user", "content": "Inspect the evidence"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "terminal",
                            "arguments": json.dumps({"command": "private provenance"}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": output},
        ],
        "tools": [{"type": "function", "function": {"name": "terminal"}}],
    }


def test_new_tool_evidence_has_one_call_lease_then_becomes_receipt(tmp_path):
    compiler, store = make_compiler(tmp_path)
    output = "useful evidence " * 20
    request = chat_request(output)
    original = copy.deepcopy(request)

    first = compiler.compile(request, session_id="s1", request_id="r1")
    assert first.request["messages"][-1]["content"] == output
    assert request == original

    second = compiler.compile(request, session_id="s1", request_id="r2")
    receipt = second.request["messages"][-1]["content"]
    assert receipt.startswith("[Token Terminator artifact ")
    assert "token_terminator action=artifact_get" in receipt
    artifact_id = second.artifact_ids[0]
    assert store.get_artifact(artifact_id).content == output
    assert store.get_artifact(artifact_id).args == {"command": "private provenance"}
    assert second.saved_chars > 0


def test_same_request_id_does_not_consume_lease_twice(tmp_path):
    compiler, _ = make_compiler(tmp_path)
    request = chat_request("x" * 200)

    assert compiler.compile(request, session_id="s1", request_id="same").receipts == 0
    assert compiler.compile(request, session_id="s1", request_id="same").receipts == 0
    assert compiler.compile(request, session_id="s1", request_id="next").receipts == 1


def test_earlier_duplicate_is_collapsed_but_newest_copy_keeps_lease(tmp_path):
    compiler, _ = make_compiler(tmp_path)
    output = "duplicate evidence " * 20
    request = chat_request(output)
    request["messages"].insert(
        -2, {"role": "tool", "tool_call_id": "older-call", "content": output}
    )

    result = compiler.compile(request, session_id="s1", request_id="r1")
    contents = [
        m.get("content") for m in result.request["messages"] if m.get("role") == "tool"
    ]
    assert contents[0].startswith("[Token Terminator artifact ")
    assert contents[1] == output
    assert result.duplicates_collapsed == 1


def test_responses_input_keeps_call_id_and_externalizes_output(tmp_path):
    compiler, _ = make_compiler(tmp_path)
    output = "responses evidence " * 20
    request = {
        "model": "example-model",
        "input": [
            {"role": "system", "content": "Stable system instructions"},
            {"role": "user", "content": "Inspect the evidence"},
            {
                "type": "function_call",
                "call_id": "call-9",
                "name": "terminal",
                "arguments": "{}",
            },
            {"type": "function_call_output", "call_id": "call-9", "output": output},
        ],
        "tools": [{"type": "function", "name": "terminal"}],
    }

    compiler.compile(request, session_id="s1", request_id="r1")
    compiled = compiler.compile(request, session_id="s1", request_id="r2").request
    output_item = compiled["input"][-1]
    assert output_item["type"] == "function_call_output"
    assert output_item["call_id"] == "call-9"
    assert output_item["output"].startswith("[Token Terminator artifact ")


def test_working_state_is_not_injected_when_it_would_enlarge_request(tmp_path):
    compiler, store = make_compiler(tmp_path)
    graph = WorkingStateGraph(store)
    graph.apply(
        [
            {
                "op": "NODE_CREATE",
                "node_id": "G1",
                "kind": "goal",
                "label": "Preserve evidence and reduce repetition",
                "priority": 0.9,
            }
        ]
    )
    request = chat_request("small")
    original = copy.deepcopy(request)

    result = compiler.compile(request, session_id="s1", request_id="r1")
    assert result.request == original
    assert result.saved_chars == 0
    assert result.graph_context_injected is False
    assert request == original


def test_working_state_can_ride_a_strictly_smaller_compilation(tmp_path):
    compiler, store = make_compiler(tmp_path)
    WorkingStateGraph(store).apply(
        [
            {
                "op": "NODE_CREATE",
                "node_id": "G1",
                "kind": "goal",
                "label": "Preserve evidence and reduce repetition",
                "priority": 0.9,
            }
        ]
    )
    request = chat_request("large evidence " * 300)
    compiler.compile(request, session_id="s1", request_id="r1")

    result = compiler.compile(request, session_id="s1", request_id="r2")
    user_content = result.request["messages"][1]["content"]
    assert "<working_state>" in user_content
    assert "G1" in user_content
    assert result.saved_chars > 0
    assert result.graph_context_injected is True


def test_denied_lease_never_reverts_to_full_evidence_when_graph_would_bloat(
    tmp_path,
):
    compiler, store = make_compiler(tmp_path, threshold=1)
    WorkingStateGraph(store).apply(
        [
            {
                "op": "NODE_CREATE",
                "node_id": "G1",
                "kind": "goal",
                "label": "working state " * 80,
                "priority": 1.0,
            }
        ]
    )
    output = "x" * 250
    request = chat_request(output)
    compiler.compile(request, session_id="s1", request_id="r1")

    result = compiler.compile(request, session_id="s1", request_id="r2")

    assert result.request["messages"][-1]["content"].startswith(
        "[Token Terminator artifact "
    )
    assert result.request["messages"][-1]["content"] != output
    assert result.saved_chars > 0
    assert result.graph_context_injected is False


def test_malformed_requests_fail_open_without_telemetry(tmp_path):
    compiler, store = make_compiler(tmp_path)

    first = compiler.compile(None, session_id="s1")
    second = compiler.compile(["not", "an", "object"], session_id="s1")

    assert first.request is None and first.failed_open
    assert second.request == ["not", "an", "object"] and second.failed_open
    assert first.request_id == ""
    assert second.request_id == ""
    assert store.counts()["requests"] == 0


def test_compiler_fails_open_without_mutating_request(tmp_path, monkeypatch):
    compiler, store = make_compiler(tmp_path)
    request = chat_request("z" * 200)
    original = copy.deepcopy(request)

    def explode(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store, "put_artifact", explode)
    result = compiler.compile(request, session_id="s1", request_id="r1")
    assert result.request == original
    assert result.failed_open is True
    assert request == original


def test_compiler_fails_open_when_request_cannot_be_deep_copied(tmp_path):
    compiler, _ = make_compiler(tmp_path)

    class Uncopyable:
        def __deepcopy__(self, memo):
            raise TypeError("cannot copy provider client")

    request = chat_request("small")
    request["provider_client"] = Uncopyable()

    result = compiler.compile(request, session_id="s1", request_id="r1")

    assert result.failed_open is True
    assert result.request is request
    assert result.error == "TypeError: cannot copy provider client"
    assert request["messages"][-1]["content"] == "small"
