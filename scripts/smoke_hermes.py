"""Installed-wheel smoke test against a real Hermes PluginManager.

Run from an isolated environment where Hermes Agent and the built Token
Terminator wheel are installed. It creates a disposable HERMES_HOME and makes
no network calls or live-profile changes.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from importlib.metadata import version
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="token-terminator-hermes-smoke-"
    ) as temp_dir:
        home = Path(temp_dir) / "hermes-home"
        home.mkdir(parents=True)
        database = home / "artifacts.sqlite3"
        os.environ["HERMES_HOME"] = str(home)
        os.environ["TOKEN_TERMINATOR_MODE"] = "balanced"
        os.environ["TOKEN_TERMINATOR_DB_PATH"] = str(database)
        os.environ["TOKEN_TERMINATOR_LEDGER_PATH"] = str(home / "experiments.sqlite3")
        os.environ["TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS"] = "100"
        (home / "config.yaml").write_text(
            "plugins:\n  enabled:\n    - token-terminator\n  disabled: []\n",
            encoding="utf-8",
        )

        # Import only after HERMES_HOME is isolated; Hermes resolves profile
        # paths at import time.
        from hermes_cli.plugins import PluginManager
        from tools.registry import registry

        installed_version = version("token-terminator")
        if installed_version != "0.3.0":
            raise AssertionError(f"unexpected installed version: {installed_version}")
        manager = PluginManager()
        manager.discover_and_load()
        plugins = manager.list_plugins()
        matching = [
            item
            for item in plugins
            if (item.get("key") or item.get("name")) == "token-terminator"
        ]
        if not matching:
            raise AssertionError("wheel entry point was not discovered")
        plugin = matching[0]
        if not plugin.get("enabled") or plugin.get("error"):
            raise AssertionError(f"plugin did not load cleanly: {plugin}")
        if not manager.has_middleware("llm_request"):
            raise AssertionError("llm_request middleware was not registered")
        if not manager.has_hook("post_tool_call"):
            raise AssertionError("post_tool_call evidence hook was not registered")
        if not manager.has_hook("transform_tool_result"):
            raise AssertionError("native result transformation hook was not registered")
        if manager._context_engine is not None:
            raise AssertionError("plugin incorrectly registered a context engine")
        if "token_terminator" not in manager._plugin_tool_names:
            raise AssertionError("single recovery tool was not registered")

        original_hook_evidence = "hook evidence " * 100
        manager.invoke_hook(
            "post_tool_call",
            tool_name="terminal",
            args={"command": "smoke"},
            result=original_hook_evidence,
            session_id="smoke-session",
            tool_call_id="hook-call-1",
        )
        with closing(sqlite3.connect(database)) as conn:
            captured = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        if captured != 1:
            raise AssertionError("post_tool_call evidence was not persisted")

        request = {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "inspect"},
                {"role": "tool", "tool_call_id": "c1", "content": "evidence " * 500},
            ]
        }
        first = manager.invoke_middleware(
            "llm_request",
            request=request,
            session_id="smoke-session",
            api_request_id="smoke-r1",
        )
        second = manager.invoke_middleware(
            "llm_request",
            request=request,
            session_id="smoke-session",
            api_request_id="smoke-r2",
        )
        if first:
            raise AssertionError(
                "first lease should leave the provider request unchanged"
            )
        if len(second) != 1 or not isinstance(second[0], dict):
            raise AssertionError("second middleware result is incompatible with Hermes")
        required_result_keys = {"request", "source", "reason", "metrics"}
        if not set(second[0]) >= required_result_keys:
            raise AssertionError("middleware result shape is incompatible with Hermes")
        second_content = second[0]["request"]["messages"][-1]["content"]
        if not second_content.startswith("[Token Terminator artifact "):
            raise AssertionError("expired evidence was not replaced by a receipt")
        if request["messages"][-1]["content"] != "evidence " * 500:
            raise AssertionError("middleware mutated the caller request")
        if second[0]["metrics"]["saved_chars"] <= 0:
            raise AssertionError("middleware accepted a non-smaller request")

        raw_native = "repeated native result\n" * 2_000
        native_results = manager.invoke_hook(
            "transform_tool_result",
            tool_name="search_files",
            args={},
            result=raw_native,
            session_id="smoke-session",
            tool_call_id="native-call-1",
        )
        transformed = next(
            (item for item in native_results if isinstance(item, str)),
            None,
        )
        if transformed is None or len(transformed) >= len(raw_native):
            raise AssertionError("native result was not strictly compressed")
        match = re.search(r"full artifact=(a_[0-9a-f]+)", transformed)
        if not match:
            raise AssertionError("native result did not contain an artifact receipt")
        artifact_id = match.group(1)
        recovered_parts = []
        offset = 0
        while True:
            recovered = json.loads(
                registry.dispatch(
                    "token_terminator",
                    {
                        "action": "artifact_get",
                        "artifact_id": artifact_id,
                        "offset": offset,
                        "limit": 20_000,
                    },
                )
            )
            if "error" in recovered:
                raise AssertionError(f"registered recovery tool failed: {recovered}")
            recovered_parts.append(recovered["content"])
            next_offset = recovered["next_offset"]
            if next_offset is None:
                break
            offset = next_offset
        if "".join(recovered_parts) != raw_native:
            raise AssertionError(
                "registered recovery tool did not return exact native output"
            )

        print(
            json.dumps(
                {
                    "plugin_loaded": True,
                    "installed_version": installed_version,
                    "context_engine_registered": False,
                    "llm_middleware_registered": True,
                    "native_transform_registered": True,
                    "single_recovery_tool_registered": True,
                    "evidence_hook_captured": True,
                    "first_call_unchanged": True,
                    "second_call_receipt": True,
                    "strictly_smaller_request": True,
                    "native_exact_recovery": True,
                    "caller_request_unchanged": True,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
