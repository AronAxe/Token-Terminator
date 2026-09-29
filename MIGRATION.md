# Migration to Token Terminator 0.11.0

## Optional learned policy

v0.10.0 was not published; its engine/scope changes are included in this v0.11.0
release. Learned mode defaults to off and does not require
a database migration. Install `[learning]` only where fitting models, not on every
Hermes runtime. See [the data/training/approval workflow](docs/LEARNED_POLICY.md).
To activate, select TT as ContextEngine, review an evaluated policy, pin its local
path and SHA-256, start with shadow, then explicitly select active and restart.
Scorer and generation targets must match the evaluated identities. Training never
changes the running policy, exports the vault or overwrites previous artifacts.
Set `TOKEN_TERMINATOR_LEARNED_POLICY_MODE=off` and restart to disable this layer;
keep the vault and referenced originals. A corrupt approved active policy preserves
history rather than falling back silently to semantic pruning.

## Call-scope safety update

Native Hermes main turns are authorized by the registered adapter; installation
and engine selection are unchanged. Generic Python/async adapters must now pass
out-of-band `request_purpose="conversation"` for their actual generation route.
Bare unscoped calls and explicit internal/service calls return `None` unchanged.
Do not propagate conversation authorization into embedding/rerank/helper work.
JEV final chat targets preserve history by default; custom aliases can set
`TOKEN_TERMINATOR_CHAT_TARGET_POLICY=preserve`. See
[the scoped behavior and hard-limit boundary](docs/CALL_SCOPE_REVIEW.md).


## Upgrade from v0.9.0

Install the `v0.11.0` tag using the Python environment that runs Hermes:

```bash
python -m pip install --upgrade \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.11.0'
python -m rtk_hermes_plus.cli install-context-engine
```

Follow [the ContextEngine guide](docs/CONTEXT_ENGINE.md). Existing released tags are
unchanged. Package installation, plugin enablement, engine selection, Desktop
activation and learned-policy approval are separate actions; none silently enables
the others.

Explicitly select `context.engine: token-terminator` and enable the generic TT
middleware plugin. Do not leave LCM selected upstream. The existing JEV provider
and keys remain valid; IR and JEV retain their own opt-in flags. Restart the host.
The installer does not edit config, touch LCM, or change Hermes core files.

The additive `tt_context_sources` table and pinned ordinary artifacts share the
existing vault. Back it up before changing packages. Session reset intentionally
does not delete backing evidence. Retention is manual and capacity failures pass
through rather than pruning pinned history. No import of an external LCM archive
is implemented; previously unavailable originals cannot be reconstructed.

Rollback: select the installed `lcm` engine or `compressor`, restart, and keep the
generic TT plugin enabled for middleware-only operation. For package rollback,
disable the Desktop half and remove only the six **managed** adapter files
listed in [the installation guide](docs/CONTEXT_ENGINE.md) before reinstalling
v0.9.0; leave unrelated files untouched. The old package does not export the new
engine or dashboard backend. Restart the gateway. Do not delete the vault.
Use `TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS=0` when exact old dialogue is
required in legacy middleware mode. Existing schema version 2 remains readable;
the new catalog does not change ordinary artifact identifiers or recovery actions.

---

# Migration and rollback: 0.2.0 / 0.4.0 / 0.5.x / 0.6.0 / 0.7.0 / 0.8.x → 0.9.0

Token Terminator 0.9.0 supersedes Token Terminator 0.8.2 and replaces the older RTK Hermes Plus 0.2.0 distribution. The Python import package remains `rtk_hermes_plus`; `token-terminator` and `rtk-hermes-plus` must not coexist because both own that package.

## 0.8.2 → 0.9.0

Context IR is an optional local stage after the existing deterministic pipeline and Jev. It is OFF by default. Set `TOKEN_TERMINATOR_CONTEXT_IR=true` to enable guarded format optimization with a measured tokenizer and provider-visible recovery tool, in the existing `balanced` or `aggressive` modes.

