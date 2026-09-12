from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one target, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))


# GC may reclaim abandoned captures, but never evidence already referenced by a
# provider-visible recovery receipt or temporal delta.
replace_once(
    "src/rtk_hermes_plus/storage.py",
    """            WHERE NOT EXISTS (
                SELECT 1 FROM terminal_snapshots t
                WHERE t.artifact_id=a.artifact_id
            )
            GROUP BY a.artifact_id
""",
    """            WHERE NOT EXISTS (
                SELECT 1 FROM terminal_snapshots t
                WHERE t.artifact_id=a.artifact_id
            )
              AND NOT EXISTS (
                SELECT 1 FROM artifact_exposures e
                WHERE e.artifact_id=a.artifact_id
            )
            GROUP BY a.artifact_id
""",
)

# Native tool-result compression is accepted before a later provider request is
# assembled, so protect its receipt immediately.
replace_once(
    "src/rtk_hermes_plus/compress.py",
    """        if len(transformed) >= len(result):
            self.metrics.add("native_not_smaller")
            return None
        self.metrics.add("native_compressed")
""",
    """        if len(transformed) >= len(result):
            self.metrics.add("native_not_smaller")
            return None
        try:
            if self.recovery.store is None:
                raise RuntimeError("recovery store unavailable")
            self.recovery.store.record_exposure(
                session_id=str(kwargs.get("session_id") or ""),
                artifact_id=artifact_id,
                request_id=f"tool:{kwargs.get('tool_call_id') or artifact_id}",
                inline=False,
            )
        except Exception:
            self.metrics.add("native_recovery_unavailable")
            return None
        self.metrics.add("native_compressed")
""",
)

# A temporal delta can name both the previous and the current exact artifact.
replace_once(
    "src/rtk_hermes_plus/temporal.py",
    """            if not candidate or len(candidate) >= len(result):
                self.metrics.add("temporal_not_smaller")
                return None

            self.metrics.add("temporal_reduced")
""",
    """            if not candidate or len(candidate) >= len(result):
                self.metrics.add("temporal_not_smaller")
                return None

            exposure_id = f"temporal:{state_key}:{current.artifact_id}"
            self.store.record_exposure(
                session_id=str(session_id or ""),
                artifact_id=previous_id,
                request_id=exposure_id,
                inline=False,
            )
            self.store.record_exposure(
                session_id=str(session_id or ""),
                artifact_id=current.artifact_id,
                request_id=exposure_id,
                inline=False,
            )
            self.metrics.add("temporal_reduced")
""",
)

# Protect every exact artifact identifier carried by an accepted provider-bound
# request. This catches compiler/context receipts and carried-forward receipts
# without protecting candidates rejected by the final request gate.
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    "import json\nimport logging\n",
    "import json\nimport logging\nimport re\n",
)
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    """INTERNAL_REQUEST_KEY_PREFIX = "_tt_"


def _strip_internal_metadata(request: Any) -> Any:
""",
    """INTERNAL_REQUEST_KEY_PREFIX = "_tt_"
_ARTIFACT_ID_PATTERN = re.compile(r"\ba_[0-9a-f]{32}(?:[0-9a-f]{32})?\b")


def _artifact_ids_in_value(value: Any) -> tuple[str, ...]:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return ()
    return tuple(sorted(set(_ARTIFACT_ID_PATTERN.findall(serialized))))


def _strip_internal_metadata(request: Any) -> Any:
""",
)
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    """        if compiled.failed_open or end_to_end_saved <= 0:
            return None
        return {
""",
    """        if compiled.failed_open or end_to_end_saved <= 0:
            return None
        if self.store is not None:
            for artifact_id in _artifact_ids_in_value(final_request):
                try:
                    self.store.record_exposure(
                        session_id=session_id,
                        artifact_id=artifact_id,
                        request_id=compiled.request_id or "provider-request",
                        inline=False,
                    )
                except Exception:
                    logger.debug(
                        "Token Terminator recovery-reference protection failed",
                        exc_info=True,
                    )
        return {
""",
)

# Regression: provider-visible recovery evidence must survive high-water GC.
tests_path = "tests/test_context_security.py"
tests = read(tests_path)
if "test_vault_retention_preserves_provider_recovery_reference" not in tests:
    tests += """


def test_vault_retention_preserves_provider_recovery_reference(tmp_path):
    store = TokenTerminatorStore(
        tmp_path / "protected.db",
        max_artifact_chars=100,
        max_vault_bytes=30,
        high_water_pct=90,
        low_water_pct=50,
    )
    protected = store.put_artifact("a" * 12, session_id="s", tool_call_id="c1")
    store.record_exposure(
        session_id="s",
        artifact_id=protected.artifact_id,
        request_id="provider-r1",
        inline=False,
    )
    unprotected = store.put_artifact("b" * 12, session_id="s", tool_call_id="c2")
    newest = store.put_artifact("c" * 12, session_id="s", tool_call_id="c3")
    assert store.get_artifact(protected.artifact_id).content == "a" * 12
    assert store.get_artifact(newest.artifact_id).content == "c" * 12
    with pytest.raises(KeyError):
        store.get_artifact(unprotected.artifact_id)
"""
    write(tests_path, tests)

# Migration and front-door documentation must describe the release actually
# produced by the branch.
migration_path = "MIGRATION.md"
migration = read(migration_path)
migration = migration.replace(
    "| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.5.0 |",
    "| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.5.1 |",
)
migration = migration.replace(
    "plugin key is `token-terminator` and version is `0.5.0`;",
    "plugin key is `token-terminator` and version is `0.5.1`;",
)
migration = migration.replace(
    "Disable 0.5.0 first and reinstall the immutable 0.4.0 tag:",
    "Disable 0.5.1 first and reinstall the immutable 0.4.0 tag:",
)
write(migration_path, migration)

readme_path = "README.md"
readme = read(readme_path)
readme = readme.replace("releases/tag/v0.5.0", "releases/tag/v0.5.1")
readme = readme.replace("Release v0.5.0", "Release v0.5.1")
readme = readme.replace("release-v0.5.0", "release-v0.5.1")
old_vault_sentence = (
    "Independent runtime instances and agent processes may share one local vault while "
    "preserving content deduplication, lease limits, and observation provenance."
)
new_vault_sentence = old_vault_sentence + (
    " High-water retention prunes only abandoned, non-recovery-referenced artifacts; "
    "evidence named by accepted recovery receipts remains protected."
)
if new_vault_sentence not in readme:
    readme = readme.replace(old_vault_sentence, new_vault_sentence)
write(readme_path, readme)

rust_doc_path = "docs/RUST_CRATE.md"
rust_doc = read(rust_doc_path).replace(
    'token-terminator = "0.5.0"', 'token-terminator = "0.5.1"'
)
write(rust_doc_path, rust_doc)

print("Final v0.5.1 recovery-safety and documentation fixes applied")
