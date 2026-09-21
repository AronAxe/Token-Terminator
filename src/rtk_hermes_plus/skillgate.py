from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .token_budget import TokenBudgetAdapter

_SKILLS_BLOCK_RE = re.compile(
    r"<available_skills>(?P<body>.*?)</available_skills>", re.IGNORECASE | re.DOTALL
)
_TOKEN_RE = re.compile(r"[\w][\w.+#/-]*", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "do",
        "for",
        "from",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "this",
        "to",
        "use",
        "we",
        "what",
        "when",
        "with",
        "you",
        "your",
    }
)
_DISCOVERY_NAMES = frozenset({"skills_list", "skill_view"})
_INSTRUCTION_KEYS = ("instructions", "system", "developer")
_CONVERSATION_KEYS = ("messages", "input")
_INSTRUCTION_ROLES = frozenset({"system", "developer"})


def _serialize(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _tokens(text: str) -> tuple[str, ...]:
    result: list[str] = []
    for match in _TOKEN_RE.findall(str(text or "").casefold()):
        token = match.strip("-_/.")
        if len(token) >= 2 and token not in _STOPWORDS:
            result.append(token)
    return tuple(result)


def _text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "input_text", "output_text"):
                    part = item.get(key)
                    if isinstance(part, str):
                        chunks.append(part)
        return "\n".join(chunks)
    if isinstance(value, dict):
        for key in ("text", "content", "input_text"):
            part = value.get(key)
            if isinstance(part, str):
                return part
    return ""


def latest_user_text(request: Any) -> str:
    if not isinstance(request, dict):
        return ""
    for key in ("messages", "input"):
        value = request.get(key)
        if isinstance(value, str) and key == "input":
            return value
        if not isinstance(value, list):
            continue
        for item in reversed(value):
            if isinstance(item, dict) and str(item.get("role") or "").lower() == "user":
                return _text_content(item.get("content", item))
    return ""


def _tool_names(request: Any) -> set[str]:
    if not isinstance(request, dict):
        return set()
    result: set[str] = set()
    tools = request.get("tools")
    if not isinstance(tools, list):
        return result
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if isinstance(name, str):
            result.add(name)
        function = tool.get("function")
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            result.add(str(function["name"]))
    return result


@dataclass(frozen=True)
class SkillEntry:
    category: str
    name: str
    description: str

    @property
    def searchable(self) -> str:
        return f"{self.name} {self.category} {self.description}".strip()


@dataclass(frozen=True)
class SkillGateResult:
    request: dict[str, Any]
    changed: bool
    catalog_skills: int = 0
    selected_skills: int = 0
    removed_skills: int = 0
    selected_names: tuple[str, ...] = ()
    raw_chars: int = 0
    final_chars: int = 0
    raw_tokens: int | None = None
    final_tokens: int | None = None
    tokenizer_backend: str = ""
    reason: str = ""

    @property
    def saved_chars(self) -> int:
        return max(0, self.raw_chars - self.final_chars)

    @property
    def saved_tokens(self) -> int | None:
        if self.raw_tokens is None or self.final_tokens is None:
            return None
        return max(0, self.raw_tokens - self.final_tokens)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "catalog_skills": self.catalog_skills,
            "selected_skills": self.selected_skills,
            "removed_skills": self.removed_skills,
            "selected_names": list(self.selected_names),
            "raw_chars": self.raw_chars,
            "final_chars": self.final_chars,
            "saved_chars": self.saved_chars,
            "raw_tokens": self.raw_tokens,
            "final_tokens": self.final_tokens,
            "saved_tokens": self.saved_tokens,
            "tokenizer_backend": self.tokenizer_backend,
            "reason": self.reason,
        }


