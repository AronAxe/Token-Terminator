# Changelog

## 0.11.2 - 2026-10-05

- Added empirically validated GPT-6.1-Sol tokenizer compatibility, without overriding upstream mappings or guessing future model IDs.
- Fixed concurrent TT directory discovery and cross-profile module reuse through an explicit, source-guarded installer repair with exact backup.
- Added non-skipping Sol pipeline and real-loader concurrency CI regressions.
- Preserved call scope, protected context, exact recovery and strict final gates.

## 0.11.1 - 2026-10-04

- Fixed the Hermes live-compression adapter's missing `_coerce_threshold_tokens_cap`
  method and lazy context-window/threshold cache invalidation.
- Reused installed Hermes route metadata and per-model threshold handling; current
  `select_context` budgets refresh the window without resetting retry/usage state.
- Preserved independent cloned-engine configuration, exact recovery, internal-call
  isolation and the existing strict tokenizer acceptance gate.
- Added nine real-Hermes regression cases and corrected their Ruff formatting.
- Updated release/install references and corrected the README's stale context-engine
  FAQ. Rust companion version aligned; its runtime behavior is unchanged.
- Unknown-model tokenizers and the host's plugin-discovery race remain separate
  limitations; publication does not install or restart a running Hermes profile.

## 0.11.0 - 2026-09-29

**Context, learning & observability.** Includes the unshipped 0.10.0 milestone;
the previous published version is 0.9.0. Existing tags are unchanged.

### Context ownership and call-scope safety

- Added an explicitly selectable Hermes ContextEngine through the supported plugin
  API, with exact pinned full-history backing, bounded lexical rediscovery and
  paginated session recovery. Middleware mode remains available; no core patch,
  generative history summarizer or automatic engine switch is required.
- Preserved compiler, SkillGate, native/temporal reduction, vault recovery and
  Context IR. The final complete-request gate requires exact-token and character
  decreases. Retries and async execution retain engine ownership and scoring caches.
- Authorized conversational scope before reduction; embeddings, reranking,
  classifier/helper calls, counting operations and internal JEV bypass unchanged.
  Execution-local guards prevent re-entry. Generic adapters must explicitly pass
  `request_purpose="conversation"` only for actual generation.
- Added conservative history retention for explicitly integrated JEV-backed chat
  wrappers. Native JEV remains a typed-decision service. Protected-history overflow
  is reported without destructive truncation; host/provider enforcement is still needed.

### Learned omission-risk policy

- Added bounded System-2 feature proposal/revision, JEV Noul/Score measurements and
  real CatBoost fitting for omission harm and recovery-token cost. JEV weights stay fixed.
- Added grouped development CV, frozen-before-holdout assessment, exact source hashes
  and generation-target/scorer/schema-bound numeric JSON artifacts. Outcome labels
  require explicit independently labelled experiments, not JEV self-labels.
- Added `off` (default), `shadow` and approved `active` modes. The policy is an extra
  omission veto; it cannot weaken fixed guards, scope, provenance or token acceptance.
- Added `policy-train` replay and consented live modes, bounded calls/data/model sizes
  and create-only private outputs. Extra JEV questions share region batches; shadow
  may double batches. No automatic export, self-training or activation is enabled.
- Kept CatBoost training-only and deployed inference standard-library-only. Policy
  SHA-256 approval hashes cover identical UTF-8 disk bytes on Windows and Unix.

### Observatory and release documentation

- Added loopback `token-terminator dashboard` on port 7474, per-profile/bot filtering,
  input/output separation, exact/fallback coverage, fourteen-day trends and configured
  USD model-rate equivalents. Recorded costs and token-weighted averages stay separate.
- Added the native Hermes Desktop bottom status-bar counter and upward summary popover
  using supported SDK/authenticated backend routes. Managed install does not change
  config or activate the engine; no model call or server auto-start is added.
- Corrected Hermes task-local profile-home precedence. Read-only accounting rejects
  duplicate source mappings and marks mixed/ambiguous historical attribution rather
  than assigning it to the wrong bot. Missing output/financial counterfactuals stay unknown.
- Added scope, exact-history, learning, accounting, security, HTTP, installer and
  cross-platform regressions, plus pinned-Hermes and Chromium dashboard verification.
  Real fitting uses synthetic data in CI; no paid inference or live quality claim.
- Refreshed README release badges/install instructions, architecture and learning-loop
  schematics, wiki navigation, migration guidance and complete release notes.

[Full v0.11.0 release notes](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/releases/v0.11.0.md).

## 0.9.0 - 2026-09-28

