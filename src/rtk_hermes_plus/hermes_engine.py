"""Hermes adapter with live-config and route-local model-window compatibility."""

from agent.context_engine import ContextEngine

from .history_engine import HistoryContextEngine


class TokenTerminatorContextEngine(HistoryContextEngine, ContextEngine):
    """Hermes updates its selected engine through context_compressor as well."""

    def __init__(self, **kwargs):
        self.threshold_tokens_cap = None
        self._config_context_length = None
        self._model_metadata_kwargs = {}
        self._resolved_context_length = 0
        self._threshold_tokens = self._tail_token_budget = None
        super().__init__(**kwargs)

    @property
    def name(self) -> str:
        return "token-terminator"

    @staticmethod
    def _coerce_threshold_tokens_cap(value) -> int | None:
        """Positive integer or None, as required by Hermes' live-config hook."""
        try:
            cap = int(value) if value is not None else 0
        except (TypeError, ValueError, OverflowError):
            return None
        return cap if cap > 0 else None

    @staticmethod
    def _effective_threshold_percent(context_length, threshold_percent):
        from agent.context_compressor import ContextCompressor

        return ContextCompressor._effective_threshold_percent(
            context_length, threshold_percent
        )

    @property
    def context_length(self) -> int:
        if self._resolved_context_length is None:
            from agent.model_metadata import get_model_context_length

            self._resolved_context_length = get_model_context_length(
                self.model,
                config_context_length=self._config_context_length,
                **self._model_metadata_kwargs,
            )
        return self._resolved_context_length

    @context_length.setter
    def context_length(self, value: int) -> None:
        self._resolved_context_length = max(0, int(value))
        self._threshold_tokens = self._tail_token_budget = None

    def _effective_threshold_cap(self, context_length: int) -> int | None:
        cap = self._coerce_threshold_tokens_cap(self.threshold_tokens_cap)
        return min(cap, context_length) if cap is not None else None

    @property
    def threshold_tokens(self) -> int:
        if self._threshold_tokens is None:
            window = self.context_length
            base = getattr(self, "_base_threshold_percent", self.threshold_percent)
            self.threshold_percent = self._effective_threshold_percent(window, base)
            threshold = int(window * self.threshold_percent)
            cap = self._effective_threshold_cap(window)
            self._threshold_tokens = (
                min(threshold, cap) if cap is not None else threshold
            )
        return self._threshold_tokens

    @threshold_tokens.setter
    def threshold_tokens(self, value: int) -> None:
        self._threshold_tokens = value

    def update_model(self, model: str, context_length: int, **kwargs) -> None:
        from agent.context_compressor import resolve_model_threshold

        with self._lock:
            self._model_metadata_kwargs = {
                key: kwargs[key]
                for key in ("base_url", "api_key", "provider", "custom_providers")
                if key in kwargs
            }
            if not hasattr(self, "_config_threshold_percent"):
                self._config_threshold_percent = self.threshold_percent
            self._base_threshold_percent = resolve_model_threshold(
                model,
                getattr(self, "model_thresholds", {}),
                self._config_threshold_percent,
                kwargs.get("provider", ""),
            )
            self.threshold_percent = self._effective_threshold_percent(
                context_length, self._base_threshold_percent
            )
            super().update_model(model, context_length, **kwargs)
            self._threshold_tokens = self._tail_token_budget = None

    def select_context(self, request_messages, **kwargs):
        from .call_scope import internal_operation

        if internal_operation():
            return None
        with self._lock:
            # The hook carries the host's current route window, not a fixed TT cap.
            # Do not use update_model here: that would reset retry/usage state.
            budget = kwargs.get("budget_tokens", 0)
            if type(budget) is int and budget > 0:
                self.context_length = budget
            return super().select_context(request_messages, **kwargs)

    def clone_for_agent(self):
        with self._lock:
            clone = type(self)(config=self.config, limits=self.limits)
            clone.threshold_percent = self.threshold_percent
            clone.threshold_tokens_cap = self.threshold_tokens_cap
            clone._config_context_length = self._config_context_length
            for key in ("_config_threshold_percent", "_base_threshold_percent"):
                if hasattr(self, key):
                    setattr(clone, key, getattr(self, key))
            clone.model_thresholds = dict(getattr(self, "model_thresholds", {}))
            clone.update_model(
                self.model, self.context_length, **self._model_metadata_kwargs
            )
            return clone

    def get_status(self):
        result = super().get_status()
        result["adapter_compat"] = "hermes-live-compression-v1"
        return result
