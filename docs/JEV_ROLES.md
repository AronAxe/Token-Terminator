# JEV: agentic control and support for an LLM

Scope: v0.11.0 review candidate, PR #19. Documentation checked September 28,
2026. This clarification does not add a new runtime mode or API integration.

## Two architectural roles, the same decision primitives

**System 1 / agentic control:** JEV can evaluate which workflow, tool, skill,
handler, priority, or escalation is appropriate. Application code applies its
structured decisions and confidence policy. An expensive generative model need
not run for every branch. TypeSafe's Hermes skill-suggestion cookbook ranks a
catalogue, checks a shortlist, and provides a suggestion to the agent; it is not
a replacement for the agent's generative model or a licence to execute arbitrary
model-selected actions.

**System 2 support:** an LLM performs slower reasoning or writing while JEV
supports the surrounding workflow: select relevant context, check inputs and
outputs, assess requirements, check claim/citation support against sources,
apply guardrail assessments, or inform accept/retry/escalate decisions.

Both roles use TypeSafe's existing state + typed questions interface. Choice,
Score and Noul can be composed into either workflow; these are not two JEV text
generation modes or a separate System Two endpoint. JEV can help control an
agent without generating that agent's prose. TypeSafe explicitly documents that
JEV is not a drop-in chat/code-generation LLM.

## Learning outside JEV is different from a fixed gate

TypeSafe's AI primer distinguishes post-training objectives: RLHF targets human
preferences, RLVR verifiable rewards, and RLCD calibrated decisions. These are
training objectives, not three mutually exclusive application roles.

Its autoresearch cookbook holds JEV fixed while an LLM proposes and revises
questions. JEV evaluates each row with the round's questions batched together.
Noul probabilities and Score-distribution statistics become CatBoost features;
validation errors guide the next proposal. The question set and downstream
predictor change, not JEV's weights. Cross-validation uses development data;
final test labels do not guide feature discovery. A large dataset still costs
many requests, even when questions share a request.

This is an external learned system, not merely a single classifier score or a
hand-written weighted sum. A fixed JEV model can supply the semantic features
for an adaptive predictor/controller. That possibility is distinct both from
training JEV itself and from applying one unchanging threshold at inference.

**Current TT boundary:** the default gate still consumes fixed relevance/guard/
salience rules. The optional v0.11.0 learner now implements a bounded external
feature-discovery loop, actual CatBoost fitting, grouped development evaluation,
and frozen-before-holdout assessment. It learns omission harm and recovery cost;
its first deployment can veto unsafe/uneconomic omissions, not relax fixed guards.
This is not a general JEV workflow controller or post-answer verifier.

Learning is explicitly invoked on labelled experiments. Off/shadow/active runtime
modes, schema/scorer/target identities, exact sources and pinned numeric artifacts
separate fitting from deployment. Live data transfer needs consent; no automatic
training, policy promotion, or data export is enabled. The existing keys are reused
and CatBoost is an optional training dependency, absent from inference.
See [the implementation, data contract and evaluation limits](LEARNED_POLICY.md).

Feature-extraction requests and LLM feature-proposal/evaluation helpers are
internal service work: their dataset text, examples, rubrics and supplied
probabilities must bypass conversational reduction. The existing scope check
already enforces this; `tests/test_jev_learning_scope.py` retains explicit
regressions, including intervening learning calls between main-request retries.

## What Token Terminator actually implements

| Capability | Current integration |
| --- | --- |
| JEV relevance/guard/salience assessment | Implemented as bounded, batched Noul questions through existing OpenRouter or direct TypeSafe support. |
| Exact history, source recovery and reversible Context IR | Implemented by TT; JEV scores are selection signals, never newly established facts. |
| SkillGate | Existing deterministic TT skill filtering; **not** an implementation of TypeSafe's two-stage JEV skill-suggestion cookbook. |
| JEV workflow/tool/skill controller | Not implemented by this ContextEngine candidate. |
| Post-answer claim/citation or requirements verification | Not implemented by this candidate. No automatic semantic accept/retry/escalate loop is claimed. |
| External learned policy / autoresearch feature discovery | Implemented as an optional bounded omission-risk learner: System-2 proposals, JEV semantic features, CatBoost fitting and held-out evaluation. Separate explicit deployment; default fixed gate/cache alone still do not learn. |
| Scope isolation for outside JEV controller/verifier/learning calls | Implemented: these service calls bypass TT unchanged; the separately authorized answering LLM request can still use TT. |

The requested context engine is a useful **subset** of System 2 support. Its
context guard question asks whether omitting a detail could change the answer;
it is not a general input/output safety guardrail. Local golden-answer tests and
vault hashes are not a live JEV citation-verification service. A broader controller
or verifier would need an explicit integration, decision schema, evidence rules,
resource limits and evaluation rather than enabling every helper call implicitly.

## Purpose before target policy

A typed JEV request, including its full state, candidates, queries and question
rubrics, is not a conversational generation request. TT's existing scope check
rejects `state`/`questions` service envelopes even under erroneous conversation
labels or a JEV target-family hint. Known controller/verifier purposes likewise
bypass. Internal JEV transports remain protected against recursive reduction.

The candidate's conservative JEV-target policy is **defensive support for an
explicitly integrated conversational wrapper** identified as JEV-backed; it does
not make native JEV accept chat messages or implement such a wrapper. Raw TypeSafe
System One/OpenRouter Decisions requests bypass before this policy is considered.
The existing preservation flag also remains usable for other explicitly selected
conversational targets. No new model capability, key or endpoint is introduced.

For real generation through a wrapper, retain the documented history-preserving
policy and exact-token gate. Unknown tokenizer or unresolved protected-history
overflow still fails open; host/provider hard-limit enforcement remains necessary.
See [the scope audit](CALL_SCOPE_REVIEW.md) for that unchanged limitation.

## Verification is probabilistic, not proof

Typed/schema-valid output does not guarantee a semantically correct judgment.
A relevance probability is not confidence that a source claim is true. A verifier
must receive the actual evidence needed for its question; its assessment does not
replace exact quote/span checks, deterministic constraints or bounded escalation.
TypeSafe documents uncertainty and recommends handling it in application code.

The additional `tests/test_jev_roles.py` cases cover controller/verifier bypass,
unaltered mixed Choice/Score/Noul envelopes, and a normal answering LLM plus retry
after intervening decision calls. They are offline scope contracts, not live
JEV accuracy, chat capability or pricing measurements. Existing transport guards,
ordinary-model semantics and JEV wrapper preservation behavior are not rewritten.

## Primary documentation checked

- [System One](https://docs.typesafe.ai/concepts/system-one)
- [JEV with coding agents](https://docs.typesafe.ai/introduction/coding-agents)
- [AI primer and training objectives](https://docs.typesafe.ai/introduction/machine-learning-primer)
- [Autoresearch feature discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)
- [Hermes skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion)
- [Intent routing](https://docs.typesafe.ai/patterns/intent-routing)
- [Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)
- [Double-checking citations](https://docs.typesafe.ai/cookbooks/citation_check)
- [Guardrails for LLMs](https://docs.typesafe.ai/cookbooks/llm_guardrails)
- [Verification and escalation cascade](https://docs.typesafe.ai/cookbooks/sde_cascade)
- [HTTP API / question schemas](https://docs.typesafe.ai/api)
- [Confidence and uncertainty](https://docs.typesafe.ai/confidence)

These are the relevant pages checked for this clarification, not a claim of an
exhaustive review of every SDK page, cookbook dependency or example execution.
