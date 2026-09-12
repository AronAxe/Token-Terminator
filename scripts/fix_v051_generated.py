from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one target, found {text.count(old)}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Retention deliberately replaces the old permanent hard-wall behavior. Keep
# the per-artifact ceiling assertion, then prove a new unique artifact evicts
# the oldest unprotected artifact instead of disabling future optimization.
replace_once(
    "tests/test_context_security.py",
    '''    with pytest.raises(VaultCapacityError):
        store.put_artifact("b" * 6, session_id="s1", tool_call_id="c2")
    assert store.counts()["artifacts"] == 1
''',
    '''    replacement = store.put_artifact(
        "b" * 6, session_id="s1", tool_call_id="c2"
    )
    assert store.get_artifact(replacement.artifact_id).content == "b" * 6
    with pytest.raises(KeyError):
        store.get_artifact(stored.artifact_id)
    counts = store.counts()
    assert counts["artifacts"] == 1
    assert counts["vault_pruned_artifacts"] == 1
''',
)

# pathlib.as_uri() is the behavior under test; make the sqlite stub's first
# parameter distinct from sqlite3.connect's `uri=` keyword argument.
replace_once(
    "tests/test_v051_hardening.py",
    '''    def fake_connect(uri, **_kwargs):
        captured.append(uri)
        return DummyConnection()
''',
    '''    def fake_connect(database, **_kwargs):
        captured.append(database)
        return DummyConnection()
''',
)

migration = Path("MIGRATION.md")
text = migration.read_text(encoding="utf-8")
text = text.replace(
    "# Migration and rollback: 0.2.0 / 0.4.0 → 0.5.0",
    "# Migration and rollback: 0.2.0 / 0.4.0 / 0.5.0 → 0.5.1",
    1,
)
text = text.replace(
    "Token Terminator 0.5.0 supersedes Token Terminator 0.4.0",
    "Token Terminator 0.5.1 supersedes Token Terminator 0.5.0",
    1,
)
text = text.replace("@v0.5.0", "@v0.5.1")
if "## 0.5.0 → 0.5.1 hardening" not in text:
    marker = "\n## "
    pos = text.find(marker)
    insert = """

## 0.5.0 → 0.5.1 hardening

0.5.1 is an in-place hardening upgrade. It keeps the content-addressed artifact identity and schema-2 compatibility, adds schema-managed temporal snapshots and additive vault metadata, introduces bounded retention before the configured vault capacity is exhausted, and makes Unicode search, async temporal reduction, rewrite caching, measurement, and security behavior consistent. Existing exact artifacts remain valid; retention may prune old unprotected artifacts only after the configured high-water mark is crossed.
"""
    if pos == -1:
        text += insert
    else:
        text = text[:pos] + insert + text[pos:]
migration.write_text(text, encoding="utf-8")
