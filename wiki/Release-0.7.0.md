# Release 0.7.0

**Date:** 2026-09-23

Token Terminator 0.7.0 adds graph-aware skill routing while keeping installed skill data private and host-local.

## Highlights

- Added a runtime **graph-of-skill-graphs** for SkillGate.
- The graph ships **empty** in the open-source repository and is populated only from the current user's installed skills at runtime.
- Each skill remains a separate outer node with its own internal section/resource graph instead of flattening all skill contents into one global graph.
- Cross-skill traversal follows only source-backed relationships such as `related_skills` and explicit dependencies; lexical overlap alone never creates an inter-skill edge.
- SkillGraph can use the contents of locally installed skills for relevance scoring without placing those contents into provider-visible context.
- Explicit required-skill relationships are followed transitively.
- The existing no-default-skill-cap, fail-open, caller-immutability, strict-character-reduction, and exact-tokenizer acceptance invariants remain intact.
- Added synthetic-only privacy and routing tests; no user's installed skill inventory is shipped in the repository.

## Compatibility

This is an in-place upgrade from v0.6.0. Existing content-addressed artifacts, vault data, and request-accounting tables remain compatible. Python support remains 3.10–3.13.

The Rust interoperability crate is released as `token-terminator 0.7.0`.

## Install

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.7.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

Start a fresh Hermes session after upgrading and verify with:

```text
/token-terminator status
```
