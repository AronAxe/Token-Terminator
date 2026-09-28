"""Purpose before policy. These signals are host kwargs, NEVER prompt metadata.

Hermes' native llm_request dispatch is currently main-turn-only; auxiliary calls
use a separate client and observer hooks. Bare SDK-shaped requests are ambiguous
and require an explicit conversation purpose from non-Hermes integrations.
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlparse

_internal_depth: ContextVar[int] = ContextVar("tt_internal_call_depth", default=0)
_CONVERSATION = frozenset(
    {"conversation", "chat", "main_generation", "main", "primary"}
)
_API_MODES = frozenset(
    {"chat_completions", "anthropic_messages", "codex_responses", "responses"}
)
_PURPOSE_KEYS = (
    "request_purpose",
    "purpose",
    "call_type",
    "call_role",
    "model_role",
    "request_scope",
)


@contextmanager
def internal_call():
    """Do not recursively optimize work performed by TT (including custom transports)."""
    token = _internal_depth.set(_internal_depth.get() + 1)
    try:
        yield
    finally:
        _internal_depth.reset(token)


def _hermes_internal_role() -> bool:
    """Read existing execution-local Hermes role signals; do not import/patch Hermes.

    Aux clients have task-bound relay context; delegated turns have a parent lease.
    These are stronger negatives than any inherited session or main-hook metadata.
    """
    auxiliary = sys.modules.get("agent.auxiliary_client")
    task = getattr(auxiliary, "_RELAY_AUX_CALL_CONTEXT", None)
    if task is not None and task.get() is not None:
        return True
    relay = sys.modules.get("agent.relay_runtime")
    current_turn = getattr(relay, "current_turn", None)
    turn = current_turn() if callable(current_turn) else None
    return bool(getattr(getattr(turn, "lease", None), "parent_session_id", ""))


def internal_operation() -> bool:
    """Lifecycle hooks lack a provider envelope but must reject known internal work."""
    try:
        return bool(_internal_depth.get() or _hermes_internal_role())
    except Exception:  # noqa: BLE001 - an unavailable role is not permission to capture
        return True


def conversational_request(request, context: dict) -> tuple[bool, str]:
    if _internal_depth.get():
        return False, "tt_internal_or_reentrant_call"
    try:
        if _hermes_internal_role():
            return False, "hermes_auxiliary_or_delegated_role"
    except Exception:  # noqa: BLE001 - unknown host scope must bypass
        return False, "host_scope_unavailable"
    if not isinstance(request, dict):
        return False, "unsupported_request"
    if any(
        context.get(k)
        for k in (
            "aux_task",
            "auxiliary_task",
            "is_internal",
            "internal",
            "parent_session_id",
        )
    ):
        return False, "auxiliary_call"
    # Explicit negatives/unknown purposes win over positives and ambient engine ownership.
    purposes = [context[k] for k in _PURPOSE_KEYS if context.get(k) is not None]
    if any(
        not isinstance(p, str) or p.lower().strip() not in _CONVERSATION
        for p in purposes
    ):
        return False, "non_conversational_or_unknown_purpose"
    api_mode = context.get("api_mode")
    if api_mode is not None and (
        not isinstance(api_mode, str) or api_mode not in _API_MODES
    ):
        return False, "non_generation_api"
    operations = [
        context[k] for k in ("operation", "endpoint") if context.get(k) is not None
    ]
    if any(
        not isinstance(operation, str)
        or operation
        not in {
            "chat.completions.create",
            "responses.create",
            "messages.create",
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/messages",
        }
        for operation in operations
    ):
        return False, "non_generation_operation"
    # Explicit service envelopes always veto, even if mislabeled as a conversation.
    if any(
        k in request
        for k in (
            "documents",
            "query",
            "queries",
            "questions",
            "state",
            "texts",
            "encoding_format",
            "dimensions",
        )
    ):
        return False, "service_envelope"
    if "messages" in request and "input" in request:
        return False, "ambiguous_service_envelope"
    histories = [
        request[k] for k in ("messages", "input") if isinstance(request.get(k), list)
    ]
    if (
        len(histories) != 1
        or not histories[0]
        or not all(isinstance(m, dict) for m in histories[0])
    ):
        return False, "not_conversation_history"
    if not any(
        m.get("role") in {"user", "assistant", "system", "developer", "tool"}
        or m.get("type") in {"function_call", "function_call_output"}
        for m in histories[0]
    ):
        return False, "not_conversation_history"
    if purposes:
        return True, "explicit_conversation"
    # This private flag is set ONLY by the registered Hermes adapter. Require the
    # current main-hook contract too; an arbitrary generic plugin invocation or
    # an inherited session/engine binding alone must not opt a helper into TT.
    if (
        context.get("_tt_hermes_main_hook") is True
        and context.get("middleware_schema_version") == "hermes.middleware.v1"
        and all(
            isinstance(context.get(k), str) and context[k]
            for k in ("session_id", "turn_id", "api_request_id")
        )
        and type(context.get("api_call_count")) is int
        and context["api_call_count"] >= 1
        and api_mode in _API_MODES
    ):
        return True, "hermes_main_turn_hook"
    return False, "unscoped_request"


def conservative_chat_target(request: dict, context: dict) -> bool:
    """Called only AFTER purpose authorization, using the actual outgoing model.

    Hermes currently supplies no target-family role. Other hosts can supply one,
    or explicitly request preservation for custom model aliases. Provider-qualified
    TypeSafe IDs are a fallback, not a substring guess about the call's purpose.
    """
    policy = context.get(
        "chat_target_policy", os.getenv("TOKEN_TERMINATOR_CHAT_TARGET_POLICY", "auto")
    )
    if policy != "auto":
        # Invalid policy values conservatively preserve, rather than enable pruning.
        return True
    family = context.get("target_model_family")
    if family is not None:
        return str(family).strip().lower() == "jev"
    model = str(request.get("model") or "").lower().strip()
    if re.fullmatch(r"~?typesafe/jev(?:-[a-z0-9._-]+)?", model):
        return True
    provider = str(context.get("provider") or "").lower()
    try:
        host = urlparse(str(context.get("base_url") or "")).hostname
    except ValueError:
        host = None
    return bool(
        (provider == "typesafe" or host == "api.typesafe.ai")
        and re.fullmatch(r"jev(?:-[a-z0-9._-]+)?", model)
    )
