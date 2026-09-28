"""Session-scoped, exact history evidence. No summaries and no inferred chronology.

The additive catalog indexes content-addressed message snapshots in the existing
vault. Pins and read-back verification precede publication of any reference.
Repeated identical snapshots share evidence; the host transcript keeps occurrences.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .storage import TokenTerminatorStore


class HistoryEvidenceError(ValueError):
    """A history reference cannot be proved against its exact backing source."""


def encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text_slot(message: Any) -> tuple[str, int | None] | None:
    """An exact text field, including a single Hermes cache-decorated text block."""
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content, None
    if (
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
        and set(content[0]) <= {"type", "text", "cache_control"}
        and isinstance(content[0].get("text"), str)
    ):
        return content[0]["text"], 0
    return None


def replace_text(message: dict, text: str) -> None:
    slot = text_slot(message)
    if slot is None:
        raise HistoryEvidenceError("unsupported text shape")
    if slot[1] is None:
        message["content"] = text
    else:
        message["content"][slot[1]]["text"] = text


_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "of",
        "to",
        "for",
        "on",
        "in",
        "it",
        "and",
        "or",
        "what",
        "which",
        "who",
        "how",
        "about",
        "please",
        "tell",
        "me",
        "my",
        "our",
        "that",
        "this",
        "do",
        "does",
        "did",
        "again",
        "recall",
        "remember",
    ]
)


def terms(query: str) -> frozenset[str]:
    return frozenset(
        t
        for t in re.findall(r"[^\W_]+", query.casefold())
        if len(t) > 2 and t not in _STOP
    )


@dataclass(frozen=True)
class HistoryHit:
    artifact_id: str
    message: dict[str, Any]
    lexical_matches: int


class HistoryCatalog:
    def __init__(self, store: TokenTerminatorStore):
        self.store = store
        with store.connection(write=True) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS tt_context_sources (
                session_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
                source_sha TEXT NOT NULL, snapshot_sha TEXT NOT NULL,
                observed_ordinal INTEGER NOT NULL,
                PRIMARY KEY(session_id, artifact_id),
                FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id) ON DELETE RESTRICT
            )""")

    def capture(self, messages: list[dict], session_id: str) -> list[str]:
        if not session_id:
            raise HistoryEvidenceError("session identity required")
        bodies = [encode(message) for message in messages]
        snapshot_sha = digest(encode(messages))
        with self.store.connection() as conn:
            known = {
                row["source_sha"]: dict(row)
                for row in conn.execute(
                    """SELECT h.*, a.content FROM tt_context_sources h
                LEFT JOIN artifacts a ON a.artifact_id=h.artifact_id WHERE h.session_id=?""",
                    (session_id,),
                )
            }
        ids = []
        for ordinal, body in enumerate(bodies):
            sha = digest(body)
            row = known.get(sha)
            if row is not None:
                if row["content"] != body or digest(row["content"]) != sha:
                    raise HistoryEvidenceError("history evidence missing or changed")
                ids.append(row["artifact_id"])
                continue
            stored = self.store.put_artifact(
                body,
                tool_name="tt_context_history",
                session_id=session_id,
                args={"snapshot_sha": snapshot_sha, "observed_ordinal": ordinal},
                pin_request_id="tt-history-" + digest(session_id),
            )
            artifact_id = stored.artifact_id
            recovered = self.store.get_artifact(artifact_id)
            if recovered is None or recovered.content != body:
                raise HistoryEvidenceError("history vault read-back failed")
            with self.store.connection(write=True) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO tt_context_sources
                    (session_id,artifact_id,source_sha,snapshot_sha,observed_ordinal)
                    VALUES (?,?,?,?,?)""",
                    (session_id, artifact_id, sha, snapshot_sha, ordinal),
                )
            ids.append(artifact_id)
            known[sha] = {"artifact_id": artifact_id, "content": body}
        return ids

    def read(self, session_id: str, artifact_id: str) -> dict:
        with self.store.connection() as conn:
            row = conn.execute(
                """SELECT source_sha FROM tt_context_sources
                WHERE session_id=? AND artifact_id=?""",
                (session_id, artifact_id),
            ).fetchone()
        if row is None:
            raise HistoryEvidenceError("source is not in this session")
        artifact = self.store.get_artifact(artifact_id)
        if artifact is None or digest(artifact.content) != row["source_sha"]:
            raise HistoryEvidenceError("history source failed integrity verification")
        message = json.loads(artifact.content)
        if not isinstance(message, dict):
            raise HistoryEvidenceError("history source is not a message")
        return message

    def find(
        self, session_id: str, query: str, *, limit: int = 8, scan_limit: int = 10000
    ) -> list[HistoryHit]:
        """Literal lexical recall across this session's entire bounded catalog.

        Hitting the scan bound is an explicit failure, not silent newest-only search.
        Exact get remains available even when automatic search cannot run.
        """
        query_terms = terms(query)
        if not query_terms:
            return []
        with self.store.connection() as conn:
            rows = conn.execute(
                """SELECT h.artifact_id,a.content,h.source_sha
                FROM tt_context_sources h LEFT JOIN artifacts a ON a.artifact_id=h.artifact_id
                WHERE h.session_id=? ORDER BY h.artifact_id LIMIT ?""",
                (session_id, scan_limit + 1),
            ).fetchall()
        if len(rows) > scan_limit:
            raise HistoryEvidenceError("history search scan bound exceeded")
        hits = []
        for row in rows:
            if row["content"] is None or digest(row["content"]) != row["source_sha"]:
                raise HistoryEvidenceError(
                    "history catalog contains unavailable evidence"
                )
            message = json.loads(row["content"])
            slot = text_slot(message)
            # Never reactivate historical tool, system or developer authority.
            if (
                slot is None
                or message.get("role") not in {"user", "assistant"}
                or message.get("tool_calls")
            ):
                continue
            matches = len(terms(slot[0]) & query_terms)
            if matches:
                hits.append(HistoryHit(row["artifact_id"], message, matches))
        hits.sort(key=lambda hit: (-hit.lexical_matches, hit.artifact_id))
        return hits[: max(1, min(32, limit))]
