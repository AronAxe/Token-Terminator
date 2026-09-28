# Token Terminator ContextEngine — v0.11.0 candidate

**Unreleased, experimental, explicit selection only.** The v0.9.0 release remains
unchanged. No Hermes core files, live profiles, LCM database, main branch, release
tag or registry publication is modified by installation of this adapter.

## Two modes, one context owner

```text
Middleware (unchanged default):
  host context engine -> TT compiler/compactor + SkillGate -> optional JEV -> optional IR -> provider

Selected ContextEngine:
  full available conversation -> TT exact session history
  -> bounded JEV relevance/guard/salience -> exact active evidence / recovery receipts
  -> existing TT compiler + SkillGate + tool vaulting -> existing Context IR
  -> strict complete-request tokenizer AND character gate -> provider
```

Selection uses the supported user-directory `ContextEngine` plugin API. The class
inherits the real Hermes `agent.context_engine.ContextEngine` ABC; it is not a
replacement `ContextCompressor` monkey-patch. Hermes constructs one selected
engine. Selecting TT excludes the normal built-in compressor and a separately
selected LCM engine. Merely enabling the generic TT plugin does **not** select it.

The supported hooks were inspected and exercised against upstream Hermes commit
[`801a9022a742562a3c4578c0d8dd12cfd393fc47`](https://github.com/NousResearch/hermes-agent/tree/801a9022a742562a3c4578c0d8dd12cfd393fc47),
including `agent/context_engine.py`, `agent/agent_init.py`,
`agent/turn_request_assembly.py`, `agent/turn_api_request.py`,
`plugins/context_engine/__init__.py`, and `hermes_cli/plugins_cmd_toggle.py`.
The dashboard's `hermes_cli/web_server_dashboard.py::_merged_plugins_hub` uses
that same context-option discovery helper. The backend option list is tested;
no browser-click/end-to-end visual claim is made.

## Call-scope safety

The final request now requires conversational authorization before using a staged
engine binding. Native auxiliary/delegated roles, service calls and TT-internal
JEV/counting callbacks bypass without altering that binding. Generic adapters
supply `request_purpose="conversation"`; the native Hermes main hook supplies
its existing contract automatically. JEV as the final chat model preserves full
supplied history by default, except measured reversible IR and minimally necessary
budget-pressure selection. See [scope audit, tests and hard-limit limits](CALL_SCOPE_REVIEW.md).

## Install this review build and select it

Use the Python interpreter of the Hermes environment, not an unrelated system
Python. The tag `v0.11.0` does not exist until the owner approves publication.

```bash
git clone --single-branch --branch feat/hermes-context-engine-v0.10.0 \
  https://github.com/AronAxe/Token-Terminator.git
cd Token-Terminator
<hermes-python> -m pip install --upgrade .
<hermes-python> -m rtk_hermes_plus.cli install-context-engine
```

The installer creates only `$HERMES_HOME/plugins/token-terminator/__init__.py` and
`plugin.yaml`. It is idempotent for its managed files and refuses unmanaged-file
or symlink replacement. It does not enable anything or edit `config.yaml`.
`--hermes-home PATH` selects another profile explicitly.

In `hermes plugins`, enable the **token-terminator** general plugin (required for
final request middleware), then choose **token-terminator** (description:
**Token Terminator**) under **Provider Plugins -> Context Engine**. The web
Plugins provider selector can use the same discovered option on the inspected
Hermes build. Equivalent configuration, preserving other enabled plugins:

```yaml
plugins:
  enabled:
    - token-terminator
context:
  engine: token-terminator
```

For profiles that restrict toolsets, include `context_engine` in the allowed
`enabled_toolsets`/platform toolset list. The host gates the engine's recovery
tool by that permission; TT refuses semantic reduction without it.

Enable the existing optional stages in the Hermes process environment:

```bash
export TOKEN_TERMINATOR_MODE=balanced
export TOKEN_TERMINATOR_JEV=true
export TOKEN_TERMINATOR_CONTEXT_IR=true
```

Keep the existing `OPENROUTER_API_KEY` **or** `TYPESAFE_API_KEY` and existing
`TOKEN_TERMINATOR_JEV_PROVIDER` setting. No second key or new endpoint is added.
Restart Hermes/the gateway so it rebuilds the plugin and engine instances.
In that actual session, call `token_terminator_history` with `{"action":"status"}`.
The tool should report `name: token-terminator`; after an eligible request its
`context_engine` status explains acceptance, savings or a safe refusal.
A missing tool means the adapter, selection or toolset permission is not active;
do not infer that selecting a label alone activated reduction.

## Why selection commits at the final middleware boundary

Hermes calls `select_context()` before sanitization, prompt-cache decoration,
tool-schema assembly and provider kwargs. Measuring only that message list
cannot prove the complete request is smaller. TT therefore stages full exact
history in the ContextEngine hook and returns `None` (no early rewrite). A
turn-scoped `ContextVar` carries **engine identity, session and generation** to
the supported `llm_request` middleware. That boundary performs JEV selection and
IR, including actual recovery schemas and actual vault IDs, then commits only a
strict decrease against the complete incoming provider envelope.

No other context engine has assembled a lossy summary upstream in this mode.
The host transcript remains exact and unmodified; request-only selection is an
explicitly supported Hermes engine operation. Provider retries retain the same
engine ownership and exact-query score cache until lifecycle completion; they
do not silently fall back to legacy age-collapse. TT's async facade propagates
the context binding into its executor. Separate agent clones do not share
session state, mutable caches or locks.

The gate measures canonical request JSON under the selected target tokenizer,
**not hidden provider framing or billed tokens**. It additionally requires a
character decrease. Without a usable exact tokenizer, the engine passes through
without calling JEV; there is no `chars/4` acceptance fallback. Configure the
actual target's `TOKEN_TERMINATOR_TOKENIZER_JSON` or an appropriate exact
counter when automatic tiktoken model lookup is not applicable. Do not select
an unrelated tokenizer merely to make the gate report savings.

The guarantee ends at TT's middleware output. Another plugin or transport that
rewrites the request afterward needs its own final measurement. Stateful
`previous_response_id`/`conversation` requests are not accepted as complete
locally measurable history.

## Exact history and rediscovery

The existing private vault stores canonical JSON of each original message,
including its role and metadata. A small additive `tt_context_sources` catalog
indexes sources by session, source hash, observed snapshot and ordinal. Original
text, quotes, code and values round-trip exactly; insignificant JSON serialization
whitespace is not an input-message byte-stream promise. Identical snapshots share
backing evidence; the untouched host transcript retains occurrence multiplicity.
The catalog does not infer global chronology or graph relations.

Every new source is pinned in the same transaction that inserts it and is read
back before a usable reference is produced. Missing/corrupt backing evidence
prevents acceptance. Old omission does not retire a source. Every complete
incoming transcript is reconsidered; a regression test returns to an omitted
fact after fifty distracting turns. For resumed/tail-only transcripts, bounded
literal lexical search over the full session catalog can reinsert exact matching
sources as **historical evidence**, never as system/developer authority. This is
not semantic embedding search or a guarantee that arbitrary paraphrases find
sources absent from the host transcript. `token_terminator_history find` exposes
all matching bounded-catalog evidence, including omitted sources.

The tool supports `find`, paginated `get`, and `status`. `get` returns exact
message JSON, original roles, page offsets and a continuation offset. Search
hits are snippets, not substitutes for exact `get`. Existing `token_terminator`
artifact recovery and IR expansion remain available. New history-tool lookups
require membership in the current session; the older general vault tool is not
redefined as a multi-tenant access-control system.

No text is rewritten into guessed graph triples. JEV scores are selection signals,
not assertions that a source is true. System/developer/tool authority, current user
wording including memory fences, recent messages and deterministic code/quote/
number/constraint guards remain protected. Unrecognized structured/provider
messages stay unchanged. Selected structured evidence may use existing lossless
IR with source-bound attention; high guard/salience retains explicit values.

## Cost and work limits

| Environment variable | Default | Bound |
|---|---:|---:|
| `TOKEN_TERMINATOR_ENGINE_MAX_BATCHES` | 2 | 1–8 |
| `TOKEN_TERMINATOR_ENGINE_PROTECT_LAST` | 6 messages | 1–64 |
| `TOKEN_TERMINATOR_ENGINE_REGION_CHARS` | 8000 | 256–64000 |
| `TOKEN_TERMINATOR_ENGINE_RECALL_SOURCES` | 3 | 0–16 |
| `TOKEN_TERMINATOR_ENGINE_SEARCH_SOURCES` | 10000 snapshots | 1–100000 |

Existing JEV settings still bound candidates per batch (12), candidate characters
(12000), complete serialized body characters (60000), timeout (1500 ms), model,
provider and threshold. Structured records get separate exact regions. Oversize
single messages can stand alone within the per-candidate cap; oversized or
unscored material remains inline. Relevance, guard and salience are requested in
one batch, not three calls or one call per span. At default limits, two sequential
provider timeouts can add roughly three seconds plus local work; the body cap is
not a dollar-spend ceiling.

At most 32 complete valid batch responses are cached in memory per engine. Cache
keys include exact source regions, query and recent conversational referents.
Session/model resets clear the cache. Identical retries need no repeated JEV calls;
changed queries/sources do. A malformed entire response or transport failure rolls
back all semantic edits; invalid/missing individual probabilities never authorize
omission. No retry loop or generative summary fallback is added.

## Important limits and migration

This is a conservative request-only engine, not an unbounded archival database or
a guarantee that arbitrary history fits the target window. Protected/unscored
history may exceed the available budget. In that case, preserving evidence takes
priority: a request can remain too large and the host/provider can refuse it.
Hermes retains the full in-memory transcript; local scan and storage costs grow.
Manual `/compress` archives but does not destructively shorten that transcript.

Routes that hard-reject oversized context **before** `llm_request` (including the
inspected Ollama preflight path), stateful Codex/native-provider compaction and
unverified middleware orderings are not certified LCM replacements by this release.
Do not enable an independent native summarizer alongside TT and assume TT owns it.
The tested boundary is stateless complete requests on the pinned Hermes plugin API.

Pins intentionally survive normal pruning/reset/restart, so archived evidence can
fill the configured vault. Capacity/search-bound failures are explicit and fail
open; this version adds no automatic evidence deletion/unpin policy. Back up the
vault and plan retention before long-running use. A vault deletion breaks recovery.
Switching from LCM cannot reconstruct material that is no longer present in the
available transcript; importing an external LCM archive is not implemented.

To return to middleware-only operation, select `compressor` or the installed LCM
engine and restart, leaving the generic TT plugin enabled. For exact-history
workloads in legacy middleware mode, set
`TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS=0`: the historical deterministic
age-collapse path emits previews, not a full archival transcript. This behavior
is preserved for compatibility, not used by the new engine.

See [benchmark report](../benchmarks/context_engine/README.md), [security](../SECURITY.md)
and [migration](../MIGRATION.md). Live JEV accuracy/cost and real-model answer
quality are not established by the offline fixture tests.
