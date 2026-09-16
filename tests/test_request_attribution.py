from __future__ import annotations

import json

from rtk_hermes_plus.request_attribution import (
    RequestAttributionAccounting,
    RequestAttributor,
)
from rtk_hermes_plus.storage import TokenTerminatorStore
from rtk_hermes_plus.token_budget import TokenMeasurement


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
        return TokenMeasurement(max(1, len(text) // 3), "test-tokenizer", active_model)

    def measure_text(self, text, *, model=""):
        return TokenMeasurement(
            max(1, len(text) // 3), "test-tokenizer", str(model or "")
        )

    def status(self):
        return {"enabled": True}


def _request():
    return {
        "model": "openai/gpt-5",
        "instructions": "Global instruction",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search files",
                    "parameters": {"type": "object"},
                },
            }
        ],
        "messages": [
            {
                "role": "system",
                "content": """System policy.
<available_skills>
  github:
    - github-release: Create releases
    - pull-request-review: Review pull requests
</available_skills>
After skill policy.""",
            },
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "tool evidence",
            },
            {"role": "user", "content": "Current question"},
        ],
        "temperature": 0.2,
    }


def test_request_attribution_separates_skill_catalog_from_instructions():
    snapshot = RequestAttributor(_Budget()).measure(_request())

    assert snapshot.exact is True
    assert snapshot.model == "openai/gpt-5"
    assert snapshot.components["instructions"].tokens > 0
    assert snapshot.components["skill_catalog"].tokens > 0
    assert snapshot.components["tool_schemas"].tokens > 0
    assert snapshot.components["tool_results"].tokens > 0
    assert snapshot.components["current_user"].tokens > 0
    assert snapshot.components["history"].tokens > 0
    assert snapshot.components["other"].tokens > 0
    payload = snapshot.as_dict()
    assert payload["source"] == "exact-tokenizer"
    assert payload["components"]["skill_catalog"]["exact"] is True


def test_component_accounting_persists_only_metrics(tmp_path):
    store = TokenTerminatorStore(tmp_path / "artifacts.sqlite3")
    budget = _Budget()
    attributor = RequestAttributor(budget)
    accounting = RequestAttributionAccounting(store)

    raw_request = _request()
    final_request = _request()
    final_request["messages"][0]["content"] = "System policy."
    raw = attributor.measure(raw_request)
    final = attributor.measure(final_request)

    assert accounting.record(
        session_id="s1",
        request_id="r1",
        raw=raw,
        final=final,
    )
    summary = accounting.summary()

    assert summary["available"] is True
    assert summary["requests"] == 1
    skill = summary["components"]["skill_catalog"]
    assert skill["raw_tokens"] > 0
    assert skill["final_tokens"] == 0
    assert skill["saved_tokens"] > 0
    with store.connection() as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(request_component_metrics)").fetchall()
        }
    assert "content" not in columns
    assert "prompt" not in columns
