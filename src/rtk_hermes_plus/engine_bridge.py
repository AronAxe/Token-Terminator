"""Turn-scoped, execution-context-local bridge between supported Hermes hooks.

select_context sees history but not the provider envelope. Selection is committed
only by llm_request middleware, after Hermes has supplied that complete envelope.
No process-global session lookup, payload marker, or core monkey-patch is used.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Binding:
    engine: Any
    session_id: str
    generation: int


_pending: ContextVar[Binding | None] = ContextVar(
    "tt_context_engine_request", default=None
)


def bind(engine: Any) -> None:
    _pending.set(Binding(engine, engine.session_id, engine.generation))


def clear(engine: Any) -> None:
    binding = _pending.get()
    if binding is not None and binding.engine is engine:
        _pending.set(None)


def current() -> Binding | None:
    # Provider retries may reuse the prepared request without rerunning selection.
    # Keep engine ownership until a lifecycle hook clears/replaces the binding.
    return _pending.get()


def take() -> Binding | None:
    binding = _pending.get()
    _pending.set(None)
    return binding
