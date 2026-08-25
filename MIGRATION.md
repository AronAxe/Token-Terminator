# Migration and rollback: 0.2.0 → 0.4.0

Token Terminator 0.4.0 replaces RTK Hermes Plus 0.2.0. This is a package replacement, not an in-place dual installation.

## Boundary

| Concern | 0.2.0 | 0.4.0 |
|---|---|---|
| Distribution | `rtk-hermes-plus` | `token-terminator` |
| Hermes plugin key | `rtk-plus` | `token-terminator` |
| Slash command | `/rtk-plus` | `/token-terminator` |
| Environment prefix | `RTK_HERMES_PLUS_*` | `TOKEN_TERMINATOR_*` |
| Python import package | `rtk_hermes_plus` | `rtk_hermes_plus` |
| Private data root | legacy `rtk-plus` paths | `<HERMES_HOME>/token-terminator/` |
| Hermes context engine | unchanged | unchanged |

Both distributions own the same Python import package. They must not coexist.

Token Terminator does not migrate or delete 0.2.0 recovery files or experiment data automatically. It begins with a new content-addressed artifact vault. Legacy environment aliases are accepted for one migration release, with `TOKEN_TERMINATOR_*` taking precedence.

## Pre-change record

Run these before the maintenance window and retain the output:

```bash
hermes plugins list
<hermes-python> -m pip show rtk-hermes-plus token-terminator
```

Record any `RTK_HERMES_PLUS_*` values you intend to translate. Do not copy legacy rotating recovery files into `artifacts.sqlite3`; the formats and retention models are different.

## Install and activate

Perform the package replacement while no Hermes process is importing `rtk_hermes_plus`.

```bash
hermes plugins disable rtk-plus
<hermes-python> -m pip uninstall -y rtk-hermes-plus token-terminator
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.4.0'
hermes plugins enable token-terminator --no-allow-tool-override
```

If a release tag cannot be resolved, use the reviewed release commit SHA instead. Never install an unpinned moving branch into a production profile.

Commence a new Hermes session after enablement. Do not run both `rtk-plus` and `token-terminator`, and do not enable another terminal rewrite plugin alongside Token Terminator.

## Post-change verification

Verify all of the following:

```text
/token-terminator status
```

- plugin key is `token-terminator` and version is `0.4.0`;
- `vault_available` is `true`;
- the selected mode is correct;
- Hermes' existing context engine is still active;
- an ordinary non-compressible tool call behaves unchanged;
- a large supported native result receives an artifact receipt;
- `token_terminator artifact_get` can recover the artifact exactly across pages;
- LCM/history behavior and unrelated plugins remain unchanged.

The decisive runtime switch is the enabled plugin key. Package installation alone does not activate the plugin for an existing session.

## Rollback

Disable Token Terminator first, then replace it with the immutable 0.2.0 commit that preceded the rename:

```bash
hermes plugins disable token-terminator
<hermes-python> -m pip uninstall -y token-terminator rtk-hermes-plus
<hermes-python> -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@2ef250cca98f691eba82e193bd8c26fd4ab652f4'
hermes plugins enable rtk-plus --no-allow-tool-override
```

Commence a new Hermes session and verify `/rtk-plus status`.

Rollback does not require Hermes core, LCM, transcript, or state-database migration. It also does not delete `<HERMES_HOME>/token-terminator/`; retain that directory for forensic recovery or remove it separately only after confirming it is no longer needed.