- Added experimental **Context IR**, OFF by default: a local compiler after deterministic TT and optional Jev, without replacing native/temporal reduction, SkillGate, compaction, vaults or recovery.
- Added schema-once positional records, typed repeated-string dictionaries and reversible exact-line templates/spans. No invented prose relations, lossy summarizer, new graph architecture or extra API key.
- Reused one Jev batch for relevance/guard/salience; private scores bind to exact source hashes and positions. Missing/malformed probabilities skip candidates; high guard/salience retains explicit values. OpenRouter/direct TypeSafe routing is unchanged.
- Added bounded complete-request format search. IR requires strict actual-tokenizer and character savings including legends, tool schemas and real vault IDs; no tokenizer means no IR. Counts cover canonical request JSON, not hidden provider billing framing.
- Protected current user wording, system/developer/tool authority, code/quotations/values and constraints. With IR enabled, the entire current user message, including memory fences, stays untouched.
- Added atomic source insertion/exposure pinning and source-hash/position/IR validation. Normal exact-recovery reads reject corrupted content; schema version 2 stays rollback-compatible.
- Added content-free IR/Jev timing and provider-reported cost metrics, including Jev calls that do not remove context.
- Added adversarial/regression tests and a reproducible three-arm benchmark with independent visible-data golden answers and exact recovery. Offline results use fixture scores; live Jev economics and LLM quality remain opt-in and unclaimed.
- Updated README, configuration, migration, security, wiki sources and release metadata.

## 0.8.2 - 2026-09-26

- Corrected Jev provider routing: Token Terminator now supports both OpenRouter's Decisions API and direct TypeSafe System One access.
- Added `TOKEN_TERMINATOR_JEV_PROVIDER=auto|openrouter|typesafe`. Auto mode prefers `OPENROUTER_API_KEY` when available and otherwise uses `TYPESAFE_API_KEY`; users never need both keys.
- Changed the OpenRouter default model to `~typesafe/jev-latest` while retaining `jev-latest` for direct TypeSafe access.
- Kept `TOKEN_TERMINATOR_JEV_API_KEY` only as a temporary backward-compatibility alias for direct TypeSafe users from v0.8.0/v0.8.1.
- Added offline endpoint-selection tests for both providers and updated the external-service boundary documentation.

## 0.8.1 - 2026-09-26

- Fixed Jev handling for Hermes memory-provider context: `<memory-context>` blocks appended to the current user message are now separated from the user's actual request and evaluated as background context.
- Preserved the current user's own words verbatim while allowing low-relevance recalled-memory blocks (including Hindsight auto-recall) to be exact-vaulted and replaced with a fenced recovery receipt.
- Added an offline regression test proving the real user request is not sent to the removal path, the fenced memory block remains recoverable exactly, and Jev still fails open.

## 0.8.0 - 2026-09-26

- Added an **optional Jev semantic context gate** after the existing request compiler and deterministic context compactor. Jev augments Token Terminator; it does not replace terminal rewriting, temporal deltas, native compression, SkillGate, vaulting, recovery, or tokenizer-aware acceptance.
- Added one batched TypeSafe System One call over the current user request and bounded prior plain-text user/assistant candidates. Each candidate receives independent relevance and guard probabilities; only candidates below both conservative thresholds are eligible for removal.
- Preserved exact recovery by writing every accepted Jev-reduced message to the content-addressed vault and replacing it with a compact recovery receipt. System/developer/tool messages, tool calls/results, structured content, and the current user turn are never Jev removal candidates.
- Kept Jev strictly opt-in and fail-open. It requires `TOKEN_TERMINATOR_JEV=true` plus `TOKEN_TERMINATOR_JEV_API_KEY` or `TYPESAFE_API_KEY`; no API key is committed, persisted, logged, or returned by status.
- Added character and exact-token veto gates around Jev reductions, bounded candidate/state sizes, a configurable timeout, offline mocked tests, response metrics, and explicit external-data-boundary documentation.
- Added a main-branch release workflow that builds verified Python artifacts and creates the immutable GitHub tag/release; the existing release-triggered Rust publication workflow remains responsible for crates.io.


## 0.7.0 - 2026-09-23

- Added an empty-by-default runtime graph-of-skill-graphs for SkillGate. Each installed skill is an outer node with its own internal section/resource graph; skill contents are discovered locally from the active host rather than shipped in the repository.
- Added a fail-open Hermes skill-document adapter for trusted project, local, external, and plugin skills, plus a host-neutral provider hook for other runtimes.
- SkillGraph routing can now match against installed skill contents, follow explicit transitive `requires` dependencies, and use `related_skills` only as a weak source-backed hint; lexical similarity never creates cross-skill edges.
- Kept private installed skill contents outside provider-visible requests and added synthetic-only privacy/routing tests.

## 0.6.0 - 2026-09-16

