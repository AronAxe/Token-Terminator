"""Tests for ContextCompactor — aggressive vaulting and turn collapsing."""

from __future__ import annotations

import copy
import json
from itertools import pairwise

import pytest

from rtk_hermes_plus.context_compactor import ContextCompactor
from rtk_hermes_plus.storage import TokenTerminatorStore


@pytest.fixture
def store(tmp_path):
    return TokenTerminatorStore(
        tmp_path / "test_context.db",
        max_artifact_chars=2_000_000,
        max_vault_bytes=10_000_000,
    )


@pytest.fixture
def compactor(store):
    return ContextCompactor(
        store,
        min_vault_chars=200,
        collapse_after_turns=4,
        inline_recent_turns=2,
    )


def _make_tool_message(content: str, call_id: str = "call_1") -> dict:
    return {"role": "tool", "content": content, "tool_call_id": call_id}


def _make_assistant_with_tools(tool_name: str, call_id: str = "call_1") -> dict:
    return {
        "role": "assistant",
        "content": "Let me check that.",
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": tool_name}}
        ],
    }


def _make_user(msg: str) -> dict:
    return {"role": "user", "content": msg}


def _make_request(messages: list[dict]) -> dict:
    return {"messages": messages, "model": "test-model"}


class TestAggressiveVaulting:
    """Old tool results should be vaulted and replaced with receipts."""

    def test_old_large_tool_result_gets_vaulted(self, compactor):
        big_result = "x" * 5000
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("search_files", "call_1"),
            _make_tool_message(big_result, "call_1"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        original = copy.deepcopy(request)
        result = compactor.compact(request, session_id="s1")

        assert result.saved_chars > 0
        assert result.vaulted_results >= 1
        # The vaulted message should now be a receipt, not the original content.
        vaulted_msg = result.request["messages"][2]
        assert "[Token Terminator artifact " in vaulted_msg["content"]
        assert "x" * 100 not in vaulted_msg["content"]
        assert request == original
        assert not any(key.startswith("_tt_") for key in result.request)
        assert result.compacted_chars == len(
            json.dumps(result.request, ensure_ascii=False, sort_keys=True, default=str)
        )

    def test_recent_tool_results_stay_inline(self, compactor):
        big_result = "x" * 5000
        # Only 2 turns — both are recent with inline_recent_turns=2.
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("search_files", "call_1"),
            _make_tool_message(big_result, "call_1"),
            _make_user("Turn 2"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        # With only 2 turns and inline_recent_turns=2, nothing should be vaulted.
        assert result.vaulted_results == 0
        assert result.saved_chars == 0

    def test_small_tool_results_not_vaulted(self, compactor):
        small_result = "just a small result"
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("search_files", "call_1"),
            _make_tool_message(small_result, "call_1"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        assert result.vaulted_results == 0

    def test_already_receipted_results_skipped(self, compactor, store):
        receipt = "[Token Terminator artifact a_old123 | tool=search_files | chars=5000 | recover with token_terminator action=artifact_get]"
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("search_files", "call_1"),
            _make_tool_message(receipt, "call_1"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        assert result.vaulted_results == 0

    def test_vaulted_content_is_recoverable(self, compactor, store):
        big_result = "Important data: " + "x" * 5000
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("read_file", "call_1"),
            _make_tool_message(big_result, "call_1"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        # Find the receipt and recover the artifact.
        receipt_msg = result.request["messages"][2]
        artifact_id = receipt_msg["content"].split("artifact ")[1].split(" ")[0]
        recovered = store.get_artifact(artifact_id)
        assert recovered.content == big_result


class TestTurnCollapsing:
    """Old turns should be collapsed into structural summaries."""

    def test_old_turns_get_collapsed(self, compactor):
        messages = []
        for i in range(8):
            messages.append(_make_user(f"User message for turn {i}"))
            messages.append(_make_assistant_with_tools("search_files", f"call_{i}"))
            messages.append(_make_tool_message("x" * 200, f"call_{i}"))
            messages.append({"role": "assistant", "content": f"Result {i}"})

        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        assert result.collapsed_turns > 0
        # Collapsed turns should contain "[Collapsed turn"
        collapsed_msgs = [
            m
            for m in result.request["messages"]
            if isinstance(m.get("content", ""), str)
            and "[Collapsed turn" in m["content"]
        ]
        assert len(collapsed_msgs) > 0

    def test_recent_turns_not_collapsed(self, compactor):
        messages = []
        for i in range(3):
            messages.append(_make_user(f"User message for turn {i}"))
            messages.append({"role": "assistant", "content": f"Result {i}"})

        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        # Only 3 turns, collapse_after_turns=4 — nothing should collapse.
        assert result.collapsed_turns == 0

    def test_collapsed_turn_preserves_user_preview(self, compactor):
        messages = []
        for i in range(6):
            messages.append(_make_user(f"This is turn {i} about topic {i}"))
            messages.append({"role": "assistant", "content": f"Answer {i}"})

        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        collapsed = [
            m
            for m in result.request["messages"]
            if "[Collapsed turn" in str(m.get("content", ""))
        ]
        if collapsed:
            # The first collapsed turn should mention the original user message.
            assert (
                "turn 0" in collapsed[0]["content"]
                or "topic 0" in collapsed[0]["content"]
            )

    def test_collapsed_turns_do_not_create_adjacent_user_roles(self, compactor):
        messages = []
        for i in range(8):
            messages.append(_make_user(f"User message for turn {i}" * 20))
            messages.append({"role": "assistant", "content": f"Answer {i}" * 20})

        result = compactor.compact(_make_request(messages), session_id="s1")

        assert result.collapsed_turns > 1
        roles = [message.get("role") for message in result.request["messages"]]
        assert all(
            current != "user" or previous != "user"
            for previous, current in pairwise(roles)
        )
        retained_user = next(
            message
            for message in result.request["messages"]
            if message.get("role") == "user"
        )
        assert "[Collapsed turn 1:" in retained_user["content"]
        assert "User message for turn 4" in retained_user["content"]

    def test_collapsed_turns_preserve_multimodal_retained_user(self, compactor):
        messages = []
        for i in range(4):
            messages.append(_make_user(f"Old user message {i}" * 20))
            messages.append({"role": "assistant", "content": f"Answer {i}" * 20})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Retained prompt"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,eA=="},
                    },
                ],
            }
        )
        messages.append({"role": "assistant", "content": "Retained answer"})
        for i in range(5, 8):
            messages.append(_make_user(f"Recent user message {i}" * 20))
            messages.append({"role": "assistant", "content": f"Answer {i}" * 20})

        result = compactor.compact(_make_request(messages), session_id="s1")

        assert result.collapsed_turns > 0
        retained_user = next(
            message
            for message in result.request["messages"]
            if isinstance(message.get("content"), list)
        )
        assert retained_user["content"][0]["type"] == "text"
        assert "[Collapsed turn 1:" in retained_user["content"][0]["text"]
        assert retained_user["content"][-1]["type"] == "image_url"


