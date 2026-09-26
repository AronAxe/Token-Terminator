# Migration and rollback: 0.2.0 / 0.4.0 / 0.5.x / 0.6.0 / 0.7.0 / 0.8.0 → 0.8.1

Token Terminator 0.8.1 supersedes Token Terminator 0.8.0 and replaces the older RTK Hermes Plus 0.2.0 distribution. The Python import package remains `rtk_hermes_plus`; `token-terminator` and `rtk-hermes-plus` must not coexist because both own that package.

## 0.8.0 → 0.8.1\n\nv0.8.1 is a patch upgrade for Hermes memory-provider integration. Hermes appends recalled memory to the current user message inside `<memory-context>` fences. Token Terminator now separates those fenced blocks from the user's actual request before Jev scoring, so Hindsight/other recalled background can participate in semantic routing without making the user's own words removable.\n\nJev remains optional and fail-open. Existing v0.8.0 settings and vault data are compatible.\n\nInstall the immutable release tag:\n\n```bash\nhermes plugins disable token-terminator\n<hermes-python> -m pip uninstall -y token-terminator\n<hermes-python> -m pip install \\\n  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'\nhermes plugins enable token-terminator --no-allow-tool-override\n```\n\n## 0.7.0 → 0.8.0

v0.8.0 is a normal in-place upgrade. It adds an optional TypeSafe Jev semantic context gate **after** the existing Token Terminator request compiler and deterministic context compactor. The existing RTK, temporal, native-compression, SkillGate, vault, recovery, and tokenizer-aware paths remain active whether Jev is enabled or not.

Jev is disabled by default. Existing installations therefore preserve 0.7.0 behavior unless you explicitly set `TOKEN_TERMINATOR_JEV=true` and provide `TOKEN_TERMINATOR_JEV_API_KEY` or `TYPESAFE_API_KEY`. The API key is environment-only and is not persisted or shown by status.

When enabled, bounded prior plain-text user/assistant candidates and the current user request are sent to TypeSafe for relevance/guard probabilities. System/developer/tool messages, structured content, and the current user turn as a removal candidate are excluded. Any candidate actually removed from provider context is written to the exact local vault first.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.6.0 → 0.7.0

v0.7.0 is a normal in-place upgrade. It adds the runtime graph-of-skill-graphs used by SkillGate. The graph ships empty and is populated only from the current host's installed skills; installed skill contents remain local and are not committed to the repository or injected into provider requests.

Each installed skill is modeled as an outer node with its own internal section/resource graph. Cross-skill traversal follows only source-backed relationships such as `related_skills` and explicit dependencies. Existing vault content, artifact identities, and request-accounting tables remain compatible.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.7.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.5.2 → 0.6.0

v0.6.0 is a normal in-place upgrade. It adds component-level request attribution and SkillGate routing. The artifact vault and content-addressed identities remain compatible; the new attribution table is additive and stores metrics only, not prompt or skill text.

SkillGate has no hard skill-count ceiling by default. It retains every skill above the relevance threshold, runs only when `skills_list` and `skill_view` remain provider-visible, and passes the original request through when routing cannot be proven smaller.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.6.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.5.1 → 0.5.2

v0.5.2 is a normal in-place package upgrade. It adds persistent tokenizer-aware savings accounting, makes `tiktoken` a default dependency, normalizes common provider-qualified OpenAI model IDs for tokenizer lookup, and propagates active model identity into native and temporal savings accounting.

The artifact vault remains compatible. No destructive migration is required, and exact artifacts keep the same content-addressed identities. Character telemetry remains available alongside exact token measurements.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.6.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

Start a new Hermes session after the upgrade. `tiktoken` is installed with Token Terminator; Hugging Face `tokenizers` is only needed when you explicitly configure a local `tokenizer.json`.

## 0.5.0 → 0.5.1 hardening

0.5.1 is an in-place hardening upgrade. It keeps the content-addressed artifact identity and schema-2 compatibility, adds schema-managed temporal snapshots and additive vault metadata, introduces bounded retention before the configured vault capacity is exhausted, and makes Unicode search, async temporal reduction, rewrite caching, measurement, and security behavior consistent. Existing exact artifacts remain valid; retention may prune old unprotected artifacts only after the configured high-water mark is crossed.

## Boundary

| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.8.1 |
|---|---|---|
| Distribution | `rtk-hermes-plus` | `token-terminator` |
| Hermes plugin key | `rtk-plus` | `token-terminator` |
| Slash command | `/rtk-plus` | `/token-terminator` |
| Environment prefix | `RTK_HERMES_PLUS_*` | `TOKEN_TERMINATOR_*` |
| Python import package | `rtk_hermes_plus` | `rtk_hermes_plus` |
| Private data root | legacy `rtk-plus` paths | `<HERMES_HOME>/token-terminator/` |
| Hermes context engine | unchanged | unchanged |

Both distributions own the same Python import package. They must not coexist.

Token Terminator does not migrate or delete 0.2.0 recovery files or experiment data automatically. It uses the content-addressed artifact vault introduced by Token Terminator 0.3.0. Existing 0.4.0+ vaults remain usable. Legacy environment aliases remain compatibility fallbacks, with `TOKEN_TERMINATOR_*` taking precedence.

## What 0.5.0 added over 0.4.0

- temporal delta compression for repeated large terminal observations in `balanced` and `aggressive` modes; commands still execute every time and the current exact output is vaulted before any delta is emitted;
- model-aware token acceptance through tiktoken or an exact Hugging Face `tokenizer.json`, with character-based fail-open fallback;
- explicit output reservation and context safety margin rather than filling a model context window to its edge;
- deterministic `artifact_peek` and `artifact_find` recovery views while `artifact_get` remains the immutable exact-recovery path;
- lease-claim rollback when a character-saving compiler candidate is rejected by the active tokenizer.

## Pre-change record

Run these before a maintenance window and retain the output:

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
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

For a local Hugging Face tokenizer, install the optional backend in the same environment:

```bash
<hermes-python> -m pip install tokenizers
```

If a release tag cannot be resolved, use the reviewed release commit SHA instead. Never install an unpinned moving branch into a production profile.

Commence a new Hermes session after enablement. Do not run both `rtk-plus` and `token-terminator`, and do not enable another terminal rewrite plugin alongside Token Terminator.

## Post-change verification

Verify:

```text
/token-terminator status
```

- plugin key is `token-terminator` and version is `0.8.1`;
- `vault_available` is `true`;
- the selected mode is correct;
- `temporal_delta` reports whether the feature is enabled and active in the selected mode;
- `token_budget` reports the configured tokenizer/budget state;
- `token_accounting` reports exact-tokenizer coverage and measured savings where available;
- `jev` reports only enable/configuration/model limits and never the API key; with Jev disabled it reports `enabled: false`;
- Hermes' existing context engine is still active;
- an ordinary non-compressible tool call behaves unchanged;
- a large supported native result receives an artifact receipt;
- `token_terminator artifact_get` can recover an artifact exactly across pages;
- `artifact_peek` and `artifact_find` provide bounded derived views without changing the exact artifact;
- LCM/history behavior and unrelated plugins remain unchanged.

For a temporal-delta smoke check, run the same large read-only terminal observation twice in one session. The second result may be replaced by a compact no-change/diff receipt only if the provider-visible result is smaller; the command itself must still execute.

## Roll back to Token Terminator 0.5.1

Disable 0.5.2 first and reinstall the immutable 0.5.1 tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

The v0.5.1 runtime ignores the newer token-accounting table. Existing exact artifact content remains in the same private vault.

## Roll back to Token Terminator 0.4.0

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.4.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

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
