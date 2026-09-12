from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from rtk_hermes_plus import AsyncRuntime, Runtime
from rtk_hermes_plus.config import Config, load_config
from rtk_hermes_plus.ledger import (
    ExperimentLedger,
    HermesAccounting,
    _bootstrap_ci,
    _summary,
)
from rtk_hermes_plus.metrics import Metrics
from rtk_hermes_plus.rewrite import Rewriter
from rtk_hermes_plus.storage import TokenTerminatorStore


def _config(tmp_path: Path, **kwargs) -> Config:
    values = {
        "mode": "balanced",
        "ledger_enabled": False,
        "ledger_path": tmp_path / "ledger.db",
        "state_db_path": tmp_path / "state.db",
        "db_path": tmp_path / "vault.db",
        "min_artifact_chars": 10,
        "native_min_chars": 1000,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


def test_context_defaults_are_identical_and_invalid_direct_pair_is_rejected(
    tmp_path, monkeypatch
):
    assert Config().context_inline_recent_turns == 5
    for name in (
        "TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS",
        "TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert load_config().context_inline_recent_turns == 5
    with pytest.raises(ValueError):
        Config(context_inline_recent_turns=5, context_collapse_after_turns=2)
    monkeypatch.setenv("TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS", "5")
    monkeypatch.setenv("TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS", "2")
    loaded = load_config()
    assert loaded.context_collapse_after_turns == 5


def test_unicode_artifact_search_casefolds_content(tmp_path):
    store = TokenTerminatorStore(tmp_path / "unicode.db")
    store.put_artifact("Straße FEHLER Übergröße", tool_name="Prüfung")
    assert len(store.search_artifacts("übergröße")) == 1
    assert len(store.search_artifacts("ÜBERGRÖSSE")) == 1
    assert len(store.search_artifacts("prüfung")) == 1


def test_rewrite_cache_is_scoped_by_cwd(tmp_path, monkeypatch):
    config = _config(tmp_path, rtk_path=tmp_path / "rtk")
    rewriter = Rewriter(config, Metrics())
    calls: list[str] = []

    def fake_run(_argv, *, cwd, **_kwargs):
        calls.append(cwd)
        return SimpleNamespace(stdout=f"rewritten:{cwd}", returncode=0)

    monkeypatch.setattr("rtk_hermes_plus.rewrite.subprocess.run", fake_run)
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    first = rewriter.rewrite("git status", cwd=a)
    again = rewriter.rewrite("git status", cwd=a)
    other = rewriter.rewrite("git status", cwd=b)
    assert first.command == again.command
    assert first.command != other.command
    assert len(calls) == 2


def test_async_runtime_gets_temporal_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS", "1")
    runtime = Runtime(_config(tmp_path))
    async_runtime = AsyncRuntime(runtime)
    args = {"command": "tree src", "cwd": str(tmp_path)}
    result = "\n".join(f"src/file_{i}.py" for i in range(300))

    first = asyncio.run(
        async_runtime.transform_tool_result(
            tool_name="terminal",
            args=args,
            result=result,
            session_id="s",
            tool_call_id="c1",
        )
    )
    second = asyncio.run(
        async_runtime.transform_tool_result(
            tool_name="terminal",
            args=args,
            result=result,
            session_id="s",
            tool_call_id="c2",
        )
    )
    assert first is None
    assert second is not None and "no output changes" in second


def test_vault_prunes_old_unprotected_artifacts_and_keeps_temporal_baseline(tmp_path):
    store = TokenTerminatorStore(
        tmp_path / "retention.db",
        max_artifact_chars=1000,
        max_vault_bytes=500,
        high_water_pct=80,
        low_water_pct=50,
    )
    a = store.put_artifact("a" * 180, tool_name="terminal")
    b = store.put_artifact("b" * 180, tool_name="process")
    with store.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO terminal_snapshots(state_key, artifact_id, command, cwd, backend, session_scope, updated_at) "
            "VALUES('state', ?, 'cmd', '.', 'local', '', 'now')",
            (a.artifact_id,),
        )
    c = store.put_artifact("c" * 180, tool_name="process")
    assert store.get_artifact(a.artifact_id).content.startswith("a")
    assert store.get_artifact(c.artifact_id).content.startswith("c")
    with pytest.raises(KeyError):
        store.get_artifact(b.artifact_id)
    usage = store.vault_usage()
    assert usage["vault_bytes"] == 360
    assert usage["vault_pruned_artifacts"] == 1


def test_terminal_snapshot_schema_exists_before_temporal_runtime(tmp_path):
    store = TokenTerminatorStore(tmp_path / "schema.db")
    with store.connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='terminal_snapshots'"
        ).fetchone()
    assert row is not None


def test_store_does_not_repermission_existing_parent(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX permission semantics")
    parent = tmp_path / "existing"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    TokenTerminatorStore(parent / "vault.db")
    assert os.stat(parent).st_mode & 0o777 == 0o755


def test_hermes_accounting_uses_path_uri(tmp_path, monkeypatch):
    db = tmp_path / "a ?# b.db"
    db.touch()
    captured: list[str] = []

    class DummyConnection:
        row_factory = None

        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("stop")

        def close(self):
            pass

    def fake_connect(database, **_kwargs):
        captured.append(database)
        return DummyConnection()

    monkeypatch.setattr("rtk_hermes_plus.ledger.sqlite3.connect", fake_connect)
    HermesAccounting(db).read("session")
    assert captured and captured[0].startswith("file://")
    assert "%20" in captured[0] and "%3F" in captured[0] and "%23" in captured[0]


def test_pinned_rtk_path_wins_over_path_lookup(tmp_path, monkeypatch):
    pinned = tmp_path / "known-rtk"
    monkeypatch.setattr(
        "rtk_hermes_plus.rewrite.shutil.which", lambda _name: "/evil/rtk"
    )
    assert Rewriter(_config(tmp_path, rtk_path=pinned), Metrics()).rtk_path == str(
        pinned
    )


def test_measurement_summary_uses_real_native_tokens_when_present():
    row = {
        "total_tokens": 100,
        "estimated_cost_usd": None,
        "actual_cost_usd": None,
        "api_equivalent_cost_usd": None,
        "completed": 1,
        "failed": 0,
        "interrupted": 0,
        "native_raw_chars": 400,
        "native_output_chars": 100,
        "native_raw_tokens": 90,
        "native_output_tokens": 20,
        "native_token_measurements": 1,
        "native_compressions": 1,
        "rewrite_count": 0,
        "recovery_reads": 0,
    }
    summary = _summary([row])
    assert summary["native_estimated_tokens_saved"] == 70
    assert summary["native_token_savings_source"] == "exact-tokenizer"
    assert summary["token_coverage"] == 1


def test_bootstrap_interval_is_deterministic_and_compare_rejects_same_mode(tmp_path):
    assert _bootstrap_ci([1, 2, 3, 4]) == _bootstrap_ci([1, 2, 3, 4])
    ledger = ExperimentLedger(
        tmp_path / "ledger.db",
        tmp_path / "missing-state.db",
        plugin_version="test",
        enabled=True,
    )
    result = ledger.compare(("balanced", "balanced"))
    assert result["error"] == "comparison modes must differ"
