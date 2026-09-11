# token-terminator (Rust interoperability crate)

Rust interoperability helpers for [Token Terminator](https://github.com/AronAxe/Token-Terminator), the evidence-preserving token-reduction layer for agent runtimes.

> **Scope:** this crate is intentionally small. The production Token Terminator runtime, SQLite vault, request compiler, token-budget adapters, temporal-delta state, and Hermes integration remain in Python. This crate exists so Rust agent hosts can produce and verify the same stable artifact identities and enforce the same baseline strict-reduction rule without embedding Python.

## Install

```bash
cargo add token-terminator
```

The library crate name is `token_terminator`:

```rust
use token_terminator::{artifact_identity, strictly_smaller_chars, verify_sha256};

let identity = artifact_identity("exact tool evidence");
assert!(identity.artifact_id.starts_with("a_"));
assert!(verify_sha256("exact tool evidence", &identity.sha256));
assert!(strictly_smaller_chars("long provider-visible evidence", "short receipt"));
```

## Compatibility contract

The helpers mirror the cross-language parts of Token Terminator 0.5.x:

- SHA-256 is computed over the exact UTF-8 bytes of artifact text.
- Normal artifact IDs use `a_` plus the first 32 lowercase SHA-256 hexadecimal characters.
- The Python vault may use `a_` plus the full digest only as a short-ID collision fallback.
- The baseline optimization invariant is **strictly smaller in characters**; the Python runtime can additionally require fewer measured tokens when an exact tokenizer is configured.

## What this crate does not do

It does not implement the Python runtime, Hermes hooks, SQLite storage, tokenizer selection, RTK rewriting, or PyO3 acceleration. A native accelerator remains a profiling-driven future option rather than a hidden dependency of the portable runtime.

Full Rust integration notes: [`docs/RUST_CRATE.md`](https://github.com/AronAxe/Token-Terminator/blob/main/docs/RUST_CRATE.md)

- Repository: https://github.com/AronAxe/Token-Terminator
- Rust API docs: https://docs.rs/token-terminator
- crates.io: https://crates.io/crates/token-terminator

MIT licensed.
