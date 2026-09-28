# Configuration

Configuration uses `TOKEN_TERMINATOR_*` environment variables. Legacy `RTK_HERMES_PLUS_*` aliases are compatibility fallbacks for the migration window; the Token Terminator namespace wins.

## Core

| Variable | Default | Meaning |
|---|---:|---|
| `TOKEN_TERMINATOR_ENABLED` | `true` | Master behavior gate |
| `TOKEN_TERMINATOR_MODE` | `balanced` | Runtime mode |
| `TOKEN_TERMINATOR_BACKENDS` | `local` | Allowed terminal backends or `all` |
| `TOKEN_TERMINATOR_TIMEOUT_MS` | `500` | RTK helper deadline |
| `TOKEN_TERMINATOR_RTK_PATH` | empty | Pin the RTK executable instead of PATH discovery |
| `TOKEN_TERMINATOR_EXCLUDE` | empty | Command prefixes never rewritten |
| `TOKEN_TERMINATOR_PYTEST_GUARD` | `true` | Avoid RTK pytest double-quiet edge cases |

## Rewrite cache

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_CACHE_TTL` | `600` seconds |
| `TOKEN_TERMINATOR_CACHE_SIZE` | `512` |

Rewrite identity includes the canonical working directory plus command, so identical command text in two repositories does not share an unsafe cached decision.

## Temporal delta

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_TEMPORAL_DELTA` | `true` |
| `TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS` | `2000` |
| `TOKEN_TERMINATOR_TEMPORAL_SCOPE` | `session` |

Scope may be `session` or `workspace`.

## Native compression

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_NATIVE_MIN_CHARS` | `12000` |
| `TOKEN_TERMINATOR_NATIVE_MAX_CHARS` | `8000` |

## Vault and recovery

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_DB_PATH` | `<HERMES_HOME>/token-terminator/artifacts.sqlite3` |
| `TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS` | `8000` |
| `TOKEN_TERMINATOR_MAX_ARTIFACT_CHARS` | `2000000` |
| `TOKEN_TERMINATOR_VAULT_MAX_BYTES` | `536870912` |
| `TOKEN_TERMINATOR_VAULT_HIGH_WATER_PCT` | `90` |
| `TOKEN_TERMINATOR_VAULT_LOW_WATER_PCT` | `80` |
| `TOKEN_TERMINATOR_INLINE_LEASES` | `1` |
| `TOKEN_TERMINATOR_MAX_PAGE_CHARS` | `20000` |
| `TOKEN_TERMINATOR_MAX_SEARCH_RESULTS` | `50` |

High-water retention can reclaim abandoned artifacts, but artifacts already referenced by accepted recovery receipts/exposures or active temporal state are protected.

## Context compaction

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_CONTEXT_COMPACTION` | `true` |
| `TOKEN_TERMINATOR_CONTEXT_MIN_VAULT_CHARS` | `4000` |
| `TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS` | `6` |
| `TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS` | `5` |
| `TOKEN_TERMINATOR_WORKING_GRAPH_CHARS` | `0` |

The collapse window must be disabled (`0`) or be at least as large as the fully-inline recent-turn window. Direct `Config(...)` construction rejects an invalid pair; environment loading clamps it to a safe boundary.

## Jev semantic context gate

Jev is **disabled by default** and does not replace any existing reduction path. It runs after the deterministic compiler/compactor.

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_JEV` | `false` |
| `TOKEN_TERMINATOR_JEV_PROVIDER` | `auto` |
| `OPENROUTER_API_KEY` | empty; used for OpenRouter |
| `TYPESAFE_API_KEY` | empty; used for direct TypeSafe |
| `TOKEN_TERMINATOR_JEV_API_KEY` | deprecated direct-TypeSafe compatibility alias |
| `TOKEN_TERMINATOR_JEV_MODEL` | provider default (`~typesafe/jev-latest` via OpenRouter, `jev-latest` direct) |
| `TOKEN_TERMINATOR_JEV_TIMEOUT_MS` | `1500` |
| `TOKEN_TERMINATOR_JEV_RELEVANCE_THRESHOLD` | `0.15` |
| `TOKEN_TERMINATOR_JEV_MIN_MESSAGE_CHARS` | `600` |
| `TOKEN_TERMINATOR_JEV_MAX_CANDIDATES` | `12` |
| `TOKEN_TERMINATOR_JEV_MAX_CANDIDATE_CHARS` | `12000` |
| `TOKEN_TERMINATOR_JEV_MAX_STATE_CHARS` | `60000` |

A candidate prior message is compacted only when both Jev's relevance and guard probabilities fall below the threshold, the exact content has been vaulted and verified, and the full provider request remains smaller. Exact-token measurement can veto a character-saving Jev candidate.

The API key is read from environment only and is never returned by `/token-terminator status`. See [Jev Semantic Context Gate](Jev-Semantic-Context-Gate).

## Context IR

