<p align="center">
  <img src="docs/assets/hero.webp" alt="A wide stream of terminal data compressed through a winged prism into a small beam of useful AI context" width="100%">
</p>

<h1 align="center">RTK Hermes Plus</h1>

<p align="center">
  <strong>Keep the useful signal. Stop paying tokens for the noise.</strong><br>
  Token-first <a href="https://github.com/rtk-ai/rtk">RTK</a> integration for
  <a href="https://github.com/NousResearch/hermes-agent">Hermes Agent</a>.
</p>

<p align="center">
  <a href="https://github.com/AronAxe/rtk-hermes-plus/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/AronAxe/rtk-hermes-plus/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.10–3.13" src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-22c55e.svg"></a>
  <img alt="No prompt overhead" src="https://img.shields.io/badge/prompt%20overhead-zero-8b5cf6">
</p>

`rtk-hermes-plus` transparently rewrites compressible terminal commands through
RTK and shortens oversized results from Hermes-native tools. It adds **no
model-visible tool, no MCP server, and no standing prompt text**. If Plus or RTK
cannot safely improve something, the original request or result passes through.

## The result

An independent benchmark against the RTK v0.45.0 source tree used real
`o200k_base` tokenization rather than the common `bytes / 4` estimate:

| Hermes result | Raw tokens | Plus tokens | Reduction |
|---|---:|---:|---:|
| Native `search_files` result | 99,239 | 2,555 | **97.4%** |
| Repetitive process log | 16,999 | 2,296 | **86.5%** |
| Aggressive native `read_file` | 27,442 | 3,110 | **88.7%** |

These are deliberately large results where compression is valuable—not a claim
that every session becomes 97% cheaper. Small results are untouched, and model
output, conversation history, system prompts, and unrelated tools remain outside
this plugin's control.

## Why Plus exists

The existing Hermes adapters stop at terminal-command rewriting. Hermes also
uses native tools such as `search_files`, `process`, and `read_file`; their
results never pass through RTK. Plus covers both paths without spending tokens
advertising itself to the model.

| Capability | Basic RTK adapter | RTK Hermes Plus |
|---|:---:|:---:|
| Transparent terminal rewriting | ✓ | ✓ |
| Modern Hermes request middleware | — | ✓ |
| Native search/process compression | — | ✓ |
| Optional structured `read_file` compression | — | ✓ |
| Positive and negative rewrite cache | — | ✓ |
| Full-result recovery | RTK terminal behavior | ✓ native + terminal |
| Remote-backend safety gate | varies | ✓ |
| RTK/pytest double-quiet guard | — | ✓ |
| Durable, content-free mode comparison | — | ✓ |
| Standing prompt/tool-schema tokens | 0 | **0** |

## How it works

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Architecture showing terminal rewriting and native tool-result compression paths" width="100%">
</p>

There are two independent paths:

1. **Terminal requests** — Plus asks `rtk rewrite` whether a command has a safe,
   token-efficient RTK equivalent. The exact decision is cached. A timeout,
   unsupported command, excluded backend, or error means pass-through.
2. **Native results** — large results from selected Hermes tools are
   deterministically compacted. The full original is stored in a private,
   rotating recovery file and a short pointer is appended to the compact result.

For example, the model can request this normally:

```text
git status
```

Hermes executes the RTK form without another model turn:

```text
rtk git status
```

The model receives RTK's concise result. It never needs to know that Plus exists.

## Quick start

### 1. Install RTK

```bash
brew install rtk
# Or use an installer from https://github.com/rtk-ai/rtk
```

Skip this step if you intend to use `native` mode exclusively; that mode never
invokes RTK.

