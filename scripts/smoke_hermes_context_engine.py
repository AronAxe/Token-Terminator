"""Exercise the REAL Hermes loader, engine factory, hook and middleware offline.

Run with a pinned Hermes checkout on PYTHONPATH. Uses an isolated HERMES_HOME,
synthetic history and fixture JEV. No provider calls and no live-profile writes.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tt-engine-smoke-") as temp:
        home = Path(temp)
        os.environ.update(
            HERMES_HOME=temp,
            TOKEN_TERMINATOR_DB_PATH=str(home / "vault.sqlite3"),
            TOKEN_TERMINATOR_LEDGER_PATH=str(home / "ledger.sqlite3"),
            TOKEN_TERMINATOR_JEV="true",
            TOKEN_TERMINATOR_JEV_API_KEY="fixture",
            TOKEN_TERMINATOR_CONTEXT_IR="true",
        )
        cfg = {
            "plugins": {"enabled": ["token-terminator"]},
            "context": {"engine": "token-terminator"},
        }
        (home / "config.yaml").write_text(
            "plugins:\n  enabled: [token-terminator]\ncontext:\n  engine: token-terminator\n",
            encoding="utf-8",
        )
        # All Hermes imports follow isolation: some host paths resolve at import.
        from rtk_hermes_plus.engine_install import install_context_engine
        from rtk_hermes_plus.plugin import _schema
        from rtk_hermes_plus.token_budget import TokenBudgetAdapter

        install_context_engine(home)
        from agent.agent_init import (
            _build_context_engine,
            _inject_context_engine_tools,
            _select_context_engine,
        )
        from agent.context_engine import ContextEngine
        from agent.conversation_loop import _apply_context_engine_selection
        from hermes_cli.plugins import PluginManager
        from hermes_cli.plugins_cmd import _discover_context_engines
        from plugins.context_engine import discover_context_engines, load_context_engine

        choices = discover_context_engines()
        assert any(n == "token-terminator" and available for n, _, available in choices)
        menu_options = _discover_context_engines()
        assert any(n == "token-terminator" for n, _ in menu_options)
        assert isinstance(load_context_engine("token-terminator"), ContextEngine)
        assert _select_context_engine({"context": {"engine": "compressor"}}) is None

        manager = PluginManager()
        manager.discover_and_load()
        assert manager.has_middleware("llm_request")
        assert manager._context_engine is None  # generic plugin must NOT auto-select

        # Exercise the real host factory. Any upstream built-in instantiation is
        # a hard test failure, rather than merely checking our engine's name.
        agent = SimpleNamespace(
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            provider="openai",
            api_mode="chat_completions",
            api_key="",
            quiet_mode=True,
            session_id="smoke",
        )
        cs = SimpleNamespace(
            model_thresholds={},
            enabled=True,
            in_place=True,
            checkpoint_required=False,
            micro_compact=False,
            micro_compact_every_n_turns=10,
            micro_compact_defrag_tokens=0,
            codex_app_server_auto=False,
            codex_responses_native=False,
            codex_responses_compact_threshold=0.75,
            max_attempts=3,
            idle_compact_after_seconds=0,
        )
        with (
            patch(
                "agent.agent_init.ContextCompressor",
                side_effect=AssertionError("built-in compressor ran"),
            ),
            patch("agent.model_metadata.get_model_context_length", return_value=128000),
        ):
            _build_context_engine(agent, cfg, cs, [], 128000, None)
        engine = agent.context_compressor
        assert isinstance(engine, ContextEngine) and engine.name == "token-terminator"
        assert not engine.should_compress(10**9)
        agent.tools = [{"type": "function", "function": _schema()}]
        agent.valid_tool_names = {"token_terminator"}
        agent.enabled_toolsets = None
        agent.platform = "cli"
        _inject_context_engine_tools(agent)
        assert "token_terminator_history" in agent._context_engine_tool_names
        batches = []

        def fixture(payload):
            batches.append(payload)
            return {
                "answers": {
                    q: {"type": "noul", "noul": 0.01} for q in payload["questions"]
                }
            }

        engine.transport = fixture
        text = (
            "The meadow was quiet while the clouds drifted over the distant hills. "
            * 40
        )
        history = [{"role": "assistant", "content": text} for _ in range(25)]
        history += [
            {"role": "user", "content": "Explain industrial robot calibration."}
        ]
        request = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Keep current wording and exact values."}
            ]
            + history,
            "tools": agent.tools,
        }
        before = copy.deepcopy(request)
        selected = _apply_context_engine_selection(
            agent,
            request["messages"],
            history,
            history[-1],
            logger=logging.getLogger(__name__),
        )
        assert (
            selected == request["messages"]
        )  # deferred, not a partial-request token gate
        results = manager.invoke_middleware(
            "llm_request",
            request=request,
            session_id="smoke",
            api_request_id="smoke-engine",
        )
        assert len(results) == 1 and results[0]["request"] != request
        final = results[0]["request"]
        assert request == before
        assert final["messages"][-1] == before["messages"][-1]
        budget = TokenBudgetAdapter()
        assert (
            budget.measure_request(final).tokens < budget.measure_request(before).tokens
        )
        receipt = final["messages"][1]["content"]
        assert receipt.startswith("[TT history ")
        artifact = receipt.split()[2].rstrip(";")
        recovered = json.loads(
            engine.handle_tool_call(
                "token_terminator_history",
                {
                    "action": "get",
                    "artifact_id": artifact,
                    "limit": 20000,
                },
            )
        )
        assert json.loads(recovered["content"]) == before["messages"][1]
        assert 1 <= len(batches) <= 2
        engine.on_turn_complete(history)
        clone = engine.clone_for_agent()
        assert clone is not engine and clone.session_id == ""
        assert clone._lock is not engine._lock
        print(
            json.dumps(
                {
                    "engine_discovered": True,
                    "cli_web_shared_options": menu_options,
                    "real_context_engine_abc": True,
                    "real_host_factory_selected_tt": True,
                    "builtin_compressor_not_constructed": True,
                    "general_plugin_did_not_autoselect": True,
                    "real_host_selection_hook": True,
                    "real_engine_tool_injection": True,
                    "real_middleware_dispatch": True,
                    "full_history_unchanged": True,
                    "exact_recovery": True,
                    "final_tokens": budget.measure_request(final).tokens,
                    "raw_tokens": budget.measure_request(before).tokens,
                    "jev_fixture_calls": len(batches),
                    "paid_calls": 0,
                    "clone_isolated": True,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