```bash
export TOKEN_TERMINATOR_CONTEXT_IR=true
# Optional; keep using ONE existing Jev route/key:
export TOKEN_TERMINATOR_JEV=true
# TOKEN_TERMINATOR_JEV_PROVIDER=auto|openrouter|typesafe
```

No new API key is needed. IR itself makes no network calls. With Jev disabled or unconfigured, IR still performs local guarded format optimization. With Jev enabled, IR requires valid scores for each candidate, reusing the same batched provider call. OpenRouter uses `OPENROUTER_API_KEY`; direct TypeSafe uses `TYPESAFE_API_KEY`. Provider/model selection is unchanged.

| Setting | Default | Hard bound / behavior |
|---|---:|---|
| `TOKEN_TERMINATOR_CONTEXT_IR` | `false` | Also requires compiler-enabled `balanced` or `aggressive` mode |
| `TOKEN_TERMINATOR_CONTEXT_IR_MIN_CHARS` | `600` | Lower candidate size bound |
| `TOKEN_TERMINATOR_CONTEXT_IR_MAX_CHARS` | `64000` | Maximum `500000`; larger sources are skipped, not truncated |
| `TOKEN_TERMINATOR_CONTEXT_IR_MAX_MESSAGES` | `8` | Maximum `64` candidate compilations per request |
| `TOKEN_TERMINATOR_CONTEXT_IR_MAX_EVALUATIONS` | `24` | Maximum `192` complete-request format evaluations |

Direct `Config(...)` construction rejects invalid limits; environment loading clamps limits safely. Sources are additionally bounded to 1,024 records/lines and 32 scalar fields per record. Existing Jev candidate/state limits still apply. With Jev enabled, a source too large to score is not silently given a guessed score; IR skips it.

The existing `TOKEN_TERMINATOR_TOKENIZER_JSON` and `TOKEN_TERMINATOR_TIKTOKEN_ENCODING` settings remain available. Use the actual target tokenizer. An unrecognized model without a configured tokenizer, disabled token budget, or tokenizer failure leaves the request unchanged at the IR stage. There is **no character-only IR fallback**.

See [Context IR](Context-IR) for formats, provenance and the strict whole-request acceptance gate.

## Token budgeting

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_TOKEN_BUDGET` | `true` |
| `TOKEN_TERMINATOR_TOKENIZER_JSON` | empty |
| `TOKEN_TERMINATOR_TIKTOKEN_ENCODING` | empty |
| `TOKEN_TERMINATOR_CONTEXT_LIMIT_TOKENS` | `0` |
| `TOKEN_TERMINATOR_OUTPUT_RESERVE_TOKENS` | `4096` |
| `TOKEN_TERMINATOR_TOKEN_SAFETY_MARGIN` | `512` |

A context limit is for reporting/acceptance headroom. It does **not** authorize silent truncation.

## Ledger

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_LEDGER` | `true` |
| `TOKEN_TERMINATOR_LEDGER_PATH` | `<HERMES_HOME>/token-terminator/experiments.sqlite3` |
| `TOKEN_TERMINATOR_STATE_DB` | Hermes `state.db` |
| `TOKEN_TERMINATOR_EXPERIMENT` | `default` |

Use `/token-terminator status` after changing configuration and start a fresh host session where required.


### Jev provider selection

`TOKEN_TERMINATOR_JEV_PROVIDER` accepts `auto`, `openrouter`, or `typesafe`. Auto mode prefers `OPENROUTER_API_KEY` when present and otherwise uses `TYPESAFE_API_KEY`. If both keys exist, OpenRouter is selected. You never need both keys for one Jev call.

## v0.10.0 selectable ContextEngine (candidate)

Explicit selection: `context.engine: token-terminator`; also enable the general
`token-terminator` plugin for final middleware. Run the candidate's
`token-terminator install-context-engine` first, preserve other plugin selections,
allow the `context_engine` toolset where restricted, then restart. Existing
OpenRouter/TypeSafe keys and JEV/IR flags are unchanged.

| Variable | Default | Range |
|---|---:|---:|
| `TOKEN_TERMINATOR_ENGINE_MAX_BATCHES` | 2 | 1–8 |
| `TOKEN_TERMINATOR_ENGINE_PROTECT_LAST` | 6 messages | 1–64 |
| `TOKEN_TERMINATOR_ENGINE_REGION_CHARS` | 8000 | 256–64000 |
| `TOKEN_TERMINATOR_ENGINE_RECALL_SOURCES` | 3 | 0–16 |
| `TOKEN_TERMINATOR_ENGINE_SEARCH_SOURCES` | 10000 | 1–100000 |

The existing JEV candidate/body/time limits also apply; the complete outbound body
is bounded. Missing/uncertain scores leave evidence inline. Search-bound/capacity
failures are explicit, not newest-only truncation. ContextEngine acceptance always
requires an exact target tokenizer; character fallback is not sufficient.

See [Context Engine](Context-Engine) for installation, retention and provider limits.
