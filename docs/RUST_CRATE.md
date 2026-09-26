# Rust crate: `token-terminator`

Token Terminator ships a small Rust interoperability crate alongside the Python runtime.

- crates.io: <https://crates.io/crates/token-terminator>
- docs.rs: <https://docs.rs/token-terminator>
- package name: `token-terminator`
- library name: `token_terminator`

## Why a Rust crate exists

Token Terminator is agent-runtime infrastructure, so adapters do not all live in Python. The Rust crate exposes only the stable pieces that a Rust host can share with the Python implementation without duplicating the whole runtime:

1. SHA-256 artifact identity over exact UTF-8 bytes;
2. normal short artifact IDs (`a_` plus the first 32 digest hex characters);
3. the full collision-fallback artifact ID;
4. exact digest and artifact-ID verification; and
5. the baseline strictly-smaller-in-characters acceptance invariant.

This keeps cross-language adapters compatible with the private artifact vault while leaving the main runtime dependency-light and fail-open.

## Install

```bash
cargo add token-terminator
```

Or pin the release explicitly:

```toml
[dependencies]
token-terminator = "0.8.1"
```

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

## Artifact identity compatibility

The Python vault computes:

```text
sha256 = SHA256(content.encode("utf-8"))
artifact_id = "a_" + sha256_hex[0:32]
```

If the 32-hex-character short ID ever collides with an existing different digest, the Python vault uses:

```text
artifact_id = "a_" + full_sha256_hex
```

The Rust crate exposes helpers for both forms. It does not access the vault database directly; the host adapter remains responsible for storage and recovery boundaries.

## Strict reduction compatibility

`strictly_smaller_chars(raw, candidate)` mirrors the portable baseline invariant: a candidate must contain fewer characters than the original provider-visible text.

The Python 0.5 runtime can impose a **second** model-aware gate when an exact tokenizer is available. The Rust interoperability crate deliberately does not guess tokenizer behavior. A Rust host that has an exact provider tokenizer should apply the same second gate itself.

## Deliberate boundary: this is not the native accelerator

Publishing a Rust crate does **not** change the v0.5 architecture:

- Python remains the production reduction engine and Hermes adapter.
- No PyO3 extension is required.
- No Rust code is imported by the Python package.
- The SQLite vault schema and lifecycle stay owned by the Python runtime.
- Rust/PyO3 hot-path acceleration remains deferred until profiling demonstrates that crossing the FFI boundary is worth the complexity.

That distinction is intentional: crates.io gives Rust agent runtimes a supported compatibility surface now, without turning an unmeasured optimization idea into a mandatory dependency.

## Release verification

The repository CI treats the Rust package as a first-class distribution surface. It runs:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
RUSTDOCFLAGS="-D warnings" cargo doc --no-deps
cargo publish --dry-run
```

The crates.io publication workflow uses the repository secret `CARGO_REGISTRY_TOKEN`, matching the publishing convention used by the author's other Rust projects. Tokens are never committed to repository files or logs.

## Versioning

The Rust crate follows Token Terminator product versions when its interoperability contract changes. Version `0.8.1` accompanies Token Terminator 0.8.1; the Rust interoperability contract itself remains stable and continues to expose artifact identity and strict-reduction helpers.
