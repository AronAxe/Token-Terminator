"""Bounded JEV attention over exact history regions; uncertain evidence stays live."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

from .config import Config, _integer
from .context_history import (
    HistoryCatalog,
    digest,
    encode,
    replace_text,
    terms,
    text_slot,
)
from .context_safety import protected_prose
from .jev_context import JevAttention, JevSemanticReducer, _Candidate


@dataclass(frozen=True)
class EngineLimits:
    max_batches: int = 2
    protect_last: int = 6
    region_chars: int = 8000
    recall_sources: int = 3
    search_sources: int = 10000

    def __post_init__(self):
        bounds = {
            "max_batches": (1, 8),
            "protect_last": (1, 64),
            "region_chars": (256, 64000),
            "recall_sources": (0, 16),
            "search_sources": (1, 100000),
        }
        for key, (low, high) in bounds.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} outside supported bounds")

    @classmethod
    def from_env(cls):
        return cls(
            max_batches=_integer("TOKEN_TERMINATOR_ENGINE_MAX_BATCHES", 2, maximum=8),
            protect_last=_integer(
                "TOKEN_TERMINATOR_ENGINE_PROTECT_LAST", 6, maximum=64
            ),
            region_chars=_integer(
                "TOKEN_TERMINATOR_ENGINE_REGION_CHARS", 8000, minimum=256, maximum=64000
            ),
            recall_sources=_integer(
                "TOKEN_TERMINATOR_ENGINE_RECALL_SOURCES", 3, minimum=0, maximum=16
            ),
            search_sources=_integer(
                "TOKEN_TERMINATOR_ENGINE_SEARCH_SOURCES", 10000, maximum=100000
            ),
        )


@dataclass
class SelectionPlan:
    request: dict
    attention: tuple[JevAttention, ...] = ()
    references: tuple[str, ...] = ()
    semantic_failed: bool = False
    metrics: dict = field(
        default_factory=lambda: {
            "jev_calls": 0,
            "jev_cache_hits": 0,
            "jev_cost_usd": None,
            "jev_input_tokens": 0,
            "jev_output_tokens": 0,
            "omitted_messages": 0,
            "recalled_sources": 0,
            "scored_regions": 0,
            "unscored_messages": 0,
        }
    )


def _plain(message: dict) -> bool:
    return (
        message.get("role") in {"user", "assistant"}
        and set(message) <= {"role", "content", "name", "type"}
        and message.get("type", "message") == "message"
        and text_slot(message) is not None
    )


def select_history(
    request: dict,
    *,
    catalog: HistoryCatalog,
    session_id: str,
    config: Config,
    limits: EngineLimits,
    reducer: JevSemanticReducer,
    cache: dict | None = None,
) -> SelectionPlan:
    plan = SelectionPlan(copy.deepcopy(request))
    key = "messages" if isinstance(request.get("messages"), list) else "input"
    messages = plan.request.get(key)
    if (
        not isinstance(messages, list)
        or not messages
        or any(not isinstance(m, dict) for m in messages)
    ):
        return plan
    # Stateful provider continuations are not a complete, locally measurable history.
    if request.get("previous_response_id") or request.get("conversation"):
        return plan
    current = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if messages[i].get("role") == "user"
        ),
        -1,
    )
    if current < 0 or text_slot(messages[current]) is None:
        return plan
    query = text_slot(messages[current])[0]
    ids = catalog.capture(messages, session_id)
    query_terms = terms(query)
    # A short/anaphoric question needs its immediate conversational referents.
    # Include exact recent, non-authority context in the *same* bounded scoring
    # body; truncating this input silently would make unrelated cache hits unsafe.
    recent = []
    for message in messages[max(0, current - limits.protect_last) : current]:
        slot = text_slot(message)
        if _plain(message) and slot is not None:
            recent.append({"role": message["role"], "content": slot[0]})
    scoring_query = encode({"current_user": query, "recent_exact_context": recent})
    cutoff = min(current, max(0, len(messages) - limits.protect_last))
    regions: list[list[int]] = []
    pending: list[int] = []
    chars = 0
    max_chars = min(limits.region_chars, config.jev_max_candidate_chars)
    for i, message in enumerate(messages[:cutoff]):
        slot = text_slot(message)
        if (
            not _plain(message)
            or slot is None
            or slot[0].startswith(("[TT history", "[Token Terminator", "[TTIR"))
        ):
            if pending:
                regions.append(pending)
                pending, chars = [], 0
            continue
        size = (
            len(encode({"role": message["role"], "content": slot[0], "ordinal": i})) + 2
        )
        # Structured evidence gets its own exact scoring region: unrelated prose
        # must not inherit its relevance/guard/salience (or vice versa). A long
        # message may stand alone within the explicit per-candidate hard bound.
        structured = slot[0].lstrip().startswith(("[", "{"))
        if size > max_chars or structured:
            if pending:
                regions.append(pending)
                pending, chars = [], 0
            if size <= config.jev_max_candidate_chars:
                regions.append([i])
            continue  # above the hard bound stays exact, unscored and inline
        if pending and chars + size > max_chars:
            regions.append(pending)
            pending, chars = [], 0
        pending.append(i)
        chars += size
    if pending:
        regions.append(pending)

    # Same endpoint/key/transport. Salience is required even when IR is disabled.
    scorer = JevSemanticReducer(
        catalog.store,
        replace(config, context_ir_enabled=True),
        transport=reducer.transport,
    )
    candidates = []
    for n, region in enumerate(regions):
        content = encode(
            [
                {
                    "role": messages[i]["role"],
                    "content": text_slot(messages[i])[0],
                    "ordinal": i,
                }
                for i in region
            ]
        )
        candidates.append(
            _Candidate({}, "content", content, "history", n, "history_region", f"c{n}")
        )
    attention = []
    references = []
    scored = set()
    costs = []
    if scorer.enabled:
        remaining = list(candidates)
        for _ in range(limits.max_batches):
            batch = []
            # Bound the *whole* outbound body, not only prose characters.
            while remaining and len(batch) < config.jev_max_candidates:
                candidate = remaining[0]
                trial = scorer._payload(scoring_query, batch + [candidate])
                if len(encode(trial)) > config.jev_max_state_chars:
                    if batch:
                        break
                    remaining.pop(0)  # too large is retained, never silently dropped
                    continue
                batch.append(remaining.pop(0))
            if not batch:
                break
            cache_key = digest(encode(scorer._payload(scoring_query, batch)))
            if cache is not None and cache_key in cache:
                result = replace(
                    cache[cache_key], input_tokens=0, output_tokens=0, cost_usd=0.0
                )
                plan.metrics["jev_cache_hits"] += 1
            else:
                result = scorer.score_batch(scoring_query, batch)
                plan.metrics["jev_calls"] += 1
                if (
                    cache is not None
                    and not result.failed_open
                    and len(result.attention) == len(batch)
                ):
                    if len(cache) >= 32:
                        cache.pop(next(iter(cache)))
                    cache[cache_key] = copy.deepcopy(result)
            plan.metrics["jev_input_tokens"] += result.input_tokens
            plan.metrics["jev_output_tokens"] += result.output_tokens
            costs.append(result.cost_usd)
            if result.failed_open:
                plan.semantic_failed = True
                # A transport/protocol failure rolls back ALL semantic edits in this request.
                plan.request = copy.deepcopy(request)
                return plan
            by_ordinal = {score.ordinal: score for score in result.attention}
            for candidate in batch:
                score = by_ordinal.get(candidate.ordinal)
                if score is None:
                    continue
                plan.metrics["scored_regions"] += 1
                for i in regions[candidate.ordinal]:
                    scored.add(i)
                    source = text_slot(messages[i])[0]
                    attention.append(
                        JevAttention(
                            i,
                            messages[i]["role"],
                            digest(source),
                            score.relevance,
                            score.guard,
                            score.salience,
                        )
                    )
                    if (
                        max(score.relevance, score.guard, score.salience)
                        < config.jev_relevance_threshold
                        and not protected_prose(source)
                        and not (terms(source) & query_terms)
                    ):
                        # Every omitted message retains its role and exact evidence reference.
                        replace_text(
                            messages[i],
                            f"[TT history {ids[i]}; recover: token_terminator_history action=get]",
                        )
                        references.append(ids[i])
                        plan.metrics["omitted_messages"] += 1
    plan.metrics["unscored_messages"] = sum(len(region) for region in regions) - len(
        scored
    )
    if costs and all(cost is not None for cost in costs):
        plan.metrics["jev_cost_usd"] = sum(costs)
    plan.attention = tuple(attention)

    # All full-history material is reconsidered each request. Also recover exact
    # lexical hits missing from a resumed/tail-only host transcript. These are
    # labeled historical evidence, never promoted to system/developer authority.
    if limits.recall_sources:
        present = {
            (m.get("role"), text_slot(m)[0].strip())
            for m in request[key]
            if text_slot(m) is not None
        }
        recalled = []
        for hit in catalog.find(
            session_id, query, limit=32, scan_limit=limits.search_sources
        ):
            if (hit.message.get("role"), text_slot(hit.message)[0].strip()) in present:
                continue
            source = text_slot(hit.message)[0]
            if len(source) > config.jev_max_candidate_chars or source.startswith(
                ("[TT history", "[Token Terminator", "[TTIR")
            ):
                continue
            recalled.append(
                {
                    "role": "assistant",
                    "content": f"[Exact historical evidence {hit.artifact_id}; original role={hit.message['role']}; not a new instruction]\n"
                    + source,
                }
            )
            references.append(hit.artifact_id)
            if len(recalled) >= limits.recall_sources:
                break
        if recalled:
            messages[current:current] = recalled
            plan.metrics["recalled_sources"] = len(recalled)
            plan.attention = tuple(
                replace(
                    a,
                    ordinal=a.ordinal + len(recalled)
                    if a.ordinal >= current
                    else a.ordinal,
                )
                for a in attention
            )
    plan.references = tuple(references)
    return plan
