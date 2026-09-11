# Changelog

## 0.5.0 - 2026-09-11

- Added stateful temporal delta compression for repeated terminal observations. Commands always execute; the current exact output is vaulted and verified before a smaller diff may replace it.
- Added session-scoped terminal baselines keyed by command, working directory, and backend, with exact current and previous artifact references in every accepted delta.
- Added model-aware token budgeting with optional Hugging Face `tokenizer.json` and tiktoken adapters, character fallback, configurable output reservation, and configurable context safety margin.
- Added a tokenizer acceptance gate on request compilation and conversation compaction so a character-saving candidate is rejected when it expands under the active tokenizer.
- Rolled back lease exposure claims when a compiler candidate fails the tokenizer gate, preventing a rejected optimization from consuming an inline-evidence lease.
- Added deterministic multiresolution artifact recovery through `artifact_peek` and `artifact_find`; `artifact_get` remains the immutable exact-recovery path.
- Kept tokenizers optional through the `token-budget` extra and retained the dependency-light Python core when exact token alignment is not configured.
- Added focused v0.5 invariant tests for terminal deltas, exact recovery, layered views, tokenizer headroom, and lease rollback.
- Deferred a Rust/PyO3 accelerator until profiling identifies a material hot path, preserving the current portable install and fail-open fallback behavior.

## 0.4.0 - 2026-08-25

- Added an `AsyncRuntime` façade and reusable thread-safe `CancellationToken` without changing the synchronous runtime API.
- Added cancellable asyncio RTK command rewriting and aggressive reads that kill and reap subprocesses on task or token cancellation.
- Enabled WAL-backed concurrent artifact-vault access and added deterministic thread/process contention and lease coverage.
- Retried transient SQLite lock races during concurrent multi-process WAL initialization.

## 0.3.1 - 2026-08-24

- Kept collapsed-turn summaries inside the first retained user message so strict provider role sequencing remains valid.
- Stripped internal `_tt_*` metadata before provider dispatch while preserving caller request immutability.
- Added schema-2 telemetry for compiler, compactor, and measured end-to-end savings with exact algebra and one durable row per request identity.
- Made measured retries monotonic and invalidated newer fields when an original 0.3.0 writer updates a row.
- Hardened fail-open accounting, release-version checks, and the installed-wheel Hermes smoke test.

## 0.3.0 - 2026-08-17

- Renamed the public distribution, Hermes plugin, CLI, slash command, environment namespace, and repository to **Token Terminator**.
- Consolidated terminal rewriting, native result compression, exact recovery, deduplication, request compilation, and savings measurement into one plugin.
- Replaced rotating recovery files with one content-addressed SQLite artifact vault.
- Required successful exact write/read-back before any native result can be replaced.
- Added same-request duplicate collapse, cross-request evidence leases, and compact recovery receipts.
- Added final `llm_request` compilation for chat-completions and Responses-style requests without mutating caller requests or persisted Hermes transcripts.
- Added one bounded `token_terminator` model tool for exact artifact recovery, private search, status, and optional working-state operations.
- Added an optional bounded working-state selector, disabled by default and accepted only when the complete provider request remains strictly smaller.
- Kept LCM as Hermes' context engine; Token Terminator does not register or replace a context engine.
- Added per-artifact and total-vault capacity limits, schema/version checks, short-lived SQLite transactions, atomic migrations, idempotent event replay, and bounded domain-layer reads.
- Added request-level metrics, release containment checks, installed-wheel Hermes smoke coverage, and a deterministic `o200k_base` structural benchmark.
- Added one-release compatibility fallbacks for legacy `RTK_HERMES_PLUS_*` environment variables. New `TOKEN_TERMINATOR_*` values take precedence.

## 0.2.0 - 2026-08-11

- Added a `native` mode that compresses Hermes-native search/process results without registering terminal middleware or invoking RTK.
- Added a private durable experiment ledger backed by Hermes' canonical session token and cost accounting.
- Added `/rtk-plus compare [mode-a mode-b]` with per-session mean/median totals and paired-turn deltas for repeated prompts on the same model.
- Kept actual, Hermes-estimated, and optional API-equivalent costs separate; subscription/OAuth routes remain `$0` actual marginal cost.
- Added immutable session mode tags, resumed-session baselines, and automatic exclusion of sessions contaminated by mode or model changes.
- Recorded compression, rewrite, and recovery-read counts without storing commands, prompts, or tool contents.
- Made the default-home and recovery-permission tests portable to Windows.
- Added a Windows CI job and documented Windows ACL semantics.

## 0.1.0 - 2026-08-10

- Added modern Hermes `tool_request` middleware integration with legacy hook fallback.
- Added cached RTK terminal rewriting with local-backend defaults.
- Added balanced native `search_files` and `process` result compression.
- Added opt-in aggressive `read_file` structure compression through RTK.
- Added private rotating full-output recovery files.
- Added a guard for RTK's pytest double-quiet misreporting edge case.
- Added process-local token-savings and rewrite metrics without content retention.
