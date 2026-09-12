# Vault and Exact Recovery

Exact recovery is not decorative metadata; it is part of the acceptance contract.

## Content-addressed artifacts

Large exact evidence is stored in a local SQLite vault. Artifact identity is derived from SHA-256 of the exact UTF-8 bytes. Normal IDs use:

```text
a_<first 32 lowercase SHA-256 hex chars>
```

A full-digest form is available as a collision fallback.

## Recovery actions

### `artifact_get`

Authoritative exact content, paged and bounded.

```json
{
  "action": "artifact_get",
  "artifact_id": "a_<id>",
  "offset": 0,
  "limit": 8000
}
```

### `artifact_peek`

Deterministic lossy synopsis: metadata, head/tail, signal lines, and shallow JSON structure when possible.

### `artifact_find`

Find matching lines inside one known artifact without returning all content.

### `artifact_search`

Search private artifacts by case-insensitive Unicode content/tool-name matching.

The layered views never replace the stored artifact. `artifact_get` remains authoritative.

## Evidence leases

The request compiler tracks whether an artifact has already been exposed inline. After the configured lease budget is exhausted, later provider requests may carry a small receipt instead of the same large evidence block.

Receipts intentionally exclude raw tool arguments and artifact content.

## Vault capacity and retention

v0.5.1 replaces a permanent hard-wall failure pattern with O(1) byte accounting and high/low watermarks.

At the high-water mark Token Terminator may prune the oldest eligible abandoned artifacts toward the low-water target. It does **not** treat all old artifacts as disposable.

Protected evidence includes, among other live references:

- artifacts used by active temporal snapshots;
- artifacts already named by accepted provider-visible recovery receipts/exposures;
- exact artifacts named by accepted temporal deltas.

If capacity cannot be made safe without deleting protected evidence, the write fails open and the host keeps the original content.

## Storage behavior

The vault uses SQLite WAL, `synchronous=NORMAL`, bounded busy retries, foreign keys, short-lived connections, and `BEGIN IMMEDIATE` writes. Keep it on a local filesystem; SQLite WAL is not a network-filesystem coordination protocol.

On POSIX, newly created private directories are `0700` and database files are `0600`. Existing parent directories are not silently re-permissioned.
