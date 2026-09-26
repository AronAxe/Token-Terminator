# Migration and Rollback

## 0.8.0 → 0.8.1

Normal patch upgrade. v0.8.1 makes Jev aware of Hermes `<memory-context>` fences so recalled background can be scored separately from the user's actual current-turn words. Existing vault content and configuration remain compatible.

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.7.0 → 0.8.0

Normal in-place upgrade. v0.8.0 adds the optional Jev semantic context gate after the existing request compiler and deterministic context compactor. Jev is off by default, so an existing 0.7.0 installation keeps its previous behavior until you explicitly enable Jev and supply a TypeSafe API key.

All existing reduction paths remain active when Jev is enabled. Existing vault content and artifact identities remain compatible.

Install the immutable release tag:

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

See [Jev Semantic Context Gate](Jev-Semantic-Context-Gate) before enabling the external API boundary.

## 0.6.0 → 0.7.0

Normal in-place upgrade. v0.7.0 adds the runtime graph-of-skill-graphs used by SkillGate. The graph starts empty and is populated from the current host's installed skills; skill contents remain local and outside provider-visible requests. Existing vault content and artifact identities remain compatible.

## 0.5.2 → 0.6.0

Normal in-place upgrade. v0.6.0 adds component-level request attribution and fail-open SkillGate routing. Existing vault content remains valid. SkillGate has no default count cap: all skills above the relevance threshold survive, while filtered skills remain available through `skills_list` and `skill_view`.

## 0.5.1 → 0.5.2

v0.5.2 adds persistent tokenizer-aware savings accounting and makes `tiktoken` a default dependency. Existing vault data remains compatible; upgrade the package in place and start a new agent session.

## 0.5.0 → 0.5.1

v0.5.1 is an in-place hardening release. Artifact identity remains compatible. Existing vaults are opened with additive schema management for temporal snapshots and vault metadata.

Key behavior changes include bounded retention, recovery-safe GC, Unicode search, async temporal parity, cwd-aware rewrite caching, and hardened measurement/security behavior.

Install the immutable release tag:

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"

hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

Start a fresh session and verify `/token-terminator status`.

## From RTK Hermes Plus 0.2.0

Uninstall the old distribution first. Do not leave `rtk-hermes-plus` and `token-terminator` installed together because they share the `rtk_hermes_plus` Python package.

Legacy recovery files are not automatically copied into the content-addressed vault.

## Rollback

Package uninstall does not erase the private Token Terminator data directory. Back it up or remove it separately if that is your intent.

For the detailed pre-change checklist, rollback commands, and compatibility boundary, use the repository's `MIGRATION.md` as the authoritative operational document.
