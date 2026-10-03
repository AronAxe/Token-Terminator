"""Optional Hermes adapter. Normal TT imports never depend on Hermes being installed."""

from agent.context_engine import ContextEngine

from .history_engine import HistoryContextEngine


class TokenTerminatorContextEngine(HistoryContextEngine, ContextEngine):
    """Selectable through Hermes' supported user ContextEngine directory mechanism."""

    def __init__(self, **kwargs):
        self.threshold_tokens_cap = None
        self.max_tokens = None
        self._base_threshold_percent = self.threshold_percent
        self._tail_token_budget = None
        self._config_context_length = None
        self._model_metadata_kwargs = {}
        super().__init__(**kwargs)

    @property
    def name(self) -> str:
        return "token-terminator"

    @staticmethod
    def _coerce_threshold_tokens_cap(value) -> int | None:
        """Hermes live config uses a positive integer, or None for ratio-only."""
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
        # Removing model.context_length invalidates this cache in Hermes. Resolve
        # against the current route rather than retaining the previous window.
        if self._resolved_context_length is None:
            from agent.model_metadata import get_model_context_length

            self._resolved_context_length = get_model_context_length(
                self.model,
                config_context_length=self._config_context_length,
                **self._model_metadata_kwargs,
            )
        self.threshold_percent = self._effective_threshold_percent(
            self._resolved_context_length, self._base_threshold_percent
        )
        return self._resolved_context_length

    @context_length.setter
    def context_length(self, value: int) -> None:
        self._resolved_context_length = max(0, int(value))
        self.threshold_percent = self._effective_threshold_percent(
            self._resolved_context_length, self._base_threshold_percent
        )
        self._threshold_tokens = None

    def _effective_threshold_cap(self, context_length: int) -> int | None:
        cap = self._coerce_threshold_tokens_cap(self.threshold_tokens_cap)
        return min(cap, context_length) if cap is not None else None

    @property
    def threshold_tokens(self) -> int:
        # The host sets _threshold_tokens=None after live config edits. A plain
        # attribute silently retains stale percent/window/cap values after that.
        if self._threshold_tokens is None:
            window = self.context_length
            from agent.context_compressor import ContextCompressor

            threshold = ContextCompressor._compute_threshold_tokens(
                window, self.threshold_percent, self.max_tokens
            )
            cap = self._effective_threshold_cap(window)
            self._threshold_tokens = (
                min(threshold, cap) if cap is not None else threshold
            )
        return self._threshold_tokens

    @threshold_tokens.setter
    def threshold_tokens(self, value: int) -> None:
        self._threshold_tokens = value

    def update_model(self, model: str, context_length: int, **kwargs) -> None:
        with self._lock:
            self._model_metadata_kwargs = {
                key: kwargs[key]
                for key in ("base_url", "api_key", "provider", "custom_providers")
                if key in kwargs
            }
            if kwargs.get("max_tokens") is not None:
                self.max_tokens = self._coerce_threshold_tokens_cap(
                    kwargs["max_tokens"]
                )
            super().update_model(model, context_length, **kwargs)
            self._threshold_tokens = None

    def clone_for_agent(self):
        with self._lock:
            clone = type(self)(config=self.config, limits=self.limits)
            clone._base_threshold_percent = self._base_threshold_percent
            clone.threshold_percent = self.threshold_percent
            clone.threshold_tokens_cap = self.threshold_tokens_cap
            clone._config_context_length = self._config_context_length
            clone.update_model(
                self.model,
                self.context_length,
                max_tokens=self.max_tokens,
                **self._model_metadata_kwargs,
            )
            return clone
