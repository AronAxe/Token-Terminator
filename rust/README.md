# token-terminator (Rust interoperability crate)

**v0.11.0** — Rust interoperability helpers for [Token Terminator](https://github.com/AronAxe/Token-Terminator), the evidence-preserving token-reduction layer for agent runtimes.

> **Scope:** this crate is intentionally small. The Python package supplies the
> ContextEngine, SQLite vault, Context IR, learned omission-risk policy, dashboard
> and Hermes integration. This companion lets Rust hosts produce and verify stable
> artifact identities and enforce the baseline strict-reduction rule.

## Install

```bash
cargo add token-terminator@0.11.0
```

The library name is `token_terminator`:

```rust
use token_terminator::{artifact_identity, strictly_smaller_chars, verify_sha256};

let identity = artifact_identity("exact tool evidence");
assert!(identity.artifact_id.starts_with("a_"));
assert!(verify_sha256("exact tool evidence", &identity.sha256));
assert!(strictly_smaller_chars("long provider-visible evidence", "short receipt"));
```

## Compatibility contract

The artifact contract introduced in Token Terminator 0.5.x remains unchanged:

- SHA-256 is computed over exact UTF-8 bytes.
- Normal artifact IDs use `a_` plus the first 32 lowercase digest characters.
- The full digest is supported as the short-ID collision fallback.
- `strictly_smaller_chars` requires a character decrease. It does not count tokens.

Python's ContextEngine and Context IR additionally require an actual-tokenizer
reduction of the complete request. Rust hosts must supply equivalent measurement
and recovery boundaries themselves; this helper is not a substitute for them.

## What this crate does not do

It does not implement the Python runtime, Hermes hooks, SQLite storage, JEV
selection, learned-policy training, Context IR, dashboard, tokenizer selection,
RTK rewriting or PyO3 acceleration. The Python package does not depend on Rust.
A native accelerator remains a profiling-driven future option.

Version 0.11.0 aligns the companion package and guides with the product release;
it does not claim new identity semantics or a Rust port of the Python features.

[Full integration notes](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/RUST_CRATE.md) ·
[Rust API docs](https://docs.rs/token-terminator/0.11.0/token_terminator/) ·
[crates.io](https://crates.io/crates/token-terminator/0.11.0)

MIT licensed.
