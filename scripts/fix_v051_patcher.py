from pathlib import Path

path = Path("scripts/apply_v051_hardening.py")
text = path.read_text(encoding="utf-8")

# Repair the original one-shot ledger schema patch so both session and turn
# tables receive the exact-token accounting fields.
old = '''replace_once(
    "src/rtk_hermes_plus/ledger.py",
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n',
    '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n',
)
'''
new = '''text = read("src/rtk_hermes_plus/ledger.py")
needle = '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n'
replacement = '    native_raw_chars INTEGER NOT NULL DEFAULT 0,\\n    native_output_chars INTEGER NOT NULL DEFAULT 0,\\n    native_raw_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_output_tokens INTEGER NOT NULL DEFAULT 0,\\n    native_token_measurements INTEGER NOT NULL DEFAULT 0,\\n    native_compressions INTEGER NOT NULL DEFAULT 0,\\n'
if text.count(needle) != 2:
    raise RuntimeError(f"ledger schema: expected two native metric blocks, found {text.count(needle)}")
text = text.replace(needle, replacement)
write("src/rtk_hermes_plus/ledger.py", text)
'''
if old in text:
    text = text.replace(old, new, 1)
elif "ledger schema: expected two native metric blocks" not in text:
    raise RuntimeError("target ledger patcher block not found")

# Fix the URI regression-test monkeypatch: sqlite3.connect has a keyword named
# `uri`, so the first positional parameter must not also be called uri.
text = text.replace(
    "    def fake_connect(uri, **_kwargs):\\n        captured.append(uri)\\n",
    "    def fake_connect(database, **_kwargs):\\n        captured.append(database)\\n",
)

# Additional correctness pass. This code is appended to the one-shot patcher
# and therefore runs against the generated 0.5.1 tree before verification.
marker = 'print("v0.5.1 hardening patch applied")\n'
if marker not in text:
    raise RuntimeError("v0.5.1 patcher completion marker not found")

extra = r'''
# ---------------------------------------------------------------------------
# Final retention/release corrections found by the first verification run.
# Provider-visible recovery references are GC pins: disk pressure may prune
# abandoned captures, never evidence that the model was promised it could get.
# ---------------------------------------------------------------------------
replace_once(
    "src/rtk_hermes_plus/storage.py",
    '''            WHERE NOT EXISTS (
                SELECT 1 FROM terminal_snapshots t
                WHERE t.artifact_id=a.artifact_id
            )
            GROUP BY a.artifact_id
''',
    '''            WHERE NOT EXISTS (
                SELECT 1 FROM terminal_snapshots t
                WHERE t.artifact_id=a.artifact_id
            )
              AND NOT EXISTS (
                SELECT 1 FROM artifact_exposures e
                WHERE e.artifact_id=a.artifact_id
            )
            GROUP BY a.artifact_id
''',
)

# A native compact result contains a recovery receipt before the next provider
# request exists. Protect it immediately so a parallel/later tool capture cannot
# evict the exact artifact in that gap.
replace_once(
    "src/rtk_hermes_plus/compress.py",
    '''        if len(transformed) >= len(result):
            self.metrics.add("native_not_smaller")
            return None
        self.metrics.add("native_compressed")
''',
    '''        if len(transformed) >= len(result):
            self.metrics.add("native_not_smaller")
            return None
        try:
            store = self.recovery.store
            if store is None:
                raise RuntimeError("recovery store unavailable")
            store.record_exposure(
                session_id=str(kwargs.get("session_id") or ""),
                artifact_id=artifact_id,
                request_id=f"tool:{kwargs.get('tool_call_id') or artifact_id}",
                inline=False,
            )
        except Exception:
            self.metrics.add("native_recovery_unavailable")
            return None
        self.metrics.add("native_compressed")
''',
)

# Temporal deltas reference both the previous and the current exact artifact.
# The snapshot table protects only the current baseline after the update, so pin
# both provider-visible IDs explicitly.
replace_once(
    "src/rtk_hermes_plus/temporal.py",
    '''            if not candidate or len(candidate) >= len(result):
                self.metrics.add("temporal_not_smaller")
                return None

            self.metrics.add("temporal_reduced")
''',
    '''            if not candidate or len(candidate) >= len(result):
                self.metrics.add("temporal_not_smaller")
                return None

            request_key = f"temporal:{state_key}:{current.artifact_id}"
            self.store.record_exposure(
                session_id=str(session_id or ""),
                artifact_id=previous_id,
                request_id=request_key,
                inline=False,
            )
            self.store.record_exposure(
                session_id=str(session_id or ""),
                artifact_id=current.artifact_id,
                request_id=request_key,
                inline=False,
            )
            self.metrics.add("temporal_reduced")
''',
)

# Protect every exact artifact ID that is actually present in the accepted
# provider-bound request. This covers compiler receipts, context-compactor
# receipts, and older recovery receipts carried forward in conversation history,
# without pinning candidates that fail the final request gate.
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    "import json\nimport logging\n",
    "import json\nimport logging\nimport re\n",
)
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    '''INTERNAL_REQUEST_KEY_PREFIX = "_tt_"


