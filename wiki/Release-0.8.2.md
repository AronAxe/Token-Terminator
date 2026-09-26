# Release 0.8.2

**Date:** 2026-09-26

Token Terminator 0.8.2 corrects the provider boundary for the optional Jev semantic context gate.

## Highlights

- Supports **OpenRouter Decisions API** and **direct TypeSafe System One API** with the same Token Terminator Jev layer.
- Adds `TOKEN_TERMINATOR_JEV_PROVIDER=auto|openrouter|typesafe`.
- In `auto` mode, `OPENROUTER_API_KEY` is preferred when available; otherwise `TYPESAFE_API_KEY` is used directly.
- Users need **one provider key only**. If both happen to exist, OpenRouter wins unless the provider is forced.
- Uses `~typesafe/jev-latest` by default through OpenRouter and `jev-latest` for direct TypeSafe.
- Retains `TOKEN_TERMINATOR_JEV_API_KEY` temporarily as a backward-compatibility alias for direct TypeSafe users from v0.8.0/v0.8.1.
- Keeps all existing Token Terminator reduction, vault, exact-recovery, fail-open, Hindsight `<memory-context>`, and tokenizer-veto behavior unchanged.
- Adds offline endpoint-selection tests; CI uses no external Jev key.

## OpenRouter

```bash
export TOKEN_TERMINATOR_JEV=true
export OPENROUTER_API_KEY='your-openrouter-key'
```

This calls:

```text
POST https://openrouter.ai/api/alpha/decisions
model: ~typesafe/jev-latest
```

## Direct TypeSafe

```bash
export TOKEN_TERMINATOR_JEV=true
export TOKEN_TERMINATOR_JEV_PROVIDER=typesafe
export TYPESAFE_API_KEY='your-typesafe-key'
```

This calls:

```text
POST https://api.typesafe.ai/v1/systemone
model: jev-latest
```

## Install

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.2'
hermes plugins enable token-terminator --no-allow-tool-override
```

Start a fresh Hermes session and verify with:

```text
/token-terminator status
```
