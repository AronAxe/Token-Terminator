# Temporal Delta Compression

Temporal delta compression reduces repeated **terminal observations**, not terminal execution.

## The sequence

For an eligible large terminal result in `balanced` or `aggressive` mode:

1. the terminal command executes normally;
2. the exact current output is stored and verified in the vault;
3. Token Terminator finds the previous baseline for the same temporal identity;
4. it builds a unified diff or compact no-change receipt;
5. the candidate is accepted only if it is strictly smaller than the current raw output;
6. previous/current exact artifacts named by an accepted delta are protected from automatic GC.

The first observation usually establishes a baseline and is not reduced by the temporal path.

## Identity

Temporal state includes command/workspace information and the configured scope:

- `session` keeps baselines within a session;
- `workspace` allows reuse across the same workspace identity.

The implementation still executes the command on every observation. A stale cached terminal result is not substituted for live execution.

## Failure behavior

Missing baselines, missing artifacts, storage failures, malformed arguments, small results, or non-smaller deltas simply disable the temporal optimization for that result.

## Async parity

v0.5.1 routes `AsyncRuntime` through the same temporal semantics as the synchronous runtime. The async façade retains cancellation-aware RTK subprocess behavior while avoiding a separate, divergent optimization policy.