### 2. Install Plus into Hermes

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/rtk-hermes-plus.git'
```

### 3. Enable the plugin

Add it to `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - rtk-plus
```

Do not enable a second `rtk-rewrite` adapter at the same time. Restart Hermes,
then confirm the integration with:

```text
/rtk-plus status
```

## Choose the right mode

| Mode | Terminal rewriting | Search/process compression | Native `read_file` compression |
|---|:---:|:---:|:---:|
| `balanced` **default** | ✓ | ✓ | — |
| `aggressive` | ✓ | ✓ | ✓ |
| `native` | — | ✓ | — |
| `terminal` | ✓ | — | — |
| `suggest` | Measure candidates only | — | — |
| `off` | — | — | — |

Start with `balanced`. Use `aggressive` when native reads are a material part of
your context bill and you prefer compact structure plus recoverability over
verbatim in-context files. Use `native` to run only the deterministic Hermes
`search_files`/`process` compressor, with no RTK terminal middleware registered
and no RTK installation required. This is also the clean experimental arm for
measuring whether native compression reduces end-to-end session cost.

```bash
export RTK_HERMES_PLUS_MODE=aggressive

# Native compression only; bypass all RTK command rewriting
export RTK_HERMES_PLUS_MODE=native
```

## Run an honest native-vs-balanced experiment

Plus records the mode a session **started** with and copies Hermes' canonical
token/cost counters into a private SQLite ledger after each turn. It does not
auto-toggle modes: changing treatment inside one session would make the result
ambiguous, so that session is marked contaminated and excluded.

1. Start fresh Hermes sessions in `native` mode and complete representative
   tasks.
2. Restart Hermes in `balanced` mode, start fresh sessions, and repeat the same
   tasks with the same model and settings.
3. Ask Hermes for the comparison:

```text
/rtk-plus compare
```

The default comparison is `native` vs `balanced`; any two modes can be named:

```text
/rtk-plus compare terminal aggressive
```

The report includes mean and median total tokens per session, separate actual
and Hermes-estimated costs, native character savings, rewrite/recovery counts,
and paired-turn deltas where the same normalized prompt and model appeared in
both arms. Reasoning remains visible as an output-detail bucket but is not
double-counted in the total. A resumed session starts from its existing Hermes
accounting baseline, so earlier tokens are not attributed to Plus.

For Codex OAuth/subscription routes, actual marginal API cost correctly remains
`$0/included`. If you want a clearly labelled API-equivalent comparison, provide
your own per-million-token rate card; Plus never substitutes that estimate for
actual cost:

```bash
export RTK_HERMES_PLUS_EQ_INPUT_USD_PER_M=2.00
export RTK_HERMES_PLUS_EQ_OUTPUT_USD_PER_M=10.00
export RTK_HERMES_PLUS_EQ_CACHE_READ_USD_PER_M=0.20
export RTK_HERMES_PLUS_EQ_CACHE_WRITE_USD_PER_M=2.00
export RTK_HERMES_PLUS_EQ_RATE_CARD='example-2026-08'
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `RTK_HERMES_PLUS_MODE` | `balanced` | `balanced`, `aggressive`, `native`, `terminal`, `suggest`, or `off` |
| `RTK_HERMES_PLUS_TIMEOUT_MS` | `500` | Deadline for RTK helper calls |
| `RTK_HERMES_PLUS_BACKENDS` | `local` | Allowed terminal backends, comma-separated, or `all` |
| `RTK_HERMES_PLUS_CACHE_TTL` | `600` | Rewrite-cache lifetime in seconds |
| `RTK_HERMES_PLUS_CACHE_SIZE` | `512` | Maximum exact-command decisions retained |
| `RTK_HERMES_PLUS_NATIVE_MIN_CHARS` | `12000` | Leave smaller native results unchanged |
| `RTK_HERMES_PLUS_NATIVE_MAX_CHARS` | `8000` | Target maximum compact result size |
| `RTK_HERMES_PLUS_RECOVERY_FILES` | `20` | Number of full native results to retain |
| `RTK_HERMES_PLUS_RECOVERY_DIR` | `~/.hermes/rtk-plus/recovery` | Recovery directory |
| `RTK_HERMES_PLUS_LEDGER` | `true` | Persist private per-session experiment accounting |
| `RTK_HERMES_PLUS_LEDGER_PATH` | `~/.hermes/rtk-plus/experiments.sqlite3` | Experiment ledger location |
| `RTK_HERMES_PLUS_STATE_DB` | Hermes `state.db` | Override canonical Hermes accounting database |
| `RTK_HERMES_PLUS_EXPERIMENT` | `default` | Isolate comparisons under a named experiment |
| `RTK_HERMES_PLUS_EQ_INPUT_USD_PER_M` | `0` | Optional API-equivalent input rate per million tokens |
| `RTK_HERMES_PLUS_EQ_OUTPUT_USD_PER_M` | `0` | Optional API-equivalent output rate per million tokens |
| `RTK_HERMES_PLUS_EQ_CACHE_READ_USD_PER_M` | `0` | Optional API-equivalent cache-read rate |
| `RTK_HERMES_PLUS_EQ_CACHE_WRITE_USD_PER_M` | `0` | Optional API-equivalent cache-write rate |
| `RTK_HERMES_PLUS_EQ_RATE_CARD` | empty | Label saved with a configured equivalent rate card |
| `RTK_HERMES_PLUS_EXCLUDE` | empty | Command prefixes that must never be rewritten |
| `RTK_HERMES_PLUS_PYTEST_GUARD` | `true` | Avoid RTK's pytest double-quiet edge case |

