from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path, *args):
    env = os.environ.copy()
    env["TOKEN_TERMINATOR_DB_PATH"] = str(tmp_path / "context.db")
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "rtk_hermes_plus.cli", *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_cli_status_and_compile_json(tmp_path):
    status = run_cli(tmp_path, "status", "--json")
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["artifacts"] == 0

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "question"},
                    {"role": "tool", "tool_call_id": "c1", "content": "x" * 9000},
                ]
            }
        ),
        encoding="utf-8",
    )
    compiled = run_cli(
        tmp_path,
        "compile",
        "--request",
        str(request_path),
        "--session",
        "cli-test",
        "--request-id",
        "r1",
        "--json",
    )
    assert compiled.returncode == 0, compiled.stderr
    payload = json.loads(compiled.stdout)
    assert payload["request"]["messages"][-1]["content"] == "x" * 9000
    assert payload["artifacts"] == 1


def test_cli_graph_apply_dry_run_does_not_mutate(tmp_path):
    operations_path = tmp_path / "ops.json"
    operations_path.write_text(
        json.dumps([{"op": "NODE_CREATE", "node_id": "N1", "kind": "goal"}]),
        encoding="utf-8",
    )

    dry = run_cli(
        tmp_path,
        "working-state",
        "apply",
        "--file",
        str(operations_path),
        "--dry-run",
        "--json",
    )
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["valid"] is True

    state = run_cli(tmp_path, "working-state", "state", "--json")
    assert state.returncode == 0, state.stderr
    assert json.loads(state.stdout)["nodes"] == {}


def test_cli_honors_configured_vault_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS", "1")
    monkeypatch.setenv("TOKEN_TERMINATOR_MAX_ARTIFACT_CHARS", "1000")
    monkeypatch.setenv("TOKEN_TERMINATOR_VAULT_MAX_BYTES", "10")
    request_path = tmp_path / "oversized-for-vault.json"
    request_path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "question"},
                    {"role": "tool", "tool_call_id": "c1", "content": "x" * 100},
                ]
            }
        ),
        encoding="utf-8",
    )

    compiled = run_cli(tmp_path, "compile", "--request", str(request_path), "--json")
    assert compiled.returncode == 0, compiled.stderr
    payload = json.loads(compiled.stdout)
    assert payload["failed_open"] is True
    assert payload["artifacts"] == 0

    status = run_cli(tmp_path, "status", "--json")
    assert status.returncode == 0, status.stderr
    status_payload = json.loads(status.stdout)
    assert status_payload["max_artifact_chars"] == 1000
    assert status_payload["vault_max_bytes"] == 10
    assert status_payload["artifacts"] == 0
