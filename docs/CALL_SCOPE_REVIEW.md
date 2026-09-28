# v0.10.0 call-scope review

Candidate under review: PR #19, `feat/hermes-context-engine-v0.10.0`.
Baseline reviewed: `0cfe572506fc87df4ccf54fcc9ed34757ac05b5f`.
No change to the released v0.9.0, main, live wiki, registries, or running profiles.

## Findings: existing isolation versus actual defects

| Call | Baseline behavior | Change |
| --- | --- | --- |
| Main conversation generation | Hermes' `agent/turn_api_request.py::build_api_request` invokes `llm_request` per physical attempt. TT had no purpose check. | Validate scope before dispatching either the bound ContextEngine or middleware pipeline. |
| Native auxiliary calls (title/compression/vision/approval/helper) | `agent/auxiliary_client.py` uses a separate client; `agent/auxiliary_hooks.py` emits distinct auxiliary observer events. TT was not subscribed. | Preserve that routing; add defense against a helper incorrectly forwarded to generic middleware. |
| Native memory search/rerank/embedding | `plugins/memory/mem0/_backend.py` directly uses its backend client/HTTP adapter. SDK embedding calls are not globally patched by TT. | No SDK/backend rewrite. Verify exact arguments with mock provider/HTTP endpoints. |
| Generic helper/classifier routed through `llm_request` | **Vulnerable:** an active engine binding was sufficient; explicit negative purpose/auxiliary kwargs were ignored. A classifier fixture fell from 5,267 to 1,536 tokens. | Explicit negatives and unknown purpose veto before vault, tokenizer, scorer, model cache or context mutation. |
| TT internal JEV | Direct urllib Decisions/System One calls already bypassed Hermes by construction. Custom transports had no explicit re-entry guard. | Execution-local guard covers both direct and injected transports, including independent scorer invocation, exceptions and async propagation. |
| Tokenizers | Local measurement adapters, not provider targets; no tokenizer monkeypatch. A custom callback could re-enter middleware. | Retain measurement behavior; recursive optimizer work and separately scoped counting calls bypass. |
| Delegated agents/inherited auxiliary turns | Main-shaped metadata/ambient binding alone could authorize reductions. | Existing Hermes auxiliary-task ContextVar and delegated parent lease veto. Internal lifecycle hooks do not capture or replace a main binding. |
| Explicit JEV-backed conversational wrapper | Same semantic pruning/age-collapse path as ordinary expensive targets. | Preservation policy below, separately from internal JEV's role. |

