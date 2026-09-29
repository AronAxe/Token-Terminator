# Architecture

**Two integration modes. One context owner. Purpose before reduction.**

![v0.11.0 context architecture](https://raw.githubusercontent.com/AronAxe/Token-Terminator/v0.11.0/docs/assets/architecture.svg)

## Ownership boundary

The host owns transcript persistence, memory, provider clients/streaming and tool
execution. In middleware mode its selected context engine stays upstream. In
ContextEngine mode, **TT owns context selection instead of LCM or the built-in
compressor**, but does not take over those other host responsibilities.

TT owns its private exact-evidence vault, source/exposure catalog, temporal baselines,
request metrics and experiment ledger. History omissions are request representations,
not deletion of the host transcript. An old source can become relevant again.

## Two paths

```text
Middleware:
  host context engine → conversational scope check
  → TT compiler / deterministic compaction / SkillGate
  → optional JEV gate → optional Context IR → final gate → provider

Selected ContextEngine:
  full available history → staged exact session sources
  → conversational scope check at the complete-request boundary
  → bounded JEV relevance / guard / salience + optional learned omission veto
  → exact active evidence / recovery references
  → existing compiler / SkillGate / exact tool evidence → optional Context IR
  → strict complete-request tokenizer AND character gate → provider
```

The early Hermes hook stages full history without rewriting the host transcript.
The supported final-request middleware makes the acceptance decision only after
real tool schemas and recovery references exist. Engine mode does not repeat the
legacy middleware JEV gate or perform lossy old-turn age-collapse. Unscoped generic
adapters and internal embeddings/rerank/helpers/counting/JEV calls bypass.

Existing RTK command rewriting, post-execution temporal deltas and native tool-result
compression remain separate supported paths. A command still executes before a
new exact observation can become a smaller delta. Returning compressed evidence to
a subsequent main conversation is not rewriting an internal service's own input.

## Learned policy: outside JEV, inside hard safety boundaries

![External learning loop](https://raw.githubusercontent.com/AronAxe/Token-Terminator/v0.11.0/docs/assets/learning-loop.svg)

A separately invoked training command uses explicit outcome-labelled experiments,
System-2 question revision, JEV probabilities and real CatBoost fitting. Development
selection precedes frozen holdout assessment. An operator approves a bounded numeric
JSON artifact before deployment; JEV weights do not change. The policy may retain
more otherwise removable evidence but never override scope/provenance/protection.
[Learned Policy](Learned-Policy) details `off`, `shadow` and `active`.

## Observatory is read-only

Existing content-free accounting feeds [localhost:7474 and Desktop](Dashboard).
Neither view reads conversation/artifact bodies or performs inference. The native
popover follows the authenticated connection's active profile; the standalone view
can aggregate explicitly mapped local bots. Missing or ambiguous values remain unknown.

## Porting and limitations

Other runtimes need stable session/request IDs, supported tool/result seams, an
explicitly authorized main-request hook and model-visible recovery. See
[Async and Adapter Integration](Async-and-Adapter-Integration). `None` or failure
means pass through. ContextEngine and IR require the real target tokenizer; no
character-only substitution is accepted. The guarantee ends at TT's output boundary.

See the [complete ContextEngine contract](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/docs/CONTEXT_ENGINE.md)
for exact hook order, supported provider envelopes, retries, archive-only lexical
recall, persistent-pin capacity and unresolved protected-history overflow.
