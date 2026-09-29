# Migration and Rollback

## v0.9.0 → v0.11.0

The unshipped v0.10.0 milestone is included in v0.11.0. Back up the private TT
vault, ledger and Hermes configuration before upgrading. Keep evidence pins:
resetting counters or uninstalling the package must not silently remove originals.

Use the Python interpreter that actually runs Hermes:

```bash
python -m pip install --upgrade \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.11.0'
python -m rtk_hermes_plus.cli install-context-engine
```

Remove the old `rtk-hermes-plus` distribution first if present: it shares the
`rtk_hermes_plus` import namespace with `token-terminator`. Do not install both.

Enable the general `token-terminator` plugin. To replace LCM or the built-in
compressor, explicitly select **Provider Plugins → Context Engine → Token
Terminator**, allow `context_engine` in restricted toolsets, and restart Hermes.
Only one engine owns context selection. Keeping another engine selected preserves
middleware-only operation. Existing OpenRouter/direct TypeSafe credentials remain
valid; JEV and Context IR still need their existing opt-in settings.

The installer does not edit `config.yaml`, enable the plugin or change your running
profile. It installs managed engine, backend and Desktop adapter files in the
chosen Hermes home. Install separately in other profile homes where needed.

## Dashboard and learned-policy activation

`token-terminator install-dashboard` installs the managed adapter assets without
selecting an engine. Enable its Desktop half under **Capabilities → Plugins** and
reload Desktop after restarting the gateway. Run `token-terminator dashboard` to
start the separate read-only service on localhost:7474. No server starts on import.
See [Dashboard](Dashboard) for profile discovery, rates and ambiguous legacy stores.

The learned policy remains `off`. Training requires explicit labelled data;
deployment requires a reviewed artifact and approved SHA-256. Start with `shadow`
before considering `active`. Training does not activate a policy, export the live
vault or change JEV's weights. See [Learned Policy](Learned-Policy).

## Return to middleware-only operation

Select your installed LCM engine or `compressor`, then restart Hermes. Keep the
general TT plugin enabled for middleware. For exact-history workloads, set
`TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS=0` to disable the legacy preview-based
age-collapse path. The selected TT ContextEngine already excludes that path.

## Roll the package back to v0.9.0

First select another context engine and disable the Desktop component. Stop
Hermes/the gateway. Remove **only TT's managed adapter files** from the relevant
`<HERMES_HOME>/plugins/token-terminator/` directory:

```text
__init__.py
plugin.yaml
dashboard/plugin_api.py
dashboard/manifest.json
dashboard/noop.js
desktop/plugin.js
```

Do not delete unrelated files, user configuration, the private evidence vault,
or an LCM archive. Install the v0.9.0 package, re-enable ordinary TT middleware
as appropriate, and restart. An older package cannot import the new engine or
Desktop/backend adapter. Disable the learned layer with
`TOKEN_TERMINATOR_LEARNED_POLICY_MODE=off` when rolling back.

Full available history is not destructively shortened by the new engine. It cannot
reconstruct originals already missing from an older LCM transcript, and it does not
import an external LCM archive. Persistent pins can fill storage; plan retention.

The repository [MIGRATION.md](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/MIGRATION.md)
is the detailed operational reference, including earlier version transitions.
[Release history](Home#release-history) preserves the earlier release notes.
