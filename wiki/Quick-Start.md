# Quick Start · v0.11.0

Install into the Python environment that runs Hermes. Replace `python` below with
that interpreter when needed; a system-wide install in another environment will
not make the plugin visible to Hermes.

## 1. Install the release

Back up the TT evidence vault before changing packages. The older `rtk-hermes-plus`
distribution must not coexist with `token-terminator`: both own the same import
package. Disable/remove that legacy distribution first if installed.

```bash
python -m pip install --upgrade \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.11.0'
python -m rtk_hermes_plus.cli install-context-engine
hermes plugins enable token-terminator --no-allow-tool-override
```

The managed installer also includes the optional Desktop/backend files. It does
not edit `config.yaml`, select an engine, enable Desktop, or start a server.
Do not enable a duplicate RTK rewrite adapter. The optional `rtk` binary is only
needed for terminal-command rewriting, not native compression, recovery or IR.

## 2. Choose middleware or ContextEngine

**Keep another engine:** leave your existing Context Engine selection unchanged;
TT runs as middleware. For exact old-dialogue workloads in legacy middleware,
set `TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS=0`.

**Replace LCM/compressor:** in `hermes plugins`, choose
**Provider Plugins → Context Engine → Token Terminator**. Equivalent YAML,
while preserving your other enabled plugins:

```yaml
plugins:
  enabled:
    - token-terminator
context:
  engine: token-terminator
```

Allow `context_engine` in restricted toolsets. Only one context engine owns the
lifecycle. Restart Hermes/gateway, then verify `token_terminator_history` with
`{"action":"status"}` in the running session.

## 3. Enable optional semantic attention and IR

```bash
export TOKEN_TERMINATOR_MODE=balanced
export TOKEN_TERMINATOR_JEV=true
export TOKEN_TERMINATOR_CONTEXT_IR=true
```

Reuse your existing **OpenRouter OR direct TypeSafe** key and provider setting.
Never commit keys. JEV uploads bounded semantic state only after explicit opt-in;
IR itself is local. ContextEngine and IR require the actual target tokenizer.
Supported tiktoken models are automatic; other models need a matching configured
counter/tokenizer, not an unrelated model's tokenizer.

## 4. Open the dashboard

```bash
token-terminator dashboard
```

Open **http://localhost:7474**. For dashboard-only managed installation,
`token-terminator install-dashboard` does not select a context engine. Enable the
Desktop half under **Capabilities → Plugins**, restart the gateway as needed, and
click **TT ↓ …** in the bottom status bar. The popover does not need the standalone
server. Install the adapter in each intended Hermes profile home.

## 5. Keep learning off until a policy is reviewed

The learned layer is off by default. Training needs explicit labelled experiments,
optional `[learning]` dependencies and either replay or consented live collection.
A private artifact and approved SHA-256 are required before `shadow` or `active`.
Nothing trains or activates merely because it is installed.

[ContextEngine guide](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/CONTEXT_ENGINE.md) ·
[Dashboard](Dashboard) · [Learning](Learned-Policy) ·
[Configuration](Configuration) · [Migration](Migration-and-Rollback)
