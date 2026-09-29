"""Conservative final-chat policy: reversible IR first; omission only under pressure.

This is not another engine. It reuses the existing IR, JEV, exact vault and final
measurement, but deliberately skips age collapse, compiler receipts and SkillGate.
"""

from __future__ import annotations

import copy
import hashlib
import time
import uuid
from dataclasses import replace

from .context_history import encode
from .context_ir import inspect_ir
from .context_safety import plain_message, protected_prose
from .history_selection import select_history
from .jev_context import JevSemanticReducer


def input_budget(runtime, request, context, engine=None):
    """Use only a known window for this actual target; never borrow a stale fallback's."""
    adapter = runtime.token_budget
    windows = [adapter.context_limit_tokens]
    if type(context.get("context_length")) is int:
        windows.append(context["context_length"])
    if engine is not None and request.get("model") == engine.model:
        windows.append(engine.context_length)
    windows = [n for n in windows if n > 0]
    if not windows:
        return None
    reserve = max(
        [adapter.output_reserve_tokens]
        + [
            request[k]
            for k in ("max_tokens", "max_completion_tokens", "max_output_tokens")
            if type(request.get(k)) is int and request[k] > 0
        ]
    )
    return max(0, min(windows) - reserve - adapter.safety_margin_tokens)


def _minimum_omissions(original, working, proposal, measure, budget, protect_last):
    """Apply only enough of an existing JEV proposal to fit; never truncate content.

    No invented candidates: a replacement must be an exact-source receipt from the
    existing selector, at the same ordinal/role. Current/recent/protected text is a
    second deterministic veto. The search is bounded by existing scorer limits.
    """
    key = "messages" if "messages" in original else "input"
    source = original[key]
    if len(source) != len(proposal[key]):
        raise ValueError("selection changed history alignment")
    omitted = 0
    for i in range(max(0, len(source) - protect_last)):
        if measure(working).tokens <= budget:
            break
        item, candidate = source[i], proposal[key][i]
        if (
            not plain_message(item)
            or protected_prose(item["content"])
            or candidate.get("role") != item["role"]
            or not isinstance(candidate.get("content"), str)
            or not candidate["content"].startswith(
                ("[TT history ", "[Token Terminator artifact ")
            )
            or candidate == item
        ):
            continue
        trial = copy.deepcopy(working)
        trial[key][i] = copy.deepcopy(candidate)
        if measure(trial).tokens < measure(working).tokens and len(encode(trial)) < len(
            encode(working)
        ):
            working, omitted = trial, omitted + 1
    return working, omitted


