# Security

Please report suspected vulnerabilities through a private GitHub security advisory rather than a public issue.

## Data boundaries

Token Terminator stores exact large tool artifacts and private provenance locally because exact recovery is part of its acceptance contract. By default, plugin-owned files live under:

```text
<HERMES_HOME>/token-terminator/
```

The artifact vault stores raw artifact text, content digests, tool names, tool arguments, observations, exposure leases, optional bounded working state, and request-reduction metrics. The separate experiment ledger stores session/turn identifiers, mode/model/provider labels, token/cost totals, transformation counts, and salted local prompt fingerprints. It does **not** store command strings, prompts, or tool contents.

With Jev disabled (the default), the reduction pipeline makes no semantic-service upload. Opting into Jev creates the external-service boundary described below. Context IR itself is entirely local.

On POSIX, Token Terminator enforces `0700` on private parent directories and `0600` on SQLite files. On Windows, files remain under the user's Hermes profile and inherit its Windows ACLs. Anyone who can read that profile can read private artifacts; treat the profile as sensitive application data.

## Execution and transformation safety

- RTK is invoked with an argument array and `shell=False`.
- Remote terminal backends are disabled by default.
- Native compression is accepted only after exact artifact write and read-back succeeds.
- The complete model-visible payload, including receipts and optional working state, must be strictly smaller.
- Request compilation operates on deep copies and fails open if a request cannot be copied safely.
- Malformed requests, unavailable storage, migration failures, vault-capacity failures, missing host APIs, and non-smaller output leave normal Hermes behavior unchanged.
- Token Terminator does not register a Hermes context engine and does not modify LCM state.
- Receipt metadata is bounded and excludes raw tool arguments and content.
- Artifact reads, searches, graph operations, identifiers, metadata, and replay batches are bounded in the domain layer.

## Operational guidance

Do not install two distributions that own the `rtk_hermes_plus` Python package. When migrating from `rtk-hermes-plus` 0.2.0, uninstall it before installing `token-terminator` 0.3.0. Enable only one Token Terminator/RTK rewrite plugin at a time.

Back up or remove `<HERMES_HOME>/token-terminator/` separately from package uninstall. Disabling or uninstalling code intentionally does not erase private artifacts.

## RTK executable trust boundary

When `TOKEN_TERMINATOR_RTK_PATH` is unset, Token Terminator discovers `rtk` through the host process `PATH`. A malicious or accidentally shadowed executable named `rtk` can therefore influence command rewriting. Security-sensitive deployments should pin the expected executable with `TOKEN_TERMINATOR_RTK_PATH` and protect that file and its parent directory from untrusted writes. Token Terminator still invokes RTK with an argument array and `shell=False`; executable discovery is the separate trust boundary.

## Optional Jev external-service boundary

Jev integration is disabled by default. Enabling it requires `TOKEN_TERMINATOR_JEV=true` plus one provider credential: `OPENROUTER_API_KEY` for OpenRouter or `TYPESAFE_API_KEY` for direct TypeSafe access. In `auto` mode OpenRouter is preferred when both are present. The legacy `TOKEN_TERMINATOR_JEV_API_KEY` remains a temporary direct-TypeSafe compatibility alias.

The key is read from the process environment only. Token Terminator does not write it to the repository, artifact vault, experiment ledger, request metrics, or status output.

When Jev is enabled, Token Terminator sends a bounded state object either to OpenRouter's `https://openrouter.ai/api/alpha/decisions` endpoint or directly to TypeSafe's `https://api.typesafe.ai/v1/systemone` endpoint. That state contains the current user request and selected prior **plain-text user/assistant** candidate messages. On Hermes, separately fenced `<memory-context>` background appended to the current user message may also be included as its own candidate. System/developer messages, tool messages and results, messages containing tool calls, structured/multimodal content, and the user's actual current-turn words as a removal candidate are excluded.

Jev is not trusted with destructive authority. Its typed relevance/guard probabilities can only nominate an eligible prior message for compaction. Token Terminator must first write and read back the exact message from the local vault, prove that the recovery receipt makes the complete request smaller, and—when exact token measurement is available—prove that it also uses fewer tokens. Network errors, timeouts, malformed responses, missing answers, storage failures, and failed size gates all leave the already-reduced non-Jev request unchanged.


