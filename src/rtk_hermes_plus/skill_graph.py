from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[\w][\w.+#/-]*", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
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


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        token
        for raw in _TOKEN_RE.findall(str(text or "").casefold())
        if (token := raw.strip("-_/.")) and len(token) >= 2 and token not in _STOPWORDS
    )


def _string_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        values = stripped.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = value
    else:
        values = (value,)
    return tuple(
        dict.fromkeys(
            item
            for raw in values
            if (item := str(raw).strip().strip("\"'"))
        )
    )


@dataclass(frozen=True)
class SkillDocument:
    """One locally installed skill used to populate the runtime-only graph."""

    name: str
    content: str
    category: str = "general"
    description: str = ""
    tags: tuple[str, ...] = ()
    related_skills: tuple[str, ...] = ()
    requires_skills: tuple[str, ...] = ()
    source: str = ""

    @property
    def fingerprint(self) -> str:
        payload = "\0".join(
            (
                self.name,
                self.category,
                self.description,
                "\0".join(self.tags),
                "\0".join(self.related_skills),
                "\0".join(self.requires_skills),
                self.content,
            )
        )
        return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()


@dataclass(frozen=True)
class SkillInternalNode:
    node_id: str
    kind: str
    title: str
    text: str = ""
    order: int = 0
    level: int = 0

    @property
    def terms(self) -> frozenset[str]:
        return _terms(f"{self.title}\n{self.text}")


@dataclass(frozen=True)
class SkillEdge:
    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class SkillNode:
    name: str
    category: str
    description: str
    tags: tuple[str, ...]
    source: str
    fingerprint: str
    internal_nodes: tuple[SkillInternalNode, ...]
    internal_edges: tuple[SkillEdge, ...]
    related_skills: tuple[str, ...]
    requires_skills: tuple[str, ...]

    @property
    def internal_terms(self) -> frozenset[str]:
        combined: set[str] = set()
        for node in self.internal_nodes:
            combined.update(node.terms)
        return frozenset(combined)


SkillDocumentProvider = Callable[[], Iterable[SkillDocument]]


def _build_internal_graph(content: str) -> tuple[tuple[SkillInternalNode, ...], tuple[SkillEdge, ...]]:
    """Turn one SKILL.md body into a bounded graph without crossing skill boundaries."""

    lines = str(content or "").splitlines()
    sections: list[SkillInternalNode] = []
    edges: list[SkillEdge] = []
    stack: list[tuple[int, str]] = []
    current_title = "root"
    current_level = 0
    current_id = "section:0"
    current_lines: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order, current_lines
        text = "\n".join(current_lines).strip()
        if text or current_id == "section:0":
            sections.append(
                SkillInternalNode(
                    node_id=current_id,
                    kind="section",
                    title=current_title,
                    text=text,
                    order=order,
                    level=current_level,
                )
            )
            order += 1
        current_lines = []

    for line in lines:
        match = _HEADING_RE.match(line)
        if not match:
            current_lines.append(line)
            continue
        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        node_id = f"section:{order}"
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            edges.append(SkillEdge(stack[-1][1], node_id, "contains"))
        if sections:
            edges.append(SkillEdge(sections[-1].node_id, node_id, "next"))
        stack.append((level, node_id))
        current_title = title
        current_level = level
        current_id = node_id

    flush()

    resource_targets: set[str] = set()
    for section in sections:
        for match in _MARKDOWN_LINK_RE.finditer(section.text):
            target = match.group(1).strip()
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            resource_id = f"resource:{target}"
            if resource_id not in resource_targets:
                sections.append(
                    SkillInternalNode(
                        node_id=resource_id,
                        kind="resource",
                        title=target,
                        order=order,
                    )
                )
                resource_targets.add(resource_id)
                order += 1
            edges.append(SkillEdge(section.node_id, resource_id, "references"))

    return tuple(sections), tuple(edges)


