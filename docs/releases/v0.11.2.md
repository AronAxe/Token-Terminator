# Token Terminator v0.11.2 — Sol counting and reliable TT discovery

This repair addresses two blockers left in 0.11.1. It does not change JEV keys,
semantic policies, the evidence vault, Context IR, or the main-call-only boundary.

## GPT-6.1-Sol

The exact `gpt-6.1-sol` ID and known OpenAI/Codex/OpenRouter-qualified forms now
resolve to `o200k_base` when the installed tiktoken model-name table lacks the ID.
An upstream mapping still wins, and an explicit operator encoding remains supported.
Unrelated providers, invented versions and sibling names are not inferred.

Five synthetic inputs were checked against OpenAI's documented input-token counter:
English, multilingual/emoji text, code/numbers, structured JSON and literal special
markers. All matched local content counts plus the same six-token message framing.
The recorded corpus distinguishes o200k_base from cl100k_base. This is empirical
compatibility evidence, not an upstream tiktoken declaration or proof about every
possible input. TT still measures complete canonical request JSON, not hidden
provider framing or billed tokens. No generation requests were used in that check.

## Concurrent Hermes discovery

The affected shared loader can return a module before its initialization completes,
and its slug-only cache can reuse one profile's module for another. TT's explicit
`install-context-engine` command now applies a source-hash-guarded repair to the
reviewed affected loader. TT loads are synchronized, recursive discovery cannot
consume a partial module, and each resolved profile path has a distinct namespace.
Other plugins use the original loader. Failed initialization can be retried.

This is a narrow host-file compatibility patch, not merely a plugin import change:
the race occurs before the plugin can run. An adjacent byte-exact backup is kept.
Unknown or modified host implementations are refused rather than overwritten.
The Python installer API and `install-dashboard` do not patch the host by default.
No changes occur on package import, and configuration/history are not rewritten.

## Install

Use the interpreter/environment actually loaded by the managed Hermes launcher:

```bash
python -m pip install --upgrade 'git+https://github.com/AronAxe/Token-Terminator.git@v0.11.2'
python -m rtk_hermes_plus.cli install-context-engine
```

The second command reports `discovery_repair`; for an affected installed host it
must say `repaired` or `already_repaired`. Then restart the appropriate idle backend
through its supervisor once. A package download alone cannot repair a running process.
Existing explicit engine selection and JEV/IR opt-ins remain unchanged.

Regression checks exercise the actual GPT-6.1-Sol model name without encoding
overrides, JEV selection, strict complete-request reduction and exact recovery.
Discovery checks include controlled overlapping initialization, 64 simultaneous
loads, profile separation, recursive loading, failed-load retry and safe installation.
A dedicated CI job runs those same tests against the actual pinned Hermes loader
source, not an optional skipped module. Full CI results are recorded on the PR.

The Rust companion is version-aligned only. Existing tags, Terminator artwork and
schematics remain unchanged. See docs/TOKENIZER_COMPAT.md and docs/HERMES_DISCOVERY.md.