def _strip_internal_metadata(request: Any) -> Any:
''',
    '''INTERNAL_REQUEST_KEY_PREFIX = "_tt_"
_ARTIFACT_ID_PATTERN = re.compile(r"\\ba_[0-9a-f]{32}(?:[0-9a-f]{32})?\\b")


def _artifact_ids_in_value(value: Any) -> tuple[str, ...]:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return ()
    return tuple(sorted(set(_ARTIFACT_ID_PATTERN.findall(serialized))))


def _strip_internal_metadata(request: Any) -> Any:
''',
)
replace_once(
    "src/rtk_hermes_plus/plugin.py",
    '''        if compiled.failed_open or end_to_end_saved <= 0:
            return None
        return {
''',
    '''        if compiled.failed_open or end_to_end_saved <= 0:
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
                    return None
        return {
''',
)

# The old hard-capacity regression intentionally changes meaning in 0.5.1:
# an unprotected old capture is now reclaimed instead of permanently disabling
# future optimization. Keep the observation-dedup assertion, then verify GC.
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

# Regression test: provider-visible recovery references are not GC candidates.
security_tests = read("tests/test_context_security.py")
retention_test = '''\n\ndef test_vault_retention_never_prunes_provider_recovery_reference(tmp_path):
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
'''
if "test_vault_retention_never_prunes_provider_recovery_reference" not in security_tests:
    security_tests += retention_test
write("tests/test_context_security.py", security_tests)

# 0.5.1 is the current install target; retain the historical 0.5.0 feature
# section but add the hardening delta and update installation/verification.
migration = read("MIGRATION.md")
migration = migration.replace(
    "# Migration and rollback: 0.2.0 / 0.4.0 → 0.5.0",
    "# Migration and rollback: 0.2.0 / 0.4.0 / 0.5.0 → 0.5.1",
    1,
)
migration = migration.replace(
    "Token Terminator 0.5.0 supersedes Token Terminator 0.4.0 and replaces the older RTK Hermes Plus 0.2.0 distribution.",
    "Token Terminator 0.5.1 supersedes Token Terminator 0.5.0, remains compatible with 0.4.0 vaults, and replaces the older RTK Hermes Plus 0.2.0 distribution.",
    1,
)
migration = migration.replace(
    "| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.5.0 |",
    "| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.5.1 |",
    1,
)
section_marker = "## What 0.5.0 adds over 0.4.0\n"
hardening_section = '''## What 0.5.1 hardens over 0.5.0

- capacity-managed vault retention with O(1) byte accounting and high/low-water pruning of abandoned, non-recovery-critical captures;
- Unicode-correct artifact search and workspace-scoped RTK rewrite caching;
- one context-window invariant and one canonical inline-turn default;
- temporal-delta parity for `AsyncRuntime`;
- schema-managed temporal snapshots, safer custom-path permissions, an optional pinned RTK path, and Windows-safe SQLite URIs;
- more explicit comparison statistics, unmatched-observation accounting, and bootstrap confidence intervals;
- provider-visible artifact references are retention pins, so automatic GC never invalidates a recovery receipt.

If recovery-critical evidence alone fills the configured hard capacity, Token Terminator still fails open rather than deleting promised evidence; `/token-terminator status` exposes vault pressure and pruning counters so this condition is visible.

'''
if hardening_section not in migration:
    migration = migration.replace(section_marker, hardening_section + section_marker, 1)
migration = migration.replace("@v0.5.0'", "@v0.5.1'", 1)
migration = migration.replace(
    "plugin key is `token-terminator` and version is `0.5.0`;",
    "plugin key is `token-terminator` and version is `0.5.1`;",
    1,
)
migration = migration.replace(
    "## Roll back to Token Terminator 0.4.0\n\nDisable 0.5.0 first",
    "## Roll back to Token Terminator 0.4.0\n\nDisable 0.5.1 first",
    1,
)
write("MIGRATION.md", migration)

# Front-door release metadata and Rust companion docs follow the synchronized
# patch version because Cargo.toml is intentionally bumped with this release.
readme = read("README.md")
readme = readme.replace("releases/tag/v0.5.0", "releases/tag/v0.5.1")
readme = readme.replace("Release v0.5.0", "Release v0.5.1")
readme = readme.replace("release-v0.5.0", "release-v0.5.1")
write("README.md", readme)
for doc_path in ("docs/RUST_CRATE.md",):
    doc = read(doc_path)
    doc = doc.replace('token-terminator = "0.5.0"', 'token-terminator = "0.5.1"')
    write(doc_path, doc)

# Correct the changelog claim: retention is evidence-safe rather than magic.
changelog = read("CHANGELOG.md")
changelog = changelog.replace(
    "pruning telemetry, and status reporting instead of a permanent hard-wall failure.",
    "pruning telemetry, and status reporting; recovery-critical evidence remains fail-open protected at the hard capacity rather than being deleted.",
)
write("CHANGELOG.md", changelog)
'''

if "Final retention/release corrections found by the first verification run" not in text:
    text = text.replace(marker, extra + "\n" + marker, 1)

path.write_text(text, encoding="utf-8")
