from __future__ import annotations

import copy
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from .config import Config
from .storage import TokenTerminatorStore

logger = logging.getLogger(__name__)

_JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
_MEMORY_BLOCK_RE = re.compile(
    r"<memory-context>\\s*.*?</memory-context>",
    re.IGNORECASE | re.DOTALL,
)


def _serialized_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


@dataclass
class JevReductionResult:
    request: Any
    raw_chars: int
    final_chars: int
    saved_chars: int
    candidates: int = 0
    compacted_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    failed_open: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        # Provider/request content must never leak into metrics or status.
        return {
            "raw_chars": self.raw_chars,
            "final_chars": self.final_chars,
            "saved_chars": self.saved_chars,
            "candidates": self.candidates,
            "compacted_messages": self.compacted_messages,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "failed_open": self.failed_open,
            "error": self.error,
        }


@dataclass
class _Candidate:
    container: dict[str, Any]
    field: str
    content: str
    role: str
    ordinal: int
    kind: str = "message"
    candidate_id: str = ""


Transport = Callable[[dict[str, Any]], dict[str, Any]]


class JevSemanticReducer:
    """Optional Jev-powered relevance gate for provider-bound context.

    Jev never replaces Token Terminator's deterministic compiler, compactor,
    vault, or exact-recovery path. It only gets a chance to compact remaining
    prior plain-text user/assistant messages after those stages have run.

    The current user turn, system/developer/tool messages, structured content,
    and messages carrying tool calls are never candidates.
    """

    def __init__(
        self,
        store: TokenTerminatorStore,
        config: Config,
        *,
        transport: Transport | None = None,
        token_budget: Any = None,
    ) -> None:
        self.store = store
        self.config = config
        self.transport = transport
        self.token_budget = token_budget

    @property
    def enabled(self) -> bool:
        return bool(self.config.jev_enabled and self.config.jev_api_key.strip())

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.config.jev_api_key.strip()),
            "model": self.config.jev_model,
            "threshold": self.config.jev_relevance_threshold,
            "min_message_chars": self.config.jev_min_message_chars,
            "max_candidates": self.config.jev_max_candidates,
            "max_state_chars": self.config.jev_max_state_chars,
            "external_api": "api.typesafe.ai",
        }

    @staticmethod
    def _mode(request: dict[str, Any]) -> str:
        if isinstance(request.get("messages"), list):
            return "messages"
        if isinstance(request.get("input"), list):
            return "responses"
        return "unknown"

    @staticmethod
    def _noul(answer: Any) -> float | None:
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            return None
        try:
            value = float(answer.get("noul"))
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, value))

    def _current_user_and_candidates(
        self, request: dict[str, Any]
    ) -> tuple[str, list[_Candidate]]:
        mode = self._mode(request)
        key = (
            "messages" if mode == "messages" else "input" if mode == "responses" else ""
        )
        items = request.get(key)
        if not key or not isinstance(items, list):
            return "", []

        latest_user_idx = -1
        current_user = ""
        latest_user_item: dict[str, Any] | None = None
        latest_user_content = ""
        for index, item in enumerate(items):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            content = item.get("content")
            if isinstance(content, str):
                latest_user_idx = index
                latest_user_item = item
                latest_user_content = content
                # Hermes appends pre_llm_call memory-provider context to the
                # current user message inside <memory-context> fences. Judge
                # that injected background against the user's actual request.
                current_user = _MEMORY_BLOCK_RE.sub("", content).strip()

        if latest_user_idx < 0 or not current_user:
            return "", []

        candidates: list[_Candidate] = []
        for index, item in enumerate(items[:latest_user_idx]):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            if role not in {"user", "assistant"}:
                continue
            if item.get("tool_calls"):
                continue
            if item.get("type") in {"function_call", "function_call_output"}:
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            if content.startswith("[Token Terminator artifact "):
                continue
            if len(content) < self.config.jev_min_message_chars:
                continue
            if len(content) > self.config.jev_max_candidate_chars:
                continue
            candidates.append(
                _Candidate(
                    container=item,
                    field="content",
                    content=content,
                    role=role,
                    ordinal=index,
                )
            )

        # Recalled memory is active context too. Score the fenced block
        # separately while leaving the user's own current request untouched.
        if latest_user_item is not None and latest_user_content:
            for match in _MEMORY_BLOCK_RE.finditer(latest_user_content):
                block = match.group(0)
                if len(block) < self.config.jev_min_message_chars:
                    continue
                if len(block) > self.config.jev_max_candidate_chars:
                    continue
                candidates.append(
                    _Candidate(
                        container=latest_user_item,
                        field="content",
                        content=block,
                        role="memory",
                        ordinal=latest_user_idx,
                        kind="memory",
                    )
                )

        # Spend Jev input on the places with the largest possible token payoff.
        candidates.sort(key=lambda candidate: len(candidate.content), reverse=True)
        selected: list[_Candidate] = []
        remaining = self.config.jev_max_state_chars - len(current_user)
        if remaining <= 0:
            return "", []
        for candidate in candidates:
            if len(selected) >= self.config.jev_max_candidates:
                break
            cost = len(candidate.content) + 128
            if cost > remaining:
                continue
            selected.append(candidate)
            remaining -= cost

        for index, candidate in enumerate(selected):
            candidate.candidate_id = f"c{index}"
        return current_user, selected

    def _payload(
        self, current_user: str, candidates: list[_Candidate]
    ) -> dict[str, Any]:
        state_candidates = {
            candidate.candidate_id: {
                "role": candidate.role,
                "kind": candidate.kind,
                "ordinal": candidate.ordinal,
                "content": candidate.content,
            }
            for candidate in candidates
        }
        questions: dict[str, Any] = {}
        for candidate in candidates:
            cid = candidate.candidate_id
            questions[f"{cid}_relevance"] = {
                "type": "noul",
                "instructions": (
                    f"Would candidates.{cid} materially help a capable language model "
                    "answer current_request correctly? Count direct subject overlap, "
                    "definitions, dependencies, unresolved references, prior decisions, "
                    "and factual context as relevant."
                ),
            }
            questions[f"{cid}_guard"] = {
                "type": "noul",
                "instructions": (
                    f"Does candidates.{cid} contain an instruction, constraint, preference, "
                    "commitment, exact value, name, code detail, quotation, or other detail "
                    "whose omission could materially change the answer to current_request?"
                ),
            }

        return {
            "state": {
                "current_request": current_user,
                "candidates": state_candidates,
            },
            "model": self.config.jev_model,
            "questions": questions,
        }

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(payload)

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        request = Request(
            _JEV_API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.jev_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Token-Terminator/Jev",
            },
            method="POST",
        )
        timeout = self.config.jev_timeout_ms / 1000.0
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TypeError("Jev response must be an object")
        return decoded

    @staticmethod
    def _receipt(artifact_id: str, char_count: int) -> str:
        return (
            f"[Token Terminator artifact {artifact_id} | context=jev | "
            f"chars={char_count} | recover with token_terminator action=artifact_get]"
        )

    def reduce(
        self,
        request: Any,
        *,
        session_id: str = "",
        model: str = "",
    ) -> JevReductionResult:
        original = request
        raw_chars = 0
        try:
            if not isinstance(request, dict):
                raise TypeError("request must be an object")
            original = copy.deepcopy(request)
            raw_chars = _serialized_chars(original)
            if not self.enabled:
                return JevReductionResult(
                    request=original,
                    raw_chars=raw_chars,
                    final_chars=raw_chars,
                    saved_chars=0,
                )

            working = copy.deepcopy(original)
            current_user, candidates = self._current_user_and_candidates(working)
            if not current_user or not candidates:
                return JevReductionResult(
                    request=original,
                    raw_chars=raw_chars,
                    final_chars=raw_chars,
                    saved_chars=0,
                )

            response = self._call(self._payload(current_user, candidates))
            answers = response.get("answers")
            if not isinstance(answers, dict):
                raise TypeError("Jev response is missing answers")

            compacted = 0
            for candidate in candidates:
                cid = candidate.candidate_id
                relevance = self._noul(answers.get(f"{cid}_relevance"))
                guard = self._noul(answers.get(f"{cid}_guard"))
                # Missing or malformed answers fail safe for that candidate.
                if relevance is None or guard is None:
                    continue
                if max(relevance, guard) >= self.config.jev_relevance_threshold:
                    continue

                stored = self.store.put_artifact(
                    candidate.content,
                    tool_name="jev_context",
                    args={
                        "role": candidate.role,
                        "kind": candidate.kind,
                        "ordinal": candidate.ordinal,
                    },
                    session_id=str(session_id or ""),
                    tool_call_id="",
                )
                recovered = self.store.get_artifact(stored.artifact_id)
                if recovered.content != candidate.content:
                    continue
                receipt = self._receipt(stored.artifact_id, len(candidate.content))
                if _serialized_chars(receipt) >= _serialized_chars(candidate.content):
                    continue
                if candidate.kind == "memory":
                    replacement = (
                        "<memory-context>\n"
                        f"{receipt}\n"
                        "</memory-context>"
                    )
                    current = candidate.container.get(candidate.field)
                    if not isinstance(current, str) or candidate.content not in current:
                        continue
                    candidate.container[candidate.field] = current.replace(
                        candidate.content, replacement, 1
                    )
                else:
                    candidate.container[candidate.field] = receipt
                compacted += 1

            final_chars = _serialized_chars(working)
            if compacted <= 0 or final_chars >= raw_chars:
                return JevReductionResult(
                    request=original,
                    raw_chars=raw_chars,
                    final_chars=raw_chars,
                    saved_chars=0,
                    candidates=len(candidates),
                )

            if self.token_budget is not None:
                raw_tokens = self.token_budget.measure_request(original, model=model)
                final_tokens = self.token_budget.measure_request(working, model=model)
                if (
                    raw_tokens.available
                    and final_tokens.available
                    and raw_tokens.tokens is not None
                    and final_tokens.tokens is not None
                    and final_tokens.tokens >= raw_tokens.tokens
                ):
                    return JevReductionResult(
                        request=original,
                        raw_chars=raw_chars,
                        final_chars=raw_chars,
                        saved_chars=0,
                        candidates=len(candidates),
                    )

            usage = (
                response.get("usage") if isinstance(response.get("usage"), dict) else {}
            )
            return JevReductionResult(
                request=working,
                raw_chars=raw_chars,
                final_chars=final_chars,
                saved_chars=raw_chars - final_chars,
                candidates=len(candidates),
                compacted_messages=compacted,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                model=str(response.get("model") or self.config.jev_model),
            )
        except Exception as exc:
            logger.debug("Jev semantic context reduction failed open", exc_info=True)
            return JevReductionResult(
                request=original,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                saved_chars=0,
                failed_open=True,
                error=f"{type(exc).__name__}: {exc}",
            )