## Context IR evidence and authority boundary (v0.9.0)

`TOKEN_TERMINATOR_CONTEXT_IR` defaults to `false` and adds no API or credential. Jev scores are untrusted attention signals, never facts. Missing, nonnumeric, nonfinite and out-of-range probabilities are rejected; errors expose types only, not external exception text.

The stage understands one `messages` list or one Responses-style `input` list. It modifies only prior plain-string user/assistant message content, retaining outer metadata and role. It skips system/developer/tool messages, tool calls/results, structured content, multimodal last-user turns, unusual message metadata, existing TT artifacts and existing IR. It does not guess which earlier user was current when the last user has structured content.

Current user wording is never recoded. When IR is on, Jev also leaves the entire current user message—including `<memory-context>` fences—unchanged. This deliberately narrows v0.8.2's memory-block selection while the new layer is enabled.

Recognizable hard constraints, code, quotes and exact values in arbitrary prose are vetoed. Structured records preserve exact scalar values but reject instruction-like keys/values and named code/quotation fields. These guards are syntactic and cannot recognize every imaginable instruction. IR is not a prompt-injection detector, instruction sanitizer, or authority upgrade. Encoded content remains data in its original message role.

Recovery must actually be present in the request: a compatible `token_terminator` tool declaration including `artifact_get`, `artifact_id`, `offset` and `limit`, with no tool choice that prohibits recovery. No implicit recovery promise is accepted.

Each winning source is inserted into the existing content-addressed vault and exposure-pinned in **one write transaction**. Concurrent writers and capacity pruning cannot delete it between insertion and pinning. Exact read-back, SHA-256 and source-position observations are checked before dispatch. Actual artifact IDs, including a collision-expanded ID, are substituted before the final size gate.

`inspect_ir(text, store)` verifies the source hash, recorded message position and the entire regenerated representation. It returns source metadata and immutable `SourceUnit` records: ordinal, Unicode-character start/end offsets and kind (`record` or `span`). Every row/span maps to a specific exact source slice. A future graph adapter can attach typed node/edge/path information to these units without accepting generated evidence.

Models use the existing `token_terminator action=artifact_get` with the displayed `artifact_id` and optional `offset`/`limit`. Existing `artifact_peek` and `artifact_find` permit progressively deeper inspection. The Python `expand_ir` helper validates the representation and returns a bounded exact source page. Normal vault recovery reads also verify hash/length integrity, so corruption after dispatch is not silently returned as exact data.

The exact source is the **post-TT, pre-IR input**. IR does not claim to reconstruct information already transformed by earlier TT stages; those stages retain their own vault/recovery contracts. Source IDs remain ordinary artifact IDs, with no new database schema or tool action.

Published evidence stays protected by existing exposure retention. If a later operation fails after pinning, safe but unused artifacts may remain pinned. This favors recoverability over aggressive cleanup. Capacity exhaustion fails open; it is not permission to evict published evidence. Back up the vault alongside transcripts. Disabling IR or rolling back does not erase it.

Each format evaluation tokenizes the **complete canonical provider-bound request JSON**, including every field, tool schema, role, source ID and decoder legend. Greedy bounded search accepts improvements over the current working request. After all real source IDs have been written, the compiler remeasures the whole request and requires strict token and character savings against the untouched pre-IR request. Backend/model changes or missing measurements veto the result. There are no provider-text additions after this gate.

The existing adapter's canonical JSON measurement is exact for that string under its selected tokenizer. It is **not** the provider's hidden chat-template framing or a claim about billed token counts. Host adapters may supply a stricter whole-request counter through the existing `measure_request` interface. Compare deltas using a tokenizer actually matched to the target model; arbitrary encoding overrides can invalidate that alignment.

Status exposes version/limits. Per-decision `metrics.context_ir` contains format counts, evaluations, raw/final tokens/chars, elapsed time, failure reason and `measurement_scope=canonical-request-json`. Source text, source IDs and raw exceptions are excluded from those metrics.

The optional live benchmark explicitly calls configured Jev and OpenRouter and validates read-only recovery calls against source IDs already in the request. Raw answers and keys are not persisted. CI never runs the live benchmark.
