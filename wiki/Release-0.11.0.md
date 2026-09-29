# v0.11.0 — ContextEngine and learned JEV omission policy

**Unreleased review candidate in PR #19.** The released baseline is v0.9.0.
The v0.10.0 ContextEngine and call-scope work was not separately published and is
included here. The branch remains `feat/hermes-context-engine-v0.10.0` so the
existing pull request and review history stay intact.

## Dashboard addition

Opt-in localhost:7474 profile/bot accounting and a supported Hermes Desktop
bottom status counter with upward popover are included. Input/output are separate;
measured input savings are not fabricated output or subscription bill savings.
Local rate cards provide gross API equivalents and token-weighted average values.
The reader is content-free and read-only, with profile/connection isolation and
explicit missing/ambiguous coverage. No server starts automatically or model call
runs for telemetry. [Setup and qualifications](Dashboard).

## Included changes

- Selectable Hermes ContextEngine through supported plugin discovery; exact full
  history backing and recovery, bounded JEV attention, existing Context IR and
  complete-request tokenizer acceptance. No generative history summarizer or
  Hermes core patch. Middleware-only mode is retained.
- Purpose-before-target scope isolation for embeddings, reranking, classifiers,
  internal JEV, tokenizers and unrelated helper calls, with preserved retry behavior.
  The defensive policy for explicitly integrated JEV-backed conversational wrappers
  preserves bounded history; native JEV remains a typed-decision service.
- Optional learned omission-harm and recovery-cost predictors fitted with CatBoost
  on JEV-derived features, plus bounded System-2 question proposal/revision driven
  by grouped development validation errors. Questions/models/thresholds freeze
  before final holdout assessment. JEV weights are not changed.
- Explicit `policy-train` command, strict offline replay and opt-in consented live
  requests using existing credentials. No automatic vault mining, training or
  deployment. Runtime `off`/`shadow`/`active` modes, approved hash-bound numeric JSON
  artifacts, scorer/target/schema binding and conservative abstention.
- Additional omission veto only: the learned system cannot override authority,
  protected exact content, uncertain regions, provenance or final token gates.
- Regression tests, actual-fit synthetic demonstration, optional learning CI,
  updated README/configuration/migration/security and documentation.

Read [Context Engine](Context-Engine), [Learned Policy](Learned-Policy), and the
[full changelog](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/CHANGELOG.md).
The Rust crate remains the interoperability companion, not a Rust port of the
Python engine or training system. This candidate has not changed main, the published
release, live wiki, package registries or a running Hermes profile.

## Release qualifications

Synthetic tests prove executable fitting, feature revision, scope/provenance safety
and request-size invariants; they do not establish live JEV calibration, production
answer quality, a dollar saving or equivalence with LCM. No paid API tests are needed
for CI. Active deployment requires a task- and target-specific labelled dataset and
reviewed policy. Existing unresolved protected-history overflow still relies on
host/provider hard-limit enforcement. Release/merge remain subject to owner review.
