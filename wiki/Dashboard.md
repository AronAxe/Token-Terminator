# Observatory · dashboard and Desktop counter

**v0.11.0 · per-profile/bot accounting · read-only · opt-in.**

```bash
token-terminator install-dashboard
token-terminator dashboard
```

Open **http://localhost:7474** for aggregate and per-profile totals, a fourteen-day
input-savings trend, model/rate breakdown, coverage and recovery-read counts.
No model call or conversation-content read is performed. The server starts only
when invoked and binds to `127.0.0.1`; it is not publicly exposed by default.

## Hermes Desktop

Enable the Python `token-terminator` plugin and restart the gateway after installing
its backend. In **Capabilities → Plugins**, enable the Desktop half and reload as
needed. **TT ↓ …** in the bottom status bar opens a summary popover above it.
The native popover uses Hermes' authenticated backend and works without the separate
localhost server. Its counter follows the active gateway profile/connection, not an
independently focused tiled bot. A remote backend is not your local port 7474.

## What the numbers mean

| Figure | Meaning |
| --- | --- |
| Input saved | Exact measured savings across complete prepared-request identities; not confirmed billed sends |
| Input prepared / observed | Post-TT request counts versus separately recorded host usage |
| Output generated | Host-reported generation, not compacted tool-result text |
| Output saved | Not measured; no counterfactual generation baseline is available |
| API-equivalent value | Configured exact-model USD input/output rates, with token-weighted averages and coverage |
| Recorded charges | Existing host cost data, separate from hypothetical equivalents |

API equivalents are not subscription bill discounts or JEV/recovery-adjusted net
savings. Missing prices/usage remain unknown; character estimates are separate.
Shared/ambiguous legacy profile ledgers are not silently assigned to the default bot.

Standard local profile stores are discovered automatically. Other compatible TT bot
stores can use explicit local mappings. The native API reads only the authorized
profile home; cross-profile aggregation belongs to the explicitly configured local
server. No database is rewritten or migrated by the UI.

The localhost service is read-only and guarded against cross-origin/Host misuse,
but **is not user-authenticated** against other local users/processes. Do not
publicly proxy it. A full Electron/authentication end-to-end test is not claimed;
real localhost Chromium, SDK contribution and native backend contracts are tested.

[Full setup, rate-card format, measurement definitions and security](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/DASHBOARD.md)
