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
