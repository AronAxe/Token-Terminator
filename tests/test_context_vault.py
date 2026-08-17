from __future__ import annotations

from rtk_hermes_plus.storage import TokenTerminatorStore


def test_artifact_round_trip_and_deduplication(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    original = "evidence αβγ\n" * 30

    first = store.put_artifact(
        original,
        tool_name="terminal",
        args={"command": "produce evidence"},
        session_id="session-a",
        tool_call_id="call-1",
    )
    second = store.put_artifact(
        original,
        tool_name="terminal",
        args={"command": "produce evidence again"},
        session_id="session-a",
        tool_call_id="call-2",
    )

    assert first.artifact_id == second.artifact_id
    assert first.created is True
    assert second.created is False
    recovered = store.get_artifact(first.artifact_id)
    assert recovered.content == original
    assert recovered.char_count == len(original)
    assert recovered.byte_count == len(original.encode("utf-8"))
    assert recovered.observation_count == 2


def test_artifact_search_and_bounded_read(tmp_path):
    store = TokenTerminatorStore(tmp_path / "context.db")
    stored = store.put_artifact("alpha needle omega", tool_name="read_file")

    hits = store.search_artifacts("needle", limit=5)
    assert [hit.artifact_id for hit in hits] == [stored.artifact_id]

    page = store.read_artifact(stored.artifact_id, offset=6, limit=6)
    assert page["content"] == "needle"
    assert page["next_offset"] == 12
    assert page["total_chars"] == len("alpha needle omega")
