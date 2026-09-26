# Release 0.8.1


> **Provider routing note:** v0.8.2 supersedes the Jev credential/endpoint setup documented below. Current installs support OpenRouter (`OPENROUTER_API_KEY`) or direct TypeSafe (`TYPESAFE_API_KEY`), one key at a time.

**Date:** 2026-09-26

Token Terminator 0.8.1 is a patch release for the optional Jev semantic context gate when Hermes memory providers inject recalled context into the current user turn.

## Highlights

- Recognizes Hermes `<memory-context>` fences used for recalled background context.
- Separates the user's actual current request from fenced recalled memory before Jev relevance scoring.
- Allows Hindsight and other memory-provider recall to participate in Jev routing as context without making the user's own words removable.
- Exact-vaults the complete fenced memory block before replacing a low-relevance block with a fenced recovery receipt.
- Keeps Jev optional and fail-open; all existing Token Terminator mechanisms continue to run whether Jev is enabled or not.
- Adds offline regression coverage; CI does not need or use a TypeSafe API key.

## Compatibility

This is an in-place upgrade from v0.8.0. Existing vault data, artifact identities, and Jev configuration remain compatible. Python support remains 3.10–3.13.

The Rust interoperability crate is released as `token-terminator 0.8.1`; its interoperability surface is unchanged.

## Install

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.1'
hermes plugins enable token-terminator --no-allow-tool-override
```

Jev remains disabled by default. To enable it:

```bash
export TOKEN_TERMINATOR_JEV=true
export TYPESAFE_API_KEY='your-key-here'
```

You may use `TOKEN_TERMINATOR_JEV_API_KEY` instead of `TYPESAFE_API_KEY`. Never commit the key.

Start a fresh Hermes session after upgrading and verify with:

```text
/token-terminator status
```
