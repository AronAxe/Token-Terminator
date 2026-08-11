# Contributing

Changes should improve net tool-result token use without adding permanent
prompt text or model-visible schemas.

Before opening a pull request:

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m build
python -m twine check dist/*
```

New compressors must be deterministic, return a strictly smaller final result,
retain a platform-appropriately private recovery copy, and include tests for
both compression and pass-through behavior.
