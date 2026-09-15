from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})
_OPENAI_MODEL_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3", "o4")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _serialize(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _tokenizer_model_name(model: str) -> str:
    """Normalize common provider-qualified model names for tokenizer lookup."""
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    # OpenRouter and several compatible gateways expose names like
    # ``openai/gpt-5``. Tiktoken expects the provider-local model name.
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if normalized.lower().startswith("openai:"):
        normalized = normalized.split(":", 1)[1]
    return normalized


@dataclass(frozen=True)
class TokenMeasurement:
    tokens: int | None
    backend: str
    model: str = ""

    @property
    def available(self) -> bool:
        return self.tokens is not None


class TokenBudgetAdapter:
    """Best-available tokenizer alignment with explicit fallback provenance.

    A configured Hugging Face ``tokenizer.json`` wins, followed by tiktoken
    model lookup or a configured tiktoken encoding. The base package ships with
    tiktoken so OpenAI-family models are measured automatically. If no suitable
    tokenizer exists, callers retain Token Terminator's character invariant and
    reporting labels the result as a fallback rather than pretending it is an
    exact token count.

    Measurements use canonical request JSON. That makes reduction deltas stable
    and tokenizer-aware, but provider-specific hidden framing may still add
    billed tokens. Provider adapters can later supply stricter framing-aware
    counters without changing this interface.
    """

    def __init__(self) -> None:
        self.enabled = _env_bool("TOKEN_TERMINATOR_TOKEN_BUDGET", True)
        tokenizer_json = os.getenv("TOKEN_TERMINATOR_TOKENIZER_JSON", "").strip()
        self.tokenizer_json = (
            Path(tokenizer_json).expanduser() if tokenizer_json else None
        )
        self.encoding_name = os.getenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", "").strip()
        self.context_limit_tokens = _env_int("TOKEN_TERMINATOR_CONTEXT_LIMIT_TOKENS", 0)
        self.output_reserve_tokens = _env_int(
            "TOKEN_TERMINATOR_OUTPUT_RESERVE_TOKENS", 4096
        )
        self.safety_margin_tokens = _env_int(
            "TOKEN_TERMINATOR_TOKEN_SAFETY_MARGIN", 512
        )
        self._hf_attempted = False
        self._hf_tokenizer: Any = None
        self._tiktoken_attempted = False
        self._tiktoken: Any = None
        self._encodings: dict[str, tuple[Any, str]] = {}

    @property
    def usable_context_tokens(self) -> int | None:
        if self.context_limit_tokens <= 0:
            return None
        return max(
            0,
            self.context_limit_tokens
            - self.output_reserve_tokens
            - self.safety_margin_tokens,
        )

    def _huggingface(self) -> Any:
        if self._hf_attempted:
            return self._hf_tokenizer
        self._hf_attempted = True
        if not self.tokenizer_json or not self.tokenizer_json.is_file():
            return None
        try:
            from tokenizers import Tokenizer

            self._hf_tokenizer = Tokenizer.from_file(str(self.tokenizer_json))
        except (ImportError, OSError, ValueError):
            self._hf_tokenizer = None
        return self._hf_tokenizer

    def _tiktoken_module(self) -> Any:
        if self._tiktoken_attempted:
            return self._tiktoken
        self._tiktoken_attempted = True
        try:
            import tiktoken

            self._tiktoken = tiktoken
        except ImportError:
            self._tiktoken = None
        return self._tiktoken

    def _tiktoken_encoding(self, model: str) -> tuple[Any, str] | tuple[None, str]:
        tiktoken = self._tiktoken_module()
        if tiktoken is None:
            return None, ""

        lookup_model = _tokenizer_model_name(model)
        cache_key = lookup_model or self.encoding_name or ""
        if cache_key in self._encodings:
            return self._encodings[cache_key]

        encoding = None
        label = ""
        if lookup_model:
            try:
                encoding = tiktoken.encoding_for_model(lookup_model)
                label = f"tiktoken:model:{lookup_model}"
            except KeyError:
                encoding = None

        if encoding is None and self.encoding_name:
            try:
                encoding = tiktoken.get_encoding(self.encoding_name)
                label = f"tiktoken:encoding:{self.encoding_name}"
            except ValueError:
                encoding = None

        # Recent OpenAI families use o200k_base. Keep the fallback narrowly
        # scoped rather than silently applying an OpenAI tokenizer to unrelated
        # model families.
        if encoding is None and lookup_model.lower().startswith(_OPENAI_MODEL_PREFIXES):
            try:
                encoding = tiktoken.get_encoding("o200k_base")
                label = "tiktoken:encoding:o200k_base"
            except ValueError:
                encoding = None

        if encoding is not None:
            self._encodings[cache_key] = (encoding, label)
        return encoding, label

    def measure_text(self, text: str, *, model: str = "") -> TokenMeasurement:
        model = str(model or "")
        if not self.enabled:
            return TokenMeasurement(None, "disabled", model)

        hf = self._huggingface()
        if hf is not None:
            try:
                return TokenMeasurement(
                    len(hf.encode(text).ids),
                    "huggingface:tokenizer-json",
                    model,
                )
            except Exception:  # noqa: BLE001 - optional optimizer must fail open
                self._hf_tokenizer = None

        encoding, label = self._tiktoken_encoding(model)
        if encoding is not None:
            try:
                return TokenMeasurement(
                    len(encoding.encode(text, disallowed_special=())),
                    label,
                    model,
                )
            except Exception:  # noqa: BLE001 - optional optimizer must fail open
                encoding = None

        return TokenMeasurement(None, "character-fallback", model)

    def measure_request(self, request: Any, *, model: str = "") -> TokenMeasurement:
        request_model = ""
        if isinstance(request, dict):
            value = request.get("model")
            if isinstance(value, str):
                request_model = value
        active_model = str(request_model or model or "")
        try:
            serialized = _serialize(request)
        except Exception:  # noqa: BLE001 - measurement must never break a request
            return TokenMeasurement(None, "character-fallback", active_model)
        return self.measure_text(serialized, model=active_model)

    def status(self) -> dict[str, Any]:
        usable = self.usable_context_tokens
        return {
            "enabled": self.enabled,
            "tokenizer_json": str(self.tokenizer_json) if self.tokenizer_json else "",
            "tiktoken_encoding": self.encoding_name,
            "context_limit_tokens": self.context_limit_tokens,
            "output_reserve_tokens": self.output_reserve_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "usable_context_tokens": usable,
        }
