# Learned omission-risk policy — v0.11.0

Available in v0.11.0, alongside the selectable ContextEngine and call-scope work
first developed under the unshipped 0.10.0 milestone. The layer is experimental
and off by default; no pretrained production policy is included.
No training or activation happens merely by installing the package.

## What actually learns

This is an optional external learning system, not a new fixed weighted score:

```text
labelled, exact-source omission experiments
  -> grouped development cross-validation of the three existing JEV features
  -> System-2 model proposes/revises additional semantic questions from dev errors
  -> JEV measures Noul probabilities / Score-distribution mean and spread
  -> CatBoost fits omission-harm and recovery-token predictors
  -> development-only feature/threshold selection, at most four proposal rounds
  -> freeze questions, models and operating threshold
  -> evaluate the untouched holdout
  -> write a private, versioned policy for explicit operator review
```

The runtime uses that fitted policy as an **additional omission veto**. It can
retain evidence that the current relevance/guard/salience gate would otherwise
omit. It cannot grant permission to remove a protected or uncertain source. This
first release does not use learning to make the existing safety envelope more
aggressive, implement a general agent controller, or verify final answers live.
JEV's weights remain fixed. CatBoost learns the outer predictors; the System-2
proposer can add, revise or discard the extra question definitions.

Extra questions share existing source-region batches through OpenRouter Decisions
or direct TypeSafe, using the existing JEV credentials. They do not cause one
request per span. Sources with different current/recent queries cannot share that
state and require separate batches. Larger question sets may fill body limits
sooner; unscored history is retained. No secret or new key scheme is added.

## Runtime modes and safety

| Mode | Behavior |
| --- | --- |
| `off` (default) | Existing engine behavior, with no policy file read or extra questions. Ordinary middleware-only mode remains unchanged. |
| `shadow` | Construct the original fixed-gate plan first, then separately audit the learned plan. Return only the baseline request. Up to twice the configured JEV batches; content-free aggregate metrics expose the difference. A shadow failure cannot alter the baseline. |
| `active` | Ask the additional questions in each bounded engine batch and use the approved fitted predictors before eligible omissions. Missing, invalid or out-of-domain features retain their region. |

The learned feature vector is tied to exact source content, current/recent query
through its request-bound cache, question schema, and configured JEV provider/model.
Declared scorer-model drift invalidates features. The artifact also names the exact
outgoing generation-model identities represented in both development and holdout;
a different target fails open instead of borrowing another model's policy. A
provider alias that changes weights without changing its identifier is not fully
detectable: use pinned versions and re-evaluate after a model/provider change.

All call-purpose checks run **before** policy loading, scoring, measurement and
vault work. Feature extraction and proposal/training/evaluation callbacks execute
under the existing internal-call guard, including intervening work between provider
retries. Raw typed JEV requests, embedding text, reranking candidates, classifiers
and unrelated helper calls are never conversational reduction targets.

The learner is downstream of fixed eligibility and upstream of the existing exact
vault/reference and final-request gates. System/developer authority, current user
wording, protected code/quotations/values/constraints, uncertain regions, and the
JEV-backed conversational-wrapper preservation policy retain their protections.
Lossless Context IR still runs where permitted. No new graph facts are invented.

Deployment requires both a local policy path and an explicitly approved SHA-256.
The bounded JSON artifact contains numeric trees, not executable code, pickle or a
native model loader. Runtime inference uses only Python's standard library and
matches the numeric CatBoost export in tests; CatBoost is needed only for training.
The checksum is integrity/approval binding, **not** a signature from a trusted
trainer or proof that labels are correct. Only load policies you trust.

A prediction cannot bypass the strictly smaller complete-request tokenizer gate.
Per-region recovery cost is compared with a measured complete-request saving, not
character count. Final real references and tool schemas remain in the outer gate.
Unknown tokenizer, corrupt evidence or failed final acceptance preserves the input.
The existing `context_limit_unresolved`/host-provider enforcement limitation is
unchanged; this is not a new unconditional provider-send cap.

