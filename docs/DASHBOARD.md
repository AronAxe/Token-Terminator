# Token Terminator Observatory

**v0.11.0 review candidate · PR #19 · read-only and opt-in.**

A local dashboard at `http://localhost:7474` shows per-profile/bot input savings,
input/output usage, rate-card equivalents and a fourteen-day savings trend.
The matching Hermes Desktop extension contributes a compact `TT ↓ 12.3K` number
to the **bottom status bar**. Click it to open a summary above the bar.
No server or window starts automatically when an agent imports TT.

## Start the main dashboard

Install this candidate in the environment that already runs TT, then:

```bash
token-terminator dashboard
```

Open `http://localhost:7474`. Stop with Ctrl+C. The server binds **only IPv4
loopback (`127.0.0.1`)**, never `0.0.0.0`. A port already in use fails visibly;
it does not pick a different port behind your back. `--port` can explicitly
choose another port. The Desktop button targets the requested default 7474.

By default the dashboard reads the normal TT databases under your Hermes home
and its direct `profiles/<name>` children. Launching from a named profile uses
the parent Hermes root for the standalone all-profile view. An explicit
`--hermes-home` is respected without unwrapping. OS-native Hermes home resolution
is retained. Other runtimes and custom stores use a local source mapping:

```bash
token-terminator dashboard --hermes-home /local/hermes-root
# or, for explicitly configured non-Hermes bot stores:
token-terminator dashboard --config /local/settings/tt-dashboard.json
```

This is a process you start, not an installed background service. Keep that
terminal running, or use your existing process manager. No Docker, frontend
build, extra LLM, external analytics account or new credential is needed.

## What is measured

| Display | Source and meaning |
| --- | --- |
| **Input saved** | Sum of existing `request_token_metrics.raw_tokens - final_tokens`, validated and grouped once per `(session_id, request_id)`. Canonical complete prepared requests measured by the runtime's configured tokenizer, **not** confirmed sends or provider billing framing. |
| **Input prepared** | Final token counts for those same measured request identities. Not added to host usage. |
| **Input used / output generated** | Host-reported session deltas already persisted in TT's `experiments.sqlite3` ledger since TT attachment. Lifecycle-hook updates, not a live per-token stream. |
| **Output saved** | **Not measured**: there is no counterfactual generation without TT. Native tool-output compression reduces later model input, not generated model output. |
| **Character estimate** | End-to-end character savings divided by four only for request identities without exact token rows. Shown separately and never added to the exact headline. |
| **API-equivalent input saving** | Measured saved input multiplied by configured input rate per model. Gross illustrative value, not a cash/net saving. |
| **Output usage value** | Observed output multiplied by the separate configured output rate, only for uncontaminated single-model sessions. The priced fraction is shown. |
| **Weighted averages** | Input value per million **covered saved input** tokens; output value per million **covered observed output** tokens. Models are weighted by tokens, not an unweighted average of price cards. |
| **Recorded actual cost** | Existing host-reported ledger charge, if supplied, with session coverage. Subscription-included marginal usage may be zero; the monthly subscription fee is not in this ledger. |

Session totals are not added to turn totals. Repeated updates to the same request
identity are not separate savings. A retry with a different identity can be a
separate prepared request, but this is still not proof either request was billed.
Stage counters and native tool-output counters are never added again. Usage and
prepared-request windows are different, so their totals need not match. Exact
coverage is among recorded exact/character-only request identities, not a claim
of coverage of every request the host ever made.

The fourteen-day chart uses the last recorded timestamp of each request identity,
in UTC; the cards/tables cover all records currently retained in the databases.
Deleted/pruned accounting cannot be reconstructed. Missing tables, absent host
usage, locks, corrupt files and read-budget exhaustion produce explicit partial
or unavailable status, not invented zeroes. Numerical estimates cannot prove
answer quality. JEV overhead, cache-price effects, full recovery-resend costs,
quota extension and **net savings** are not inferred.

## API versus subscription valuation

An API rate card answers: **what would these measured tokens be worth at this
assumed input/output price?** It does not identify which omitted prefix would
have received a cache discount, or deduct JEV/service overhead.

A subscription buys a plan. The same rate-card figure is labelled an
**API-equivalent comparison**, not money taken off the subscription bill.
No tokens-to-quota percentage or monthly fee allocation is fabricated. Billing
mode is inferred only from recorded billing/status metadata, or explicitly
supplied locally. Mixed or unrecognized billing remains labelled as such.
All current valuation is in **USD**; there is no currency conversion or automatic
price fetch. `as_of` is a user-supplied rate-date/provenance label, not a freshness
certification. Changing a rate card revalues retained records using that card;
this is not a historical invoice-rate database.

## Local configuration

The optional file is `<hermes-home>/token-terminator/dashboard.json`, or the
explicit `--config` file. Only `sources` and `rates` are accepted. With no
`sources`, standard profile discovery remains active. Example rate numbers below
are **illustrative placeholders**, not quotes for a real model:

```json
{
  "rates": {
    "YOUR-EXACT-MODEL-ID": {
      "input_usd_per_million": 1.0,
      "output_usd_per_million": 4.0,
      "as_of": "replace with your verified rate and date"
    }
  }
}
```

Exact model identities, including provider prefixes where recorded, are matched;
missing prices remain unknown. Output sessions that changed model cannot be
priced at their final model's rate. Existing ledger API-equivalent figures are
not combined with this independently configured valuation.

