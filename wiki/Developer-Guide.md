# Developer Guide

## Local verification

```bash
python -m pip install -e '.[dev]'
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -p no:cacheprovider
python scripts/benchmark.py
python -m build
python -m twine check dist/*
python scripts/verify_release.py 'dist/*'
```

For the Rust interoperability crate:

```bash
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
RUSTDOCFLAGS='-D warnings' cargo doc --no-deps
cargo publish --dry-run
```

## Design rules worth defending

A change should preserve:

- fail-open behavior;
- immutable caller-owned requests;
- exact evidence recovery for accepted recoverable transformations;
- strict complete-payload reduction;
- exact-tokenizer veto when configured;
- bounded receipts, search results, and artifact pages;
- separation between host transcript/memory ownership and Token Terminator's private optimization state.

## Profiling before acceleration

Do not add PyO3/Rust hot-path complexity without profiling. Request deep-copy, serialization, tokenizer measurement, SQLite, and RTK subprocess costs should be measured separately before choosing an optimization target.

## Tests for regressions

When fixing a correctness bug, add a test that reproduces the old failure mode. v0.5.1 follows this pattern for configuration invariants, Unicode search, cwd cache identity, async temporal parity, Windows URI handling, vault retention, and measurement semantics.