The safety statement is relative to fixed eligibility computed for the same
request. Additional questions may affect live JEV's base probabilities; identical
answers between separately queried off/active runs are not guaranteed. Shadow
mode deliberately obtains a separate baseline rather than assuming equivalence.

## The dataset: explicit observed outcomes, not guessed labels

`policy-train` reads an explicitly supplied local UTF-8 JSONL file. It does **not**
read, mine, export or label the live vault automatically. Collect controlled omission
experiments for the actual generation target: compare full-source and omitted-source
answers against independent evidence/constraint checks, or have a human assess them.
Include subsequent recovery/resend costs; an answer that is shorter but wrong is not
a positive example. JEV's assessment must not serve as its own outcome label.

Each row has exactly these fields:

| Field | Meaning |
| --- | --- |
| `row_id`, `session_id`, `task_id` | Stable identities for rows and related task/session groups. |
| `split` | `dev` or `holdout`, decided before discovery. |
| `target_model` | Exact outgoing generation model used in the labelled experiment. |
| `query`, `recent` | Current user text and exact recent user/assistant `{role,content}` records used by the scoring query. |
| `source` | Exact region as a list of `{role,content,ordinal}` records; only plain user/assistant dialogue. |
| `source_sha256` | `policy_features.fingerprint(source)`; validated again before learning. |
| `omit_harm` | Observed integer 0 or 1: did omitting this region damage the required answer/evidence/constraint? |
| `recovery_tokens` | Observed additional input tokens caused by recovery, including full provider resends where applicable. |
| `saved_tokens` | Measured initial saving for that omission experiment, including receipts. |
| `label_origin` | `human`, `deterministic`, or explicitly `synthetic`; never `jev`. |

There must be 12–512 rows, at least as many independent development groups as
folds, and at least two holdout groups. Every deployment target needs both outcome
classes in both splits. Shared sessions, tasks, duplicate source regions and shared
individual source messages are unioned into connected groups and cannot cross
folds or the dev/holdout boundary. Duplicating a source under another row/ordinal
cannot evade that rule. This detects exact overlaps, not every paraphrased duplicate.

A human must still choose meaningful independent tasks and avoid leakage through
labels or collection procedures. The fixed shared query of the synthetic demo does
not establish generalization to diverse workloads. Reusing a holdout across separate
runs is not automatically detected; retire it after inspecting its results.

## Training, inspection and activation

Install the optional training dependencies in a separate training environment or
in the source checkout. Hermes only needs the ordinary runtime installation:

```bash
python -m pip install -e '.[learning]'
python -m rtk_hermes_plus.cli policy-train --help
```

For strict offline replay, supply a recorded replay file produced by a previous
explicit training run, with the same dataset, configured scorer identity and round
count. Missing response digests fail; there is no network fallback or key requirement.

```bash
python -m rtk_hermes_plus.cli policy-train \
  --dataset labelled-experiments.jsonl --replay recorded-replay.json \
  --output-dir reviewed-run-001 --rounds 2 --max-calls 64
```

For live feature discovery, configure the existing JEV route/key and a pinned
`TOKEN_TERMINATOR_JEV_MODEL` (not `latest`). The built-in generative proposer uses an
explicitly chosen chat model and the **existing** `OPENROUTER_API_KEY`. Direct TypeSafe
can still supply JEV features; it does not itself supply the chat-model proposer.
With no OpenRouter chat credential, use recorded proposals/replay or pass your
existing System-2 callback to the Python `discover` function instead. No new key is
required for normal JEV/TT use, and native JEV is not treated as a chat model.

```bash
python -m rtk_hermes_plus.cli policy-train \
  --dataset labelled-experiments.jsonl --live --allow-external-data \
  --proposal-model "$SYSTEM2_MODEL" --output-dir reviewed-run-002 \
  --rounds 2 --folds 3 --iterations 64 \
  --max-calls 64 --max-total-chars 2000000 --deadline-seconds 300
```

