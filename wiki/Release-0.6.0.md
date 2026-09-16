# Release 0.6.0

**Date:** 2026-09-16

Token Terminator v0.6.0 adds **request component attribution** and **SkillGate**.

## Highlights

- Provider-bound requests are now attributed across instructions, skill catalogs, tool schemas, tool results, current-user content, history, other fields, and request framing.
- SkillGate reduces large Hermes `<available_skills>` indexes before provider dispatch while preserving `skills_list` / `skill_view` discovery.
- There is **no default maximum number of retained skills**. Every skill above the relevance threshold is kept; an explicit `max_skills` remains available only as an opt-in host constraint.
- Routing touches only trusted system/developer instruction fields and leaves quoted skill tags in user/tool/history content unchanged.
- The current lexical-IDF scorer is deterministic and dependency-free; `Runtime.set_skill_scorer(...)` is the extension point for a future tiny trained/local relevance model.
- Raw/final component metrics are content-free and use exact tokenizer measurements when available, with the existing labelled fallback otherwise.

## Compatibility

This is an in-place upgrade from v0.5.2. Existing content-addressed artifacts remain valid. The new request-attribution telemetry is additive. Python support remains 3.10–3.13. The Rust interoperability crate is released as `token-terminator` 0.6.0.

The v0.6.0 Git tag and GitHub release are cut from the same tested source tree used for the Python package and Rust crate.

## Install

```bash
python -m pip install 'git+https://github.com/AronAxe/Token-Terminator.git@v0.6.0'
```

Rust:

```toml
[dependencies]
token-terminator = "0.6.0"
```
