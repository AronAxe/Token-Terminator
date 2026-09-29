from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import threading
from pathlib import Path

import pytest
from dashboard_fixtures import RATES, populate

from rtk_hermes_plus import dashboard_data
from rtk_hermes_plus.cli import main
from rtk_hermes_plus.dashboard import DashboardReader, DashboardServer, asset
from rtk_hermes_plus.dashboard_data import (
    configuration,
    read_database,
    snapshot,
    source_for_home,
)
from rtk_hermes_plus.engine_install import install_context_engine


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_actual_ledger_and_measurement_tables_reconcile_per_profile(tmp_path):
    first, *_ = populate(tmp_path)
    second, *_ = populate(
        tmp_path / "profiles" / "brain",
        "brain",
        model="fixture/model-b",
        billing="subscription",
        multiplier=2,
    )
    data = snapshot([first, second], RATES)
    a, b = data["profiles"]
    assert a["input"]["saved"] == 2400
    assert b["input"]["saved"] == 4800
    assert data["totals"]["input_saved"] == 7200
    assert data["totals"]["input_prepared"] == 4800
    assert data["totals"]["input_observed"] == 4800
    assert data["totals"]["output_observed"] == 600
    assert data["totals"]["output_saved"] is None
    assert a["input"]["estimated_saved"] == 150  # kept separate
    assert a["input"]["exact_coverage_pct"] == 80
    assert a["value"]["saved_api_equivalent_usd"] == pytest.approx(0.0048)
    assert b["value"]["saved_api_equivalent_usd"] == pytest.approx(0.024)
    assert a["value"]["output_api_equivalent_usd"] == pytest.approx(0.0016)
    assert b["value"]["output_api_equivalent_usd"] == pytest.approx(0.0048)
    assert a["value"]["output_weighted_usd_per_million"] == 8
    assert a["value"]["actual_cost_usd"] == 0.02
    assert b["value"]["actual_cost_usd"] == 0
    assert b["billing"] == "subscription"
    assert b["value"]["cash_savings_usd"] is None
    assert a["value"]["net_savings_usd"] is None
    assert a["usage"]["recovery_reads"] == 2
    assert (
        a["output"]["saved"] is None
    )  # native tool-output reductions are NOT output savings
    assert "PRIVATE_CONVERSATION" not in json.dumps(data)
    assert str(tmp_path) not in json.dumps(data)
    assert (
        snapshot([first, second], RATES, profile="brain")["totals"]["input_saved"]
        == 4800
    )


def test_read_only_and_no_provider_or_tokenizer_work(tmp_path, monkeypatch):
    source, *_ = populate(tmp_path)
    before = {p: digest(p) for p in (source.vault, source.ledger)}
    from rtk_hermes_plus.config import Config
    from rtk_hermes_plus.token_budget import TokenBudgetAdapter

    def forbidden(*_a, **_kw):
        raise AssertionError("dashboard must not instantiate runtime/model/tokenizer")

    monkeypatch.setattr(Config, "from_env", forbidden)
    monkeypatch.setattr(TokenBudgetAdapter, "__init__", forbidden)
    assert snapshot([source], RATES)["totals"]["input_saved"] == 2400
    assert before == {p: digest(p) for p in before}
    with read_database(source.vault) as db, pytest.raises(sqlite3.OperationalError):
        db.execute("CREATE TABLE forbidden (x)")


def test_missing_and_unpriced_stay_unknown_and_do_not_create_db(tmp_path):
    source = source_for_home(tmp_path)
    data = snapshot([source], {})
    assert data["totals"]["input_saved"] is None
    assert data["totals"]["output_observed"] is None
    assert not tmp_path.joinpath("token-terminator").exists()
    source, *_ = populate(tmp_path)
    p = snapshot([source], {})["profiles"][0]
    assert p["value"]["saved_api_equivalent_usd"] is None
    assert p["value"]["output_api_equivalent_usd"] is None
    assert p["value"]["price_coverage_pct"] == 0


