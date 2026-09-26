# Release 0.8.0

Released: **2026-09-26**

Token Terminator 0.8.0 adds an **optional TypeSafe Jev semantic context gate** without replacing any existing Token Terminator mechanism.

## What changed

- Jev runs after the normal request compiler and deterministic context compactor.
- Existing RTK rewriting, temporal deltas, native compression, SkillGate, vaulting, exact recovery, and tokenizer-aware acceptance remain active when Jev is enabled.
- One batched System One request evaluates bounded prior plain-text user/assistant messages against the current user request.
- Each candidate receives a relevance probability and a guard probability.
- A candidate is eligible for compaction only when both probabilities are below the configured threshold.
- Jev does not generate a replacement summary. Token Terminator exact-vaults the original and substitutes a compact recovery receipt.
- Exact-token measurement can veto a character-saving Jev reduction.
- Network errors, timeouts, malformed answers, storage errors, and failed size gates leave the already-reduced non-Jev request unchanged.

## Opt in

Jev is **off by default**.

```bash
export TOKEN_TERMINATOR_JEV=true
export TYPESAFE_API_KEY="..."
```

Or provide the key through `TOKEN_TERMINATOR_JEV_API_KEY`.

No API key is stored in GitHub, the Token Terminator vault, metrics, or status output.

## External data boundary

When Jev is enabled, the current user request plus selected prior plain-text user/assistant candidates are sent to TypeSafe's API. System/developer messages, tool messages/results, tool-call-bearing messages, structured/multimodal content, and the current user message as a removal candidate are excluded.

See [Jev Semantic Context Gate](Jev-Semantic-Context-Gate) and [Security and Trust Model](Security-and-Trust-Model).

## Upgrade

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"

hermes plugins disable token-terminator
"$HERMES_PY" -m pip uninstall -y token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

Start a fresh Hermes session and inspect:

```text
/token-terminator status
```

The `jev` status block reports whether the feature is enabled/configured and its public limits. It never returns the API key.