No new API key or database schema is required. OpenRouter/direct TypeSafe configuration remains valid. Jev gains salience only when IR is on; no extra batch call is added. With IR on, the entire current user message, including memory fences, stays untouched. Missing scores cannot authorize compression.

After the v0.9.0 release is published, install its immutable tag with `<hermes-python> -m pip install --upgrade 'git+https://github.com/AronAxe/Token-Terminator.git@v0.9.0'`.

Disable only IR by unsetting its variable or setting it to `false`, then restarting the host. Roll back the package by reinstalling v0.8.2. Schema version 2 and ordinary artifact IDs/actions are retained. Do not delete the vault while transcripts reference it. Corrupted content now raises an error rather than being returned as exact evidence.

See [Context IR](docs/CONTEXT_IR.md) for limits and the canonical-request measurement boundary. The offline benchmark is not a live-model non-inferiority result.

## 0.8.1 → 0.8.2

v0.8.2 corrects the Jev provider boundary. Jev can now use either OpenRouter's Decisions API or TypeSafe directly.

The default is `TOKEN_TERMINATOR_JEV_PROVIDER=auto`:
- if `OPENROUTER_API_KEY` exists, OpenRouter is used;
- otherwise, if `TYPESAFE_API_KEY` exists, TypeSafe is used directly;
- if both exist, OpenRouter wins;
- set `TOKEN_TERMINATOR_JEV_PROVIDER=openrouter` or `typesafe` to force a route.

No user needs two keys. The old `TOKEN_TERMINATOR_JEV_API_KEY` remains only as a temporary direct-TypeSafe compatibility alias.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.2'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.8.0 → 0.8.1

v0.8.1 is a patch upgrade for Hermes memory-provider integration. Hermes appends recalled memory to the current user message inside `<memory-context>` fences. Token Terminator now separates those fenced blocks from the user's actual request before Jev scoring, so Hindsight/other recalled background can participate in semantic routing without making the user's own words removable.

Jev remains optional and fail-open. Existing v0.8.0 settings and vault data are compatible.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

## 0.7.0 → 0.8.0

v0.8.0 is a normal in-place upgrade. It adds an optional TypeSafe Jev semantic context gate **after** the existing Token Terminator request compiler and deterministic context compactor. The existing RTK, temporal, native-compression, SkillGate, vault, recovery, and tokenizer-aware paths remain active whether Jev is enabled or not.

Jev is disabled by default. Existing installations therefore preserve 0.7.0 behavior unless you explicitly set `TOKEN_TERMINATOR_JEV=true` and provide `TOKEN_TERMINATOR_JEV_API_KEY` or `TYPESAFE_API_KEY`. The API key is environment-only and is not persisted or shown by status.

When enabled, bounded prior plain-text user/assistant candidates and the current user request are sent to TypeSafe for relevance/guard probabilities. System/developer/tool messages, structured content, and the current user turn as a removal candidate are excluded. Any candidate actually removed from provider context is written to the exact local vault first.

Install the immutable release tag:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.0'
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

| Concern | RTK Hermes Plus 0.2.0 | Token Terminator 0.8.2 |
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
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.2'
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

- plugin key is `token-terminator` and version is `0.8.2`;
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

## Dashboard / Desktop addition to v0.11.0

`token-terminator dashboard` serves localhost:7474 when explicitly started.
`token-terminator install-dashboard` (or re-running `install-context-engine`)
adds the managed Desktop status contribution and backend files; it does not
change the selected engine or enabled-plugin configuration. Restart the gateway
for new backend routes and enable the Desktop half separately. See
[the complete guide](docs/DASHBOARD.md) for root discovery, custom paths and pricing.

Hermes task-local profile home now takes precedence over the launch environment.
This fixes new default vault/ledger locations for multiplexed profile runtimes;
explicit path overrides are unchanged. Historical shared stores are not copied,
split or deleted. Contradictory profile attribution is displayed as unavailable
rather than guessed. Keep prior vaults for recovery and map custom stores
explicitly in local `dashboard.json`. Set no new API keys. Stopping the dashboard
and disabling its Desktop half removes UI without changing the reducer policy.
