"""Regression against the real optional Hermes live-config implementation."""

import copy
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from tui_gateway.session_compression import _apply_live_compression_config
except ImportError as exc:
    raise unittest.SkipTest("requires a current Hermes checkout") from exc

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.hermes_engine import TokenTerminatorContextEngine as Engine
from rtk_hermes_plus.history_engine import HistoryContextEngine


class LiveConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = Engine(
            config=Config(
                db_path=Path(self.tmp.name) / "vault.db", ledger_enabled=False
            )
        )
        self.engine.update_model("fixture-main", 272000, provider="fixture")
        self.agent = types.SimpleNamespace(
            context_compressor=self.engine, model="fixture-main", provider="fixture"
        )

    def apply(self, cfg, pin=None):
        with patch(
            "agent.agent_init.config_context_length_for_runtime", return_value=pin
        ):
            _apply_live_compression_config(self.agent, cfg)

    def test_cap_values(self):
        cases = [
            (None, None), (0, None), (-1, None), ("bad", None),
            ("", None), (180000, 180000), ("180000", 180000), (float("inf"), None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    self.engine._coerce_threshold_tokens_cap(value), expected
                )

    def test_actual_live_hook_updates_pin_and_cap(self):
        self.apply(
            {"compression": {"threshold": 0.7, "threshold_tokens": 180000}},
            pin=1000000,
        )
        self.assertEqual(self.engine.context_length, 1000000)
        self.assertEqual(self.engine.threshold_tokens, 180000)
        self.assertEqual(self.engine._config_context_length, 1000000)

    def test_removed_pin_reresolves_current_route(self):
        self.apply(
            {"compression": {"threshold": 0.7, "threshold_tokens": 180000}},
            pin=1000000,
        )
        with patch(
            "agent.model_metadata.get_model_context_length", return_value=600000
        ) as resolver:
            self.apply(
                {"compression": {"threshold": 0.7, "threshold_tokens": None}}
            )
            self.assertIsNone(self.engine._config_context_length)
            self.assertEqual(self.engine.context_length, 600000)
            self.assertEqual(self.engine.threshold_tokens, 420000)
            self.assertEqual(resolver.call_args.args[0], "fixture-main")
            self.assertEqual(resolver.call_args.kwargs["provider"], "fixture")

    def test_live_small_window_threshold_floor(self):
        self.apply({"compression": {"threshold": 0.1, "threshold_tokens": None}})
        self.assertEqual(self.engine.threshold_tokens, 204000)

    def test_model_switch_preserves_cap_and_changes_route(self):
        self.engine.threshold_tokens_cap = 180000
        self.engine._threshold_tokens = None
        self.engine.update_model("fixture-small", 32000, provider="other")
        self.assertEqual(self.engine.threshold_tokens, 24000)
        self.assertEqual(self.engine._model_metadata_kwargs, {"provider": "other"})

    def test_host_request_window_replaces_stale_272k(self):
        self.engine.last_prompt_tokens = 270000
        messages = [{"role": "user", "content": "Keep this exact."}]
        original = copy.deepcopy(messages)
        with patch.object(
            HistoryContextEngine, "select_context", return_value=None
        ) as select:
            self.engine.select_context(messages, budget_tokens=1000000)
            select.assert_called_once()
        self.assertEqual(self.engine.context_length, 1000000)
        self.assertEqual(self.engine.last_prompt_tokens, 270000)
        self.assertEqual(messages, original)

    def test_unknown_window_does_not_erase_known_window(self):
        with patch.object(HistoryContextEngine, "select_context", return_value=None):
            self.engine.select_context([], budget_tokens=0)
        self.assertEqual(self.engine.context_length, 272000)

    def test_clones_do_not_share_mutable_budget_state(self):
        self.engine.threshold_tokens_cap = 100000
        self.engine.model_thresholds = {"fixture": 0.6}
        other = self.engine.clone_for_agent()
        other.threshold_tokens_cap = 50000
        other.model_thresholds["fixture"] = 0.9
        other.context_length = 1000000
        self.assertEqual(self.engine.threshold_tokens_cap, 100000)
        self.assertEqual(self.engine.model_thresholds, {"fixture": 0.6})
        self.assertEqual(self.engine.context_length, 272000)

    def test_no_summarizer_or_destructive_compression(self):
        self.assertFalse(self.engine.should_compress(9999999))
        self.assertFalse(self.engine.should_compress_preflight([]))
        self.assertIsNone(self.engine._catalog)