class SkillGraph:
    """Runtime-only graph of skill nodes, each owning an isolated internal graph.

    The package ships with no skill data. A document provider may populate the graph
    from the current host's installed skills. Skill contents remain process-local and
    are never added to provider context by this class.
    """

    def __init__(self, document_provider: SkillDocumentProvider | None = None) -> None:
        self._provider = document_provider
        self._nodes: dict[str, SkillNode] = {}
        self._idf: dict[str, float] = {}
        self._catalog_fingerprint = ""
        self._loaded = False
        self._load_error = ""

    def set_document_provider(self, provider: SkillDocumentProvider | None) -> None:
        self._provider = provider
        self.clear()

    def clear(self) -> None:
        self._nodes.clear()
        self._idf.clear()
        self._catalog_fingerprint = ""
        self._loaded = False
        self._load_error = ""

    def replace_documents(self, documents: Iterable[SkillDocument]) -> None:
        nodes: dict[str, SkillNode] = {}
        for document in documents:
            name = str(document.name or "").strip()
            if not name or name.casefold() in nodes:
                continue
            internal_nodes, internal_edges = _build_internal_graph(document.content)
            nodes[name.casefold()] = SkillNode(
                name=name,
                category=str(document.category or "general"),
                description=str(document.description or ""),
                tags=tuple(document.tags),
                source=str(document.source or ""),
                fingerprint=document.fingerprint,
                internal_nodes=internal_nodes,
                internal_edges=internal_edges,
                related_skills=tuple(document.related_skills),
                requires_skills=tuple(document.requires_skills),
            )
        self._nodes = nodes
        self._rebuild_idf()
        self._loaded = True
        self._load_error = ""

    def _rebuild_idf(self) -> None:
        frequency: Counter[str] = Counter()
        for node in self._nodes.values():
            frequency.update(node.internal_terms)
        size = max(1, len(self._nodes))
        self._idf = {
            term: math.log((size + 1) / (count + 1)) + 1.0
            for term, count in frequency.items()
        }

    @staticmethod
    def _catalog_digest(entries: Iterable[Any]) -> str:
        rows = sorted(
            (
                str(getattr(entry, "name", "") or ""),
                str(getattr(entry, "category", "") or ""),
                str(getattr(entry, "description", "") or ""),
            )
            for entry in entries
        )
        payload = "\n".join("\0".join(row) for row in rows)
        return hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()

    def sync_catalog(self, entries: Iterable[Any]) -> None:
        """Refresh local graph only when the host-visible skill catalog changes."""

        entries = tuple(entries)
        digest = self._catalog_digest(entries)
        if self._loaded and digest == self._catalog_fingerprint:
            return
        self._catalog_fingerprint = digest
        if self._provider is None:
            self._loaded = True
            return
        try:
            self.replace_documents(tuple(self._provider()))
            self._catalog_fingerprint = digest
        except Exception as exc:  # fail open: routing can keep using catalog metadata
            self._load_error = f"{type(exc).__name__}: {exc}"
            self._loaded = True

    def get(self, name: str) -> SkillNode | None:
        return self._nodes.get(str(name or "").casefold())

    def internal_score(self, prompt: str, name: str) -> float:
        """Score prompt relevance against one skill's *internal* graph only."""

        node = self.get(name)
        if node is None:
            return 0.0
        prompt_folded = str(prompt or "").casefold()
        prompt_terms = _terms(prompt)
        if not prompt_terms:
            return 0.0

        body_overlap = prompt_terms & node.internal_terms
        score = sum(1.15 * self._idf.get(term, 1.0) for term in body_overlap)

        best_heading = 0.0
        for internal in node.internal_nodes:
            if internal.kind != "section":
                continue
            title = internal.title.casefold()
            heading_terms = _terms(internal.title)
            heading_score = sum(
                1.75 * self._idf.get(term, 1.0)
                for term in prompt_terms & heading_terms
            )
            if title and title != "root" and title in prompt_folded:
                heading_score += 4.0
            best_heading = max(best_heading, heading_score)
        return min(12.0, score + best_heading)

    def required_closure(self, names: Iterable[str]) -> frozenset[str]:
        """Follow explicit requires edges only; related edges never imply necessity."""

        selected = {str(name).casefold() for name in names if name}
        queue = deque(selected)
        while queue:
            source = queue.popleft()
            node = self._nodes.get(source)
            if node is None:
                continue
            for required in node.requires_skills:
                target = str(required).casefold()
                if not target or target in selected:
                    continue
                selected.add(target)
                if target in self._nodes:
                    queue.append(target)
        return frozenset(selected)

    def related(self, name: str) -> tuple[str, ...]:
        node = self.get(name)
        return node.related_skills if node is not None else ()

    def status(self) -> dict[str, Any]:
        return {
            "loaded": self._loaded,
            "skills": len(self._nodes),
            "internal_nodes": sum(len(node.internal_nodes) for node in self._nodes.values()),
            "internal_edges": sum(len(node.internal_edges) for node in self._nodes.values()),
            "outer_related_edges": sum(len(node.related_skills) for node in self._nodes.values()),
            "outer_requires_edges": sum(len(node.requires_skills) for node in self._nodes.values()),
            "load_error": self._load_error,
        }


