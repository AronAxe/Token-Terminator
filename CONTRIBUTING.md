# Contributing

Changes must improve net provider-visible token use without claiming Hermes' context-engine slot or mutating caller-owned requests, persisted transcripts, or LCM state.

Before opening a pull request:

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

New transformations must be deterministic, fail open, preserve exact recoverability when evidence is removed, and prove the **complete** transformed request/result is strictly smaller after receipts, annotations, schemas, and optional working-state blocks are counted.

Persistence changes require atomic migrations, fault-injected rollback coverage, bounded domain-layer outputs, idempotent replay, conflict detection, and archive scans for databases, WAL/SHM files, caches, environments, credentials, and machine-specific paths.

A green source suite is not a green release artifact. Rebuild after every source or metadata edit, install the built wheel into an isolated Hermes environment, and run `scripts/smoke_hermes.py` against the real `PluginManager` before release.
