from __future__ import annotations

import json
import re
from typing import Any

from .storage import TokenTerminatorStore

_SIGNAL = re.compile(r"\b(error|warning|failed|failure|exception|traceback|fatal)\b", re.I)


def _clip(value: str, limit: int) -> str:
    limit = max(1, int(limit))
    if len(value) <= limit:
        return value
    if limit <= 1:
        return "…"[:limit]
    return value[: limit - 1] + "…"


def _json_structure(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = [str(key) for key in list(value)[:50]]
        return {
            "type": "object",
            "keys": keys,
            "key_count": len(value),
            "truncated_keys": len(value) > len(keys),
        }
    if isinstance(value, list):
        item_types = sorted({type(item).__name__ for item in value[:100]})
        return {
            "type": "array",
            "items": len(value),
            "sample_item_types": item_types,
        }
    return {"type": type(value).__name__}


def artifact_peek(
    store: TokenTerminatorStore, artifact_id: str, *, limit: int = 2_000
) -> dict[str, Any]:
    """Return a deterministic lossy synopsis while preserving exact recovery."""
    artifact = store.get_artifact(artifact_id)
    limit = max(200, min(int(limit), store.max_page_chars))
    lines = artifact.content.splitlines()
    head = [_clip(line, 500) for line in lines[:6]]
    tail = [_clip(line, 500) for line in lines[-6:]] if len(lines) > 6 else []
    signals = [_clip(line, 500) for line in lines if _SIGNAL.search(line)][:8]

    structure: dict[str, Any] | None = None
    if artifact.char_count <= 250_000:
        try:
            structure = _json_structure(json.loads(artifact.content))
        except (TypeError, ValueError):
            structure = None

    synopsis = {
        "head": head,
        "tail": tail,
        "signals": signals,
    }
    serialized = json.dumps(synopsis, ensure_ascii=False, sort_keys=True)
    if len(serialized) > limit:
        synopsis = {
            "head": [_clip(line, 240) for line in lines[:3]],
            "tail": [_clip(line, 240) for line in lines[-3:]] if len(lines) > 3 else [],
            "signals": [_clip(line, 240) for line in signals[:3]],
        }

    return {
        "artifact_id": artifact.artifact_id,
        "sha256": artifact.sha256,
        "tool_name": artifact.tool_name,
        "total_chars": artifact.char_count,
        "total_bytes": artifact.byte_count,
        "line_count": len(lines),
        "observation_count": artifact.observation_count,
        "created_at": artifact.created_at,
        "structure": structure,
        "synopsis": synopsis,
        "lossy": True,
        "exact_recovery": "token_terminator action=artifact_get",
    }


def artifact_find(
    store: TokenTerminatorStore,
    artifact_id: str,
    query: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    """Find matching lines inside one vaulted artifact without returning it all."""
    needle = str(query or "").strip().lower()
    if not needle:
        raise ValueError("query must not be empty")
    max_hits = max(1, min(int(limit), 100))
    artifact = store.get_artifact(artifact_id)
    hits: list[dict[str, Any]] = []
    total_matches = 0
    for line_number, line in enumerate(artifact.content.splitlines(), start=1):
        if needle not in line.lower():
            continue
        total_matches += 1
        if len(hits) < max_hits:
            hits.append({"line": line_number, "text": _clip(line, 1_000)})
    return {
        "artifact_id": artifact.artifact_id,
        "query": query,
        "matches": hits,
        "total_matches": total_matches,
        "truncated": total_matches > len(hits),
        "lossy": True,
        "exact_recovery": "token_terminator action=artifact_get",
    }
