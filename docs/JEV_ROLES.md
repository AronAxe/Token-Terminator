# JEV: agentic control and support for an LLM

Scope: v0.10.0 review candidate, PR #19. Documentation checked September 28,
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

## What Token Terminator actually implements

| Capability | Current integration |
| --- | --- |
| JEV relevance/guard/salience assessment | Implemented as bounded, batched Noul questions through existing OpenRouter or direct TypeSafe support. |
| Exact history, source recovery and reversible Context IR | Implemented by TT; JEV scores are selection signals, never newly established facts. |
| SkillGate | Existing deterministic TT skill filtering; **not** an implementation of TypeSafe's two-stage JEV skill-suggestion cookbook. |
| JEV workflow/tool/skill controller | Not implemented by this ContextEngine candidate. |
| Post-answer claim/citation or requirements verification | Not implemented by this candidate. No automatic semantic accept/retry/escalate loop is claimed. |
| Scope isolation for outside JEV controller/verifier calls | Implemented: these service calls bypass TT unchanged; the separately authorized answering LLM request can still use TT. |

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
