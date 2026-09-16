from __future__ import annotations

import copy
import json

from rtk_hermes_plus import Runtime
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.token_budget import TokenMeasurement


def _config(tmp_path, **kwargs):
    values = {
        "mode": "balanced",
        "ledger_enabled": False,
        "ledger_path": tmp_path / "experiments.sqlite3",
        "state_db_path": tmp_path / "state.db",
        "db_path": tmp_path / "artifacts.sqlite3",
        "min_artifact_chars": 20,
        "native_min_chars": 1_000,
        "graph_context_chars": 0,
    }
    values.update(kwargs)
    return Config(**values)


class _Budget:
    usable_context_tokens = None

    def measure_request(self, request, *, model=""):
        request_model = request.get("model", "") if isinstance(request, dict) else ""
        active_model = str(request_model or model or "")
        text = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return TokenMeasurement(len(text), "test-tokenizer", active_model)

    def measure_text(self, text, *, model=""):
        return TokenMeasurement(len(text), "test-tokenizer", str(model or ""))

    def status(self):
        return {"enabled": True, "backend": "test-tokenizer"}


def _install_budget(runtime, budget):
    runtime.token_budget = budget
    runtime._sync_token_budget()


def _request():
    catalog = """System rules.
<available_skills>
  github:
    - github-release: Create and publish GitHub releases and tags
    - pull-request-review: Review GitHub pull requests and diffs
  productivity:
    - calendar: Create and edit calendar events
    - email: Search, draft, and send email messages
  data:
    - spreadsheets: Analyze spreadsheet formulas and tables
    - sql: Query relational databases and inspect schemas
  media:
    - images: Generate and edit images
    - slides: Build presentation decks
</available_skills>
Use a relevant skill when needed."""
    return {
        "model": "openai/gpt-5",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "skills_list",
                    "description": "Search installed skills",
                    "parameters": {"type": "object"},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "skill_view",
                    "description": "Load a skill",
                    "parameters": {"type": "object"},
                },
            },
        ],
        "messages": [
            {"role": "system", "content": catalog},
            {"role": "user", "content": "Publish this project as a GitHub release."},
        ],
    }


def test_runtime_returns_skillgate_only_reduction(tmp_path):
    runtime = Runtime(_config(tmp_path))
    _install_budget(runtime, _Budget())
    request = _request()
    original = copy.deepcopy(request)

    decision = runtime.llm_request_middleware(
        request=request,
        session_id="s1",
        api_request_id="r1",
    )

    assert decision is not None
    assert request == original
    assert decision["metrics"]["skill_gate"]["changed"] is True
    assert decision["metrics"]["saved_tokens"] > 0
    assert "github-release" in decision["request"]["messages"][0]["content"]
    assert "calendar" not in decision["request"]["messages"][0]["content"]


def test_runtime_persists_original_to_final_attribution(tmp_path):
    runtime = Runtime(_config(tmp_path))
    _install_budget(runtime, _Budget())
    request = _request()
    raw_tokens = runtime.token_budget.measure_request(request).tokens

    decision = runtime.llm_request_middleware(
        request=request,
        session_id="s-attribution",
        api_request_id="r-attribution",
    )

    assert decision is not None
    with runtime.store.connection() as conn:
        token_row = conn.execute(
            """
            SELECT raw_tokens, final_tokens, saved_tokens
            FROM request_token_metrics
            WHERE session_id=? AND request_id=?
            """,
            ("s-attribution", "r-attribution"),
        ).fetchone()
        skill_row = conn.execute(
            """
            SELECT raw_tokens, final_tokens
            FROM request_component_metrics
            WHERE session_id=? AND request_id=? AND component='skill_catalog'
            """,
            ("s-attribution", "r-attribution"),
        ).fetchone()

    assert token_row is not None
    assert token_row["raw_tokens"] == raw_tokens
    assert token_row["final_tokens"] < token_row["raw_tokens"]
    assert (
        token_row["saved_tokens"] == token_row["raw_tokens"] - token_row["final_tokens"]
    )
    assert skill_row is not None
    assert skill_row["raw_tokens"] > skill_row["final_tokens"]

    status = runtime.status()
    assert status["request_attribution"]["requests"] == 1
    assert (
        status["request_attribution"]["components"]["skill_catalog"]["saved_tokens"] > 0
    )
    assert status["skill_gate"]["scorer"] == "lexical-idf"


def test_non_compiler_mode_does_not_route_provider_request(tmp_path):
    runtime = Runtime(_config(tmp_path, mode="native"))
    _install_budget(runtime, _Budget())
    request = _request()

    decision = runtime.llm_request_middleware(
        request=request,
        session_id="s-native",
        api_request_id="r-native",
    )

    assert decision is None
    status = runtime.status()
    assert status["skill_gate"]["enabled"] is False
