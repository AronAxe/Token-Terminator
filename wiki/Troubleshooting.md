# Troubleshooting

## `/token-terminator status` says the vault is unavailable

Check the configured `TOKEN_TERMINATOR_DB_PATH`, parent-directory permissions, local filesystem availability, and whether another process is holding/migrating the database abnormally.

Token Terminator should fail open while storage is unavailable.

## Large output was not compressed

That can be correct. Check:

- active mode;
- tool name is eligible;
- result exceeds the relevant minimum size;
- backend is allowed;
- exact vault write/read-back succeeded;
- candidate including the recovery note is actually smaller;
- exact tokenizer did not show token expansion.

A non-reduction is preferable to a misleading or larger reduction.

## Temporal delta never appears

Check:

- mode is `balanced` or `aggressive`;
- temporal delta is enabled;
- result size exceeds `TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS`;
- the same temporal identity has a previous baseline;
- the second diff/no-change receipt is actually smaller than the raw current result.

The first observation usually creates the baseline.

## Same command behaves differently in two directories

That is expected when RTK rewrite decisions depend on repository/workspace context. v0.5.1 includes canonical working directory in rewrite-cache identity.

## Unicode artifact search misses a match

v0.5.1 uses Python `casefold()` through SQLite for Unicode-correct case-insensitive substring matching. Confirm you are actually running v0.5.1 and not an older installed package.

## Context collapse seems too aggressive

Check:

```text
TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS
TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS
```

The collapse setting must be `0` or at least the inline-recent value. The default is `6` and `5`.

Remember: compaction changes the provider-bound copy, not the persisted host transcript.

## Vault reaches capacity

Inspect status/usage telemetry and watermarks. v0.5.1 prunes only eligible unprotected evidence. If protected evidence consumes the available budget, new vault writes may still fail open rather than break recovery guarantees.

## RTK appears to be the wrong executable

Set `TOKEN_TERMINATOR_RTK_PATH` to the exact trusted executable and verify the parent directory is not writable by untrusted users.

## Compare output looks suspiciously perfect

Do not compare a mode to itself. Use fresh stable sessions with the same model/settings. Inspect paired/unpaired counts and bootstrap intervals rather than relying on a single mean.
