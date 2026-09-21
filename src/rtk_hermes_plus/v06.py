from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from .enhancements import RuntimeV05
from .request_attribution import RequestAttributionAccounting, RequestAttributor
from .skill_graph import (
    SkillDocument,
    SkillDocumentProvider,
    SkillGraph,
    discover_hermes_skill_documents,
)
from .skillgate import SkillEntry, SkillGate, SkillGateResult


def _serialized_chars(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


class RuntimeV06(RuntimeV05):
    """v0.6 routing/accounting layer over the stable v0.5 runtime."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.request_attributor = RequestAttributor(self.token_budget)
        self.request_attribution = RequestAttributionAccounting(self.store)
        self.skill_graph = SkillGraph(discover_hermes_skill_documents)
        self.skill_gate = SkillGate(self.token_budget, skill_graph=self.skill_graph)

    def _sync_token_budget(self) -> None:
        super()._sync_token_budget()
        if hasattr(self, "request_attributor"):
            self.request_attributor.token_budget = self.token_budget
        if hasattr(self, "skill_gate"):
            self.skill_gate.token_budget = self.token_budget

    def set_skill_document_provider(
        self, provider: SkillDocumentProvider | None
    ) -> None:
        """Replace the host adapter that supplies installed skill documents.

        The graph ships empty. Hosts populate it from their own local skill
        inventory; Token Terminator never carries a built-in skill catalog.
        """
        self.skill_graph.set_document_provider(provider)

    def replace_skill_documents(self, documents: list[SkillDocument]) -> None:
        """Populate the runtime graph explicitly for a non-Hermes host or test."""
        self.skill_graph.set_document_provider(None)
        self.skill_graph.replace_documents(documents)

    def set_skill_scorer(
        self, scorer: Callable[[str, SkillEntry], float] | None
    ) -> None:
        """Install an optional local/learned skill relevance scorer.

        The scorer receives only the current user prompt and one skill routing
        card. Returning a larger number means more relevant. Passing ``None``
        restores the deterministic lexical-IDF scorer.
        """
        self.skill_gate.set_scorer(scorer)

    def llm_request_middleware(self, *, request: dict, **kwargs: Any):
        if not isinstance(request, dict):
            return super().llm_request_middleware(request=request, **kwargs)

        self._sync_token_budget()
        session_id = str(kwargs.get("session_id") or "")
        model = self._model_for(session_id, request)
        if session_id and model:
            self._session_models[session_id] = model

        call_kwargs = dict(kwargs)
        request_id = str(
            call_kwargs.get("api_request_id") or call_kwargs.get("request_id") or ""
        )
        if not request_id:
            request_id = f"tt-{uuid.uuid4().hex}"
            call_kwargs["request_id"] = request_id

        raw_measurement = self.token_budget.measure_request(request, model=model)
        raw_attribution = self.request_attributor.measure(request, model=model)

        if self.config.compiler_enabled:
            skill_gate = self.skill_gate.route(request, model=model)
        else:
            raw_chars = _serialized_chars(request)
            skill_gate = SkillGateResult(
                request=request,
                changed=False,
                raw_chars=raw_chars,
                final_chars=raw_chars,
                reason="request compiler disabled in current mode",
            )

        if skill_gate.changed:
            self.metrics.add("skillgate_requests")
            self.metrics.add("skillgate_catalog_skills", skill_gate.catalog_skills)
            self.metrics.add("skillgate_selected_skills", skill_gate.selected_skills)
            self.metrics.add("skillgate_removed_skills", skill_gate.removed_skills)
            self.metrics.add("skillgate_saved_chars", skill_gate.saved_chars)
            if skill_gate.saved_tokens is not None:
                self.metrics.add("skillgate_saved_tokens", skill_gate.saved_tokens)

        routed_request = skill_gate.request if skill_gate.changed else request
        decision = super().llm_request_middleware(
            request=routed_request,
            **call_kwargs,
        )
        final_request = (
            decision.get("request") if decision is not None else routed_request
        )

        final_measurement = self.token_budget.measure_request(
            final_request, model=model
        )
        # RuntimeV05 has already recorded routed->final. Replace that same
        # request identity with the true original->final measurement so v0.6
        # savings include SkillGate rather than double-accounting around it.
        token_recorded = self.token_accounting.record(
            session_id=session_id,
            request_id=request_id,
            raw=raw_measurement,
            final=final_measurement,
        )
        final_attribution = self.request_attributor.measure(final_request, model=model)
        attribution_recorded = self.request_attribution.record(
            session_id=session_id,
            request_id=request_id,
            raw=raw_attribution,
            final=final_attribution,
        )

        if decision is None and not skill_gate.changed:
            return None
        if decision is None:
            decision = {
                "request": final_request,
                "source": "token-terminator",
                "reason": "strictly smaller skill-routed provider request",
                "metrics": {},
            }

        metrics = decision.setdefault("metrics", {})
        raw_chars = _serialized_chars(request)
        final_chars = _serialized_chars(final_request)
        metrics.update(
            {
                "raw_chars": raw_chars,
                "final_chars": final_chars,
                "end_to_end_saved_chars": max(0, raw_chars - final_chars),
                "saved_chars": max(0, raw_chars - final_chars),
                "skill_gate": skill_gate.as_dict(),
                "request_attribution_recorded": attribution_recorded,
                "token_measurement_persisted": token_recorded,
            }
        )
        if raw_measurement.tokens is not None and final_measurement.tokens is not None:
            metrics.update(
                {
                    "raw_tokens": raw_measurement.tokens,
                    "final_tokens": final_measurement.tokens,
                    "saved_tokens": raw_measurement.tokens - final_measurement.tokens,
                    "token_savings_source": "exact-tokenizer",
                }
            )
        else:
            metrics.update(
                {
                    "estimated_saved_tokens": round(
                        max(0, raw_chars - final_chars) / 4
                    ),
                    "token_savings_source": "chars/4-fallback",
                }
            )
        metrics["request_attribution"] = {
            "raw": raw_attribution.as_dict(),
            "final": final_attribution.as_dict(),
        }
        if skill_gate.changed:
            decision["reason"] = (
                "strictly smaller final provider request with SkillGate routing"
            )
        return decision

    def observe_tool_call(self, *, tool_name: str, args: dict, **kwargs: Any) -> None:
        if tool_name == "skill_view" and isinstance(args, dict) and args.get("name"):
            self.metrics.add("skillgate_skill_loads")
        super().observe_tool_call(tool_name=tool_name, args=args, **kwargs)

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["request_attribution"] = self.request_attribution.summary()
        status["skill_graph"] = self.skill_graph.status()
        status["skill_gate"] = {
            "enabled": self.skill_gate.enabled and self.config.compiler_enabled,
            "max_skills": self.skill_gate.max_skills,
            "min_score": self.skill_gate.min_score,
            "min_catalog_skills": self.skill_gate.min_catalog_skills,
            "scorer": "custom" if self.skill_gate.scorer is not None else "lexical-idf",
        }
        return status


def install(plugin_module: Any) -> None:
    """Install v0.6 behavior without changing host adapter contracts."""
    if getattr(plugin_module, "_tt_v06_installed", False):
        return
    plugin_module.Runtime = RuntimeV06
    plugin_module._tt_v06_installed = True