`--allow-external-data` explicitly authorizes sending source/query data to the chosen
JEV provider and up to six development error examples per round to the proposer.
Never use this on private data without appropriate permission. Provider terms and
retention still apply. The budget counts feature and proposal requests together,
including failures, and checks actual built-in proposal request serialization.
There are no automatic retries. Calls, question counts, rows, model size, response
size and rounds are bounded. Deadlines are checked between/after work; they cannot
preempt an arbitrary Python callback or guarantee a precise wall-clock cutoff during
a fit. Built-in HTTP clients additionally have per-call timeouts. These are **not
a hard dollar ceiling**; unreported service cost is `null`, not zero.

The new private directory contains `policy.json`, `report.json`, and `replay.json`.
Output is create-only: no existing version is overwritten. Unix-created files have
mode 0600 and directories 0700; secure parent directories/platform ACLs remain the
operator's responsibility. Replay stores source-request hashes and numeric answers,
not a source transcript. Learned questions could themselves reproduce training
information, and numeric models can leak training properties: treat all artifacts
as sensitive. No artifact is committed, uploaded or activated by the trainer.

Inspect development and per-target holdout results, question wording, provider/model
identity, and real answer regressions. `activation_eligible` requires zero observed
harmful omissions on the selected development operating point and final holdout,
plus positive holdout recovery-adjusted savings. It is a finite dataset eligibility
check, not a statistical non-inferiority certificate or calibrated harm guarantee.
The harm threshold is selected on development data; holdout labels never change
questions, fitted weights or that threshold. A failed holdout is a rejected candidate,
not an invitation to tune against that holdout.

Begin with shadow mode in the already selected TT ContextEngine profile:

```bash
export TOKEN_TERMINATOR_LEARNED_POLICY_PATH=/private/policies/run-002/policy.json
export TOKEN_TERMINATOR_LEARNED_POLICY_SHA256="COPY_THE_REVIEWED_64_HEX_DIGEST_HERE"
export TOKEN_TERMINATOR_LEARNED_POLICY_MODE=shadow
```

After explicit review, change only `shadow` to `active` and restart Hermes. A bad
hash, incompatible scorer/target or ineligible active artifact retains history.
Unknown/invalid mode values default to off. To roll back, set the mode to `off`
and restart; do not delete the existing exact-evidence vault. Questions/model files
are not hot-retrained. An updated policy requires a new artifact and hash approval.

Ordinary middleware mode does not deploy this learned engine policy. The complete
existing middleware path and off-mode engine benchmarks remain regression controls.
The original ContextEngine installation/selector steps are in [CONTEXT_ENGINE.md](CONTEXT_ENGINE.md).

## Evaluation and limits

Run the bounded synthetic executable demonstration after installing `[learning]`:

```bash
python scripts/benchmark_learned_policy.py --repeats 3 --output /private/learned-results.json
```

It uses fixture JEV/proposer responses but **real CatBoost fitting**, including an
unhelpful proposed feature rejected before a useful one is selected. It then sends
held-out history through the actual TT engine, compares off/shadow/active modes,
checks exact visible evidence, protected boundaries, unchanged host history,
recovery and retries, and measures complete requests under two actual tokenizers.
The trained fixture policy is temporary, not shipped or deployed as a production
policy. The recovery probe is an induced exact-evidence append and full-request
remeasurement, not a live Hermes tool-call/network transaction.

The small synthetic case intentionally gives the fixed gate poor base judgments.
It proves the learning/inference wiring can rescue omissions; it is not a claim
about normal live JEV error rates or representative model quality. The active prompt
can be larger than an incorrectly pruned prompt—that is the intended repair. See
[the benchmark report](../benchmarks/learned_policy/README.md).

Range-based abstention detects out-of-range numerical features, not arbitrary
semantic distribution shift. Correct source linkage does not prove a semantic
judgment. Training labels and complete-request costs must be reliable, real models
need task-specific held-out validation, and final provider billing framing remains
outside TT's canonical-request tokenizer measurement.

Primary design references: TypeSafe's [autoresearch cookbook](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery),
[AI primer](https://docs.typesafe.ai/introduction/machine-learning-primer), and
[typed-question API](https://docs.typesafe.ai/api). This is TT's bounded
omission-risk application, not a port of all TypeSafe agentic-control examples.
