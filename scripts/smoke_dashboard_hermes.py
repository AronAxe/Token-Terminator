"""Real pinned-Hermes discovery/mount/profile dependency; isolated API test app.

No full Electron/gateway process or authentication bypass is installed. The
FastAPI harness substitutes only the app shell and enabled-plugin inventory.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def main():
    with tempfile.TemporaryDirectory(prefix="tt-dashboard-hermes-") as temp:
        home = Path(temp)
        os.environ["HERMES_HOME"] = str(home)
        os.environ.pop("HERMES_PROFILE_NAME", None)
        os.environ.pop("HERMES_PROFILE", None)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
        from dashboard_fixtures import RATES, populate
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from rtk_hermes_plus.engine_install import install_context_engine

        populate(home)
        populate(home / "profiles/brain", "brain", multiplier=2)
        for h in (home, home / "profiles/brain"):
            h.joinpath("config.yaml").write_text(
                "plugins:\n  enabled: [token-terminator]\n"
            )
            h.joinpath("token-terminator/dashboard.json").write_text(
                json.dumps({"rates": RATES})
            )
        install_context_engine(home)
        # Current Hermes modules, not replicas of their discovery/mount code.
        import hermes_cli.web_server_dashboard as native
        from hermes_constants import get_hermes_home

        with patch.object(
            native,
            "_dashboard_plugin_search_dirs",
            return_value=[(home / "plugins", "user")],
        ):
            entries = native._discover_dashboard_plugins()
        plugin = next(p for p in entries if p["name"] == "token-terminator")
        assert plugin["has_api"] and plugin["tab"]["hidden"]
        assert native._plugin_api_mount_skip_reason(plugin, set(), set())
        assert (
            native._plugin_api_mount_skip_reason(plugin, {"token-terminator"}, set())
            is None
        )
        assert native._plugin_api_mount_skip_reason(
            plugin, {"token-terminator"}, {"token-terminator"}
        )
        shell = ModuleType("hermes_cli.web_server")
        shell.app = FastAPI()
        shell._get_dashboard_plugins = lambda: entries
        with (
            patch.dict(sys.modules, {"hermes_cli.web_server": shell}),
            patch(
                "hermes_cli.plugins_cmd._get_enabled_set",
                return_value={"token-terminator"},
            ),
            patch("hermes_cli.plugins_cmd._get_disabled_set", return_value=set()),
        ):
            native._mount_plugin_api_routes()
        with TestClient(shell.app) as client:
            first = client.get("/api/plugins/token-terminator/summary?profile=default")
            assert first.status_code == 200, first.text
            second = client.get("/api/plugins/token-terminator/summary?profile=brain")
            assert second.status_code == 200, second.text
            assert first.json()["totals"]["input_saved"] == 2400
            assert second.json()["totals"]["input_saved"] == 4800
            assert second.json()["scope"]["profile"] == "brain"
            assert len(second.json()["profiles"]) == 1
            assert (
                client.get(
                    "/api/plugins/token-terminator/summary?profile=../default"
                ).status_code
                == 400
            )
            assert (
                client.post("/api/plugins/token-terminator/summary").status_code == 405
            )
            assert (
                client.get(
                    "/api/plugins/token-terminator/summary?profile=default"
                ).json()
                == first.json()
            )
            assert (
                str(home) not in first.text and "PRIVATE_CONVERSATION" not in first.text
            )
        assert get_hermes_home() == home
        print(
            json.dumps(
                {
                    "actual_hermes_discovery": True,
                    "actual_hermes_api_mount": True,
                    "actual_profile_dependency": True,
                    "enable_disable_gate": True,
                    "per_profile_isolation": True,
                    "context_restored": True,
                    "content_free": True,
                    "full_gateway_auth_e2e": False,
                    "model_calls": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
