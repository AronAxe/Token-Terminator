# Rust Interoperability

The `token-terminator` **0.11.0** crate supplies stable cross-language artifact
identity and reduction helpers. It is the Rust interoperability companion, **not**
a second implementation of the Python ContextEngine, learned policy or dashboard.

## Install

```bash
cargo add token-terminator@0.11.0
```

Or declare:

```toml
[dependencies]
token-terminator = "0.11.0"
```

## Example

```rust
use token_terminator::{artifact_identity, strictly_smaller_chars, verify_sha256};

let evidence = "exact tool evidence";
let identity = artifact_identity(evidence);
assert!(identity.artifact_id.starts_with("a_"));
assert!(verify_sha256(evidence, &identity.sha256));
assert!(strictly_smaller_chars("long provider-visible evidence", "short receipt"));
```

## Stable compatibility contract

SHA-256 covers exact UTF-8 bytes. Normal IDs use `a_` followed by the first 32
lowercase digest characters; the full-digest collision fallback remains supported.
The helper's strict character-reduction check is a baseline, not an exact-token
measurement. Hosts must apply their own actual target-tokenizer gate where required.

The crate does not supply SQLite storage, Hermes hooks, Context IR, semantic
selection, CatBoost training, tokenizers, the dashboard, RTK rewriting or PyO3
acceleration. The Python package remains dependency-light at runtime; Rust is not
silently imported by it. Version 0.11.0 aligns the companion package and documentation
with the product release without claiming a new artifact identity scheme.

[Complete integration notes](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/RUST_CRATE.md) ·
[Rust API](https://docs.rs/token-terminator/0.11.0/token_terminator/) ·
[crates.io](https://crates.io/crates/token-terminator/0.11.0)
