from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .config import Config
from .graph import WorkingStateGraph
from .storage import TokenTerminatorStore

logger = logging.getLogger(__name__)


def _serialized_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _receipt_tool_name(value: str) -> str:
    normalized = "_".join(str(value or "tool").split())
    safe = "".join(
        char if char.isalnum() or char in "._:/-" else "_" for char in normalized
    )
    return safe[:80] or "tool"


@dataclass
class CompileResult:
    request: Any
    raw_chars: int
    compiled_chars: int
    saved_chars: int
    artifact_ids: list[str]
    receipts: int = 0
    duplicates_collapsed: int = 0
    graph_context_injected: bool = False
    failed_open: bool = False
    error: str = ""
    request_mode: str = "unknown"
    tool_schema_chars: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _EvidenceSlot:
    container: dict[str, Any]
    field: str
    content: str
    tool_name: str
    args: dict[str, Any]
    call_id: str
    ordinal: int
    artifact_id: str = ""
    sha256: str = ""


class RequestCompiler:
    """Compile a provider request without mutating persisted Hermes history."""

    def __init__(
        self,
        store: TokenTerminatorStore,
        graph: WorkingStateGraph,
        config: Config,
    ):
        self.store = store
        self.graph = graph
        self.config = config

    @staticmethod
    def _mode(request: dict[str, Any]) -> str:
        if isinstance(request.get("messages"), list):
            return "messages"
        if isinstance(request.get("input"), list):
            return "responses"
        return "unknown"

    @staticmethod
    def _tool_args(value: Any) -> dict[str, Any]:
        """Recover JSON-object tool arguments for private provenance only."""
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _request_key(request: dict[str, Any]) -> str:
        encoded = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return "req_" + hashlib.sha256(encoded).hexdigest()[:32]

    def _chat_slots(self, request: dict[str, Any]) -> list[_EvidenceSlot]:
        messages = request.get("messages")
        if not isinstance(messages, list):
            return []
        call_names: dict[str, str] = {}
        call_args: dict[str, dict[str, Any]] = {}
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                call_id = call.get("id")
                function = call.get("function")
                if isinstance(call_id, str) and isinstance(function, dict):
                    name = function.get("name")
                    if isinstance(name, str):
                        call_names[call_id] = name
                    call_args[call_id] = self._tool_args(function.get("arguments"))
        slots: list[_EvidenceSlot] = []
        for ordinal, message in enumerate(messages):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            content = message.get("content")
            if (
                not isinstance(content, str)
                or len(content) < self.config.min_artifact_chars
                or len(content) > self.config.max_artifact_chars
            ):
                continue
            call_id = str(message.get("tool_call_id") or "")
            slots.append(
                _EvidenceSlot(
                    container=message,
                    field="content",
                    content=content,
                    tool_name=call_names.get(call_id, "tool"),
                    args=call_args.get(call_id, {}),
                    call_id=call_id,
                    ordinal=ordinal,
                )
            )
        return slots

    def _responses_slots(self, request: dict[str, Any]) -> list[_EvidenceSlot]:
        items = request.get("input")
        if not isinstance(items, list):
            return []
        call_names: dict[str, str] = {}
        call_args: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            call_id = item.get("call_id")
            name = item.get("name")
            if isinstance(call_id, str) and isinstance(name, str):
                call_names[call_id] = name
                call_args[call_id] = self._tool_args(item.get("arguments"))
        slots: list[_EvidenceSlot] = []
        for ordinal, item in enumerate(items):
            if not isinstance(item, dict) or item.get("type") != "function_call_output":
                continue
            output = item.get("output")
            if (
                not isinstance(output, str)
                or len(output) < self.config.min_artifact_chars
                or len(output) > self.config.max_artifact_chars
            ):
                continue
            call_id = str(item.get("call_id") or "")
            slots.append(
                _EvidenceSlot(
                    container=item,
                    field="output",
                    content=output,
                    tool_name=call_names.get(call_id, "tool"),
                    args=call_args.get(call_id, {}),
                    call_id=call_id,
                    ordinal=ordinal,
                )
            )
        return slots

    @staticmethod
    def _receipt(slot: _EvidenceSlot) -> str:
        return (
            f"[Token Terminator artifact {slot.artifact_id} | "
            f"tool={_receipt_tool_name(slot.tool_name)} | "
            f"chars={len(slot.content)} | sha256={slot.sha256[:16]}… | "
            "recover with token_terminator action=artifact_get]"
        )

    def _inject_graph_context(self, request: dict[str, Any], mode: str) -> bool:
        block = self.graph.render_context(self.config.graph_context_chars)
        if not block:
            return False
        key = "messages" if mode == "messages" else "input"
        items = request.get(key)
        if not isinstance(items, list):
            return False
        for item in reversed(items):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            content = item.get("content")
            if isinstance(content, str):
                item["content"] = f"{content}\n\n{block}" if content else block
                return True
            if isinstance(content, list):
                part_type = "text" if mode == "messages" else "input_text"
                content.append({"type": part_type, "text": block})
                return True
        return False

    def _record_metric(
        self, result: CompileResult, session_id: str, request_id: str
    ) -> None:
        try:
            self.store.record_request_metric(
                session_id=session_id,
                request_id=request_id,
                request_mode=result.request_mode,
                raw_chars=result.raw_chars,
                compiled_chars=result.compiled_chars,
                saved_chars=result.saved_chars,
                artifact_count=len(result.artifact_ids),
                receipts=result.receipts,
                duplicates_collapsed=result.duplicates_collapsed,
                tool_schema_chars=result.tool_schema_chars,
                failed_open=result.failed_open,
            )
        except Exception:
            # Metrics are observational and must never affect provider behavior.
            logger.debug("Token Terminator request metric write failed", exc_info=True)

    def compile(
        self,
        request: Any,
        *,
        session_id: str = "",
        request_id: str = "",
    ) -> CompileResult:
        original = request
        raw_chars = 0
        mode = "unknown"
        request_id = str(request_id or "")
        tool_schema_chars = 0
        try:
            if not isinstance(request, dict):
                raise TypeError("request must be an object")
            original = copy.deepcopy(request)
            raw_chars = _serialized_chars(original)
            mode = self._mode(original)
            request_id = str(request_id or self._request_key(original))
            tools = original.get("tools")
            tool_schema_chars = (
                _serialized_chars(tools) if isinstance(tools, list) else 0
            )

            if not self.config.compiler_enabled:
                result = CompileResult(
                    request=original,
                    raw_chars=raw_chars,
                    compiled_chars=raw_chars,
                    saved_chars=0,
                    artifact_ids=[],
                    request_mode=mode,
                    tool_schema_chars=tool_schema_chars,
                )
                self._record_metric(result, session_id, request_id)
                return result

            working = copy.deepcopy(original)
            slots = (
                self._chat_slots(working)
                if mode == "messages"
                else self._responses_slots(working)
                if mode == "responses"
                else []
            )
            artifact_ids: list[str] = []
            for slot in slots:
                stored = self.store.put_artifact(
                    slot.content,
                    tool_name=slot.tool_name,
                    args=slot.args,
                    session_id=session_id,
                    tool_call_id=slot.call_id,
                )
                slot.artifact_id = stored.artifact_id
                slot.sha256 = stored.sha256
                if stored.artifact_id not in artifact_ids:
                    artifact_ids.append(stored.artifact_id)

            receipts = 0
            duplicates = 0
            pending_claims: list[tuple[_EvidenceSlot, str]] = []
            if self.config.compiler_enabled:
                grouped: dict[str, list[_EvidenceSlot]] = {}
                for slot in slots:
                    receipt = self._receipt(slot)
                    # A lease can only be enforced when its recovery receipt is
                    # itself a strict structural reduction for this slot.
                    if _serialized_chars(receipt) < _serialized_chars(slot.content):
                        grouped.setdefault(slot.artifact_id, []).append(slot)
                for artifact_id, group in grouped.items():
                    group.sort(key=lambda slot: slot.ordinal)
                    for duplicate in group[:-1]:
                        duplicate.container[duplicate.field] = self._receipt(duplicate)
                        receipts += 1
                        duplicates += 1
                    newest = group[-1]
                    try:
                        inline = self.store.exposure_available(
                            session_id=session_id,
                            artifact_id=artifact_id,
                            request_id=request_id,
                            inline_limit=self.config.inline_lease_exposures,
                        )
                    except Exception:
                        # A read failure cannot suppress native evidence.
                        logger.debug(
                            "Token Terminator exposure preflight failed", exc_info=True
                        )
                        inline = True
                    if not inline:
                        newest.container[newest.field] = self._receipt(newest)
                        receipts += 1
                    else:
                        pending_claims.append((newest, artifact_id))

            # Prove the preflight candidate before durable inline claims. The
            # claim is authoritative; a concurrent winner can only replace an
            # inline candidate with a smaller receipt.
            preclaim_chars = _serialized_chars(working)
            if preclaim_chars < raw_chars or not receipts:
                for newest, artifact_id in pending_claims:
                    try:
                        claimed = self.store.claim_exposure(
                            session_id=session_id,
                            artifact_id=artifact_id,
                            request_id=request_id,
                            inline_limit=self.config.inline_lease_exposures,
                        )
                    except Exception:
                        # Persistence failure is fail-open for this artifact.
                        logger.debug(
                            "Token Terminator exposure claim failed", exc_info=True
                        )
                        claimed = True
                    if not claimed:
                        newest.container[newest.field] = self._receipt(newest)
                        receipts += 1

            graph_injected = False
            if self.config.compiler_enabled and mode in {"messages", "responses"}:
                without_graph = copy.deepcopy(working)
                try:
                    graph_injected = self._inject_graph_context(working, mode)
                    if _serialized_chars(working) >= raw_chars:
                        working = without_graph
                        graph_injected = False
                except Exception:
                    # Working-state context is optional and must not discard
                    # otherwise valid receipt reductions.
                    logger.debug(
                        "Token Terminator working-state injection failed", exc_info=True
                    )
                    working = without_graph
                    graph_injected = False

            compiled_chars = _serialized_chars(working)
            # Token Terminator is an optimizer, not a context decorator. A
            # graph block or receipt metadata may never make the provider
            # payload larger. Artifact capture remains private, but the
            # provider request is accepted only on strict reduction.
            if compiled_chars >= raw_chars:
                result = CompileResult(
                    request=original,
                    raw_chars=raw_chars,
                    compiled_chars=raw_chars,
                    saved_chars=0,
                    artifact_ids=artifact_ids,
                    request_mode=mode,
                    tool_schema_chars=tool_schema_chars,
                )
                self._record_metric(result, session_id, request_id)
                return result
            result = CompileResult(
                request=working,
                raw_chars=raw_chars,
                compiled_chars=compiled_chars,
                saved_chars=raw_chars - compiled_chars,
                artifact_ids=artifact_ids,
                receipts=receipts,
                duplicates_collapsed=duplicates,
                graph_context_injected=graph_injected,
                request_mode=mode,
                tool_schema_chars=tool_schema_chars,
            )
            self._record_metric(result, session_id, request_id)
            return result
        except Exception as exc:  # noqa: BLE001 - fail-open is the middleware contract
            metric_request_id = request_id or f"failopen_{uuid.uuid4().hex}"
            result = CompileResult(
                request=original,
                raw_chars=raw_chars,
                compiled_chars=raw_chars,
                saved_chars=0,
                artifact_ids=[],
                failed_open=True,
                error=f"{type(exc).__name__}: {exc}",
                request_mode=mode,
                tool_schema_chars=tool_schema_chars,
            )
            self._record_metric(result, session_id, metric_request_id)
            return result