def discover_hermes_skill_documents() -> tuple[SkillDocument, ...]:
    """Best-effort local Hermes adapter.

    Imports Hermes lazily so the Token Terminator core stays host-agnostic. Only
    trusted/project-visible skill roots supplied by Hermes are scanned. Nothing is
    persisted or transmitted.
    """

    try:
        from agent.skill_utils import (
            get_all_skills_dirs,
            get_disabled_skill_names,
            get_project_skills_dirs,
            iter_project_skill_files,
            iter_skill_index_files,
            parse_frontmatter,
            skill_matches_environment,
            skill_matches_platform,
        )
    except Exception:
        return ()

    try:
        project_dirs = list(get_project_skills_dirs())
        normal_dirs = list(get_all_skills_dirs())
        disabled = {str(name).casefold() for name in get_disabled_skill_names()}
    except Exception:
        return ()

    documents: list[SkillDocument] = []
    seen: set[str] = set()

    def add_file(skill_md: Path, root: Path, *, qualified_name: str = "") -> None:
        try:
            raw = skill_md.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(raw)
            if not skill_matches_platform(frontmatter) or not skill_matches_environment(frontmatter):
                return
            name = str(qualified_name or frontmatter.get("name") or skill_md.parent.name).strip()
            key = name.casefold()
            if not name or key in seen or key in disabled:
                return
            description = str(frontmatter.get("description") or "")
            if not description:
                description = next(
                    (
                        line.strip()
                        for line in body.splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                    ),
                    "",
                )
            try:
                relative = skill_md.relative_to(root)
                category = relative.parts[0] if len(relative.parts) >= 3 else "general"
            except ValueError:
                category = "general"

            metadata = frontmatter.get("metadata")
            hermes_meta = (
                metadata.get("hermes", {})
                if isinstance(metadata, dict) and isinstance(metadata.get("hermes"), dict)
                else {}
            )
            tags = _string_list(hermes_meta.get("tags") or frontmatter.get("tags"))
            related = _string_list(
                hermes_meta.get("related_skills") or frontmatter.get("related_skills")
            )
            requires = tuple(
                dict.fromkeys(
                    _string_list(frontmatter.get("requires_skills"))
                    + _string_list(frontmatter.get("depends_on"))
                    + _string_list(hermes_meta.get("requires_skills"))
                )
            )
            documents.append(
                SkillDocument(
                    name=name,
                    category=category,
                    description=description,
                    tags=tags,
                    related_skills=related,
                    requires_skills=requires,
                    content=body,
                    source=str(skill_md),
                )
            )
            seen.add(key)
        except Exception:
            return

    for root in project_dirs:
        try:
            files = iter_project_skill_files(root)
            for skill_md in files:
                add_file(Path(skill_md), Path(root))
        except Exception:
            continue

    for root in normal_dirs:
        try:
            files = iter_skill_index_files(root, "SKILL.md")
            for skill_md in files:
                add_file(Path(skill_md), Path(root))
        except Exception:
            continue

    try:
        from hermes_cli.plugins import discover_plugins, get_plugin_manager

        discover_plugins()
        manager = get_plugin_manager()
        for metadata in manager.list_plugin_skill_metadata():
            name = str(metadata.get("name") or "").strip()
            if not name or name.casefold() in seen or name.casefold() in disabled:
                continue
            path = manager.find_plugin_skill(name)
            if path is not None:
                add_file(Path(path), Path(path).parent.parent, qualified_name=name)
    except Exception:
        pass

    return tuple(documents)
