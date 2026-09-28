"""Optional Hermes adapter. Normal TT imports never depend on Hermes being installed."""

from agent.context_engine import ContextEngine

from .history_engine import HistoryContextEngine


class TokenTerminatorContextEngine(HistoryContextEngine, ContextEngine):
    """Selectable through Hermes' supported user ContextEngine directory mechanism."""

    @property
    def name(self) -> str:
        return "token-terminator"
