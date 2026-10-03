# Hermes live-compression compatibility repair

This patch adds the adapter members used by current Hermes Desktop/TUI live
configuration. It does not change semantic selection, tokenizers or transcript
retention, and does not run Hermes' built-in generative summarizer.

## Fixed

- `_coerce_threshold_tokens_cap` accepts a positive integer or null/invalid input.
- `threshold_tokens` responds to `_threshold_tokens = None` invalidation.
- Threshold arithmetic includes the host's output reserve and small-window floor.
- Live context-length changes and removal of explicit pins are honored. Re-resolution
  uses this engine's route metadata rather than a previous model/profile's window.
- Clones preserve threshold configuration while retaining isolated locks and caches.

## Installed-host regression

`python scripts/smoke_hermes_live_config.py` runs eleven tests against the actual
`tui_gateway.session_compression._apply_live_compression_config` function. It needs
Hermes and TT installed in the same environment (or Hermes on PYTHONPATH). Model
metadata lookup is mocked; no paid provider calls or live-profile writes occur.
Vault fixtures are temporary. The tests reject construction of ContextCompressor.

Executed on Windows/Python 3.14 against Hermes commit
`188a1a5efd098f067638032fea6e24c42d06178f`: 11 passed. This is not a claim that the
entire test suite or every multiplex lifecycle race has been certified.

## Deployment precautions

A managed Hermes launcher may resolve TT from an editable plugin source in its
managed environment, not from an older `hermes-agent/venv` directory. Identify the
package after the launcher's normal bootstrap before patching. Back up originals,
validate imports/tests, then restart the correct idle backend once. Do not launch
competing replacement gateways, clear histories, or delete exact-evidence storage.

The host plugin loader can expose a partially initialized module during concurrent
discovery. This patch does not alter that host-wide loader or claim to eliminate
that race. Verify TT registration/API availability after the controlled restart.

## Independent tokenizer and window failures

An unknown target tokenizer still causes ContextEngine/IR to pass through rather
than invent an exact measurement. A successful compatibility test or a healthy
restart does not prove the current provider request was reduced. Inspect current
model-specific request telemetry; older rows for other models are not evidence.

This patch does not override model.context_length pins, guess a replacement for a
stale provider catalog value, or equate a tokenizer for another model with the
actual target. Those are separate operational conditions, not fixed by supplying
one missing method. No published tag or release is modified.
