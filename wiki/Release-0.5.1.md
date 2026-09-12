# Release 0.5.1

**Date:** 2026-09-12

v0.5.1 is the hardening release following v0.5.0's temporal-delta, tokenizer-budget, and layered-recovery work.

## Main changes

### Vault lifecycle

- O(1) total-byte accounting instead of scanning `SUM(byte_count)` for every new write.
- Configurable high/low watermarks.
- Retention telemetry.
- Active temporal references protected from GC.
- Accepted provider-visible recovery references and temporal delta artifacts protected from GC.

### Correctness

- Unified five-turn recent-inline default.
- Collapse-window invariant enforced in direct config, environment loading, and compactor behavior.
- Unicode-safe case-insensitive artifact search.
- RTK rewrite cache scoped by command + canonical cwd.
- Async temporal-delta parity.

### Measurement

- Same-mode comparisons rejected.
- Prompt-fingerprint/model groups aggregated rather than arbitrary `zip()` pairing.
- Eligible/paired/unpaired observations reported.
- Deterministic 95% bootstrap intervals.
- Exact native/temporal token savings used when a tokenizer is available; fallback estimates are labelled.

### Schema / security / portability

- `terminal_snapshots` moved into storage schema management.
- Existing parent directories are not forcibly chmodded.
- Windows read-only SQLite URI handling fixed.
- Optional RTK executable pinning.
- Documentation expanded for compaction, retention, token budgeting, and trust boundaries.

## Verification

The final tree passed the permanent CI matrix on:

- Python 3.10
- Python 3.11
- Python 3.12
- Python 3.13
- Windows
- Rust fmt/Clippy/tests/rustdoc
- package build, Twine checks, and release-content verification

A focused final verification reported **174 passed, 2 skipped**.
