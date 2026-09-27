"""Conservative guards for the optional Context IR boundary.

These are vetoes, not an instruction classifier or a prompt-injection defence.
Unrecognised context is left alone. JEV cannot override a deterministic veto.
"""

from __future__ import annotations

import re
from typing import Any

_AUTHORITY = re.compile(
    r"\b(?:must|shall|never|always|only|unless|cannot|avoid|prefer|preserve|retain|required|requirement|constraint|instruction|"
    r"policy|policies|system|developer|override|ignore|execute|sudo|"
    r"password|secret|credential|verbatim|exactly|quotation)\b|"
    r"\b(?:do\s+not|may\s+not|don't|api[_ -]?key|tool[_ -]?call)\b",
    re.IGNORECASE,
)
_RECEIPT = re.compile(r"TTIR/1|\[Token Terminator|\ba_[0-9a-f]{32,64}\b")


def authority_text(text: str) -> bool:
    return bool(_AUTHORITY.search(text) or _RECEIPT.search(text) or "```" in text)


def protected_prose(text: str) -> bool:
    # Exact values, quotations, code, and constraints stay verbatim. Structured
    # records have a separate typed, round-trip-checked path preserving values.
    return bool(
        authority_text(text)
        or re.search(r"[0-9`\"“”‘’]|(?:^|\n)\s*(?:def |class |import |#|<)", text)
        or re.search(r"(?<!\w)'[^'\n]+'(?!\w)", text)
        or "<memory-context>" in text.lower()
    )


def history_items(request: Any) -> tuple[str, list[Any], int]:
    """Find prior history without mistaking a multimodal last user for the past."""
    if not isinstance(request, dict):
        return "", [], -1
    keys = [key for key in ("messages", "input") if isinstance(request.get(key), list)]
    if len(keys) != 1:
        return "", [], -1
    key = keys[0]
    items = request[key]
    latest = max(
        (
            i
            for i, item in enumerate(items)
            if isinstance(item, dict) and item.get("role") == "user"
        ),
        default=-1,
    )
    if latest < 0 or not isinstance(items[latest].get("content"), str):
        return "", [], -1
    return key, items, latest


def plain_message(item: Any) -> bool:
    return bool(
        isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
        and set(item).issubset({"role", "content", "name", "type"})
        and not any(
            key in item for key in ("tool_calls", "tool_call_id", "function_call")
        )
        and item.get("type", "message") == "message"
        and not _RECEIPT.search(item["content"])
    )