def preserve_chat_request(runtime, request, *, engine=None, **context):
    """Preserve all supplied history by default, with measured reversible IR allowed.

    A known over-budget input can request bounded, guarded JEV omission. If the
    protected/unscored evidence still cannot fit, return the original and surface
    context_limit_unresolved; this fail-open hook cannot cancel a provider call.
    """
    started = time.perf_counter()
    status = {
        "policy": "preserve",
        "state": "preserved",
        "jev_calls": 0,
        "omitted_messages": 0,
    }
    session = str(context.get("session_id") or "")
    request_id = str(
        context.get("api_request_id") or context.get("request_id") or uuid.uuid4().hex
    )
    raw = None
    final = request
    try:
        if not runtime.config.compiler_enabled or runtime.store is None:
            return None
        if request.get("previous_response_id") or request.get("conversation"):
            status["state"] = "unsupported_stateful_request"
            return None
        original = copy.deepcopy(request)
        runtime._sync_token_budget()
        model = str(request.get("model") or "")
        raw = runtime.token_budget.measure_request(original, model=model)
        status["raw_tokens"] = raw.tokens
        if raw.tokens is None:
            status["state"] = "exact_tokenizer_unavailable"
            return None

        def measure(value):
            measured = runtime.token_budget.measure_request(value, model=model)
            if measured.tokens is None or (measured.backend, measured.model) != (
                raw.backend,
                raw.model,
            ):
                raise ValueError("tokenizer changed or unavailable")
            return measured

        budget = input_budget(runtime, original, context, engine)
        status["usable_context_tokens"] = budget
        working = original
        # No auxiliary scoring just to decide whether lossless IR is worthwhile.
        ir = (
            runtime.context_ir.reduce(
                original,
                session_id=session,
                request_id=request_id,
                model=model,
                require_attention=False,
            )
            if runtime.context_ir
            else None
        )
        if ir is not None:
            status["context_ir"] = ir.as_dict()
            if ir.failed_open:
                status["state"] = "ir_failed_open"
                return None
            working = ir.request
        current = measure(working)
        if budget is not None and current.tokens > budget:
            status["budget_pressure"] = True
            # The engine scorer's source/query-bound cache preserves retry behavior.
            scorer = JevSemanticReducer(
                runtime.store,
                replace(runtime.config, context_ir_enabled=True),
                transport=(engine.transport if engine is not None else None)
                or (runtime.jev_reducer.transport if runtime.jev_reducer else None),
                token_budget=runtime.token_budget,
            )
            if engine is not None:
                catalog = engine._history()
                plan = select_history(
                    original,
                    catalog=catalog,
                    session_id=session,
                    config=scorer.config,
                    limits=replace(engine.limits, recall_sources=0),
                    reducer=scorer,
                    cache=engine._score_cache,
                )
                status.update(plan.metrics)
                if plan.semantic_failed:
                    status["state"] = "jev_failed_open"
                    return None
                proposal = plan.request
                for artifact_id in plan.references:
                    catalog.read(session, artifact_id)
            else:
                reduction = scorer.reduce(
                    original, session_id=session, model=model, request_id=request_id
                )
                status["jev_calls"] = int(scorer.enabled and reduction.candidates > 0)
                status["jev_cost_usd"] = reduction.cost_usd
                if reduction.failed_open:
                    status["state"] = "jev_failed_open"
                    return None
                proposal = copy.deepcopy(reduction.request)
                # The legacy middleware gate omits on relevance/guard only. For a
                # preservation target, independently veto salient or unbound units.
                key = "messages" if "messages" in original else "input"
                attention = {score.ordinal: score for score in reduction.attention}
                for i, item in enumerate(original[key]):
                    if proposal[key][i] == item:
                        continue
                    score = attention.get(i)
                    text = item.get("content")
                    if (
                        score is None
                        or not isinstance(text, str)
                        or score.role != item.get("role")
                        or score.sha256
                        != hashlib.sha256(text.encode("utf-8")).hexdigest()
                        or max(score.relevance, score.guard, score.salience)
                        >= runtime.config.jev_relevance_threshold
                    ):
                        proposal[key][i] = copy.deepcopy(item)
            working, omitted = _minimum_omissions(
                original,
                working,
                proposal,
                measure,
                budget,
                engine.limits.protect_last if engine is not None else 6,
            )
            status["omitted_messages"] = omitted
            current = measure(working)
            if current.tokens > budget:
                status.update(
                    state="context_limit_unresolved", candidate_tokens=current.tokens
                )
                return None  # never silently force-cut protected or unscored evidence
        # Revalidate IR evidence after any scorer/transport work, before committing.
        key = "messages" if "messages" in working else "input"
        for item in working[key]:
            text = item.get("content")
            if isinstance(text, str) and text.startswith("TTIR/1 "):
                inspect_ir(text, runtime.store)
        # Verify exact source receipts after *all* operations as well.
        from .plugin import _artifact_ids_in_value

        for artifact_id in _artifact_ids_in_value(working):
            runtime.store.get_artifact(artifact_id)
        current = measure(working)
        if current.tokens >= raw.tokens or len(encode(working)) >= len(
            encode(original)
        ):
            return None
        final = working
        status.update(state="accepted", final_tokens=current.tokens)
        return {
            "request": final,
            "source": "token-terminator",
            "reason": "conservative chat target: reversible IR or bounded budget-pressure selection",
            "metrics": {
                "raw_chars": len(encode(original)),
                "final_chars": len(encode(final)),
                "saved_chars": len(encode(original)) - len(encode(final)),
                "raw_tokens": raw.tokens,
                "final_tokens": current.tokens,
                "saved_tokens": raw.tokens - current.tokens,
                "chat_target": status,
            },
        }
    except Exception as exc:  # noqa: BLE001 - preserve original, never log source/credentials
        status.update(state="failed_open", error=type(exc).__name__)
        return None
    finally:
        status["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        status.setdefault("final_tokens", raw.tokens if raw is not None else None)
        runtime._last_chat_target = status
        if raw is not None:
            try:
                runtime.token_accounting.record(
                    session_id=session,
                    request_id=request_id,
                    raw=raw,
                    final=runtime.token_budget.measure_request(
                        final, model=str(request.get("model") or "")
                    ),
                )
            except Exception:  # noqa: BLE001 - accounting must not change the decision
                status["accounting_failed"] = True