“Unchanged” here means **TT does not rewrite the service input**. A host/backend
can apply its own preprocessing (for example, Mem0's sync-length limit); this
review neither removes nor certifies that separate behavior. Tool-result
compression for evidence subsequently shown to the conversational model remains
an existing TT feature, not interception of the service request that produced it.

## Scope contract

`call_scope.py` is a small boundary check, not another context-engine framework.
It consumes **out-of-band host kwargs**, never purported instructions, private
markers, or purpose declarations inside a prompt/provider payload.

1. TT-internal/re-entrant execution always bypasses. Native Hermes auxiliary-task
   context or a delegated turn's `lease.parent_session_id` also vetoes.
2. Explicit `request_purpose`, `purpose`, `call_type`, `call_role`, `model_role`,
   or `request_scope` must identify conversation/chat/main generation. An unknown,
   malformed or conflicting value bypasses. `aux_task`, `auxiliary_task`, internal
   flags, non-generation operations/endpoints and service envelopes also veto.
3. Without an explicit purpose, only the **registered Hermes adapter** accepts the
   inspected main-hook contract: middleware schema, nonempty session/turn/attempt
   identities, positive API call count, supported generation mode and a message
   history. An engine binding or a model name alone is insufficient.
4. Only then choose an ordinary or conservative final-target policy.

Hermes currently provides no dedicated main-request purpose/target-family field
at this middleware boundary. The adapter uses its actual supported main-turn hook
and available negative role signals, not a fabricated Hermes setting. Other hosts
must opt actual generation requests in explicitly:

```python
decision = runtime.llm_request_middleware(
    request=provider_kwargs,
    request_purpose="conversation",  # host routing decision, not user/prompt data
    session_id=session_id,
    api_request_id=attempt_id,
)
```

Do not forward embedding/rerank/helper work with this authorization. They should
bypass the optimizer, or supply their real negative purpose and receive `None`.
This is a deliberate safety tightening for generic adapters; the ordinary
**authorized** non-JEV reduction algorithm is unchanged. Hermes users do not need
new configuration to authorize native main turns.

A third-party plugin that deliberately forges the entire trusted main-hook
contract while hiding all internal-role signals cannot be distinguished from a
main call at this boundary. Arbitrary in-process Python is not a sandbox. New
Hermes hook/role contracts are tested when pinned, not assumed compatible forever.
TT's async facade carries ContextVars; custom executors must also propagate their
host context. A bare call without that context bypasses rather than guessing.

## Conservative policy for an explicit JEV-backed conversational wrapper

**Architecture clarification:** native JEV returns typed decisions, not
conversational prose. This defensive policy does not add a native JEV chat
API or implement a controller/wrapper. Typed control and verification calls
bypass before it is considered. TT currently implements context-selection
support, not a general workflow router or post-answer citation verifier.
See [JEV roles and the primary documentation](JEV_ROLES.md).

Purpose is established first. Within an authorized conversation, a host-provided
`target_model_family="jev"` has priority. Hermes currently supplies no such field,
so use the **actual outgoing request's model**, not an earlier session model or
TT's scorer configuration: exact provider-qualified `typesafe/jev[-version]` or
`~typesafe/jev[-version]`; bare `jev[-version]` only with the TypeSafe provider or
`api.typesafe.ai` endpoint. No generic substring test. A custom alias can force
preservation with out-of-band `chat_target_policy="preserve"`, or:

```bash
export TOKEN_TERMINATOR_CHAT_TARGET_POLICY=preserve
```

Default is `auto`; invalid policy values preserve conservatively. There is no
new API key, paid model lookup, separate summarizer, or global provider override.
Provider retries/fallbacks reconsider the **outgoing** model on each attempt.

- With room (or no verified window), retain all supplied dialogue by default.
  Skip semantic pruning, turn-age collapse, SkillGate omission and compiler
  receipts/working-state injection. Existing reversible Context IR may run when
  enabled, recoverable and strictly smaller under the actual tokenizer; it does
  not call JEV merely to decide whether a lossless representation is worthwhile.
- If a **known target window** is exceeded, try reversible IR first. Reserve the
  larger of configured output allowance and actual requested max output, plus
  the existing safety margin. Never borrow a different fallback model's window.
- Only remaining budget pressure permits the existing bounded JEV scorer to
  propose low-relevance, low-guard, low-salience omissions. Keep recent/current,
  instructions, code, quotes, exact values, constraints and unscored/uncertain
  evidence. Apply only enough individually token-and-character-saving receipts
  to fit, with verified exact vault backing. Engine retries reuse the existing
  source/query-bound score cache.
- Acceptance rechecks the complete request, tool schemas, real references and
  source integrity. Unknown tokenizer, unavailable evidence/recovery, malformed
  scores or measurement failures preserve the original. No character-only IR or
  invented JEV tokenizer is substituted.

### Hard-limit boundary — do not confuse fail-open with a guaranteed send cap

An accepted budget-pressure candidate must fit the known measured input budget.
But protected/unscored history can itself exceed that budget. Then TT records
`chat_target.state = context_limit_unresolved` and returns the original; it does
**not** silently truncate, invent a summary, or claim that the call fits.
Hermes' current fail-open request/execution middleware cannot reliably abort a
provider call by throwing. Host/provider hard-limit enforcement remains necessary
for that unresolved case and for pre-middleware provider preflights. This change
does not promise a universal hard cap or alter Hermes core to obtain one.

Measurements are complete canonical provider-request JSON under the configured
actual tokenizer, not hidden provider chat-template framing or billed tokens.
The JEV-target arithmetic tests deliberately use a **labelled fixture tokenizer**;
no actual JEV tokenizer, live JEV chat availability/quality or economics is claimed.

## Verification

Audit reads cover upstream Hermes
`5458de948379badc5b84ba624dc029367a28ece4` (September 28, 2026), notably
`agent/turn_api_request.py`, `hermes_cli/middleware.py`,
`agent/auxiliary_hooks.py` and `plugins/memory/mem0/_backend.py`.
The native contract workflow exercises both that snapshot and the candidate's
prior pinned Hermes snapshot `801a9022a742562a3c4578c0d8dd12cfd393fc47`.

The dedicated tests cover every negative scope before any reduction work,
embedding/rerank envelopes even under a wrong chat label, purpose spoofing inside
payloads, native host roles, independent OpenRouter/TypeSafe transport re-entry,
measurement callback recursion, async/cancellation cleanup, JEV preservation,
reversible IR, bounded emergency selection, salience veto, unknown tokenizers,
exact recovery, protected overflows and ordinary/JEV provider fallback retries.

`scripts/smoke_hermes_context_engine.py` now calls the **real main request builder**
and per-attempt middleware, real auxiliary relay helpers, SDK embedding serialization,
and actual Hermes Mem0 adapters against fake provider/HTTP endpoints. It verifies
that already-isolated internal clients never dispatch middleware, and incorrectly
forwarded auxiliary/delegated calls cannot consume the main engine binding.
No paid calls or live profile changes are involved.

Local full suite: **403 passed, 2 optional integration skips** (72 additional
scope/policy evaluations over the original 331). Ordinary non-JEV benchmark:
**120 evaluations**, all transformations non-enlarging; engine visible-answer
checks **30/30**. Prior token totals reproduce exactly:

| Arm | GPT-4o tokenizer: five tasks once | GPT-4 tokenizer: five tasks once |
| --- | ---: | ---: |
| Default middleware | 19,002 | 20,088 |
| Middleware + JEV + IR | 12,962 | 13,598 |
| Quality-preserving middleware, age-collapse off | 70,554 | 74,251 |
| ContextEngine + JEV + IR | 31,934 | 32,100 |

The first two arms still fail the benchmark's old-evidence checks; shorter is not
quality-preserving. This audit does not change or relabel that prior finding.
Full observations and native smoke output are retained by CI; final CI status is
reported on PR #19, not assumed from local results. No unbounded/live paid tests.
