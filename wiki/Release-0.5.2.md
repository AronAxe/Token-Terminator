# Release 0.5.2

**Date:** 2026-09-15

v0.5.2 turns tokenizer-aware acceptance into durable tokenizer-aware accounting. Token Terminator now records exact raw, final, and saved request tokens whenever a supported tokenizer is available, together with model and tokenizer-backend provenance.

## Highlights

- Persistent per-request exact token savings and tokenizer coverage reporting.
- `tiktoken` installed by default for automatic supported OpenAI-family measurement.
- Provider-qualified OpenAI model names normalized for tokenizer lookup.
- Active model identity propagated into native and temporal compression accounting.
- Character counts retained as the deterministic reduction invariant and audit trail.
- Explicit `chars/4` fallback labelling where no exact tokenizer is available.
- README now links directly to this GitHub Wiki.

## Compatibility

The artifact vault remains compatible with v0.5.1. No destructive data migration is required. The public Python import package remains `rtk_hermes_plus`.
