# Migration and Rollback

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