class TestStrictReduction:
    """The compacted request must always be strictly smaller."""

    def test_request_not_made_larger(self, compactor):
        # Even if vaulting and collapsing run, the result must be smaller.
        big_result = "x" * 10000
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("search_files", "call_1"),
            _make_tool_message(big_result, "call_1"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        assert result.compacted_chars < result.raw_chars
        assert result.saved_chars > 0

    def test_fail_open_on_non_dict(self, compactor):
        result = compactor.compact("not a dict", session_id="s1")
        assert result.failed_open
        assert result.saved_chars == 0

    def test_fail_open_on_empty_messages(self, compactor):
        result = compactor.compact({"messages": []}, session_id="s1")
        assert result.saved_chars == 0


class TestResponsesApi:
    """Test compaction with the Responses API format."""

    def test_responses_old_output_vaulted(self, compactor):
        big_output = "y" * 5000
        request = {
            "input": [
                {"type": "message", "role": "user", "content": "Turn 1"},
                {"type": "function_call", "call_id": "c1", "name": "search_files"},
                {"type": "function_call_output", "call_id": "c1", "output": big_output},
                {"type": "message", "role": "user", "content": "Turn 2"},
                {"type": "message", "role": "user", "content": "Turn 3"},
            ]
        }
        original = copy.deepcopy(request)
        result = compactor.compact(request, session_id="s1")

        assert result.vaulted_results >= 1
        vaulted_item = result.request["input"][2]
        assert "[Token Terminator artifact " in vaulted_item["output"]
        assert request == original
        assert not any(key.startswith("_tt_") for key in result.request)
        assert result.compacted_chars == len(
            json.dumps(result.request, ensure_ascii=False, sort_keys=True, default=str)
        )


class TestToolNameExtraction:
    """Tool names should be correctly extracted for receipts."""

    def test_tool_name_from_assistant_message(self, compactor):
        big_result = "x" * 5000
        messages = [
            _make_user("Turn 1"),
            _make_assistant_with_tools("read_file", "call_42"),
            _make_tool_message(big_result, "call_42"),
            _make_user("Turn 2"),
            _make_user("Turn 3"),
        ]
        request = _make_request(messages)
        result = compactor.compact(request, session_id="s1")

        receipt_msg = result.request["messages"][2]
        assert "tool=read_file" in receipt_msg["content"]


class TestNoStoreInteraction:
    """Verify the compactor doesn't break when vault is unavailable."""

    def test_compactor_without_store_fails_open(self):
        # This shouldn't normally happen because the plugin guards it,
        # but the compactor should be safe.
        compactor = ContextCompactor(
            store=None,  # type: ignore[arg-type]
            min_vault_chars=200,
        )
        result = compactor.compact({"messages": [_make_user("test")]}, session_id="s1")
        # Either fails open or returns unchanged.
        assert result.saved_chars == 0
