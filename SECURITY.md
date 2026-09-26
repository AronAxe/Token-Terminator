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

## RTK executable trust boundary

When `TOKEN_TERMINATOR_RTK_PATH` is unset, Token Terminator discovers `rtk` through the host process `PATH`. A malicious or accidentally shadowed executable named `rtk` can therefore influence command rewriting. Security-sensitive deployments should pin the expected executable with `TOKEN_TERMINATOR_RTK_PATH` and protect that file and its parent directory from untrusted writes. Token Terminator still invokes RTK with an argument array and `shell=False`; executable discovery is the separate trust boundary.

## Optional Jev external-service boundary

Jev integration is disabled by default. Enabling it requires both `TOKEN_TERMINATOR_JEV=true` and an API key supplied through `TOKEN_TERMINATOR_JEV_API_KEY` or `TYPESAFE_API_KEY`.

The key is read from the process environment only. Token Terminator does not write it to the repository, artifact vault, experiment ledger, request metrics, or status output.

When Jev is enabled, Token Terminator sends a bounded state object to TypeSafe's `https://api.typesafe.ai/v1/systemone` endpoint. That state contains the current user request and selected prior **plain-text user/assistant** candidate messages. System/developer messages, tool messages and results, messages containing tool calls, structured/multimodal content, and the current user message as a removal candidate are excluded.

Jev is not trusted with destructive authority. Its typed relevance/guard probabilities can only nominate an eligible prior message for compaction. Token Terminator must first write and read back the exact message from the local vault, prove that the recovery receipt makes the complete request smaller, and—when exact token measurement is available—prove that it also uses fewer tokens. Network errors, timeouts, malformed responses, missing answers, storage failures, and failed size gates all leave the already-reduced non-Jev request unchanged.

