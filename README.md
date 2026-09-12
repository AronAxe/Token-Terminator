<p align="center">
  <img src="docs/assets/hero.webp" alt="A chrome endoskeleton foot crushing AI token chips beneath the Token Terminator title" width="100%">
</p>

<h1 align="center">Token Terminator</h1>

<p align="center">
  <strong>Keep the evidence. Terminate the redundant tokens.</strong><br>
  Portable token reduction for agent runtimes, with a first-party
  <a href="https://github.com/NousResearch/hermes-agent">Hermes Agent</a> adapter.
</p>

<p align="center">
  <a href="https://github.com/AronAxe/Token-Terminator/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/AronAxe/Token-Terminator/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/AronAxe/Token-Terminator/releases/tag/v0.5.1"><img alt="Release v0.5.1" src="https://img.shields.io/badge/release-v0.5.1-ef2b25"></a>
  <a href="https://crates.io/crates/token-terminator"><img alt="crates.io" src="https://img.shields.io/crates/v/token-terminator?logo=rust"></a>
  <a href="https://docs.rs/token-terminator"><img alt="docs.rs" src="https://img.shields.io/docsrs/token-terminator?logo=docs.rs"></a>
  <img alt="Python 3.10–3.13" src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-22c55e.svg"></a>
  <img alt="Portable core" src="https://img.shields.io/badge/core-agent--agnostic-ef2b25">
  <img alt="Fail open" src="https://img.shields.io/badge/failure%20mode-pass%20through-8b5cf6">
</p>

Token Terminator is an agent-runtime optimization layer. It removes token bloat at the tool-result and provider-request boundaries without discarding the underlying evidence.

The engine has five cooperating reduction paths:

