from __future__ import annotations

import json

from rtk_hermes_plus.skill_graph import SkillDocument, SkillGraph
from rtk_hermes_plus.skillgate import SkillGate
from rtk_hermes_plus.token_budget import TokenMeasurement


class _Budget:
    usable_context_tokens = None

    def measure_request(self, request, *, model=""):
        text = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return TokenMeasurement(len(text), "test-tokenizer", str(model or ""))

    def measure_text(self, text, *, model=""):
        return TokenMeasurement(len(text), "test-tokenizer", str(model or ""))

    def status(self):
        return {"enabled": True}


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


def _request(prompt: str, rows: list[tuple[str, str]]) -> dict:
    lines = ["<available_skills>", "  synthetic:"]
    lines.extend(f"    - {name}: {description}" for name, description in rows)
    lines.append("</available_skills>")
    return {
        "model": "test/model",
        "tools": _tools(),
        "messages": [
            {"role": "system", "content": "\n".join(lines)},
            {"role": "user", "content": prompt},
        ],
    }


def _padded_rows(*rows: tuple[str, str]) -> list[tuple[str, str]]:
    output = list(rows)
    for index in range(8):
        output.append(
            (
                f"synthetic-filler-{index}",
                f"Maintain fictional lunar orchard inventory register number {index}",
            )
        )
    return output


def test_graph_ships_empty():
    graph = SkillGraph()

    status = graph.status()

    assert status["loaded"] is False
    assert status["skills"] == 0
    assert status["internal_nodes"] == 0
    assert status["outer_related_edges"] == 0
    assert status["outer_requires_edges"] == 0


def test_graph_of_graphs_preserves_skill_boundaries():
    graph = SkillGraph()
    graph.replace_documents(
        [
            SkillDocument(
                name="alpha",
                description="Alpha workflow",
                content="# Prepare\nUnique alpha preparation.\n## Verify\nCheck alpha.",
                related_skills=("beta",),
            ),
            SkillDocument(
                name="beta",
                description="Beta workflow",
                content="# Prepare\nUnique beta preparation.\n## Publish\nShip beta.",
            ),
        ]
    )

    alpha = graph.get("alpha")
    beta = graph.get("beta")

    assert alpha is not None and beta is not None
    assert alpha.internal_nodes != beta.internal_nodes
    assert any(edge.kind == "contains" for edge in alpha.internal_edges)
    assert graph.related("alpha") == ("beta",)
    assert graph.related("beta") == ()


def test_no_outer_edges_are_inferred_from_shared_words():
    graph = SkillGraph()
    graph.replace_documents(
        [
            SkillDocument(name="alpha", content="# Deploy\nShared deployment token."),
            SkillDocument(name="beta", content="# Deploy\nShared deployment token."),
        ]
    )

    assert graph.related("alpha") == ()
    assert graph.related("beta") == ()
    assert graph.status()["outer_related_edges"] == 0


def test_internal_skill_graph_can_route_on_content_not_catalog_description():
    graph = SkillGraph()
    graph.replace_documents(
        [
            SkillDocument(
                name="alpha",
                description="Generic workflow",
                content="# Specialized operation\nHandle zirconium-reticulation safely.",
            ),
            SkillDocument(
                name="beta",
                description="Generic workflow",
                content="# Other operation\nHandle ordinary table exports.",
            ),
        ]
    )
    gate = SkillGate(
        _Budget(),
        min_catalog_skills=1,
        min_score=2.0,
        skill_graph=graph,
    )

    result = gate.route(
        _request(
            "I need zirconium-reticulation for this task.",
            _padded_rows(
                ("alpha", "Generic workflow"),
                ("beta", "Generic workflow"),
            ),
        )
    )

    assert result.changed is True
    assert result.selected_names == ("alpha",)


def test_explicit_requires_edge_keeps_dependency():
    graph = SkillGraph()
    graph.replace_documents(
        [
            SkillDocument(
                name="publisher",
                description="Publish a package",
                content="# Publish\nShip the frobnicator package.",
                requires_skills=("verifier",),
            ),
            SkillDocument(
                name="verifier",
                description="Verification support",
                content="# Verify\nRun package integrity checks.",
            ),
        ]
    )
    gate = SkillGate(
        _Budget(),
        min_catalog_skills=1,
        min_score=2.0,
        skill_graph=graph,
    )

    result = gate.route(
        _request(
            "Ship the frobnicator package.",
            _padded_rows(
                ("publisher", "Publish a package"),
                ("verifier", "Verification support"),
                ("calendar", "Calendar operations"),
            ),
        )
    )

    assert result.changed is True
    assert "publisher" in result.selected_names
    assert "verifier" in result.selected_names


def test_private_skill_contents_never_enter_routed_request():
    marker = "PRIVATE-INSTALLED-SKILL-CONTENT-94731"
    graph = SkillGraph()
    graph.replace_documents(
        [
            SkillDocument(
                name="alpha",
                description="Generic workflow",
                content=f"# Secret procedure\n{marker}\nHandle zirconium-reticulation.",
            )
        ]
    )
    gate = SkillGate(
        _Budget(),
        min_catalog_skills=1,
        min_score=2.0,
        skill_graph=graph,
    )

    result = gate.route(
        _request(
            "Do zirconium-reticulation.",
            _padded_rows(("alpha", "Generic workflow")),
        )
    )

    serialized = json.dumps(result.request, ensure_ascii=False)
    assert result.changed is True
    assert "alpha" in result.selected_names
    assert marker not in serialized


def test_provider_refreshes_only_when_catalog_changes():
    calls = 0

    def provider():
        nonlocal calls
        calls += 1
        return [
            SkillDocument(
                name="alpha",
                description="Generic workflow",
                content="# Specialized\nHandle zirconium-reticulation.",
            )
        ]

    graph = SkillGraph(provider)
    gate = SkillGate(
        _Budget(),
        min_catalog_skills=1,
        min_score=2.0,
        skill_graph=graph,
    )
    request = _request(
        "Do zirconium-reticulation.",
        _padded_rows(("alpha", "Generic workflow")),
    )

    first = gate.route(request)
    second = gate.route(request)
    changed_catalog = gate.route(
        _request(
            "Do zirconium-reticulation.",
            _padded_rows(("alpha", "Updated generic workflow")),
        )
    )

    assert first.changed is True
    assert second.changed is True
    assert changed_catalog.changed is True
    assert calls == 2
