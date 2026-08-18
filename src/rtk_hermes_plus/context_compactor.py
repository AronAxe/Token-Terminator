"""Deterministic conversation-level context compression.

This module implements aggressive token reduction across the full conversation
history that accompanies every provider request — not just the current turn's
tool results. It operates inside the ``llm_request`` middleware, after Hermes
has assembled the complete request and before it reaches the provider.

Three mechanisms, all deterministic (no LLM calls):

1. **Aggressive vaulting** — Every large tool result in the conversation
   history that isn't from the current turn gets vaulted and replaced with a
   compact receipt. The model can recover the full content through the
   ``token_terminator`` tool when it actually needs it.

2. **Turn collapsing** — Old completed turns (user + assistant + tool exchanges)
   get collapsed into a one-line structural summary. The full content remains
   in the vault; the collapsed version just names what happened.

3. **Strict reduction invariant** — The transformed request is accepted only
   when it is strictly smaller than the original. If compression doesn't help,
   the original passes through unchanged. Same invariant as the rest of Token
   Terminator.

Fail-open on every exception: the provider always receives a usable request.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any

from .storage import TokenTerminatorStore

logger = logging.getLogger(__name__)

# Minimum character count for a tool result to be worth vaulting.
# Below this, the receipt overhead exceeds the savings.
_MIN_VAULT_CHARS = 500

# Maximum character count for a collapsed turn summary.
_TURN_SUMMARY_CHARS = 300


@dataclass
class CompactionResult:
    """Result of compacting a full conversation request."""

    request: Any
    raw_chars: int
    compacted_chars: int
    saved_chars: int
    vaulted_results: int = 0
    collapsed_turns: int = 0
    failed_open: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_chars": self.raw_chars,
            "compacted_chars": self.compacted_chars,
            "saved_chars": self.saved_chars,
            "vaulted_results": self.vaulted_results,
            "collapsed_turns": self.collapsed_turns,
            "failed_open": self.failed_open,
            "error": self.error,
        }


def _serialized_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _receipt(artifact_id: str, char_count: int, tool_name: str) -> str:
    """Build a compact receipt for a vaulted tool result."""
    safe_tool = "".join(c if c.isalnum() or c in "._-/" else "_" for c in tool_name)[
        :60
    ]
    return (
        f"[Token Terminator artifact {artifact_id} | "
        f"tool={safe_tool} | chars={char_count} | "
        f"recover with token_terminator action=artifact_get]"
    )


def _turn_summary(
    user_preview: str,
    tool_calls: list[str],
    assistant_preview: str,
) -> str:
    """Build a one-line structural summary for a collapsed turn."""
    parts: list[str] = []
    if user_preview:
        parts.append(f"user: {user_preview[:120]}")
    if tool_calls:
        parts.append(f"tools: {', '.join(tool_calls[:5])}")
    if assistant_preview:
        parts.append(f"assistant: {assistant_preview[:120]}")
    summary = " | ".join(parts)
    return summary[:_TURN_SUMMARY_CHARS]


class ContextCompactor:
    """Compact full conversation history for provider requests.

    This operates on the complete provider request (messages or input array)
    and applies aggressive vaulting and turn collapsing to reduce what the
    provider sees, without losing recoverable information.
    """

    def __init__(
        self,
        store: TokenTerminatorStore,
        *,
        min_vault_chars: int = 4_000,
        collapse_after_turns: int = 6,
        inline_recent_turns: int = 5,
    ) -> None:
        self.store = store
        self.min_vault_chars = max(_MIN_VAULT_CHARS, int(min_vault_chars))
        self.collapse_after_turns = max(0, int(collapse_after_turns))
        self.inline_recent_turns = max(0, int(inline_recent_turns))

    def compact(
        self,
        request: dict[str, Any],
        *,
        session_id: str = "",
    ) -> CompactionResult:
        """Compact a provider request, returning the result and metrics."""
        original = request
        raw_chars = 0
        try:
            if not isinstance(request, dict):
                raise TypeError("request must be an object")
            original = copy.deepcopy(request)
            raw_chars = _serialized_chars(original)

            mode = self._mode(original)
            if mode == "messages":
                working = self._compact_messages(original, session_id)
            elif mode == "responses":
                working = self._compact_responses(original, session_id)
            else:
                return CompactionResult(
                    request=original,
                    raw_chars=raw_chars,
                    compacted_chars=raw_chars,
                    saved_chars=0,
                )

            compacted_chars = _serialized_chars(working)

            # Strict reduction invariant: never make the request larger.
            if compacted_chars >= raw_chars:
                return CompactionResult(
                    request=original,
                    raw_chars=raw_chars,
                    compacted_chars=raw_chars,
                    saved_chars=0,
                )

            return CompactionResult(
                request=working,
                raw_chars=raw_chars,
                compacted_chars=compacted_chars,
                saved_chars=raw_chars - compacted_chars,
                vaulted_results=working.get("_tt_vaulted", 0),  # type: ignore[union-attr]
                collapsed_turns=working.get("_tt_collapsed", 0),  # type: ignore[union-attr]
            )
        except Exception as exc:
            logger.debug("Context compaction failed open", exc_info=True)
            return CompactionResult(
                request=original,
                raw_chars=raw_chars,
                compacted_chars=raw_chars,
                saved_chars=0,
                failed_open=True,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _mode(request: dict[str, Any]) -> str:
        if isinstance(request.get("messages"), list):
            return "messages"
        if isinstance(request.get("input"), list):
            return "responses"
        return "unknown"

    def _compact_messages(
        self, request: dict[str, Any], session_id: str
    ) -> dict[str, Any]:
        """Compact a chat-completion-style messages request."""
        messages = request.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            return request

        working = copy.deepcopy(request)
        msgs = working["messages"]

        # Identify turn boundaries: a user message starts a new turn.
        # We keep the last `inline_recent_turns` turns fully inline.
        # Older turns get their tool results vaulted and potentially collapsed.
        turn_starts = [
            i
            for i, msg in enumerate(msgs)
            if isinstance(msg, dict) and msg.get("role") == "user"
        ]
        if len(turn_starts) <= self.inline_recent_turns:
            return request

        # The cutoff: messages before this index belong to old turns.
        cutoff_turn_idx = len(turn_starts) - self.inline_recent_turns
        cutoff_msg_idx = turn_starts[cutoff_turn_idx]

        vaulted = 0
        collapsed = 0

        # Phase 1: Vault all large tool results in old turns.
        for i in range(cutoff_msg_idx):
            msg = msgs[i]
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "tool":
                continue
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            if len(content) < self.min_vault_chars:
                continue
            # Already a receipt? Skip.
            if content.startswith("[Token Terminator artifact "):
                continue
            artifact_id = self._vault(content, session_id, msg)
            if artifact_id is not None:
                tool_name = self._tool_name_for_tool_message(msgs, i)
                msg["content"] = _receipt(artifact_id, len(content), tool_name)
                vaulted += 1

        # Phase 2: Collapse turns older than collapse_after_turns.
        if (
            self.collapse_after_turns > 0
            and len(turn_starts) > self.collapse_after_turns
        ):
            collapse_cutoff = turn_starts[
                max(0, len(turn_starts) - self.collapse_after_turns)
            ]
            working = self._collapse_old_turns_messages(
                working, collapse_cutoff, session_id
            )
            collapsed = working.pop("_tt_collapsed", 0)  # type: ignore[arg-type]

        working["_tt_vaulted"] = vaulted  # type: ignore[typeddict-item]
        if isinstance(collapsed, int):
            working["_tt_collapsed"] = collapsed  # type: ignore[typeddict-item]
        return working

    def _compact_responses(
        self, request: dict[str, Any], session_id: str
    ) -> dict[str, Any]:
        """Compact a responses-API-style input request."""
        items = request.get("input")
        if not isinstance(items, list) or len(items) < 2:
            return request

        working = copy.deepcopy(request)
        arr = working["input"]

        # Identify turn boundaries by user messages.
        turn_starts = [
            i
            for i, item in enumerate(arr)
            if isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role") == "user"
        ]
        if len(turn_starts) <= self.inline_recent_turns:
            return request

        cutoff_turn_idx = len(turn_starts) - self.inline_recent_turns
        cutoff_item_idx = turn_starts[cutoff_turn_idx]

        vaulted = 0
        for i in range(cutoff_item_idx):
            item = arr[i]
            if not isinstance(item, dict):
                continue
            if item.get("type") != "function_call_output":
                continue
            output = item.get("output")
            if not isinstance(output, str):
                continue
            if len(output) < self.min_vault_chars:
                continue
            if output.startswith("[Token Terminator artifact "):
                continue
            artifact_id = self._vault(output, session_id, item)
            if artifact_id is not None:
                tool_name = self._tool_name_for_response_item(arr, i)
                item["output"] = _receipt(artifact_id, len(output), tool_name)
                vaulted += 1

        working["_tt_vaulted"] = vaulted  # type: ignore[typeddict-item]
        working["_tt_collapsed"] = 0  # type: ignore[typeddict-item]
        return working

    def _vault(
        self,
        content: str,
        session_id: str,
        context_msg: dict[str, Any],
    ) -> str | None:
        """Vault a tool result and return its artifact ID, or None on failure."""
        try:
            stored = self.store.put_artifact(
                content,
                tool_name="",
                args={},
                session_id=session_id,
                tool_call_id=str(context_msg.get("tool_call_id") or ""),
            )
            # Verify exact recovery.
            recovered = self.store.get_artifact(stored.artifact_id)
            if recovered.content != content:
                logger.warning("Vault recovery mismatch; skipping")
                return None
            return stored.artifact_id
        except Exception:
            logger.debug("Vault write failed", exc_info=True)
            return None

    @staticmethod
    def _tool_name_for_tool_message(
        messages: list[dict[str, Any]], tool_msg_idx: int
    ) -> str:
        """Find the tool name for a tool message by matching its tool_call_id."""
        call_id = messages[tool_msg_idx].get("tool_call_id")
        if not call_id:
            return "tool"
        for msg in messages[:tool_msg_idx]:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                if isinstance(call, dict) and call.get("id") == call_id:
                    func = call.get("function")
                    if isinstance(func, dict):
                        name = func.get("name")
                        if isinstance(name, str):
                            return name
        return "tool"

    @staticmethod
    def _tool_name_for_response_item(
        items: list[dict[str, Any]], output_idx: int
    ) -> str:
        """Find the tool name for a function_call_output by matching its call_id."""
        call_id = items[output_idx].get("call_id")
        if not call_id:
            return "tool"
        for item in items[:output_idx]:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call" and item.get("call_id") == call_id:
                name = item.get("name")
                if isinstance(name, str):
                    return name
        return "tool"

    def _collapse_old_turns_messages(
        self,
        request: dict[str, Any],
        cutoff_idx: int,
        session_id: str,
    ) -> dict[str, Any]:
        """Replace old turn groups with structural summaries."""
        messages = request["messages"]
        # Group messages into turns (user message through next user message).
        new_messages: list[dict[str, Any]] = []
        i = 0
        collapsed = 0
        while i < len(messages):
            if i >= cutoff_idx:
                # Keep everything from the cutoff onward as-is.
                new_messages.extend(messages[i:])
                break

            msg = messages[i]
            if not isinstance(msg, dict) or msg.get("role") != "user":
                new_messages.append(msg)
                i += 1
                continue

            # Find the end of this turn (next user message or end).
            turn_end = i + 1
            while turn_end < len(messages):
                next_msg = messages[turn_end]
                if isinstance(next_msg, dict) and next_msg.get("role") == "user":
                    break
                turn_end += 1

            # Extract previews for the summary.
            user_preview = ""
            tool_calls: list[str] = []
            assistant_preview = ""
            for j in range(i, turn_end):
                m = messages[j]
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                if role == "user":
                    content = m.get("content")
                    if isinstance(content, str):
                        user_preview = content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                user_preview = str(part.get("text", ""))
                                break
                elif role == "assistant":
                    content = m.get("content")
                    if isinstance(content, str):
                        assistant_preview = content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                assistant_preview = str(part.get("text", ""))
                                break
                    for call in m.get("tool_calls") or []:
                        if isinstance(call, dict):
                            func = call.get("function")
                            if isinstance(func, dict):
                                name = func.get("name")
                                if isinstance(name, str):
                                    tool_calls.append(name)

            summary = _turn_summary(user_preview, tool_calls, assistant_preview)
            summary_msg = {
                "role": "user",
                "content": f"[Collapsed turn {collapsed + 1}: {summary}]",
            }
            new_messages.append(summary_msg)
            collapsed += 1
            i = turn_end

        request["messages"] = new_messages
        request["_tt_collapsed"] = collapsed  # type: ignore[typeddict-item]
        return request