An explicit list replaces automatic discovery. Supply absolute local paths:

```json
{
  "sources": [
    {"id":"default", "label":"Hermes", "home":"/local/hermes-root", "billing":"subscription"},
    {"id":"brain", "label":"Brain", "home":"/local/hermes-root/profiles/brain", "billing":"api"},
    {"id":"other-agent", "label":"Other agent", "vault":"/local/other/vault.sqlite3", "ledger":"/local/other/experiments.sqlite3", "billing":"unknown"}
  ]
}
```

This supports compatible TT stores from other runtimes, not arbitrary unrelated
agent database schemas. Custom existing TT DB/ledger environment overrides are
**not guessed from `.env` files**; map their actual paths here. One physical
DB may not be mapped to two sources, including via a hard link. A multi-profile
legacy ledger is marked ambiguous, and its counts are withheld rather than
credited to a default bot. Standard discovered sources also verify stored
profile names. A single legacy alias can be mapped explicitly; this does not
reconstruct per-profile history that was never attributed. No database is moved,
rewritten or deleted by the dashboard.

Up to 64 sources, 128 rate cards and 256 model groups per source are supported.
Reads use SQLite `mode=ro`, `query_only`, existing WAL snapshots, short lock/query
timeouts, a bounded aggregate deadline and a five-second cache. A slow source
cannot block the agent: the standalone server is separate and the Desktop read
runs in its backend's worker pool. Requests are bounded; incomplete totals are
visibly partial. These controls do not preempt an arbitrarily stalled filesystem.

## Hermes Desktop installation

Use the Python environment belonging to Hermes:

```bash
token-terminator install-dashboard
# install-context-engine also installs these same managed UI/backend files.
```

The installer writes only its managed files under
`$HERMES_HOME/plugins/token-terminator/`. It rejects symlinked destinations or
unmanaged files. It does **not** change `config.yaml`, select a ContextEngine,
start the 7474 server, enable a plugin, or edit Hermes core.

1. Enable the **Python token-terminator plugin** in `hermes plugins` or your
   existing `plugins.enabled` configuration. Preserve other enabled entries.
2. In Desktop **Capabilities → Plugins**, Rescan as needed and enable the
   **Token Terminator Desktop half**. Current Desktop discovers the packaged
   `desktop/plugin.js` automatically. Restart the gateway after adding backend
   routes. A hidden status bar must be shown using Desktop's own visibility
   control.
3. Click the bottom-bar counter. The popover summarizes the **active gateway
   profile**, clearly labelled; it is not mislabelled as an independently focused
   split-pane bot. Start `token-terminator dashboard` to use its local link.

Keep `context.engine: token-terminator` only when you intend TT to own the
ContextEngine lifecycle; the dashboard also works with middleware-only mode.
No JEV setting or learned-policy activation is required to view recorded data.

Desktop uses the supported SDK status-bar and Popover contributions, React Query
and **`ctx.rest`**. Its cache keys contain connection identity, active profile and
backend target profile. Route inventory is asynchronous and cached. Profile
changes during a read are discarded. Summary refresh is ten seconds while
connected/visible; stale data is marked. It uses the existing authenticated
Hermes backend, not direct cross-origin browser access to port 7474.

The backend reads **only the already authorized profile home** and refuses
external configured stores there; those are available only through the explicitly
configured standalone server. It follows Hermes' task-local home binding rather
than the launch process environment. Configuration's home lookup was corrected
for the same reason so new profile-local TT accounting/vault paths remain isolated;
explicit `TOKEN_TERMINATOR_DB_PATH` / ledger overrides still take precedence.
Old shared data is not silently repartitioned.

On remote connections the widget queries that remote backend. It does not open
your laptop's unrelated localhost dashboard. Run the standalone server on the
intended host and deliberately tunnel its loopback port. The Desktop package
must also be installed locally when using a remote-only agent installation.

SDK and backend contract checked against official Hermes commit
`fd0b98f6256446a9115c54f1a92ace5ea74c929f`. Older Desktop builds lacking the SDK
contributions/routing API are not supported; the standalone dashboard still works.
No full Electron installation or authentication end-to-end test is claimed by the
isolated contribution/backend tests.

## Security and rollback

The standalone service is **not user-authenticated**: any process/user able to
reach this machine's loopback can read the numeric accounting. Do not expose it
through a public proxy. Exact Host validation, same-origin/Fetch-Metadata checks,
no CORS, a restrictive CSP, no-store, frame denial and escaped DOM text defend the
browser boundary. No HTTP endpoint reads arbitrary paths, writes settings,
resets counters or returns messages, artifacts, request IDs, session IDs or keys.
Profile labels, model identities, counts and configured prices are visible.

No source-content table is read and no provider/tokenizer/learning work is invoked.
The normal Hermes host's authentication/profile-scope plumbing remains its own
responsibility. Local configured paths and installed plugin code are trusted;
this is not isolation from an adversary who can replace the user's filesystem.

Stop the dashboard process and disable the Desktop half to remove the UI. To
remove Python backend exposure, disable TT's Python plugin only when you also
intend to disable its other runtime contributions, then restart the gateway.
Keep your vault and ledger for exact recovery. The UI does not change learned
policy mode, context selection, optimizer thresholds, request scope or retries.