1. transparent terminal-command rewriting through [RTK](https://github.com/rtk-ai/rtk);
2. temporal delta compression for repeated terminal observations, after the command has actually executed;
3. deterministic compression of large tool results;
4. content-addressed vaulting, duplicate collapse, evidence leases, compact recovery receipts, and deterministic layered recovery views;
5. final provider-request compilation, with model-aware token acceptance when an exact tokenizer is available and optional bounded working-state injection only when the complete request is still smaller.

The reduction core is not intrinsically tied to Hermes: it operates on Python dictionaries, strings, stable request/session identifiers, and a local SQLite vault. The repository includes a turnkey Hermes plugin because Hermes exposes the required lifecycle hooks. Other agent runtimes need a small adapter that presents the same boundaries; they do not need a fork of the reduction engine.

Async agent frameworks can use the included `AsyncRuntime` façade. It keeps provider loops responsive by moving compiler, vault, and telemetry work to an executor, propagates task or token cancellation, and uses native cancellable subprocess paths for RTK command rewriting and aggressive reads. The synchronous `Runtime` API remains unchanged.

It does **not** replace the host's context engine, memory system, transcript store, or provider client. It does not add an MCP server or standing prompt text. If storage, recovery, middleware, token measurement, or compilation is unavailable or unsafe, the host receives the original request or result unchanged.

## What it does

- **Shrinks before the model sees it.** Large tool output is compacted, repeated terminal observations can become exact-recoverable deltas, and repeated evidence is replaced with bounded receipts.
- **Keeps the original evidence.** Exact content is stored in a private, content-addressed SQLite vault and can be recovered exactly, previewed deterministically, or searched without returning the whole artifact.
- **Compiles the final request.** Duplicate artifacts, expired inline exposures, and old context are reduced after the host assembles the provider payload.
- **Aligns with the active tokenizer when possible.** A configured Hugging Face `tokenizer.json` or tiktoken backend adds a second acceptance gate; unavailable tokenizers fall back to the established character invariant.
- **Refuses bad optimizations.** A transformed payload is used only when it is strictly smaller, recoverable, provider-valid, and leaves caller-owned objects untouched.
- **Measures the result.** Content-free request/session telemetry separates compiler, compactor, and end-to-end savings.

## Core invariant

A provider-visible transformation is accepted only when:

- the complete transformed payload—including receipts and optional working state—is **strictly smaller**;
- when an exact tokenizer is available, the transformed request also uses fewer measured tokens;
- the exact native content has been written to the private vault and read back successfully; and
- caller-owned request objects remain unchanged.

Temporal terminal deltas obey the same rule: the command always executes, the new exact output is vaulted first, and a diff is shown only when it is smaller than the current raw output.

This is an optimizer, not a context decorator.

## Portability: core versus adapter

| Layer | Runtime dependency | Status |
|---|---|---|
| Vault, receipts, leases, temporal deltas, native compression, request compiler, telemetry | Agent-agnostic Python | Included |
| Exact tokenizer alignment | Optional `tiktoken` or Hugging Face `tokenizers` | Included, optional |
| Rust artifact interoperability | `token-terminator` Rust crate | Published on crates.io |
| RTK command rewriting | Optional `rtk` binary plus a terminal-tool adapter | Included |
| Hermes lifecycle hooks, slash command, and recovery model tool | Hermes Agent | First-party and turnkey |
| LangGraph, OpenAI Agents SDK, AutoGen, CrewAI, custom loops | Their tool/request hook APIs | Adapter required |

**In practical terms:** Token Terminator is agent-agnostic as an engine, not universally plug-and-play as a package. Hermes works out of the box. Another runtime must connect tool results, final provider requests, stable request/session IDs, and the recovery tool. The core behavior and storage format stay the same.

## What it reduces

| Mechanism | Scope | Exact recovery |
|---|---|:---:|
| RTK terminal rewriting | Supported `terminal` commands | RTK behavior |
| Temporal terminal delta | Repeated large terminal observations in `balanced`/`aggressive` | ✓ |
| Native result compression | Large `search_files` and `process` results | ✓ |
| Aggressive structured reads | Large `read_file` results | ✓ |
| Same-request duplicate collapse | Repeated large tool artifacts | ✓ |
| Cross-request evidence leases | Previously exposed large artifacts | ✓ |
| Request compiler | Final provider request, after normal Hermes context assembly | ✓ |
| Token-aware acceptance gate | Complete request when an exact tokenizer is available | n/a |
| Bounded working state | Optional request-selection aid; disabled by default | n/a |
| Experiment ledger | Request/session savings and mode comparison | content-free |

The Python import package remains `rtk_hermes_plus` for source compatibility. The public distribution, Hermes plugin, CLI, slash command, model tool, environment namespace, and repository are Token Terminator.

## Architecture

<p align="center">
  <img src="docs/assets/architecture.svg" alt="Token Terminator architecture: an agent-agnostic reduction core connected to a host runtime through an adapter" width="100%">
</p>

The host runtime continues to own the conversation, transcript, context-engine lifecycle, and provider dispatch. Token Terminator owns only its private data directory and adapter-visible middleware/hooks. In the included Hermes adapter these are:

- `tool_request` middleware for terminal rewrites;
- `transform_tool_result` for native compression and temporal terminal deltas;
- observational lifecycle and `post_tool_call` hooks;
- `llm_request` middleware for final request reduction and optional tokenizer-aware acceptance;
- one compact `token_terminator` tool for exact artifact recovery, deterministic layered views, private search, and optional working-state operations.

## Structural benchmark

`scripts/benchmark.py` uses `o200k_base`, makes zero provider calls, and measures each mechanism's complete provider-visible payload. The terminal case executes the real RTK rewrite and compact-result path in a disposable Git repository. This is a deterministic structural benchmark—not a claim about answer quality or causal end-to-end session cost.

| Case | Raw tokens | Output tokens | Reduction |
|---|---:|---:|---:|
| RTK terminal rewrite | 152,074 | 911 | **99.40%** |
| Native search result | 190,999 | 1,213 | **99.36%** |
| Repeated artifact, second exposure | 77,097 | 164 | **99.79%** |
| Duplicate artifact in one request | 154,116 | 77,183 | **49.92%** |
| Working-state no-bloat guard | 21 | 21 | **0%** |
| Receipt plus working-state, combined | 77,097 | 257 | **99.67%** |
| Small request pass-through | 17 | 17 | **0%** |
| **Aggregate** | **651,421** | **79,766** | **87.76%** |

Small results are intentionally untouched. Ordinary sessions will not resemble these deliberately pathological fixtures; use the experiment ledger for representative session comparisons. Temporal-delta and tokenizer-aware paths are covered by invariant tests rather than folded into this older structural fixture, so the table remains directly comparable with the previous release.

## Modes

| Mode | Terminal rewrite | Temporal delta | Native search/process | Native `read_file` | Request compiler |
|---|:---:|:---:|:---:|:---:|:---:|
| `balanced` **default** | ✓ | ✓ | ✓ | — | ✓ |
| `aggressive` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `native` | — | — | ✓ | — | — |
| `terminal` | ✓ | — | — | — | — |
| `suggest` | Measure only | — | — | — | — |
| `off` | — | — | — | — | — |

The optional working-state block defaults to zero characters, even in `balanced` and `aggressive` modes.

## Install: Hermes Agent (turnkey)

Token Terminator 0.5.1 supersedes 0.5.0 and replaces the earlier `rtk-hermes-plus` distribution. `token-terminator` and `rtk-hermes-plus` must not coexist because both own the `rtk_hermes_plus` Python import package.

This is the supported zero-glue installation: the repository already contains the Hermes hooks, slash command, recovery tool, and lifecycle accounting. The commands below pin the immutable `v0.5.1` release tag.

### 1. Install RTK when using terminal rewriting

```bash
brew install rtk
# Or use an installer from https://github.com/rtk-ai/rtk
```

RTK is not required for `native` mode.

### 2. Replace the old distribution in Hermes' environment

Disable the old plugin before replacing its package. A first-time installation may simply report that `rtk-plus` is not enabled.

POSIX example:

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
hermes plugins disable rtk-plus
"$HERMES_PY" -m pip uninstall -y rtk-hermes-plus token-terminator
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1'
```

Windows example:

```powershell
$HermesPy = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
hermes plugins disable rtk-plus
& $HermesPy -m pip uninstall -y rtk-hermes-plus token-terminator
& $HermesPy -m pip install "git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1"
```

Exact tokenizer alignment is optional. Install `tiktoken` for supported cloud-model tokenizers and/or Hugging Face `tokenizers` when pointing Token Terminator at a local `tokenizer.json`:

```bash
"$HERMES_PY" -m pip install tiktoken tokenizers
```

Without either package, Token Terminator retains the character-based strict-reduction invariant.

### 3. Enable one plugin

```bash
hermes plugins enable token-terminator --no-allow-tool-override
```

Do not enable a second RTK rewrite adapter alongside Token Terminator.

After commencing a new Hermes session:

```text
/token-terminator status
```

Installation and enablement are separate operations. Disabling affects subsequent sessions; it does not delete private vault data. See [MIGRATION.md](MIGRATION.md) for the reviewed 0.2.0 replacement and rollback procedure.

## Rust interoperability crate

Rust agent hosts can use the supported `token-terminator` companion crate for the stable cross-language pieces of the Token Terminator contract:

```bash
cargo add token-terminator
```

```rust
use token_terminator::{artifact_identity, strictly_smaller_chars, verify_sha256};

let evidence = "exact tool evidence";
let identity = artifact_identity(evidence);
assert!(verify_sha256(evidence, &identity.sha256));
assert!(strictly_smaller_chars("long provider-visible evidence", "short receipt"));
```

The crate mirrors vault-compatible SHA-256 artifact identities, short/full artifact-ID verification, and the portable strictly-smaller-in-characters baseline. It is deliberately **not** a second Token Terminator runtime and does not introduce PyO3 into the Python install. Rust/PyO3 hot-path acceleration remains profiling-driven and deferred until it earns its complexity.

See [the Rust crate integration guide](docs/RUST_CRATE.md), [crates.io](https://crates.io/crates/token-terminator), and [docs.rs](https://docs.rs/token-terminator).

## Install: another agent runtime (adapter API)

Install the same distribution in the environment that owns your agent loop:

```bash
python -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@v0.5.1'
```

Then connect your runtime's tool-result and final-request hooks to `Runtime`. The adapter must map equivalent tools to Token Terminator's canonical names (`search_files`, `process`, and optionally `read_file`) and expose `Runtime.tool` to the model for exact recovery.

```python
from pathlib import Path

from rtk_hermes_plus.config import Config
from rtk_hermes_plus.plugin import Runtime

terminator = Runtime(
    Config(
        mode="balanced",
        db_path=Path(".token-terminator/artifacts.sqlite3"),
        ledger_enabled=False,
    ),
    profile_name="my-agent",
)


def reduce_tool_result(name, arguments, result, *, session_id, call_id):
    try:
        reduced = terminator.transform_tool_result(
            tool_name=name,
            args=arguments,
            result=result,
            session_id=session_id,
            tool_call_id=call_id,
        )
    except Exception:
        return result
    return reduced if reduced is not None else result


def reduce_provider_request(request, *, session_id, request_id):
    try:
        decision = terminator.llm_request_middleware(
            request=request,
            session_id=session_id,
            request_id=request_id,
        )
    except Exception:
        return request
    return decision["request"] if decision is not None else request
```

An adapter must preserve four contracts: stable request/session identity, original-object immutability, pass-through on `None` or error, and model access to `artifact_get`. The `Runtime` surface is usable today; framework-specific one-command adapters beyond Hermes are not yet shipped.

### Async runtimes, cancellation, and concurrency

Wrap the same synchronous runtime when the host owns an asyncio event loop:

```python
from rtk_hermes_plus import AsyncRuntime, CancellationToken, Runtime

terminator = AsyncRuntime(Runtime(config, profile_name="my-agent"))
cancellation = CancellationToken()

reduced = await terminator.transform_tool_result(
    tool_name="search_files",
    args={"pattern": "ContextEngine"},
    result=large_result,
    session_id=session_id,
    tool_call_id=call_id,
    cancellation=cancellation,
)

compiled = await terminator.llm_request_middleware(
    request=provider_request,
    session_id=session_id,
    request_id=request_id,
    cancellation=cancellation,
)
```

`AsyncRuntime` mirrors the adapter-facing tool, result, request, recovery, and session methods. Pass a custom `concurrent.futures.Executor` to `AsyncRuntime(runtime, executor=...)` when the host needs a dedicated worker pool.

Cancelling the awaiting asyncio task, or calling the thread-safe `cancellation.cancel()`, raises `asyncio.CancelledError` at the adapter boundary. Active RTK subprocesses are killed and reaped. Compiler and SQLite operations already running in an executor remain atomic and may finish in that worker after the caller has stopped waiting; their result is discarded. Token Terminator does not intercept or buffer provider response streams, so adapters compile immediately before dispatch and leave streaming responses under host control.

The artifact vault enables SQLite WAL mode and uses `synchronous=NORMAL`, a ten-second busy timeout, bounded retries for transient multi-process startup locks, short-lived connections, and `BEGIN IMMEDIATE` writes. Independent runtime instances and agent processes may share one local vault while preserving content deduplication, lease limits, and observation provenance. High-water retention prunes only abandoned, non-recovery-referenced artifacts; evidence named by accepted recovery receipts remains protected. Keep the database on a local filesystem: SQLite WAL is not a network-filesystem coordination protocol.

## Exact and layered recovery

Compressed results, temporal deltas, and request receipts contain an artifact identifier. The model can recover an exact page through the registered tool:

```json
{
  "action": "artifact_get",
  "artifact_id": "a_<content-address>",
  "offset": 0,
  "limit": 8000
}
```

Supported actions are:

- `artifact_get` — page exact immutable content;
- `artifact_peek` — deterministic lossy synopsis with metadata, head/tail, signal lines, and shallow JSON structure when available;
- `artifact_find` — search for matching lines inside one known artifact without returning the whole artifact;
- `artifact_search` — locate private artifacts by content or tool name;
- `status` — inspect bounded plugin state, including temporal-delta and tokenizer status;
- `working_state_apply` and `working_state_get` — control the optional bounded working-state selector.

`artifact_peek` and `artifact_find` never replace the authoritative artifact. They are progressive-disclosure views; `artifact_get` remains the exact-recovery contract.

Artifact text and tool arguments stay in the plugin-owned SQLite vault. Receipts expose only a bounded tool label, character count, artifact ID, and abbreviated digest.

## Configuration

All plugin-owned files default under `<HERMES_HOME>/token-terminator/`.

| Variable | Default | Purpose |
|---|---|---|
| `TOKEN_TERMINATOR_ENABLED` | `true` | Master plugin behavior gate |
| `TOKEN_TERMINATOR_MODE` | `balanced` | Select one mode from the table above |
| `TOKEN_TERMINATOR_TIMEOUT_MS` | `500` | RTK helper deadline |
| `TOKEN_TERMINATOR_BACKENDS` | `local` | Allowed terminal backends, comma-separated, or `all` |
| `TOKEN_TERMINATOR_RTK_PATH` | empty | Optional explicit RTK executable path; avoids PATH-based discovery |
| `TOKEN_TERMINATOR_CACHE_TTL` | `600` | Rewrite-cache lifetime in seconds |
| `TOKEN_TERMINATOR_CACHE_SIZE` | `512` | Maximum exact-command decisions retained |
| `TOKEN_TERMINATOR_TEMPORAL_DELTA` | `true` | Enable repeated-terminal delta reduction where the active mode permits it |
| `TOKEN_TERMINATOR_TEMPORAL_MIN_CHARS` | `2000` | Minimum terminal result size considered for temporal deltas |
| `TOKEN_TERMINATOR_TEMPORAL_SCOPE` | `session` | Baseline scope: `session` or `workspace` |
| `TOKEN_TERMINATOR_NATIVE_MIN_CHARS` | `12000` | Leave smaller native results unchanged |
| `TOKEN_TERMINATOR_NATIVE_MAX_CHARS` | `8000` | Native compact-text target |
| `TOKEN_TERMINATOR_DB_PATH` | `token-terminator/artifacts.sqlite3` | Vault, leases, working state, temporal baselines, and request metrics |
| `TOKEN_TERMINATOR_MIN_ARTIFACT_CHARS` | `8000` | Minimum request artifact size |
| `TOKEN_TERMINATOR_MAX_ARTIFACT_CHARS` | `2000000` | Per-artifact character ceiling |
| `TOKEN_TERMINATOR_VAULT_MAX_BYTES` | `536870912` | Total exact-content capacity |
| `TOKEN_TERMINATOR_VAULT_HIGH_WATER_PCT` | `90` | Start retention pruning before the hard capacity wall |
| `TOKEN_TERMINATOR_VAULT_LOW_WATER_PCT` | `80` | Prune toward this target when the high-water mark is crossed |
| `TOKEN_TERMINATOR_INLINE_LEASES` | `1` | Full provider exposures per session/artifact |
| `TOKEN_TERMINATOR_MAX_PAGE_CHARS` | `20000` | Hard artifact-read page ceiling |
| `TOKEN_TERMINATOR_MAX_SEARCH_RESULTS` | `50` | Hard artifact-search result ceiling |
| `TOKEN_TERMINATOR_WORKING_GRAPH_CHARS` | `0` | Optional bounded working-state block; `0` disables it |
| `TOKEN_TERMINATOR_TOKEN_BUDGET` | `true` | Use exact token acceptance when a supported tokenizer backend is available |
| `TOKEN_TERMINATOR_TOKENIZER_JSON` | empty | Exact Hugging Face `tokenizer.json` path for local models |
| `TOKEN_TERMINATOR_TIKTOKEN_ENCODING` | empty | Explicit tiktoken encoding override |
| `TOKEN_TERMINATOR_CONTEXT_COMPACTION` | `true` | Enable deterministic old-turn/tool-result compaction |
| `TOKEN_TERMINATOR_CONTEXT_MIN_VAULT_CHARS` | `4000` | Minimum old tool-result size eligible for context vaulting |
| `TOKEN_TERMINATOR_CONTEXT_COLLAPSE_AFTER_TURNS` | `6` | Collapse completed turns older than this window; `0` disables turn collapse |
| `TOKEN_TERMINATOR_CONTEXT_INLINE_RECENT_TURNS` | `5` | Recent turns that must remain fully inline |
| `TOKEN_TERMINATOR_PREVIEW_MARKER` | `false` | Prefix rewritten terminal commands with the RTK preview marker |
| `TOKEN_TERMINATOR_CONTEXT_LIMIT_TOKENS` | `0` | Optional model context limit; `0` disables budget reporting |
| `TOKEN_TERMINATOR_OUTPUT_RESERVE_TOKENS` | `4096` | Tokens reserved for model output when a context limit is configured |
| `TOKEN_TERMINATOR_TOKEN_SAFETY_MARGIN` | `512` | Additional context headroom; Token Terminator does not fill the window to the edge |
| `TOKEN_TERMINATOR_LEDGER` | `true` | Persist content-free experiment accounting |
| `TOKEN_TERMINATOR_LEDGER_PATH` | `token-terminator/experiments.sqlite3` | Experiment ledger |
| `TOKEN_TERMINATOR_STATE_DB` | Hermes `state.db` | Canonical Hermes accounting source |
| `TOKEN_TERMINATOR_EXPERIMENT` | `default` | Comparison namespace |
| `TOKEN_TERMINATOR_EXCLUDE` | empty | Terminal command prefixes never rewritten |
| `TOKEN_TERMINATOR_PYTEST_GUARD` | `true` | Avoid RTK's pytest double-quiet edge case |

The `TOKEN_TERMINATOR_EQ_*` variables optionally attach a labelled API-equivalent rate card. Actual OAuth/subscription marginal cost remains distinct. Legacy `RTK_HERMES_PLUS_*` aliases are accepted for one migration release, but the new namespace takes precedence.

## Metrics and experiments

Inside Hermes:

```text
/token-terminator status
/token-terminator stats
/token-terminator compare
/token-terminator compare native balanced
/token-terminator reset-stats
```

The process-local metrics contain bounded counters and character totals. Durable request metrics separate compiler-stage savings (`raw_chars - compiled_chars`), context-compactor savings (`compiled_chars - final_chars`), and measured end-to-end savings (`raw_chars - final_chars`). Compiler-only rows are reported separately from requests whose final provider payload was observed. These columns are an additive schema-2 extension so a rollback to the original 0.3.0 package can still open and write the database. If that legacy writer updates a measured identity, a database trigger clears the newer fields so status reports the row as unmeasured rather than retaining stale end-to-end telemetry.

When exact token measurement is available, provider-request decisions also report the tokenizer backend and raw/final/saved token counts. A configured context limit reports the usable budget after the output reservation and safety margin; it does not authorize Token Terminator to silently truncate a request.

The durable experiment ledger stores session/turn identifiers, mode/model labels, token/cost totals, transformation counts, and salted local prompt fingerprints. It does not store command strings, prompts, or tool contents.

A valid comparison requires separate fresh sessions with stable modes, the same model/settings, and representative repeated tasks. Mode/model changes contaminate a session and exclude it rather than manufacturing a persuasive number.

For answer quality—not just token accounting—use the paired non-inferiority harness in [`docs/QUALITY_AB_EXPERIMENT.md`](docs/QUALITY_AB_EXPERIMENT.md). It sends identical synthetic prompts and evidence to the same model in fresh `off` and `balanced` sessions, randomizes arm order, rejects provider/model drift, and grades easily degraded answers deterministically. The first 36 matched pairs are an answer-quality checkpoint; a final non-inferiority decision remains withheld until the precommitted 72-pair extension is complete. Token savings are secondary and cannot compensate for lower answer quality.

## Security and privacy

- Exact raw artifacts and their private provenance are stored locally because recovery is part of the product contract.
- Temporal deltas never skip command execution and never replace the exact current artifact in the vault.
- Layered recovery views are deterministic and explicitly lossy; the immutable artifact remains authoritative.
- The vault enforces per-artifact and total-capacity limits, SQLite WAL, foreign keys, busy timeouts, schema-version checks, short-lived transactions, and serialized writes.
- POSIX storage uses `0700` parent directories and `0600` databases. Windows storage inherits the user's profile ACLs.
- RTK subprocesses use argument arrays with `shell=False`.
- Remote terminal backends are disabled by default.
- Tool arguments and artifact contents never enter receipts, metrics, or the experiment ledger.
- Unsupported, malformed, unavailable, non-recoverable, non-smaller, or token-expanding transformations pass through unchanged.

See [SECURITY.md](SECURITY.md) for the reporting policy and data boundaries.

## FAQ

### Is Token Terminator only for Hermes?

No. The reduction engine and vault are ordinary Python and SQLite. Hermes is the first runtime with a complete, maintained adapter in this repository. Other runtimes need to connect their equivalent tool-result, provider-request, identity, and recovery seams.

### Is RTK required?

Only for terminal-command rewriting. Native tool-result compression, vaulting, recovery, request compilation, and tokenizer-aware acceptance do not require the `rtk` binary. Use `native` mode to disable both RTK and request compilation, or a custom adapter with `balanced`/`aggressive` mode to use the broader engine.

### Does it summarize away evidence?

No. Provider-visible content may be compacted, and `artifact_peek` is deliberately lossy, but accepted transformations retain exact native content in the private vault and emit a recovery receipt. `artifact_get` remains authoritative. If write-and-read-back verification fails, the original content passes through.

### Does it replace the host's memory or context engine?

No. Token Terminator operates after or alongside normal context assembly. It does not own the transcript, alter persisted conversation history, or require a particular memory engine.

### What happens when it fails?

The optimization is skipped. Unsupported payloads, storage errors, timeouts, malformed data, tokenizer errors, non-smaller results, and adapter exceptions must all resolve to the original request or result.

## Rollback to RTK Hermes Plus 0.2.0

Disable/remove `token-terminator` from the profile first, then replace the distribution with the immutable pre-rename commit:

```bash
HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
"$HERMES_PY" -m pip uninstall -y token-terminator rtk-hermes-plus
"$HERMES_PY" -m pip install \
  'git+https://github.com/AronAxe/Token-Terminator.git@2ef250cca98f691eba82e193bd8c26fd4ab652f4'
```

Re-enable only `rtk-plus` for subsequent sessions. The rollback does not require Hermes core or LCM changes and does not delete Token Terminator's private data directory.

## Development and release verification

```bash
python -m pip install -e '.[dev]'
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m pytest -p no:cacheprovider
python scripts/benchmark.py
python -m build
python -m twine check dist/*
python scripts/verify_release.py 'dist/*'
```

`scripts/smoke_hermes.py` must be run from an isolated environment containing the built wheel and a compatible Hermes Agent installation. It creates a disposable `HERMES_HOME`, uses the real `PluginManager`, makes no network calls, and does not touch a live profile.

Contributions must preserve the central invariant: **strictly smaller complete provider payload, fewer measured tokens when an exact tokenizer is available, exact recovery, immutable caller requests, and fail-open host behavior.**

<p align="center">
  <img src="docs/assets/judgement-day.webp" alt="Judgement Day for Token Bloat — a Terminator-style machine skull looming over a ruined city as AI tokens explode" width="100%">
</p>

## [![Repography logo](https://images.repography.com/logo.svg)](https://repography.com) / Structure
[![Structure](https://images.repography.com/159618761/AronAxe/Token-Terminator/structure/A7QJwtSXEOGss8ODJwQPKIn55FhNAsEbvIP7cEEvbkw/9ST6BC_-XGIjAFSA5TC3Qm7lZ1arJSZUerDm3LBx2eA_table.svg)](https://github.com/AronAxe/Token-Terminator)

## Acknowledgements

Token Terminator retains and extends the original RTK integration, inspired by Vinicius Gallotti's MIT-licensed [`rtk-hermes`](https://github.com/ogallotti/rtk-hermes) adapter and built around RTK's command-rewrite protocol.

## License

[MIT](LICENSE) © 2026 Aron Bijl