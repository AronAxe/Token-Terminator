# Live-compression adapter repair

The v0.11.0 adapter omitted the compatibility surface used by current Hermes
`_apply_live_compression_config`. That host function updates the selected
`context_compressor` even when it is a plugin ContextEngine, including calling
`_coerce_threshold_tokens_cap` and clearing lazy window/threshold caches.

This patch supplies positive-int/None cap normalization, lazy threshold and window
invalidation, current-route metadata resolution when an explicit pin is removed,
per-model threshold handling and isolated clone state. The current host request's
`budget_tokens` refreshes the engine's window without resetting response counters.
No hardcoded 272k or assumed replacement window is introduced. Host-side metadata
is reused; the underlying request tokenizer and reduction acceptance gate are not
relaxed. Internal service calls remain excluded. No generative compressor is built.

Nine offline regression tests passed against the installed Hermes checkout
`188a1a5efd098f067638032fea6e24c42d06178f` on Python 3.14. The tests call the real
live-config function with mocked model metadata and disposable stores. They do not
claim paid-provider validation or a reduction of an existing live session.

Operational state: applying the tested patch to the live managed installation was
blocked by the remote execution tool. No live adapter replacement or backend restart
was performed. The test candidate is retained separately. A partial older patch
was already present in the managed source; it must not be confused with repository
v0.11.0 or evidence that a running process has loaded a repair.

The observed host directory loader can expose a partially initialized cached module
to simultaneous discovery. This adapter patch does not modify that upstream loader
or claim to resolve its race. Deployment must use the host's managed plugin update
path and a controlled backend restart, then check loaded engine identity and actual
provider-request metrics. Do not kill unrelated relay/messaging/dashboard processes,
delete conversation/vault data, or claim a reset UI percentage proves reduction.
