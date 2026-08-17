# Security

Please report suspected vulnerabilities through a private GitHub security advisory rather than a public issue.

## Data boundaries

Token Terminator stores exact large tool artifacts and private provenance locally because exact recovery is part of its acceptance contract. By default, plugin-owned files live under:

```text
<HERMES_HOME>/token-terminator/
```

The artifact vault stores raw artifact text, content digests, tool names, tool arguments, observations, exposure leases, optional bounded working state, and request-reduction metrics. The separate experiment ledger stores session/turn identifiers, mode/model/provider labels, token/cost totals, transformation counts, and salted local prompt fingerprints. It does **not** store command strings, prompts, or tool contents.

Nothing is uploaded by the plugin.

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
