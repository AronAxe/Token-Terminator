# v0.11.0 — Context, learning & observability

**Released September 29, 2026.** The unshipped 0.10.0 milestone is included here;
the previous published version is 0.9.0. Existing release tags remain unchanged.

## Highlights

- [Selectable Hermes ContextEngine](Context-Engine): full available history,
  exact pinned sources, bounded JEV attention, rediscovery and recovery, with no
  generative history summarizer or Hermes core patch. Middleware mode remains.
- Purpose-first scope safety: embeddings, reranking, helpers/classifiers,
  tokenizer work and internal JEV bypass reduction; retries stay isolated.
- [Learned omission-risk policy](Learned-Policy): System-2 question revision,
  batched JEV features and real CatBoost fitting outside JEV's weights. Off by
  default; operator-approved numeric JSON may veto omissions, never relax guards.
- [Observatory](Dashboard): localhost:7474 profile/bot dashboard, separate
  input/output accounting, configured API-equivalent values and a native Desktop
  bottom status-bar counter/upward popover.
- Updated architecture and learning-loop schematics, release installation,
  migration, security and documentation. The original Terminator artwork is unchanged.

Python and Rust package versions are **0.11.0**. Rust remains the interoperability
companion, not a port of the Python runtime or learner. Installation does not
select a ContextEngine, start a server, train a model or enable a policy.

[Complete release notes](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/releases/v0.11.0.md) ·
[GitHub release](https://github.com/AronAxe/Token-Terminator/releases/tag/v0.11.0) · [Quick Start](Quick-Start)

## Evaluation boundaries

The implementation baseline passed 611 tests with two optional integration skips;
final release-commit checks are visible in Actions. Synthetic training demonstrates
fitting, revision and exact-evidence retention, not live model quality or monetary
savings. No production policy is shipped. Output savings and subscription discounts
are not inferred. Protected-history overflow still needs host/provider enforcement.
