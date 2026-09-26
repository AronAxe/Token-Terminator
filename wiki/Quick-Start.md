# Quick Start

This page gets a Hermes Agent installation onto Token Terminator **v0.8.2** with the fewest moving parts.

## 1. Optional: install RTK

RTK is only required for terminal-command rewriting. Native compression, vaulting, recovery, request compilation, and token-aware acceptance work without it.

```bash
brew install rtk
```

For security-sensitive deployments, prefer an explicit executable path later with `TOKEN_TERMINATOR_RTK_PATH`.

## 2. Replace any older distribution

`token-terminator` and the old `rtk-hermes-plus` package both own the `rtk_hermes_plus` Python import package. Do not install them together.

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"

hermes plugins disable rtk-plus
hermes plugins disable token-terminator

"$HERMES_PY" -m pip uninstall -y rtk-hermes-plus token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.8.2'

hermes plugins enable token-terminator --no-allow-tool-override
```

On Windows, use the Hermes virtual-environment Python under `%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe`.

## 3. Optional: exact tokenizer alignment

```bash
"$HERMES_PY" -m pip install tiktoken tokenizers
```

Use a Hugging Face `tokenizer.json` or a supported tiktoken encoding through the configuration variables described in [Configuration](Configuration). If no exact tokenizer is available, the strict character-reduction invariant remains active.

## 4. Optional: enable Jev semantic context reduction

Jev is not required. The existing Token Terminator pipeline works without it.

OpenRouter (preferred automatically when its key exists):

```bash
export TOKEN_TERMINATOR_JEV=true
export OPENROUTER_API_KEY="..."
```

Or direct TypeSafe:

```bash
export TOKEN_TERMINATOR_JEV=true
export TOKEN_TERMINATOR_JEV_PROVIDER=typesafe
export TYPESAFE_API_KEY="..."
```

Never commit either key. You need only one provider key. Enabling Jev sends the bounded Jev state either through OpenRouter's Decisions API or directly to TypeSafe; see [Jev Semantic Context Gate](Jev-Semantic-Context-Gate) and [Security and Trust Model](Security-and-Trust-Model).

## 5. Start a fresh Hermes session

Then check:

```text
/token-terminator status
/token-terminator stats
```

You want to see the plugin enabled, the expected mode, and a usable vault. If temporal delta or token budgeting is configured, their status is shown here too.

## 6. First recovery smoke test

After a large supported tool result is compressed, its receipt contains an artifact ID. Recover the exact content with the model tool:

```json
{
  "action": "artifact_get",
  "artifact_id": "a_<content-address>",
  "offset": 0,
  "limit": 8000
}
```

If exact write/read-back verification fails, Token Terminator must leave the original result untouched.

## Recommended starting mode

Use `balanced` unless you have a specific reason not to. It enables terminal rewriting, temporal terminal deltas, native compression for large search/process results, and final request compilation without aggressive large-file rewriting.
