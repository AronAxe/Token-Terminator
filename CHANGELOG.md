# Changelog

## Unreleased

- Added a `native` mode that compresses Hermes-native search/process results
  without registering terminal middleware or invoking RTK.
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
