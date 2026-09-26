# Jev Semantic Context Gate

Token Terminator 0.8.0 added the **optional** semantic context gate backed by TypeSafe Jev. v0.8.1 adds Hermes memory-provider awareness for fenced recalled context.

It is not a replacement mode. The normal Token Terminator pipeline still runs first.

```text
host assembles provider request
        ↓
SkillGate (when applicable)
        ↓
request compiler
        ↓
deterministic context compactor
        ↓
optional Jev semantic gate
        ↓
strict character/token acceptance
        ↓
provider
```

With Jev disabled, the pipeline behaves as before.

## What Jev does

After deterministic Token Terminator reduction, some prior natural-language conversation can still remain inline. Jev receives the current user request plus a bounded set of remaining prior plain-text user/assistant messages. On Hermes, `<memory-context>` background injected by memory providers such as Hindsight is separated from the user's actual words and may be scored as its own candidate. Jev answers two typed `noul` questions per candidate in one batched System One request:

1. **relevance** — would this prior message materially help answer the current request?
2. **guard** — does it contain an instruction, constraint, preference, commitment, exact value/name/code/quotation, or other detail whose omission could materially change the answer?

A message is eligible for compaction only when **both** probabilities are below the configured threshold.

Jev does not generate replacement prose. Token Terminator writes the exact original message to the local content-addressed vault and replaces it with a compact recovery receipt. This avoids paying tokens for a generated summary and preserves exact recovery.

## What Jev never receives from this feature

The semantic gate excludes:

- system messages;
- developer messages;
- tool messages and tool results;
- messages carrying tool calls;
- structured or multimodal message content;
- oversized candidates beyond the configured safety cap.

The newest user message is sent as the query against which relevance is judged, but it is never itself a removal candidate.

## Enable it

Jev is off by default.

```bash
export TOKEN_TERMINATOR_JEV=true
export TYPESAFE_API_KEY="..."
```

You can alternatively use:

```bash
export TOKEN_TERMINATOR_JEV_API_KEY="..."
```

The Token Terminator-specific variable takes precedence over `TYPESAFE_API_KEY`.

No API key belongs in the repository. Token Terminator does not persist or print it.

## Defaults

| Variable | Default |
|---|---:|
| `TOKEN_TERMINATOR_JEV` | `false` |
| `TOKEN_TERMINATOR_JEV_MODEL` | `jev-latest` |
| `TOKEN_TERMINATOR_JEV_TIMEOUT_MS` | `1500` |
| `TOKEN_TERMINATOR_JEV_RELEVANCE_THRESHOLD` | `0.15` |
| `TOKEN_TERMINATOR_JEV_MIN_MESSAGE_CHARS` | `600` |
| `TOKEN_TERMINATOR_JEV_MAX_CANDIDATES` | `12` |
| `TOKEN_TERMINATOR_JEV_MAX_CANDIDATE_CHARS` | `12000` |
| `TOKEN_TERMINATOR_JEV_MAX_STATE_CHARS` | `60000` |

The threshold is intentionally conservative. A candidate is removed only if both the relevance and guard probabilities fall below it.

## Failure behavior

Every Jev failure is fail-open relative to the **already-reduced Token Terminator request**.

A timeout, HTTP error, malformed response, missing answer, vault failure, character expansion, or exact-token expansion simply skips the Jev reduction. It does not undo compiler, compactor, SkillGate, temporal, native, RTK, or vault work that already succeeded.

## External-service boundary

Enabling Jev explicitly permits the bounded current user request, selected prior plain-text user/assistant candidates, and separately fenced Hermes `<memory-context>` background to be sent to TypeSafe's API. Keep `TOKEN_TERMINATOR_JEV=false` when that external transfer is not appropriate.

The exact removed content remains authoritative in Token Terminator's local vault. Jev supplies typed decisions; it never owns the evidence or the recovery path.
