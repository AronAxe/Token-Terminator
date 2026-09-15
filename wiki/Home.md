# Token Terminator Wiki

**Keep the evidence. Terminate the redundant tokens.**

Token Terminator is an agent-runtime optimization layer that reduces provider-visible token bloat at tool-result and final-request boundaries while preserving exact recoverability. Hermes Agent has the turnkey adapter; the reduction core itself is ordinary Python + SQLite and can be integrated with other runtimes.

## Start here

- [Quick Start](Quick-Start) — install v0.5.2 and verify it is active.
- [Architecture](Architecture) — understand the host/adapter/core boundary.
- [Modes and Reduction Pipeline](Modes-and-Reduction-Pipeline) — see what each mode enables.
- [Configuration](Configuration) — all important environment controls.
- [Vault and Exact Recovery](Vault-and-Exact-Recovery) — artifact identity, receipts, retention, and recovery.
- [Security and Trust Model](Security-and-Trust-Model) — local data, RTK trust boundary, and fail-open rules.
- [Troubleshooting](Troubleshooting) — common symptoms and checks.

## The core contract

A transformation is accepted only when it is safer than passing the original through:

1. the complete provider-visible result is strictly smaller;
2. if an exact tokenizer is available, measured token count also decreases;
3. exact evidence has been written to the private vault and verified by read-back when recovery is required;
4. caller-owned request objects are not mutated;
5. any unsupported or unsafe condition fails open to the original request/result.

Temporal terminal reduction adds one more rule: **the command still executes every time**. Only the representation shown to the model may become a smaller delta.

## What v0.5.1 hardened

v0.5.1 is the post-0.5.0 hardening release. It adds bounded vault lifecycle management, Unicode-safe artifact search, cwd-aware rewrite caching, async temporal parity, schema-owned temporal snapshots, more honest experiment statistics, Windows URI fixes, safer permissions, RTK path pinning, and recovery-safe GC. Artifacts already named by accepted recovery receipts or temporal deltas are protected from automatic retention pruning.

## Current release

- Python package/release: **v0.5.1**
- Python support: **3.10–3.13**
- Rust interoperability crate: **token-terminator 0.5.1**
- First-party runtime adapter: **Hermes Agent**