For remote execution, RTK and any paths used by aggressive reads must exist in
the same backend. That is why only `local` is enabled by default.

## Observability without surveillance

Inside Hermes:

```text
/rtk-plus status
/rtk-plus stats
/rtk-plus compare
/rtk-plus reset-stats
```

`stats` contains process-local category totals, character savings, and rewrite
timing. These counters reset when Hermes exits. `compare` reads the durable
experiment ledger, whose per-session token and cost totals survive restarts.

Neither store retains command strings, prompts, or tool contents. To recognize a
repeated task across modes, the ledger saves only a salted local SHA-256
fingerprint of the normalized prompt. The salt is generated locally; the ledger
is never uploaded by Plus. Mode/model changes within a session are flagged and
excluded from comparison rather than quietly blended into a result.

## Recovery and privacy

When Plus shortens a native result, it appends a pointer like:

```text
[rtk-plus: 76.4% fewer characters; full output: ~/.hermes/rtk-plus/recovery/...]
```

On POSIX systems, the recovery directory is forced to mode `0700` and new files
use `0600`. On Windows, recovery artifacts remain under the user's profile and
inherit its Windows ACLs. Files rotate automatically. Terminal recovery remains
governed by RTK itself. The experiment ledger uses the same private parent
directory and is forced to `0600` on POSIX; on Windows it inherits the user's
profile ACLs.

## Safety model

- **Fail open:** errors, timeouts, and non-smaller transformations return the
  original behavior.
- **No shell interpolation:** RTK helper calls use argument arrays with
  `shell=False`.
- **No silent remote execution:** non-local backends require explicit opt-in.
- **No nominal compression:** metadata is counted before a compact result is
  accepted.
- **No content telemetry:** metrics and the ledger never include commands,
  prompts, or tool contents.
- **Pytest correctness guard:** projects already configured with quiet pytest
  output bypass RTK's currently incorrect double-quiet result.

## Development

```bash
git clone https://github.com/AronAxe/rtk-hermes-plus.git
cd rtk-hermes-plus
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

The standard suite contains 52 tests. Two optional integration tests exercise
the current Hermes middleware contract and a real RTK executable:

```bash
HERMES_AGENT_SOURCE=/path/to/hermes-agent \
RTK_INTEGRATION_BIN=/path/to/rtk \
.venv/bin/python -m pytest tests/test_external_integration.py
```

Contributions should preserve the central invariant: **a transformation is only
accepted when the final model-visible result is strictly smaller and the full
native result remains recoverable.**

## Acknowledgements

Inspired by Vinicius Gallotti's MIT-licensed
[`rtk-hermes`](https://github.com/ogallotti/rtk-hermes) adapter and built around
RTK's command-rewrite protocol. This implementation is independent and retains
the same sensible fail-open principle.

## License

[MIT](LICENSE) © 2026 Aron Bijl
