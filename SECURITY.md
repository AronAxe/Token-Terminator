# Security

Please report suspected vulnerabilities through a private GitHub security advisory rather than a public issue.

## Data boundaries

Token Terminator stores exact large tool artifacts and private provenance locally because exact recovery is part of its acceptance contract. By default, plugin-owned files live under:

```text
<HERMES_HOME>/token-terminator/
```

The artifact vault stores raw artifact text, content digests, tool names, tool arguments, observations, exposure leases, optional bounded working state, and request-reduction metrics. The separate experiment ledger stores session/turn identifiers, mode/model/provider labels, token/cost totals, transformation counts, and salted local prompt fingerprints. It does **not** store command strings, prompts, or tool contents.

With Jev disabled (the default), the reduction pipeline makes no semantic-service upload. Opting into Jev creates the external-service boundary described below. Context IR itself is entirely local.

On POSIX, Token Terminator enforces `0700` on private parent directories and `0600` on SQLite files. On Windows, files remain under the user's Hermes profile and inherit its Windows ACLs. Anyone who can read that profile can read private artifacts; treat the profile as sensitive application data.

## Execution and transformation safety

- RTK is invoked with an argument array and `shell=False`.
- Remote terminal backends are disabled by default.
- Native compression is accepted only after exact artifact write and read-back succeeds.
- The complete model-visible payload, including receipts and optional working state, must be strictly smaller.
- Request compilation operates on deep copies and fails open if a request cannot be copied safely.
- Malformed requests, unavailable storage, migration failures, vault-capacity failures, missing host APIs, and non-smaller output leave normal Hermes behavior unchanged.
- Token Terminator registers a ContextEngine only through explicit installation/selection; it does not modify LCM state.
- Receipt metadata is bounded and excludes raw tool arguments and content.
- Artifact reads, searches, graph operations, identifiers, metadata, and replay batches are bounded in the domain layer.

## Operational guidance

Do not install two distributions that own the `rtk_hermes_plus` Python package. When migrating from `rtk-hermes-plus` 0.2.0, uninstall it before installing `token-terminator` 0.3.0. Enable only one Token Terminator/RTK rewrite plugin at a time.

Back up or remove `<HERMES_HOME>/token-terminator/` separately from package uninstall. Disabling or uninstalling code intentionally does not erase private artifacts.

## RTK executable trust boundary

When `TOKEN_TERMINATOR_RTK_PATH` is unset, Token Terminator discovers `rtk` through the host process `PATH`. A malicious or accidentally shadowed executable named `rtk` can therefore influence command rewriting. Security-sensitive deployments should pin the expected executable with `TOKEN_TERMINATOR_RTK_PATH` and protect that file and its parent directory from untrusted writes. Token Terminator still invokes RTK with an argument array and `shell=False`; executable discovery is the separate trust boundary.

## Optional Jev external-service boundary

Jev integration is disabled by default. Enabling it requires `TOKEN_TERMINATOR_JEV=true` plus one provider credential: `OPENROUTER_API_KEY` for OpenRouter or `TYPESAFE_API_KEY` for direct TypeSafe access. In `auto` mode OpenRouter is preferred when both are present. The legacy `TOKEN_TERMINATOR_JEV_API_KEY` remains a temporary direct-TypeSafe compatibility alias.

The key is read from the process environment only. Token Terminator does not write it to the repository, artifact vault, experiment ledger, request metrics, or status output.

When Jev is enabled, Token Terminator sends a bounded state object either to OpenRouter's `https://openrouter.ai/api/alpha/decisions` endpoint or directly to TypeSafe's `https://api.typesafe.ai/v1/systemone` endpoint. That state contains the current user request and selected prior **plain-text user/assistant** candidate messages. On Hermes, separately fenced `<memory-context>` background appended to the current user message may also be included as its own candidate. System/developer messages, tool messages and results, messages containing tool calls, structured/multimodal content, and the user's actual current-turn words as a removal candidate are excluded.

Jev is not trusted with destructive authority. Its typed relevance/guard probabilities can only nominate an eligible prior message for compaction. Token Terminator must first write and read back the exact message from the local vault, prove that the recovery receipt makes the complete request smaller, and—when exact token measurement is available—prove that it also uses fewer tokens. Network errors, timeouts, malformed responses, missing answers, storage failures, and failed size gates all leave the already-reduced non-Jev request unchanged.


## Context IR evidence and authority boundary (v0.9.0)

`TOKEN_TERMINATOR_CONTEXT_IR` defaults to `false` and adds no API or credential. Jev scores are untrusted attention signals, never facts. Missing, nonnumeric, nonfinite and out-of-range probabilities are rejected; errors expose types only, not external exception text.

