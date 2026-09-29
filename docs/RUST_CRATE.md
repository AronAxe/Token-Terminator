# Rust crate: `token-terminator` 0.11.0

Token Terminator ships a small Rust interoperability crate alongside its Python
runtime. The package name is `token-terminator`; the library is `token_terminator`.

[crates.io](https://crates.io/crates/token-terminator/0.11.0) ·
[Rust API](https://docs.rs/token-terminator/0.11.0/token_terminator/)

## Why a Rust crate exists

Adapters do not all live in Python. The crate exposes stable pieces a Rust host
can share with TT without duplicating its runtime: SHA-256 identity over exact
UTF-8 bytes, normal short IDs, the full collision-fallback ID, digest/ID verification,
and the baseline strictly-smaller-in-characters invariant. Storage, recovery and
provider-specific measurement remain the host adapter's responsibility.

## Install

```bash
cargo add token-terminator@0.11.0
```

Or declare the compatible release series:

```toml
[dependencies]
token-terminator = "0.11.0"
```

Use `=0.11.0` instead when an exact Cargo version requirement is desired.

## Example

```rust
use token_terminator::{
    artifact_id_matches,
    artifact_identity,
    strictly_smaller_chars,
    verify_sha256,
};

let raw = "the complete exact tool result";
let identity = artifact_identity(raw);
assert!(verify_sha256(raw, &identity.sha256));
assert!(artifact_id_matches(raw, &identity.artifact_id));
assert!(strictly_smaller_chars(raw, "receipt"));
```

## Artifact identity

The Python vault computes `SHA256(content.encode("utf-8"))`. The normal ID is
`a_` followed by the first 32 lowercase hexadecimal digest characters. A short-ID
collision with different exact content uses `a_` plus the full digest instead.
The Rust helpers support both forms without opening the vault database.

## Measurement and recovery boundaries

`strictly_smaller_chars(raw, candidate)` only compares character lengths. It does
not prove exact token savings, source availability, valid provider shape or answer
quality. Python's ContextEngine and Context IR require strict actual-tokenizer AND
character decreases across complete canonical request JSON. Legacy middleware
can retain its character-only fallback. A Rust host must implement the matching
measurement and exact-source recovery checks for its integration.

## Not a Rust port or mandatory accelerator

The full-history ContextEngine, JEV attention, learned omission-risk system,
Context IR, SQLite vault, dashboard, temporal state and Hermes hooks remain in
Python. CatBoost is optional and training-only. The crate supplies none of these
features and is not loaded by the Python package. No PyO3/FFI dependency is added.
Native acceleration remains contingent on actual profiling, not the publication
of an interoperability crate.

## Release verification

CI and crate publication run:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
RUSTDOCFLAGS="-D warnings" cargo doc --no-deps
cargo publish --dry-run
```

Publication uses the existing repository `CARGO_REGISTRY_TOKEN` secret. The token
is never committed. Version 0.11.0 aligns this companion with the Python release
and its refreshed documentation; the artifact identity contract remains unchanged.