- Added content-free component-level request token attribution for instructions, skill catalogs, tool schemas, tool results, the current user turn, prior history, other fields, and request framing, with raw/final token and character totals.
- Added SkillGate routing for Hermes-style `<available_skills>` indexes so irrelevant skill metadata can be removed before the expensive model sees it while omitted skills remain discoverable through `skills_list` and `skill_view`.
- Kept SkillGate fail-open: it runs only when both discovery tools are provider-visible, never rewrites user/tool/history content, preserves caller immutability, and accepts a routed payload only when the complete request is strictly smaller.
- Removed the default SkillGate count ceiling. Every skill above the relevance threshold is retained; `max_skills` is now an explicit opt-in host constraint rather than a Token Terminator default.
- Added a pluggable `(prompt, skill) -> relevance` scorer boundary so a tiny trained/local reranker can replace the deterministic lexical-IDF bootstrap without changing middleware plumbing.
- Updated Python and Rust package metadata, install docs, migration notes, and the source-controlled GitHub Wiki for v0.6.0.

## 0.5.2 - 2026-09-15

- Added durable tokenizer-aware request accounting with exact raw/final/saved token counts, model identity, tokenizer backend provenance, coverage reporting, and persistent per-request metrics.
- Made `tiktoken` a default Python dependency and normalized common provider-qualified OpenAI model IDs so supported models are measured automatically without manual tokenizer configuration.
- Propagated the active session model into native and temporal tool-result accounting so those reductions can be measured with the correct tokenizer instead of silently falling back to characters.
- Kept character counts as the deterministic reduction invariant and audit trail while clearly separating exact-tokenizer savings from explicitly labelled `chars/4` fallback estimates.
- Linked the README to the source-controlled GitHub Wiki and synchronized current install, migration, Rust interoperability, and release documentation for v0.5.2.

## 0.5.1 - 2026-09-12

- Added capacity-managed vault retention with O(1) byte accounting, configurable high/low watermarks, protected temporal baselines, pruning telemetry, and status reporting instead of a permanent hard-wall failure.
- Enforced the context-collapse/inline-window invariant in direct config, environment loading, and the compactor itself; unified the inline-recent default at five turns.
- Added Unicode-correct case-insensitive artifact search using Python `casefold()` through a deterministic SQLite function.
- Keyed RTK rewrite caching by canonical working directory plus command and added `TOKEN_TERMINATOR_RTK_PATH` for explicit executable pinning.
- Restored temporal-delta parity in `AsyncRuntime` through the same v0.5 semantic temporal entry point used synchronously.
- Moved `terminal_snapshots` into vault schema management and protected referenced artifacts from retention pruning.
- Made provider-exposure lease accounting reflect the request actually delivered when character or tokenizer gates reject a candidate.
- Added exact native/temporal token-savings accounting when the configured tokenizer is available; retained and explicitly labelled the chars/4 fallback otherwise.
- Reworked experiment comparison to reject identical modes, aggregate by prompt-fingerprint/model group, report unpaired observations, and include deterministic 95% bootstrap intervals.
- Hardened Windows read-only SQLite URIs, stopped chmodding pre-existing parent directories, corrected recovery-note savings, removed dead/duplicated adapter code, and documented every context-compaction/retention/security control.

## 0.5.0 - 2026-09-11

- Added stateful temporal delta compression for repeated terminal observations. Commands always execute; the current exact output is vaulted and verified before a smaller diff may replace it.
- Added session-scoped terminal baselines keyed by command, working directory, and backend, with exact current and previous artifact references in every accepted delta.
- Added model-aware token budgeting with optional Hugging Face `tokenizer.json` and tiktoken adapters, character fallback, configurable output reservation, and configurable context safety margin.
- Added a tokenizer acceptance gate on request compilation and conversation compaction so a character-saving candidate is rejected when it expands under the active tokenizer.
- Rolled back lease exposure claims when a compiler candidate fails the tokenizer gate, preventing a rejected optimization from consuming an inline-evidence lease.
- Added deterministic multiresolution artifact recovery through `artifact_peek` and `artifact_find`; `artifact_get` remains the immutable exact-recovery path.
- Kept tokenizers optional through the `token-budget` extra and retained the dependency-light Python core when exact token alignment is not configured.
- Added focused v0.5 invariant tests for terminal deltas, exact recovery, layered views, tokenizer headroom, and lease rollback.
- Added the `token-terminator` Rust interoperability crate for vault-compatible artifact identities, digest verification, and the baseline strict-reduction invariant, without making Rust a Python runtime dependency.
- Added dedicated Rust integration documentation plus CI coverage for rustfmt, Clippy, unit tests, rustdoc, and `cargo publish --dry-run`.
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