The stage understands one `messages` list or one Responses-style `input` list. It modifies only prior plain-string user/assistant message content, retaining outer metadata and role. It skips system/developer/tool messages, tool calls/results, structured content, multimodal last-user turns, unusual message metadata, existing TT artifacts and existing IR. It does not guess which earlier user was current when the last user has structured content.

Current user wording is never recoded. When IR is on, Jev also leaves the entire current user message—including `<memory-context>` fences—unchanged. This deliberately narrows v0.8.2's memory-block selection while the new layer is enabled.

Recognizable hard constraints, code, quotes and exact values in arbitrary prose are vetoed. Structured records preserve exact scalar values but reject instruction-like keys/values and named code/quotation fields. These guards are syntactic and cannot recognize every imaginable instruction. IR is not a prompt-injection detector, instruction sanitizer, or authority upgrade. Encoded content remains data in its original message role.

Recovery must actually be present in the request: a compatible `token_terminator` tool declaration including `artifact_get`, `artifact_id`, `offset` and `limit`, with no tool choice that prohibits recovery. No implicit recovery promise is accepted.

Each winning source is inserted into the existing content-addressed vault and exposure-pinned in **one write transaction**. Concurrent writers and capacity pruning cannot delete it between insertion and pinning. Exact read-back, SHA-256 and source-position observations are checked before dispatch. Actual artifact IDs, including a collision-expanded ID, are substituted before the final size gate.

`inspect_ir(text, store)` verifies the source hash, recorded message position and the entire regenerated representation. It returns source metadata and immutable `SourceUnit` records: ordinal, Unicode-character start/end offsets and kind (`record` or `span`). Every row/span maps to a specific exact source slice. A future graph adapter can attach typed node/edge/path information to these units without accepting generated evidence.

Models use the existing `token_terminator action=artifact_get` with the displayed `artifact_id` and optional `offset`/`limit`. Existing `artifact_peek` and `artifact_find` permit progressively deeper inspection. The Python `expand_ir` helper validates the representation and returns a bounded exact source page. Normal vault recovery reads also verify hash/length integrity, so corruption after dispatch is not silently returned as exact data.

The exact source is the **post-TT, pre-IR input**. IR does not claim to reconstruct information already transformed by earlier TT stages; those stages retain their own vault/recovery contracts. Source IDs remain ordinary artifact IDs, with no new database schema or tool action.

Published evidence stays protected by existing exposure retention. If a later operation fails after pinning, safe but unused artifacts may remain pinned. This favors recoverability over aggressive cleanup. Capacity exhaustion fails open; it is not permission to evict published evidence. Back up the vault alongside transcripts. Disabling IR or rolling back does not erase it.

Each format evaluation tokenizes the **complete canonical provider-bound request JSON**, including every field, tool schema, role, source ID and decoder legend. Greedy bounded search accepts improvements over the current working request. After all real source IDs have been written, the compiler remeasures the whole request and requires strict token and character savings against the untouched pre-IR request. Backend/model changes or missing measurements veto the result. There are no provider-text additions after this gate.

The existing adapter's canonical JSON measurement is exact for that string under its selected tokenizer. It is **not** the provider's hidden chat-template framing or a claim about billed token counts. Host adapters may supply a stricter whole-request counter through the existing `measure_request` interface. Compare deltas using a tokenizer actually matched to the target model; arbitrary encoding overrides can invalidate that alignment.

Status exposes version/limits. Per-decision `metrics.context_ir` contains format counts, evaluations, raw/final tokens/chars, elapsed time, failure reason and `measurement_scope=canonical-request-json`. Source text, source IDs and raw exceptions are excluded from those metrics.

The optional live benchmark explicitly calls configured Jev and OpenRouter and validates read-only recovery calls against source IDs already in the request. Raw answers and keys are not persisted. CI never runs the live benchmark.


## v0.10.0 selected ContextEngine boundary

Selection is explicit; installing its user-directory adapter does not select it,
change Hermes core/config, or migrate LCM. Full available conversation messages
(including sensitive content) are persisted locally as exact message JSON in the
existing private vault. Hashes prove integrity, not truth. Persistent history pins
survive reset and normal pruning; vault capacity and bounded-search failures retain
original requests and return explicit recovery errors. This release has no automatic
history deletion/unpin policy. Back up and secure the vault; deleting it invalidates
references. File-system protection is not encryption or multi-tenant isolation.

Enabling existing JEV sends bounded exact older user/assistant regions, the current
query and recent plain conversation to the configured OpenRouter/TypeSafe service.
This is an expanded historical-data boundary, not a local-only classifier. It adds
no API key model. The complete body, batches and timeout are bounded; caps are not
a verified dollar budget. Scores may be wrong or missing and are not factual claims.
Malformed global results undo all semantic edits; individual invalid probabilities
never authorize omission. Only complete valid score batches are cached in process,
bound to the full payload hash; session/model resets clear the cache.

