"""Explicitly synthetic accounting records for tests, never shipped as live data."""

from __future__ import annotations

import sqlite3

from rtk_hermes_plus.dashboard_data import source_for_home
from rtk_hermes_plus.ledger import ExperimentLedger
from rtk_hermes_plus.storage import TokenTerminatorStore
from rtk_hermes_plus.token_accounting import RequestTokenAccounting
from rtk_hermes_plus.token_budget import TokenMeasurement

RATES = {
    "fixture/model-a": {
        "input_usd_per_million": 2,
        "output_usd_per_million": 8,
        "as_of": "synthetic fixture, not a market price",
    },
    "fixture/model-b": {
        "input_usd_per_million": 5,
        "output_usd_per_million": 12,
        "as_of": "synthetic fixture, not a market price",
    },
}


def populate(
    home, name="default", *, model="fixture/model-a", billing="api", multiplier=1
):
    source = source_for_home(home, name)
    store = TokenTerminatorStore(source.vault)
    evidence_marker = "PRIVATE_CONVERSATION_SENTINEL_7f937c8e"
    store.put_artifact(evidence_marker)
    accounting = RequestTokenAccounting(store)
    for i in range(4):
        raw = TokenMeasurement(1000 * multiplier, "fixture-exact", model)
        final = TokenMeasurement(400 * multiplier, "fixture-exact", model)
        # Repeated callback/outer-stage updates must not add a second saving.
        for _ in range(2):
            accounting.record(session_id="s", request_id=f"r{i}", raw=raw, final=final)
        store.record_request_metric(
            session_id="s",
            request_id=f"r{i}",
            raw_chars=4000,
            compiled_chars=2000,
            final_chars=1600,
            end_to_end_measured=True,
        )
    store.record_request_metric(
        session_id="s",
        request_id="unmeasured",
        raw_chars=1000,
        compiled_chars=500,
        final_chars=400,
        end_to_end_measured=True,
    )
    values = {
        "model": model,
        "billing_provider": "fixture",
        "billing_mode": billing,
        "cost_status": "included" if billing == "subscription" else "actual",
        "input_tokens": 0,
        "output_tokens": 0,
        "actual_cost_usd": 0,
    }
    ledger = ExperimentLedger(
        source.ledger,
        home / "state.db",
        plugin_version="0.11.0",
        profile=name,
        session_reader=lambda _session: values,
    )
    ledger.ensure_session("s", "balanced")
    values.update(
        input_tokens=1600 * multiplier,
        output_tokens=200 * multiplier,
        actual_cost_usd=0 if billing == "subscription" else 0.02,
        api_call_count=4,
    )
    ledger.ensure_session("s", "balanced")
    with sqlite3.connect(source.ledger) as db:
        db.execute(
            "UPDATE sessions SET recovery_reads=2, native_raw_tokens=1000000, native_output_tokens=100 WHERE session_id='s'"
        )
    return source, store, accounting, ledger