@pytest.mark.parametrize("change", ["missing", "corrupt", "busy"])
def test_one_unavailable_source_does_not_hide_others(tmp_path, change):
    good, *_ = populate(tmp_path / "good")
    bad, *_ = populate(tmp_path / "bad", "bad")
    held = None
    if change == "missing":
        bad.vault.unlink()
    elif change == "corrupt":
        bad.vault.write_bytes(b"not sqlite")
    else:
        held = sqlite3.connect(bad.vault)
        held.execute("PRAGMA journal_mode=DELETE")
        held.execute("BEGIN EXCLUSIVE")
    try:
        data = snapshot([good, bad], RATES)
        assert data["totals"]["input_saved"] == 2400
        assert data["profiles"][1]["issues"]
        assert data["profiles"][1]["input"]["saved"] is None
    finally:
        if held:
            held.close()


def test_invalid_measurements_excluded(tmp_path):
    source, *_ = populate(tmp_path)
    with sqlite3.connect(source.vault) as db:
        db.execute(
            "UPDATE request_token_metrics SET saved_tokens=999999 WHERE request_id='r0'"
        )
    p = snapshot([source], RATES)["profiles"][0]
    assert p["input"]["saved"] == 1800
    assert "invalid_measurement_rows_excluded" in p["issues"]


def test_output_model_change_never_priced_as_last_model(tmp_path):
    source, *_ = populate(tmp_path)
    with sqlite3.connect(source.ledger) as db:
        db.execute(
            "UPDATE sessions SET initial_model='other', contaminated=1, contamination_reason='model changed'"
        )
    p = snapshot([source], RATES)["profiles"][0]
    assert p["output"]["observed"] == 200
    assert p["value"]["output_api_equivalent_usd"] is None
    assert p["value"]["output_price_coverage_pct"] == 0


def test_unavailable_accounting_zero_is_not_observed_zero(tmp_path):
    source, *_ = populate(tmp_path)
    with sqlite3.connect(source.ledger) as db:
        db.execute(
            "UPDATE sessions SET input_tokens=0,output_tokens=0,contaminated=1,contamination_reason='accounting unavailable'"
        )
    p = snapshot([source], RATES)["profiles"][0]
    assert p["output"]["observed"] is None
    assert p["value"]["actual_cost_usd"] is None
    assert p["input"]["saved"] == 2400


def test_snapshot_deadline_reports_partial_sources(tmp_path, monkeypatch):
    source, *_ = populate(tmp_path)
    monkeypatch.setattr(dashboard_data, "SNAPSHOT_SECONDS", -1)
    p = snapshot([source], RATES)["profiles"][0]
    assert p["input"]["saved"] is None
    assert "measurement_budget_exceeded" in p["issues"]


def test_discovery_and_explicit_custom_store(tmp_path):
    populate(tmp_path)
    populate(tmp_path / "profiles" / "brain", "brain")
    sources, _ = configuration(tmp_path)
    assert [s.id for s in sources] == ["default", "brain"]
    config = tmp_path / "custom.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {"id": "agent", "home": str(tmp_path), "billing": "subscription"}
                ],
                "rates": RATES,
            }
        )
    )
    sources, rates = configuration(tmp_path, config)
    assert sources[0].id == "agent"
    assert sources[0].billing == "subscription"
    assert rates == RATES


@pytest.mark.parametrize(
    "obj",
    [
        {"sources": []},
        {"sources": [{"id": "../bad"}]},
        {"sources": [{"id": "x"}, {"id": "x"}]},
        {"sources": [{"id": "a"}, {"id": "b"}]},  # shared stores
        {"rates": {"m": {"input_usd_per_million": -1}}},
        {"rates": {"m": {"input_usd_per_million": True}}},
        {"rates": {"m": {"output_usd_per_million": float("nan")}}},
        {"rates": {"m": {"currency": "EUR"}}},
        {"endpoint": "https://not-allowed.example"},
    ],
)
def test_invalid_config_rejected(tmp_path, obj):
    config = tmp_path / "dashboard.json"
    config.write_text(json.dumps(obj))
    with pytest.raises(ValueError):
        configuration(tmp_path, config)