class SkillGate:
    """Route large skill catalogs down to the entries relevant this turn.

    SkillGate recognizes Hermes-style ``<available_skills>`` blocks in trusted
    system/developer instruction fields. It never rewrites user, assistant, or
    tool content that merely quotes the same tag. Routing activates only when
    both ``skills_list`` and ``skill_view`` are provider-visible so filtered
    skills remain discoverable on demand.

    There is no skill-count ceiling by default: every skill whose score clears
    ``min_score`` is retained. ``max_skills`` is an explicit opt-in cap for hosts
    with their own bounded-context requirements.

    The default scorer is deterministic lexical-IDF. A future tiny learned
    reranker can be injected through ``scorer`` without changing the middleware.
    """

    def __init__(
        self,
        token_budget: TokenBudgetAdapter,
        *,
        enabled: bool = True,
        max_skills: int | None = None,
        min_score: float = 2.0,
        min_catalog_skills: int = 8,
        always_keep: tuple[str, ...] = (),
        scorer: Callable[[str, SkillEntry], float] | None = None,
    ) -> None:
        self.token_budget = token_budget
        self.enabled = bool(enabled)
        self.max_skills = None if max_skills is None else max(1, int(max_skills))
        self.min_score = max(0.0, float(min_score))
        self.min_catalog_skills = max(1, int(min_catalog_skills))
        self.always_keep = frozenset(name.casefold() for name in always_keep if name)
        self.scorer = scorer

    def set_scorer(self, scorer: Callable[[str, SkillEntry], float] | None) -> None:
        self.scorer = scorer

    @staticmethod
    def _parse(body: str) -> list[SkillEntry]:
        entries: list[SkillEntry] = []
        category = "general"
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("["):
                continue
            if not stripped.startswith("-") and stripped.endswith(":"):
                category = stripped[:-1].strip() or "general"
                continue
            if not stripped.startswith("-"):
                continue
            payload = stripped[1:].strip()
            if not payload:
                continue
            if ": " in payload:
                name, description = payload.rsplit(": ", 1)
            else:
                name, description = payload, ""
            name = name.strip()
            if not name:
                continue
            entries.append(
                SkillEntry(
                    category=category,
                    name=name,
                    description=description.strip(),
                )
            )
        return entries

    @staticmethod
    def _idf(entries: list[SkillEntry]) -> dict[str, float]:
        document_frequency: Counter[str] = Counter()
        for entry in entries:
            document_frequency.update(set(_tokens(entry.searchable)))
        size = max(1, len(entries))
        return {
            token: math.log((size + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }

    def _score_default(
        self,
        prompt: str,
        entry: SkillEntry,
        *,
        idf: dict[str, float],
    ) -> float:
        prompt_folded = prompt.casefold()
        name_folded = entry.name.casefold()
        score = 0.0
        if name_folded and name_folded in prompt_folded:
            score += 20.0

        prompt_terms = set(_tokens(prompt))
        if not prompt_terms:
            return score
        name_terms = set(_tokens(entry.name))
        category_terms = set(_tokens(entry.category))
        description_terms = set(_tokens(entry.description))

        score += sum(5.0 * idf.get(token, 1.0) for token in prompt_terms & name_terms)
        score += sum(
            2.5 * idf.get(token, 1.0) for token in prompt_terms & category_terms
        )
        score += sum(
            1.0 * idf.get(token, 1.0) for token in prompt_terms & description_terms
        )
        return score

    def _select(self, prompt: str, entries: list[SkillEntry]) -> list[SkillEntry]:
        idf = self._idf(entries)
        if self.skill_graph is not None:
            # The graph starts empty and is populated from this host's installed
            # skills only when the provider-visible catalog is first encountered
            # or changes. Skill contents never enter the provider request here.
            self.skill_graph.sync_catalog(entries)

        scores: dict[str, tuple[float, SkillEntry]] = {}
        for entry in entries:
            key = entry.name.casefold()
            if key in self.always_keep:
                score = float("inf")
            elif self.scorer is not None:
                try:
                    score = float(self.scorer(prompt, entry))
                except Exception:  # noqa: BLE001 - routing extension must fail open
                    score = self._score_default(prompt, entry, idf=idf)
            else:
                score = self._score_default(prompt, entry, idf=idf)

            # The outer catalog card stays compact. The internal graph contributes
            # relevance from the actual installed skill without flattening skill
            # contents together or exposing them to the provider.
            if self.skill_graph is not None and score != float("inf"):
                score += self.skill_graph.internal_score(prompt, entry.name)
            scores[key] = (score, entry)

        if self.skill_graph is not None:
            # Explicit "related_skills" edges are weak hints only. They may lift
            # an already somewhat relevant skill, but never make an unrelated
            # neighbor relevant merely because two skills are connected.
            direct_selected = {
                key for key, (score, _entry) in scores.items() if score >= self.min_score
            }
            for source in tuple(direct_selected):
                source_score = scores[source][0]
                if source_score == float("inf"):
                    relation_boost = 1.0
                else:
                    relation_boost = min(1.0, max(0.25, source_score * 0.05))
                for related in self.skill_graph.related(source):
                    target = str(related).casefold()
                    if target not in scores:
                        continue
                    target_score, target_entry = scores[target]
                    if 0.0 < target_score < self.min_score:
                        scores[target] = (target_score + relation_boost, target_entry)

            selected_names = {
                key for key, (score, _entry) in scores.items() if score >= self.min_score
            }
            # "requires" is different from "related": explicit dependencies are
            # part of the selected procedure and are followed transitively.
            required = self.skill_graph.required_closure(
                scores[key][1].name for key in selected_names
            )
            selected_names.update(name for name in required if name in scores)
        else:
            selected_names = {
                key for key, (score, _entry) in scores.items() if score >= self.min_score
            }

        scored = [
            (score, key, entry)
            for key, (score, entry) in scores.items()
            if key in selected_names
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [item[2] for item in scored]
        if self.max_skills is None:
            return selected
        return selected[: self.max_skills]

    @staticmethod
    def _render(entries: list[SkillEntry], *, total: int) -> str:
        if not entries:
            body = (
                "  [Token Terminator SkillGate: no direct match. "
                "Use skills_list(query=...) to discover a specialized skill, "
                "then skill_view(name) to load it.]"
            )
            return f"<available_skills>\n{body}\n</available_skills>"

        lines = [
            "<available_skills>",
            (
                f"  [Token Terminator SkillGate: {len(entries)}/{total} likely relevant. "
                "Other skills remain available through skills_list(query=...) and skill_view(name).]"
            ),
        ]
        current_category = None
        for entry in entries:
            if entry.category != current_category:
                current_category = entry.category
                lines.append(f"  {current_category}:")
            suffix = f": {entry.description}" if entry.description else ""
            lines.append(f"    - {entry.name}{suffix}")
        lines.append("</available_skills>")
        return "\n".join(lines)

    def _route_text(self, text: str, prompt: str) -> tuple[str, int, list[SkillEntry]]:
        total_entries = 0
        selected_all: list[SkillEntry] = []

        def replace(match: re.Match[str]) -> str:
            nonlocal total_entries
            entries = self._parse(match.group("body"))
            if len(entries) < self.min_catalog_skills:
                return match.group(0)
            selected = self._select(prompt, entries)
            total_entries += len(entries)
            selected_all.extend(selected)
            return self._render(selected, total=len(entries))

        return _SKILLS_BLOCK_RE.sub(replace, text), total_entries, selected_all

    def _route_instruction_value(
        self, value: Any, prompt: str
    ) -> tuple[Any, int, list[SkillEntry]]:
        """Route skill catalogs only inside a trusted instruction value."""
        if isinstance(value, str):
            if "<available_skills>" not in value.lower():
                return value, 0, []
            return self._route_text(value, prompt)
        if isinstance(value, list):
            total = 0
            selected: list[SkillEntry] = []
            output: list[Any] = []
            for item in value:
                routed, count, chosen = self._route_instruction_value(item, prompt)
                output.append(routed)
                total += count
                selected.extend(chosen)
            return output, total, selected
        if isinstance(value, dict):
            total = 0
            selected: list[SkillEntry] = []
            output: dict[Any, Any] = {}
            for key, item in value.items():
                routed, count, chosen = self._route_instruction_value(item, prompt)
                output[key] = routed
                total += count
                selected.extend(chosen)
            return output, total, selected
        return value, 0, []

    def _route_instruction_fields(
        self, request: dict[str, Any], prompt: str
    ) -> tuple[dict[str, Any], int, list[SkillEntry]]:
        candidate = copy.deepcopy(request)
        total = 0
        selected: list[SkillEntry] = []

        for key in _INSTRUCTION_KEYS:
            if key not in candidate:
                continue
            routed, count, chosen = self._route_instruction_value(
                candidate[key], prompt
            )
            candidate[key] = routed
            total += count
            selected.extend(chosen)

        for key in _CONVERSATION_KEYS:
            items = candidate.get(key)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip().lower()
                if role not in _INSTRUCTION_ROLES:
                    continue
                if "content" not in item:
                    continue
                routed, count, chosen = self._route_instruction_value(
                    item["content"], prompt
                )
                candidate[key][index]["content"] = routed
                total += count
                selected.extend(chosen)

        return candidate, total, selected

    def route(self, request: dict[str, Any], *, model: str = "") -> SkillGateResult:
        raw_chars = len(_serialize(request))
        if not self.enabled:
            return SkillGateResult(
                request=request,
                changed=False,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="disabled",
            )
        if not _DISCOVERY_NAMES.issubset(_tool_names(request)):
            return SkillGateResult(
                request=request,
                changed=False,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="skill discovery tools unavailable",
            )
        prompt = latest_user_text(request)
        if not prompt.strip():
            return SkillGateResult(
                request=request,
                changed=False,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="no user prompt available",
            )

        candidate, catalog_count, selected = self._route_instruction_fields(
            request, prompt
        )
        if catalog_count <= 0 or candidate == request:
            return SkillGateResult(
                request=request,
                changed=False,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="no routable skill catalog",
            )
        final_chars = len(_serialize(candidate))
        if final_chars >= raw_chars:
            return SkillGateResult(
                request=request,
                changed=False,
                catalog_skills=catalog_count,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="candidate not smaller in characters",
            )

        raw_tokens = self.token_budget.measure_request(request, model=model)
        final_tokens = self.token_budget.measure_request(candidate, model=model)
        if (
            raw_tokens.available
            and final_tokens.available
            and int(final_tokens.tokens or 0) >= int(raw_tokens.tokens or 0)
        ):
            return SkillGateResult(
                request=request,
                changed=False,
                catalog_skills=catalog_count,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                raw_tokens=int(raw_tokens.tokens or 0),
                final_tokens=int(raw_tokens.tokens or 0),
                tokenizer_backend=raw_tokens.backend,
                reason="candidate not smaller in tokens",
            )

        unique_names = tuple(dict.fromkeys(entry.name for entry in selected))
        return SkillGateResult(
            request=candidate,
            changed=True,
            catalog_skills=catalog_count,
            selected_skills=len(unique_names),
            removed_skills=max(0, catalog_count - len(unique_names)),
            selected_names=unique_names,
            raw_chars=raw_chars,
            final_chars=final_chars,
            raw_tokens=int(raw_tokens.tokens or 0) if raw_tokens.available else None,
            final_tokens=int(final_tokens.tokens or 0)
            if final_tokens.available
            else None,
            tokenizer_backend=(
                final_tokens.backend if final_tokens.available else "character-fallback"
            ),
            reason="routed skill catalog",
        )
