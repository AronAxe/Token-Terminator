# Learned omission-risk policy (v0.11.0 candidate)

**Review candidate, off by default.** This is a fitted outer system around JEV,
not a renamed fixed relevance score and not fine-tuning of JEV's weights.

```text
Explicit exact-source omission experiments with observed outcomes
-> grouped development cross-validation
-> System-2 model proposes or revises semantic feature questions from dev errors
-> batched JEV Noul/Score features
-> CatBoost omission-harm and recovery-token predictors
-> freeze questions, models and threshold
-> separate final holdout evaluation
-> operator review and explicit deployment
```

The learned layer is an additional veto on otherwise eligible omissions. It can
rescue evidence the fixed gate would lose; it cannot authorize discarding protected
or uncertain context. Exact evidence/vault references, conversational call-scope
isolation, conservative JEV-wrapper behavior and complete-request token gates remain.

Runtime modes are `off`, `shadow` and `active`. Off performs no policy work. Shadow
returns the original fixed-gate request and separately measures the learned plan,
using up to twice the configured JEV batches. Active asks extra questions in the
existing batches and applies an approved fitted policy. Invalid/missing features,
artifact hashes, incompatible scorer/target identities or numerical domain checks
retain evidence. CatBoost is a training-only optional dependency; inference reads a
bounded numeric JSON tree format, never pickle or executable model content.

```bash
export TOKEN_TERMINATOR_LEARNED_POLICY_PATH=/private/policies/run-002/policy.json
export TOKEN_TERMINATOR_LEARNED_POLICY_SHA256="COPY_THE_REVIEWED_64_HEX_DIGEST_HERE"
export TOKEN_TERMINATOR_LEARNED_POLICY_MODE=shadow
```

Training uses `token-terminator policy-train` and optional `[learning]` dependencies.
It requires an explicit labelled JSONL dataset and either exact offline replay or
`--live --allow-external-data` plus an explicitly chosen generative proposal model.
Existing OpenRouter/direct TypeSafe JEV credentials are reused. The built-in
System-2 proposer uses the existing OpenRouter chat credential; a Python callback
or recorded replay can supply another existing System-2 integration. Native JEV
is not treated as a generative chat model. No live vault mining, automatic data
export, automatic activation or background self-training is enabled.

Limits cover rows, rounds, questions, model size, serialized request volume and
combined proposal/feature calls; there are no automatic retries. Cooperative
deadlines and HTTP timeouts are not a hard dollar ceiling. Unknown cost remains
unknown. Artifacts are private create-only files and must be reviewed for training
information leakage. Shared session/task/exact source evidence cannot cross folds
or holdout. Finite holdout eligibility is not proof of calibrated omission risk or
universal answer-quality preservation.

See the [complete training/configuration/security guide](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/docs/LEARNED_POLICY.md)
and [executable synthetic benchmark](https://github.com/AronAxe/Token-Terminator/blob/feat/hermes-context-engine-v0.10.0/benchmarks/learned_policy/README.md).
The benchmark runs actual CatBoost fitting but fixture JEV/proposer responses;
it does not validate live service economics or real-model answer quality. A trained
fixture policy is not shipped or automatically deployed. Roll back by setting mode
to `off` and restarting; keep the exact-evidence vault.
