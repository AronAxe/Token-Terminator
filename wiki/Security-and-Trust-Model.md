# Security and Trust Model

Token Terminator intentionally stores exact evidence locally because exact recovery is part of its product contract.

## Private data

By default plugin-owned files live under:

```text
<HERMES_HOME>/token-terminator/
```

The artifact vault may contain raw tool artifacts, tool arguments, provenance, observations, exposure records, temporal state, bounded working state, and request-reduction metrics.

The separate experiment ledger stores content-free accounting and salted prompt fingerprints. It does not store prompt text, command strings, or tool contents.

The plugin itself does not upload this private data by default.

## Optional Jev external-service boundary

Jev is disabled by default. If you explicitly enable it with `TOKEN_TERMINATOR_JEV=true`, Token Terminator uses one selected-provider credential: `OPENROUTER_API_KEY` for OpenRouter or `TYPESAFE_API_KEY` for direct TypeSafe. Auto mode prefers OpenRouter when both exist. The old `TOKEN_TERMINATOR_JEV_API_KEY` is only a temporary direct-TypeSafe compatibility alias.

The bounded state is sent either through OpenRouter's Decisions API or directly to TypeSafe. It contains the current user request and selected prior **plain-text user/assistant** candidate messages. Hermes `<memory-context>` background appended to the current user message may also be included as a separately fenced candidate. System/developer messages, tool messages/results, messages containing tool calls, structured/multimodal content, and the user's actual current-turn words as a removal candidate are excluded.

The API key is read from the process environment only. It is not stored in the artifact vault, experiment ledger, request metrics, repository, or status output.

Jev has no destructive authority. A low relevance/guard decision only makes a prior message eligible for compaction; Token Terminator must still exact-vault and read back the original, prove a smaller complete request, and pass the exact-token veto when available. Any Jev failure leaves the already-reduced non-Jev request unchanged.

## Transformation safety

- RTK is invoked with an argument array and `shell=False`.
- Remote terminal backends are disabled by default.
- Native compression requires successful exact write + read-back.
- The complete provider-visible payload must be smaller.
- Exact-tokenizer expansion vetoes a character-saving candidate.
- Request compilation works on copies.
- Unsupported or unsafe states fail open.
- Token Terminator does not replace the host memory/context engine.

## RTK executable trust boundary

If `TOKEN_TERMINATOR_RTK_PATH` is unset, executable discovery uses the host process `PATH`. A shadowed malicious `rtk` executable can influence rewrite decisions.

Security-sensitive deployments should pin the expected binary:

```text
TOKEN_TERMINATOR_RTK_PATH=/absolute/path/to/rtk
```

Protect the binary and its parent directory from untrusted writes.

## Recovery-safe retention

Automatic vault GC is allowed to reclaim abandoned evidence under capacity pressure, but not evidence already promised through accepted recovery receipts/exposures or active temporal references.

This distinction is essential: disk management must not silently break the model's recovery contract.

## Reporting vulnerabilities

Use a private GitHub security advisory rather than a public issue.

## v0.10.0 history-engine boundary

The explicitly selected engine persists full available message snapshots, including
sensitive source content, in the existing private vault. Pinned evidence survives
reset and pruning; plan retention, do not delete referenced artifacts. The new
history tool enforces session membership and hash verification; the general vault
tool's existing access scope is unchanged. With JEV enabled, bounded historical
regions plus query/recent referents cross the existing configured provider boundary.
Invalid scores cannot authorize omission. Source identity is not a truth verdict.
Unknown tokenizers/missing tools/stale bindings/capacity faults fail open. Hard host
limits before middleware and later third-party rewrites are outside the final gate.
See [Context Engine](Context-Engine) for complete limits.
