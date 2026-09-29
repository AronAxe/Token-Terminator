# Dashboard & Desktop counter (v0.11.0 candidate)

**Unreleased, opt-in addition in PR #19.** Run `token-terminator dashboard` and
open `http://localhost:7474`. The dark, responsive dashboard shows per-profile/bot
input savings and input/output usage, an exact-savings trend, configured model
rate cards and token-weighted value. API equivalents are not subscription cash
savings; output savings and net economics remain unknown without measurement.
No source text, credentials, LLM or tokenizer is needed to read the counters.

`token-terminator install-dashboard` adds the managed Hermes backend and Desktop
half. Enable the Python plugin and then the Desktop half in Capabilities →
Plugins, restarting the gateway for backend routes. A compact token count in the
bottom status bar opens an upward summary popover for the active connection and
profile. No Hermes core modification, auto-start or engine switch is performed.

Standalone defaults to local profile discovery; custom non-Hermes TT stores use
local source mappings. Duplicate databases and contradictory profile attribution
are refused rather than counted twice. The Desktop backend reads only its
already authorized task-local home; the standalone unauthed loopback server must
not be exposed publicly. Unknown data remains unknown. Historical mixed stores
are not automatically repartitioned.

Read [installation, configuration, accounting and security](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/docs/DASHBOARD.md).
