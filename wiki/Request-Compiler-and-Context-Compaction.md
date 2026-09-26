# Request Compiler and Context Compaction

Tool-result compression is only half the problem. Agent runtimes can still assemble a provider request containing repeated evidence, old large tool results, and redundant completed turns. Token Terminator therefore performs a final provider-bound pass.

## Request compiler

The compiler operates on a deep copy. It can:

- identify repeated large artifacts;
- replace later exposures with bounded receipts;
- collapse same-request duplicates;
- optionally inject bounded working state;
- record request metrics without storing prompt content.

The caller-owned request remains untouched.

## Strict final gate

The compiler does not accept a local improvement merely because one field got smaller. It measures the **complete final provider payload** after receipts, metadata, optional working state, and context compaction.

If the final serialized payload is not smaller, Token Terminator passes through the original request.

When an exact tokenizer is configured, measured token count is a second veto gate.

## Context compaction

Old large tool results can be vaulted and replaced with receipts. Completed old turns may be folded into deterministic compact summaries for the provider-bound copy.

The configured recent-turn invariant matters:

```text
collapse_after_turns == 0
OR
collapse_after_turns >= inline_recent_turns
```

The default is six turns before collapse, with the five most recent turns guaranteed fully inline.

This does **not** delete the host's persisted transcript. It changes only the provider-bound copied request.

## Optional Jev phase

When `TOKEN_TERMINATOR_JEV=true` and a TypeSafe API key is available, Token Terminator can run one additional semantic pass **after** deterministic context compaction.

The current user request and bounded prior plain-text user/assistant candidates are sent to Jev in one batch. Each candidate gets independent relevance and guard probabilities. A candidate is eligible for replacement only when both are below the configured threshold.

Jev does not generate a summary. Token Terminator stores the exact original candidate in the local vault and substitutes a compact recovery receipt. If Jev fails, returns malformed data, or fails either the character or exact-token reduction gate, the already-reduced deterministic request remains in use.

See [Jev Semantic Context Gate](Jev-Semantic-Context-Gate).

## Working-state injection

`TOKEN_TERMINATOR_WORKING_GRAPH_CHARS` defaults to `0`. When enabled, the bounded selector is optional context, not a second memory system. If injecting it would erase the end-to-end reduction, it is removed.

## Exposure accounting

v0.5.1 makes exposure/lease accounting track the request actually accepted. A candidate rejected by the final character/token gate should not consume a provider exposure as though it had been delivered.
