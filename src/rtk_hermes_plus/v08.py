from __future__ import annotations

import uuid
from typing import Any

from .jev_context import JevReductionResult, JevSemanticReducer, _serialized_chars
from .v06 import RuntimeV06


class RuntimeV08(RuntimeV06):
    """v0.8 optional Jev semantic context reduction over the v0.7 runtime."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.jev_reducer = (
            JevSemanticReducer(
                self.store,
                self.config,
                token_budget=self.token_budget,
            )
            if self.store is not None
            else None
        )

    def _sync_token_budget(self) -> None:
        super()._sync_token_budget()
        if self.jev_reducer is not None:
            self.jev_reducer.token_budget = self.token_budget

    def llm_request_middleware(self, *, request: dict, **kwargs: Any):
        if not isinstance(request, dict):
            return super().llm_request_middleware(request=request, **kwargs)

        self._sync_token_budget()
        session_id = str(kwargs.get("session_id") or "")
        model = self._model_for(session_id, request)

        call_kwargs = dict(kwargs)
        request_id = str(
            call_kwargs.get("api_request_id") or call_kwargs.get("request_id") or ""
        )
        if not request_id:
            request_id = f"tt-{uuid.uuid4().hex}"
            call_kwargs["request_id"] = request_id

        raw_measurement = self.token_budget.measure_request(request, model=model)
        raw_attribution = self.request_attributor.measure(request, model=model)

        decision = super().llm_request_middleware(request=request, **call_kwargs)
        base_request = decision.get("request") if decision is not None else request

        jev_result = JevReductionResult(
            request=base_request,
            raw_chars=_serialized_chars(base_request),
            final_chars=_serialized_chars(base_request),
            saved_chars=0,
        )
        if (
            self.config.compiler_enabled
            and self.jev_reducer is not None
            and self.jev_reducer.enabled
        ):
            jev_result = self.jev_reducer.reduce(
                base_request,
                session_id=session_id,
                model=model,
            )

        final_request = (
            jev_result.request if jev_result.saved_chars > 0 else base_request
        )
        if decision is None and jev_result.saved_chars <= 0:
            return None
        if decision is None:
            decision = {
                "request": final_request,
                "source": "token-terminator",
                "reason": "strictly smaller Jev-routed provider request",
                "metrics": {},
            }
        else:
            decision["request"] = final_request

        final_measurement = self.token_budget.measure_request(
            final_request, model=model
        )
        token_recorded = self.token_accounting.record(
            session_id=session_id,
            request_id=request_id,
            raw=raw_measurement,
            final=final_measurement,
        )
        final_attribution = self.request_attributor.measure(
            final_request, model=model
        )
        attribution_recorded = self.request_attribution.record(
            session_id=session_id,
            request_id=request_id,
            raw=raw_attribution,
            final=final_attribution,
        )

        metrics = decision.setdefault("metrics", {})
        raw_chars = _serialized_chars(request)
        final_chars = _serialized_chars(final_request)
        metrics.update(
            {
                "raw_chars": raw_chars,
                "final_chars": final_chars,
                "end_to_end_saved_chars": max(0, raw_chars - final_chars),
                "saved_chars": max(0, raw_chars - final_chars),
                "jev": jev_result.as_dict(),
                "request_attribution_recorded": attribution_recorded,
                "token_measurement_persisted": token_recorded,
            }
        )
        # Never leak provider-bound request content through nested metrics.
        metrics["jev"].pop("request", None)

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
        if jev_result.saved_chars > 0:
            decision["reason"] = (
                "strictly smaller final provider request with optional Jev semantic routing"
            )
        return decision

    def status(self) -> dict[str, Any]:
        status = super().status()
        status["jev"] = (
            self.jev_reducer.status()
            if self.jev_reducer is not None
            else {
                "enabled": False,
                "configured": False,
                "model": self.config.jev_model,
                "error": "artifact vault unavailable",
            }
        )
        return status


def install(plugin_module: Any) -> None:
    """Install v0.8 as an additive runtime layer without rewriting older modules."""
    if getattr(plugin_module, "_tt_v08_installed", False):
        return
    plugin_module.Runtime = RuntimeV08
    plugin_module._tt_v08_installed = True
