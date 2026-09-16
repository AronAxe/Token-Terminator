from __future__ import annotations

import copy
import json

from rtk_hermes_plus.skillgate import SkillGate
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
        return TokenMeasurement(len(text), "test-tokenizer", active_model)

    def measure_text(self, text, *, model=""):
        return TokenMeasurement(len(text), "test-tokenizer", str(model or ""))

    def status(self):
        return {"enabled": True}


class _ReverseBudget(_Budget):
    def measure_request(self, request, *, model=""):
        measured = super().measure_request(request, model=model)
        # Deliberately claim shorter serialized requests use more tokens.
        return TokenMeasurement(
            1_000_000 - int(measured.tokens or 0),
            measured.backend,
            measured.model,
        )


def _tools():
    return [
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
                "description": "Load one skill",
                "parameters": {"type": "object"},
            },
        },
    ]


def _catalog():
    return """You are an agent.
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
Follow the relevant skill when one applies."""


def _request(prompt="Publish the current project as a GitHub release."):
    return {
        "model": "openai/gpt-5",
        "tools": _tools(),
        "messages": [
            {"role": "system", "content": _catalog()},
            {"role": "user", "content": prompt},
        ],
    }


def test_routes_to_relevant_skills_without_mutating_input():
    gate = SkillGate(_Budget(), max_skills=2)
    request = _request()
    original = copy.deepcopy(request)

    result = gate.route(request, model="openai/gpt-5")

    assert result.changed is True
    assert request == original
    assert result.catalog_skills == 8
    assert "github-release" in result.selected_names
    assert result.removed_skills >= 6
    rendered = result.request["messages"][0]["content"]
    assert "github-release" in rendered
    assert "calendar" not in rendered
    assert "skills_list(query=...)" in rendered
    assert result.final_chars < result.raw_chars
    assert result.final_tokens < result.raw_tokens


def test_no_direct_match_becomes_compact_discovery_pointer():
    gate = SkillGate(_Budget(), max_skills=2)
    result = gate.route(_request("Tell me a joke about penguins."))

    assert result.changed is True
    assert result.selected_skills == 0
    rendered = result.request["messages"][0]["content"]
    assert "no direct match" in rendered
    assert "skills_list(query=...)" in rendered
    assert "github-release" not in rendered


def test_requires_both_skill_discovery_tools():
    gate = SkillGate(_Budget())
    request = _request()
    request["tools"] = request["tools"][:1]

    result = gate.route(request)

    assert result.changed is False
    assert result.request is request
    assert result.reason == "skill discovery tools unavailable"


def test_small_catalog_is_left_untouched():
    gate = SkillGate(_Budget(), min_catalog_skills=9)
    request = _request()

    result = gate.route(request)

    assert result.changed is False
    assert result.request is request


def test_custom_scorer_can_replace_lexical_router():
    gate = SkillGate(_Budget(), max_skills=1, min_score=0.1)
    gate.set_scorer(lambda _prompt, skill: 100.0 if skill.name == "calendar" else 0.0)

    result = gate.route(_request("Publish the repository."))

    assert result.changed is True
    assert result.selected_names == ("calendar",)
    rendered = result.request["messages"][0]["content"]
    assert "calendar" in rendered
    assert "github-release" not in rendered


def test_tokenizer_gate_rejects_character_only_win_when_tokens_expand():
    gate = SkillGate(_ReverseBudget(), max_skills=1)
    request = _request()

    result = gate.route(request)

    assert result.changed is False
    assert result.request is request
    assert result.reason == "candidate not smaller in tokens"


def test_user_quoted_skill_catalog_is_never_rewritten():
    gate = SkillGate(_Budget(), max_skills=1)
    quoted = _catalog()
    request = _request(
        "Here is some literal text I am debugging:\n" + quoted + "\nDo not alter the quote."
    )
    original_user = request["messages"][1]["content"]

    result = gate.route(request)

    assert result.changed is True
    assert result.request["messages"][1]["content"] == original_user
    assert result.request["messages"][0]["content"] != request["messages"][0]["content"]
