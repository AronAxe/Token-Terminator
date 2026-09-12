# Migration and rollback: 0.2.0 / 0.4.0 / 0.5.0 → 0.5.1

Token Terminator 0.5.1 supersedes Token Terminator 0.5.0 and replaces the older RTK Hermes Plus 0.2.0 distribution. Upgrading from 0.4.0 is an ordinary package replacement. Migrating from 0.2.0 is a distribution/plugin rename as well as a package replacement; the two distributions must not coexist.


## 0.5.0 → 0.5.1 hardening

0.5.1 is an in-place hardening upgrade. It keeps the content-addressed artifact identity and schema-2 compatibility, adds schema-managed temporal snapshots and additive vault metadata, introduces bounded retention before the configured vault capacity is exhausted, and makes Unicode search, async temporal reduction, rewrite caching, measurement, and security behavior consistent. Existing exact artifacts remain valid; retention may prune old unprotected artifacts only after the configured high-water mark is crossed.

## Boundary

| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.5.0 |
|---|---|---|
| Distribution | `rtk-hermes-plus` | `token-terminator` |
| Hermes plugin key | `rtk-plus` | `token-terminator` |
| Slash command | `/rtk-plus` | `/token-terminator` |
| Environment prefix | `RTK_HERMES_PLUS_*` | `TOKEN_TERMINATOR_*` |
| Python import package | `rtk_hermes_plus` | `rtk_hermes_plus` |
| Private data root | legacy `rtk-plus` paths | `<HERMES_HOME>/token-terminator/` |
| Hermes context engine | unchanged | unchanged |

Both distributions own the same Python import package. They must not coexist.

Token Terminator does not migrate or delete 0.2.0 recovery files or experiment data automatically. It uses the content-addressed artifact vault introduced by Token Terminator 0.3.0. Existing 0.4.0 vaults remain usable; 0.5.0 adds temporal-terminal baseline state without replacing exact artifacts or changing their content-addressed identity. Legacy environment aliases remain compatibility fallbacks, with `TOKEN_TERMINATOR_*` taking precedence.

## What 0.5.0 adds over 0.4.0

- temporal delta compression for repeated large terminal observations in `balanced` and `aggressive` modes; commands still execute every time and the current exact output is vaulted before any delta is emitted;
- optional model-aware token acceptance through tiktoken or an exact Hugging Face `tokenizer.json`, with character-based fail-open fallback;
- explicit output reservation and context safety margin rather than filling a model context window to its edge;
- deterministic `artifact_peek` and `artifact_find` recovery views while `artifact_get` remains the immutable exact-recovery path;
- lease-claim rollback when a character-saving compiler candidate is rejected by the active tokenizer.

The tokenizer packages are optional. Install them only when exact alignment is useful for the models you route through Token Terminator.

## Pre-change record

Run these before the maintenance window and retain the output:

```bash
hermes plugins list
<hermes-python> -m pip show rtk-hermes-plus token-terminator
```

Record any `RTK_HERMES_PLUS_*` or `TOKEN_TERMINATOR_*` values you intend to retain. Do not copy legacy rotating recovery files into `artifacts.sqlite3`; the formats and retention models are different.

## Install and activate

Perform the package replacement while no Hermes process is importing `rtk_hermes_plus`.

```bash
hermes plugins disable rtk-plus
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y rtk-hermes-plus token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

If you want exact tokenizer alignment, install one or both optional backends in the same environment:

```bash
<hermes-python> -m pip install tiktoken tokenizers
```

If a release tag cannot be resolved, use the reviewed release commit SHA instead. Never install an unpinned moving branch into a production profile.

Commence a new Hermes session after enablement. Do not run both `rtk-plus` and `token-terminator`, and do not enable another terminal rewrite plugin alongside Token Terminator.

## Post-change verification

Verify:

```text
/token-terminator status
```

- plugin key is `token-terminator` and version is `0.5.0`;
- `vault_available` is `true`;
- the selected mode is correct;
- `temporal_delta` reports whether the feature is enabled and active in the selected mode;
- `token_budget` reports the configured tokenizer/budget state;
- Hermes' existing context engine is still active;
- an ordinary non-compressible tool call behaves unchanged;
- a large supported native result receives an artifact receipt;
- `token_terminator artifact_get` can recover an artifact exactly across pages;
- `artifact_peek` and `artifact_find` provide bounded derived views without changing the exact artifact;
- LCM/history behavior and unrelated plugins remain unchanged.

For a temporal-delta smoke check, run the same large read-only terminal observation twice in one session. The second result may be replaced by a compact no-change/diff receipt only if the provider-visible result is smaller; the command itself must still execute.

The decisive runtime switch is the enabled plugin key. Package installation alone does not activate the plugin for an existing session.

## Roll back to Token Terminator 0.4.0

Disable 0.5.0 first and reinstall the immutable 0.4.0 tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.4.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

The 0.4.0 runtime ignores 0.5.0's additional temporal-baseline table. Exact artifact content remains in the same private vault.

## Roll back to RTK Hermes Plus 0.2.0

To return all the way to the pre-rename implementation, disable Token Terminator and install the immutable 0.2.0 commit:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator rtk-hermes-plus
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@2ef250cca98f691eba82e193bd8c26fd4ab652f4'
hermes plugins enable rtk-plus --no-allow-tool-override
```

Commence a new Hermes session and verify `/rtk-plus status`.

Rollback does not require Hermes core, LCM, transcript, or state-database migration. It also does not delete `<HERMES_HOME>/token-terminator/`; retain that directory for forensic recovery or remove it separately only after confirming it is no longer needed.