def test_hardlinked_databases_cannot_be_counted_twice(tmp_path):
    source, *_ = populate(tmp_path)
    other = tmp_path / "other.sqlite3"
    os.link(source.vault, other)
    config = tmp_path / "dashboard.json"
    config.write_text(
        json.dumps(
            {
                "sources": [
                    {"id": "a", "home": str(tmp_path)},
                    {"id": "b", "home": str(tmp_path / "b"), "vault": str(other)},
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="shared"):
        configuration(tmp_path, config)


@pytest.mark.parametrize("target", ["database", "config", "directory"])
def test_symlinks_refused(tmp_path, target):
    source, *_ = populate(tmp_path / "real")
    link = tmp_path / "link"
    try:
        link.symlink_to(
            source.vault if target == "database" else tmp_path / "real",
            target_is_directory=target != "database",
        )
    except OSError:
        pytest.skip("symlinks require permission")
    if target == "database":
        with pytest.raises(FileNotFoundError), read_database(link):
            pass
    elif target == "directory":
        with pytest.raises(ValueError):
            install_context_engine(link)
    else:
        with pytest.raises(ValueError):
            configuration(tmp_path, link)


@pytest.fixture
def server(tmp_path):
    populate(tmp_path)
    instance = DashboardServer(DashboardReader(tmp_path), 0)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=3)


def get(server, path="/api/v1/summary", headers=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    c.request(method, path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    result = (r.status, dict(r.getheaders()), body)
    c.close()
    return result


@pytest.mark.parametrize(
    "path",
    ["/", "/dashboard.css", "/dashboard.js", "/api/v1/summary", "/api/v1/health"],
)
def test_real_http_route_and_security_headers(server, path):
    status, headers, body = get(server, path)
    assert status == 200 and body
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Access-Control-Allow-Origin" not in headers
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert b"PRIVATE_CONVERSATION" not in body


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_rebinding_and_cross_origin_requests_denied(server, headers):
    assert get(server, headers=headers)[0] == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def test_http_is_read_only(server, method):
    assert get(server, method=method)[0] == 405


@pytest.mark.parametrize(
    "path,status",
    [
        ("/../artifacts.sqlite3", 404),
        ("/api/v1/summary?path=/etc/passwd", 400),
        ("/api/v1/summary?profile=default&profile=brain", 400),
        ("/api/v1/summary?profile=missing", 404),
        ("/api/v1/summary?profile=default", 200),
    ],
)
def test_profile_filter_and_closed_path_surface(server, path, status):
    assert get(server, path)[0] == status


def test_reader_uses_one_snapshot_for_filter(tmp_path, monkeypatch):
    populate(tmp_path)
    populate(tmp_path / "profiles" / "brain", "brain", multiplier=2)
    reader = DashboardReader(tmp_path)
    all_data = reader.read()

    def forbidden(*a, **kw):
        raise AssertionError("unexpected reread")

    monkeypatch.setattr(dashboard_data, "read_database", forbidden)
    one = reader.read("brain")
    assert one["generated_at"] == all_data["generated_at"]
    assert one["totals"]["input_saved"] == 4800


def test_installer_packages_both_desktop_and_backend_without_config_change(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("context:\n  engine: lcm\n")
    result = install_context_engine(tmp_path)
    assert install_context_engine(tmp_path) == result
    dest = Path(result["installed"])
    assert (dest / "desktop/plugin.js").read_bytes() == asset("plugin.js")
    assert (
        json.loads((dest / "dashboard/manifest.json").read_text())["api"]
        == "plugin_api.py"
    )
    assert (
        "dashboard_api import router" in (dest / "dashboard/plugin_api.py").read_text()
    )
    assert config.read_text() == "context:\n  engine: lcm\n"
    assert not list(dest.rglob("*.tt-new"))


@pytest.mark.parametrize(
    "file", ["desktop/plugin.js", "dashboard/plugin_api.py", "dashboard/manifest.json"]
)
def test_installer_refuses_unmanaged_ui_files_before_writing(tmp_path, file):
    dest = tmp_path / "plugins/token-terminator"
    path = dest / file
    path.parent.mkdir(parents=True)
    path.write_text("not owned")
    with pytest.raises(ValueError):
        install_context_engine(tmp_path)
    assert not (dest / "__init__.py").exists()
    assert path.read_text() == "not owned"


def test_cli_dashboard_does_not_construct_runtime(tmp_path, monkeypatch):
    from rtk_hermes_plus import cli, dashboard

    def forbidden():
        raise AssertionError("runtime created")

    calls = []
    monkeypatch.setattr(cli, "_runtime", forbidden)
    monkeypatch.setattr(
        dashboard, "serve", lambda home, conf, port: calls.append((home, conf, port))
    )
    assert main(["dashboard", "--hermes-home", str(tmp_path)]) == 0
    assert calls == [(tmp_path, None, 7474)]
    assert main(["dashboard", "--port", "0"]) == 2


def test_backend_scope_never_aggregates_other_homes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from rtk_hermes_plus import dashboard_api

    populate(tmp_path)
    populate(tmp_path / "profiles" / "brain", "brain", multiplier=2)
    monkeypatch.setattr(dashboard_api, "_hermes_home", lambda: tmp_path)
    dashboard_api._cache.clear()
    assert dashboard_api._current_snapshot()["totals"]["input_saved"] == 2400
    monkeypatch.setattr(
        dashboard_api, "_hermes_home", lambda: tmp_path / "profiles" / "brain"
    )
    data = dashboard_api._current_snapshot()
    assert data["scope"]["profile"] == "brain"
    assert data["totals"]["input_saved"] == 4800
    assert len(data["profiles"]) == 1


@pytest.mark.parametrize("traversal", [False, True])
def test_backend_cannot_follow_config_outside_authorized_home(
    tmp_path, monkeypatch, traversal
):
    pytest.importorskip("fastapi")
    from rtk_hermes_plus import dashboard_api

    home = tmp_path / "home"
    home.mkdir()
    populate(tmp_path / "other")
    (home / "token-terminator").mkdir()
    (home / "token-terminator/dashboard.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "default",
                        "home": str(
                            home / ".." / "other" if traversal else tmp_path / "other"
                        ),
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(dashboard_api, "_hermes_home", lambda: home)
    dashboard_api._cache.clear()
    with pytest.raises(ValueError):
        dashboard_api._current_snapshot()


@pytest.mark.parametrize("profiles", [("brain",), ("default", "brain")])
def test_ambiguous_legacy_profile_accounting_never_credited_to_default(
    tmp_path, profiles
):
    source, *_ = populate(tmp_path)
    with sqlite3.connect(source.ledger) as db:
        db.execute("UPDATE sessions SET profile=?", (profiles[0],))
        if len(profiles) > 1:
            db.execute(
                "INSERT INTO sessions(session_id,mode,plugin_version,experiment,profile,tagged_at,last_seen_at) VALUES('other','balanced','0.11.0','test','brain',0,0)"
            )
    p = snapshot([source], RATES)["profiles"][0]
    assert p["input"]["saved"] is None
    assert p["output"]["observed"] is None
    assert p["attribution"] == "ambiguous_legacy_store"
    assert "profile_attribution_ambiguous" in p["issues"]


def test_task_local_hermes_home_precedes_launch_environment(tmp_path, monkeypatch):
    import sys
    from types import ModuleType

    from rtk_hermes_plus.config import Config, _hermes_home

    module = ModuleType("hermes_constants")
    module.get_hermes_home = lambda: tmp_path / "profiles/brain"
    monkeypatch.setitem(sys.modules, "hermes_constants", module)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("TOKEN_TERMINATOR_DB_PATH", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_LEDGER_PATH", raising=False)
    assert _hermes_home() == tmp_path / "profiles/brain"
    config = Config.from_env()
    assert (
        config.db_path == tmp_path / "profiles/brain/token-terminator/artifacts.sqlite3"
    )
    assert (
        config.ledger_path
        == tmp_path / "profiles/brain/token-terminator/experiments.sqlite3"
    )


def test_standalone_home_environment_still_supported(tmp_path, monkeypatch):
    import sys

    from rtk_hermes_plus.config import _hermes_home

    monkeypatch.setitem(sys.modules, "hermes_constants", None)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert _hermes_home() == tmp_path


def test_dashboard_refresh_preserves_main_retry_and_scorer_cache(tmp_path):
    from test_history_engine import low_scores, request, setup
    from test_jev_roles import invoke

    from rtk_hermes_plus.dashboard_data import Source

    runtime, engine = setup(tmp_path)
    req = request(engine)
    engine.select_context(req["messages"])
    calls = []

    def transport(payload):
        calls.append(True)
        return low_scores(payload)

    engine.transport = transport
    first = invoke(runtime, req, True)
    assert first and calls
    count = len(calls)
    source = Source("test", "test", runtime.config.db_path, runtime.config.ledger_path)
    data = snapshot([source], {})
    assert data["totals"]["input_saved"] > 0
    retry = invoke(runtime, req, True)
    assert retry["request"] == first["request"]
    assert len(calls) == count
