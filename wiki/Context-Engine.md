# Token Terminator ContextEngine (v0.11.0 candidate)

**Prepared for review; not released.** TT can be explicitly selected as the Hermes
ContextEngine without a Hermes core patch. Ordinary middleware mode is unchanged.
The full [installation and design guide](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/docs/CONTEXT_ENGINE.md)
includes the pinned upstream API, caveats, recovery and all configuration bounds.

Install the review checkout into the Hermes Python environment, then run
`token-terminator install-context-engine`. Enable the generic `token-terminator`
plugin for its final request middleware. In **hermes plugins -> Provider Plugins
-> Context Engine**, choose **Token Terminator** (slug `token-terminator`). The
inspected web dashboard uses the same provider-options discovery.

```yaml
plugins:
  enabled: [token-terminator]
context:
  engine: token-terminator
```

Preserve other enabled plugins and allow the `context_engine` toolset in restricted
profiles. Keep existing OpenRouter/direct TypeSafe keys; enable the existing
`TOKEN_TERMINATOR_JEV=true` and `TOKEN_TERMINATOR_CONTEXT_IR=true` flags. Restart
Hermes and check `token_terminator_history` with `action=status` in the actual session.

The engine archives full available messages in TT's pinned exact vault, batches
JEV relevance/guard/salience over exact regions and preserves guarded/unscored
material. It revisits old context and can rediscover archived literal matches.
There are no generative summaries or guessed graph relations. The supported early
engine hook stages history; the final TT middleware commits only a complete-request
exact-token **and** character decrease after IR. Provider retries and async
execution preserve engine ownership. No second context engine runs upstream.

The transcript is not destructively shortened. Protected history can still exceed
the context window; pre-middleware hard-limit routes and stateful native compaction
are not certified. Unknown tokenizers, missing recovery, malformed scoring, corrupt
sources and capacity failures preserve originals. Pins survive reset/pruning, so
retention needs planning. An external LCM archive is not automatically imported.

`token_terminator_history` provides session-scoped `find`, exact paginated `get`,
and `status`. Existing artifact/IR recovery remains available. See the
[benchmark](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/benchmarks/context_engine/README.md):
five fifty-turn tasks, two tokenizers, four executable arms, 120 evaluations. LCM
+ TT was not reproduced; real JEV/model quality and service cost remain unmeasured.

## Optional learned omission-risk layer

The v0.11.0 candidate adds [an external learned policy](Learned-Policy) to this
engine. Bounded offline or explicitly consented live feature discovery uses JEV
probabilities and System-2 question proposals to train CatBoost omission-harm and
recovery-cost predictors. JEV's weights remain unchanged. Deployment is off by
default and requires an approved local artifact plus SHA-256; shadow mode audits
without changing the fixed-gate request, and active mode can veto eligible omissions.
It cannot overrule protected context, scope checks, exact recovery or the final
tokenizer gate. The branch name still contains v0.10.0 to preserve PR #19; that
unreleased milestone is included in the v0.11.0 candidate.
