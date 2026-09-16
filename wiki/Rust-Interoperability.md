# Rust Interoperability

The `token-terminator` crate provides the stable cross-language pieces of the artifact contract. It is intentionally **not** a second implementation of the full Python runtime.

## Install

```bash
cargo add token-terminator
```

Or pin:

```toml
[dependencies]
token-terminator = "0.6.0"
```

## Example

```rust
use token_terminator::{
    artifact_identity,
    strictly_smaller_chars,
    verify_sha256,
};

let evidence = "exact tool evidence";
let identity = artifact_identity(evidence);

assert!(identity.artifact_id.starts_with("a_"));
assert!(verify_sha256(evidence, &identity.sha256));
assert!(strictly_smaller_chars(
    "long provider-visible evidence",
    "short receipt",
));
```

## Compatibility contract

The crate mirrors:

- SHA-256 over exact UTF-8 bytes;
- normal artifact IDs as `a_` + first 32 lowercase digest hex characters;
- full-digest collision fallback compatibility;
- the portable strictly-smaller-in-characters baseline.

The Python runtime can additionally require fewer exact measured tokens.

## Not included in the crate

The Rust crate does not implement:

- the SQLite vault;
- Hermes hooks;
- request compilation;
- temporal state;
- tokenizer adapters;
- RTK rewriting;
- PyO3 acceleration.

Native acceleration remains profiling-driven. The project should not add a Rust/PyO3 dependency merely because Rust exists elsewhere in the repository.
