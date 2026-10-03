"""Offline regression against the installed Hermes live-config function.

Run in a Hermes environment: python scripts/smoke_hermes_live_config.py
No model calls or live-profile writes. All vault work uses temporary directories.
"""

import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent import model_metadata
from agent.context_compressor import ContextCompressor
from tui_gateway import session_compression

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.hermes_engine import TokenTerminatorContextEngine as TT


class LiveAdapterTests(unittest.TestCase):
    def setUp(self):
        logger_patch = patch.object(
            session_compression,
            "logger",
            logging.getLogger("tt-live-adapter-test"),
            create=True,
        )
        logger_patch.start()
        self.addCleanup(logger_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.no_summarizer = patch.object(
            ContextCompressor,
            "__init__",
            side_effect=AssertionError("must not instantiate built-in compressor"),
        )
        self.no_summarizer.start()
        self.addCleanup(self.no_summarizer.stop)
        self.engine = TT(
            config=Config(
                mode="balanced",
                db_path=Path(self.temp.name) / "vault.db",
                ledger_enabled=False,
            )
        )
        self.engine.update_model(
            "fixture-chat", 900000, provider="fixture", max_tokens=8192
        )
        self.agent = SimpleNamespace(
            model="fixture-chat",
            provider="fixture",
            base_url="",
            api_mode="chat_completions",
            context_compressor=self.engine,
        )

    def apply(self, compression, window=900000):
        model = {"default": "fixture-chat", "provider": "fixture"}
        if window is not None:
            model["context_length"] = window
        cfg = {"model": model, "compression": compression}
        # Isolate adapter semantics without network discovery. The actual host
        # live-config function still sets/invalidates both cached window copies.
        with patch(
            "agent.agent_init.config_context_length_for_runtime", return_value=window
        ):
            session_compression._apply_live_compression_config(self.agent, cfg)

    def test_cap_normalization(self):
        for value, expected in [
            (None, None),
            (0, None),
            (-1, None),
            ("bad", None),
            ("200000", 200000),
            (1, 1),
            (float("inf"), None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(TT._coerce_threshold_tokens_cap(value), expected)

    def test_exact_reported_live_api_does_not_raise(self):
        self.apply({"threshold": 0.7, "threshold_tokens": 200000})
        self.assertEqual(self.engine.threshold_tokens, 200000)
        self.assertEqual(self.agent._config_context_length, 900000)
        self.assertEqual(self.engine._config_context_length, 900000)

    def test_cache_invalidated_after_cap_edit(self):
        self.apply({"threshold": 0.7, "threshold_tokens": 200000})
        self.assertEqual(self.engine.threshold_tokens, 200000)
        self.apply({"threshold": 0.7, "threshold_tokens": 120000})
        self.assertEqual(self.engine.threshold_tokens, 120000)

    def test_null_cap_restores_ratio_and_output_reserve(self):
        self.apply({"threshold": 0.7, "threshold_tokens": 200000})
        self.apply({"threshold": 0.7, "threshold_tokens": None})
        self.assertEqual(
            self.engine.threshold_tokens,
            ContextCompressor._compute_threshold_tokens(900000, 0.7, 8192),
        )

    def test_missing_cap_restores_real_host_default(self):
        self.apply({"threshold": 0.7, "threshold_tokens": 123456})
        self.apply({"threshold": 0.7})
        expected = TT._coerce_threshold_tokens_cap(
            session_compression._default_threshold_tokens_cap()
        )
        self.assertEqual(self.engine.threshold_tokens_cap, expected)

    def test_window_edit_reaches_both_caches(self):
        self.apply({"threshold": 0.7, "threshold_tokens": None}, 1050000)
        self.assertEqual(self.engine.context_length, 1050000)
        self.assertEqual(self.agent._config_context_length, 1050000)
        self.assertEqual(
            self.engine.threshold_tokens,
            ContextCompressor._compute_threshold_tokens(1050000, 0.7, 8192),
        )

    def test_removed_pin_resolves_current_route(self):
        self.apply({"threshold": 0.7, "threshold_tokens": None})
        with patch.object(
            model_metadata, "get_model_context_length", return_value=1050000
        ) as probe:
            self.apply({"threshold": 0.7, "threshold_tokens": None}, None)
            self.assertEqual(self.engine.context_length, 1050000)
            self.assertIsNone(self.agent._config_context_length)
            self.assertIsNone(self.engine._config_context_length)
            self.assertEqual(probe.call_args.args[0], "fixture-chat")
            self.assertEqual(probe.call_args.kwargs["provider"], "fixture")

    def test_small_window_uses_host_floor(self):
        self.apply({"threshold": 0.5, "threshold_tokens": None}, 64000)
        self.assertEqual(self.engine.threshold_percent, 0.75)
        self.assertLess(self.engine.threshold_tokens, 64000 - 8192)

    def test_clone_isolated_and_preserves_reserve(self):
        self.apply({"threshold": 0.7, "threshold_tokens": 150000})
        clone = self.engine.clone_for_agent()
        self.assertIsNot(clone._lock, self.engine._lock)
        self.assertIsNot(
            clone._model_metadata_kwargs, self.engine._model_metadata_kwargs
        )
        self.assertEqual(clone.max_tokens, 8192)
        self.assertEqual(clone.threshold_tokens, 150000)
        clone.threshold_tokens_cap = 120000
        clone._threshold_tokens = None
        self.assertEqual(self.engine.threshold_tokens, 150000)
        self.assertEqual(clone.threshold_tokens, 120000)

    def test_no_destructive_compression(self):
        self.engine.on_session_start("repair-fixture")
        messages = [
            {"role": "user", "content": "Keep exactly 12.30 and this quotation."}
        ]
        self.assertIs(self.engine.compress(messages), messages)
        self.assertFalse(self.engine.should_compress(900000))
        self.assertFalse(self.engine.should_compress_preflight(messages))

    def test_output_budget_none_retains_reservation(self):
        self.engine.update_model(
            "other-fixture", 64000, provider="other", max_tokens=None
        )
        self.assertEqual(self.engine.max_tokens, 8192)
        self.assertEqual(self.engine._model_metadata_kwargs, {"provider": "other"})
        self.engine.update_model(
            "other-fixture", 64000, provider="other", max_tokens=0
        )
        self.assertIsNone(self.engine.max_tokens)


if __name__ == "__main__":
    unittest.main(verbosity=2)