The new history tool checks session membership and source hashes before returning
exact pages. Historical recall is labeled data and cannot regain system/developer
or tool authority. Existing generic artifact recovery retains its original scope;
this addition is not an authorization retrofit for unrelated tools. Regex guards
are conservative vetoes, not a universal multilingual instruction detector or
prompt-injection defense. Source text is never converted into invented graph facts.

A turn-scoped execution-context binding prevents cross-session plan reuse and keeps
provider retries out of legacy age-collapse. The async adapter copies this binding
to executor work. Missing tools, stale bindings, unsupported stateful requests,
unknown tokenizers and storage/measurement failures do not authorize compaction.
The final invariant covers the complete request at TT's middleware output, not later
third-party rewrites, hidden provider framing or pre-middleware host hard limits.
The user transcript remains unchanged even when the provider cannot fit it.


## Call-purpose boundary (v0.10.0 review)

The public request entry point checks purpose before any engine/semantic/tokenizer
work. Internal service envelopes and negative/unknown host role signals bypass;
TT's own work has an execution-local re-entry guard. Prompt metadata cannot opt a
request in. Native Hermes auxiliary clients already bypass this hook and remain
unchanged. This is routing defense, not a sandbox against arbitrary trusted
plugins forging all main-hook metadata. See [call-scope review](docs/CALL_SCOPE_REVIEW.md)
for the exact authorization contract, executor propagation and unresolved context
limit handling. No new external service or credential boundary is introduced.

## v0.11.0 learned-policy boundary

The learner is an opt-in ContextEngine omission veto, not a source of facts or
instruction authority. It cannot relax existing guards, exact source/recovery
verification or the final tokenizer gate. Invalid deployment artifacts/features
retain evidence. Policy loading occurs only after conversational scope approval;
feature/proposal/evaluation callbacks run under internal-call protection.

Deployment accepts only bounded numeric JSON trees with an explicitly pinned
SHA-256, matching feature/scorer/generation-target identities and an eligible
held-out assessment. No pickle, eval, arbitrary imports or native CatBoost model
loader runs in Hermes. A checksum is not a signature or proof of label quality.

Training reads only an explicitly supplied labelled file; it does not mine or
export the live vault. Live mode requires explicit data-transfer consent. Current
query/source data goes to the configured JEV provider, and up to six development
error examples per round go to the chosen System-2 proposer. Holdout labels never
guide discovery or fitting. Connected session/task/exact-source groups prevent
exact split leakage, not all semantic duplication or reuse across separate runs.

Treat generated question rubrics, numeric models, replay and reports as private:
questions can reproduce training information even when reports omit raw source
fields. Outputs are local/create-only, mode 0600 with new directories 0700 on
Unix; secure parents and platform ACLs remain the operator's responsibility. No
training data, policy or outcome telemetry is uploaded or enabled automatically.
Request/body/round budgets and HTTP timeouts bound built-in service work but are
not a hard spending ceiling or preemptive sandbox for arbitrary custom callbacks.
Use trusted callbacks and bounded synthetic/recorded tests before live operation.

See [LEARNED_POLICY.md](docs/LEARNED_POLICY.md) for exact limits, deployment
approval, finite-sample quality qualifications and the existing unresolved
context-limit enforcement boundary.

## Local dashboard and Desktop accounting (v0.11.0 candidate)

The optional standalone dashboard binds only 127.0.0.1:7474. It has no user
authentication: local users/processes can read profile labels, model ids and
numeric accounting. Do not publish it to a network. It offers GET-only fixed
assets/aggregate endpoints, strict Host/Origin checks, no CORS, frame denial,
no-store and CSP. Local configuration is the only source of database paths;
symlinked or duplicate/hardlinked sources are refused. It reads SQLite accounting
columns in read-only snapshots, never vault/source content or credentials, and
never calls a provider or tokenizer. A local adversary who controls those files
is outside this boundary. Some incomplete/unattributed legacy stores are withheld.

The Desktop half uses supported namespaced `ctx.rest` behind Hermes' existing
authentication and Python plugin allowlist. Its backend limits reads to the
current task-local profile home; client parameters cannot choose a filesystem
path. The status counter and cache are connection/profile-scoped and do not
silently route a remote dashboard to this machine's localhost. Installation and
enable are separate and opt-in. See [DASHBOARD.md](docs/DASHBOARD.md) for limits,
accounting qualifications and rollback. The dashboard adds no service credential,
background training or publication.
