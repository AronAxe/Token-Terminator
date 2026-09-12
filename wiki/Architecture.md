# Architecture

Token Terminator is designed as an **optimization layer**, not a replacement runtime.

## Ownership boundary

### The host runtime owns

- conversation/transcript persistence;
- memory and context-engine lifecycle;
- provider client and response streaming;
- tool execution;
- authoritative session/request identity.

### Token Terminator owns

- its private SQLite artifact vault;
- content-addressed evidence and observations;
- exposure/receipt accounting;
- temporal terminal baselines;
- request-reduction metrics and experiment ledger;
- middleware transformations at adapter-defined boundaries.

That separation is deliberate. Token Terminator can disappear or fail and the host should still behave normally.

## Pipeline

A typical request cycle can touch five reduction paths:

1. **Terminal rewrite** — eligible terminal commands can be rewritten through RTK before execution.
2. **Temporal delta** — after a repeated terminal command actually executes, the new exact output may be represented as a smaller diff/no-change receipt.
3. **Native tool-result compression** — supported large tool outputs can be compacted after exact evidence is vaulted.
4. **Evidence vault / receipts** — duplicate or previously exposed evidence can be represented by bounded recovery receipts.
5. **Final request compiler** — the fully assembled provider request is deep-copied, compacted, measured, and accepted only if the final payload is smaller.

Optional tokenizer-aware measurement adds a second acceptance gate after character reduction.

## Hermes adapter seams

The first-party Hermes adapter connects the core through:

- `tool_request` middleware for terminal rewrites;
- `transform_tool_result` for native and temporal result reduction;
- observational lifecycle and `post_tool_call` hooks;
- `llm_request` middleware for provider-bound request compilation;
- the compact `token_terminator` recovery/status tool.

## Porting to another runtime

A custom adapter needs four things:

1. stable session/request/tool-call identifiers;
2. a tool-result transformation seam;
3. a final provider-request seam;
4. a recovery tool exposed to the model.

The adapter must interpret `None` or an exception as **pass through unchanged**. See [Async and Adapter Integration](Async-and-Adapter-Integration) for the API shape.
