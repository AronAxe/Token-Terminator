# Changelog

## 0.2.0 - 2026-08-11

- Added a `native` mode that compresses Hermes-native search/process results
  without registering terminal middleware or invoking RTK.
- Added a private durable experiment ledger backed by Hermes' canonical session
  token and cost accounting.
- Added `/rtk-plus compare [mode-a mode-b]` with per-session mean/median totals
  and paired-turn deltas for repeated prompts on the same model.
- Kept actual, Hermes-estimated, and optional API-equivalent costs separate;
  subscription/OAuth routes remain `$0` actual marginal cost.
- Added immutable session mode tags, resumed-session baselines, and automatic
  exclusion of sessions contaminated by mode or model changes.
- Recorded compression, rewrite, and recovery-read counts without storing
  commands, prompts, or tool contents.
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
