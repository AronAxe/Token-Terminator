# Metrics and Experiments

Token Terminator separates local optimization telemetry from claims about model quality.

## Hermes commands

```text
/token-terminator status
/token-terminator stats
/token-terminator compare
/token-terminator compare native balanced
/token-terminator reset-stats
```

## Request metrics

Durable request rows distinguish:

- compiler-stage savings: `raw_chars - compiled_chars`;
- compactor savings: `compiled_chars - final_chars`;
- measured end-to-end savings: `raw_chars - final_chars`.

When an exact tokenizer is available, token counts are recorded alongside character counts. Native/temporal token savings use exact measurements when available; otherwise the fallback estimate is explicitly labelled rather than presented as exact.

## Experiment ledger

The experiment ledger stores content-free session/turn data:

- session/turn identifiers;
- mode/model/provider labels;
- token and cost totals;
- transformation counters;
- salted local prompt fingerprints.

It does not store prompts, commands, or tool contents.

## Comparison rules

A valid comparison should use fresh sessions, stable modes, the same model/settings, and representative repeated tasks. Mode/model drift contaminates a session and excludes it.

v0.5.1 hardens comparison output by:

- rejecting identical-mode comparisons;
- matching by salted prompt fingerprint + model;
- aggregating repeated observations within a matched group instead of arbitrary `zip()` pairing;
- reporting eligible, paired, and unpaired observations;
- reporting mean/median deltas;
- adding deterministic 95% bootstrap intervals.

## Quality is separate

Structural token reduction does not prove answer quality. Use the repository's paired non-inferiority quality harness for controlled answer-quality evaluation. Token savings cannot compensate for a lower-quality answer.
