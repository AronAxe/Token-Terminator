# Security and Trust Model

Token Terminator intentionally stores exact evidence locally because exact recovery is part of its product contract.

## Private data

By default plugin-owned files live under:

```text
<HERMES_HOME>/token-terminator/
```

The artifact vault may contain raw tool artifacts, tool arguments, provenance, observations, exposure records, temporal state, bounded working state, and request-reduction metrics.

The separate experiment ledger stores content-free accounting and salted prompt fingerprints. It does not store prompt text, command strings, or tool contents.

The plugin itself does not upload this private data.

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
