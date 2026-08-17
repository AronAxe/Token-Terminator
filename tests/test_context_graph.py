from __future__ import annotations

import pytest

import rtk_hermes_plus.graph as graph_module
from rtk_hermes_plus.graph import GraphValidationError, WorkingStateGraph
from rtk_hermes_plus.storage import TokenTerminatorStore


def test_graph_operations_are_event_sourced_and_replayable(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    graph = WorkingStateGraph(store)
    operations = [
        {
            "op": "NODE_CREATE",
            "node_id": "O4",
            "kind": "observation",
            "label": "Observed behavior",
            "confidence": 0.95,
        },
        {
            "op": "PROPOSITION_CREATE",
            "node_id": "H17",
            "label": "Candidate explanation",
            "confidence": 0.24,
        },
        {
            "op": "EDGE_CREATE",
            "edge_id": "E39",
            "kind": "supports",
            "source": "O4",
            "target": "H17",
            "confidence": 0.81,
        },
        {
            "op": "NODE_UPDATE",
            "node_id": "H17",
            "confidence": 0.83,
            "priority": 0.7,
        },
    ]

    result = graph.apply(operations, session_id="session-a")
    assert result["accepted"] == 4
    state = graph.state()
    assert state["nodes"]["H17"]["confidence"] == 0.83
    assert state["edges"]["E39"]["source"] == "O4"
    assert store.counts()["graph_events"] == 4

    replay_store = TokenTerminatorStore(tmp_path / "replayed.db")
    replay_graph = WorkingStateGraph(replay_store)
    replay_result = replay_graph.replay(graph.events())
    assert replay_result["accepted"] == 4
    assert replay_graph.state() == graph.state()
    assert replay_graph.replay(graph.events()) == {"accepted": 0, "event_ids": []}


def test_invalid_batch_is_transactional(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    graph = WorkingStateGraph(store)
    before = store.counts()

    with pytest.raises(GraphValidationError):
        graph.apply(
            [
                {"op": "NODE_CREATE", "node_id": "N1", "kind": "claim"},
                {
                    "op": "EDGE_CREATE",
                    "edge_id": "E1",
                    "kind": "supports",
                    "source": "N1",
                    "target": "MISSING",
                },
            ]
        )

    assert store.counts() == before
    assert graph.state() == {"nodes": {}, "edges": {}}


def test_retirement_preserves_history_but_hides_from_active_state(tmp_path):
    graph = WorkingStateGraph(TokenTerminatorStore(tmp_path / "context.db"))
    graph.apply([{"op": "NODE_CREATE", "node_id": "N1", "kind": "question"}])
    graph.apply([{"op": "NODE_RETIRE", "node_id": "N1"}])

    assert "N1" not in graph.state()["nodes"]
    assert graph.state(include_retired=True)["nodes"]["N1"]["status"] == "retired"
    assert len(graph.events()) == 2


def test_replay_failure_is_atomic_and_conflicts_are_rejected(tmp_path):
    graph = WorkingStateGraph(TokenTerminatorStore(tmp_path / "replay.db"))
    events = [
        {
            "event_id": "evt-node",
            "session_id": "s1",
            "op": "NODE_CREATE",
            "node_id": "N1",
            "kind": "claim",
        },
        {
            "event_id": "evt-edge",
            "session_id": "s1",
            "op": "EDGE_CREATE",
            "edge_id": "E1",
            "kind": "supports",
            "source": "N1",
            "target": "MISSING",
        },
    ]
    with pytest.raises(GraphValidationError):
        graph.replay(events)
    assert graph.state() == {"nodes": {}, "edges": {}}
    assert graph.events() == []

    graph.replay([events[0]])
    conflict = {**events[0], "kind": "observation"}
    with pytest.raises(GraphValidationError, match="conflicting replay event"):
        graph.replay([conflict])
    assert graph.state()["nodes"]["N1"]["kind"] == "claim"


def test_node_retirement_cascades_edges_and_limited_state_has_no_dangling_edges(
    tmp_path,
):
    graph = WorkingStateGraph(TokenTerminatorStore(tmp_path / "cascade.db"))
    graph.apply(
        [
            {"op": "NODE_CREATE", "node_id": "N1", "kind": "claim"},
            {"op": "NODE_CREATE", "node_id": "N2", "kind": "claim"},
            {
                "op": "EDGE_CREATE",
                "edge_id": "E1",
                "kind": "supports",
                "source": "N1",
                "target": "N2",
            },
        ]
    )
    limited = graph.state(limit=1)
    assert limited["edges"] == {}

    graph.apply([{"op": "NODE_RETIRE", "node_id": "N1"}])
    assert graph.state()["edges"] == {}
    retired = graph.state(include_retired=True)
    assert retired["edges"]["E1"]["status"] == "retired"


def test_working_state_has_hard_entity_and_event_caps(tmp_path, monkeypatch):
    graph = WorkingStateGraph(TokenTerminatorStore(tmp_path / "bounded.db"))
    monkeypatch.setattr(graph_module, "MAX_GRAPH_NODES", 1)
    graph.apply([{"op": "NODE_CREATE", "node_id": "N1", "kind": "claim"}])
    with pytest.raises(GraphValidationError, match="must not exceed 1 nodes"):
        graph.apply([{"op": "NODE_CREATE", "node_id": "N2", "kind": "claim"}])

    monkeypatch.setattr(graph_module, "MAX_GRAPH_EVENTS", 1)
    with pytest.raises(GraphValidationError, match="must not exceed 1 events"):
        graph.apply([{"op": "NODE_UPDATE", "node_id": "N1", "label": "later"}])
