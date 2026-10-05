# Hermes TT discovery repair

The reviewed Hermes shared directory loader inserts a new module into sys.modules
before running it, but treats a cached module with __file__ as ready. Concurrent
requests can receive that half-module. User engine module names also contain only
the plugin slug, not the profile path. These are initialization and isolation bugs.

## What 0.11.2 installs

The explicit `token-terminator install-context-engine` command requests the repair.
It patches only a reviewed loader file with normalized SHA-256
`402d3fd6f6077c344f15713ac3b793fbccbe0602181bceff7a23690270e3ff35`, checked against
Hermes `188a1a5efd098f067638032fea6e24c42d06178f` and the installed affected source.

The appended wrapper applies only to token-terminator in the user ContextEngine
namespace. A lock covers the original load until initialization finishes. Other
profiles receive path-derived namespaces; unrelated plugins retain original
behavior. Recursive same-thread loads return unavailable, never a partial module.
Waiting is bounded to ten seconds. Failed imports remain retryable.

No plugin-only hook can repair a lookup that happens before that plugin starts.
This release therefore makes the host-file change explicit. It is not a general
Hermes plugin-loader rewrite, new runtime dependency, or replacement context engine.

The original bytes are backed up beside the source as
`plugin_loader.py.tt-before-0.11.2`. The installer refuses unknown source versions,
modified patches, symlinks, mismatching backups and concurrent source changes.
Package import and ordinary middleware do not write host files. The Python
`install_context_engine` API defaults to `repair_discovery=False`; callers that
want the explicit CLI behavior pass `repair_discovery=True`.

## Verification and rollback

`tests/test_discovery_repair.py` deterministically holds one initialization open
while another lookup arrives. It also tests 64 parallel calls and profile isolation.
Set TT_HERMES_LOADER to a copy or checkout of the actual reviewed plugin_loader.py
to test its real implementation; tests only modify temporary files.

After installation, restart the correct idle backend once and verify discovery and
provider-request measurements. Do not delete history, vaults or unrelated plugins.
To roll back, stop the affected backend and restore the adjacent original backup
only after checking that no subsequent Hermes changes would be overwritten. If
Hermes upgrades its loader, review that new implementation rather than forcing this
patch onto it. A successful health check alone is not proof of token reduction.
