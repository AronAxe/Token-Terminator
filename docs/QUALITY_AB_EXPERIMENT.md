# Token Terminator quality A/B experiment

## Objective

Determine whether Token Terminator `balanced` mode is **non-inferior in answer quality on the fixed synthetic challenge suite** to `off` mode while reducing provider-visible input tokens.

This is a paired controlled experiment. Each pair sends the exact same prompt bytes and synthetic evidence corpus to the same Hermes model/provider/reasoning configuration in two fresh sessions. The only intended variable is `TOKEN_TERMINATOR_MODE`:

- **Control:** `off`
- **Treatment:** `balanced`

The experiment tests model answers, not merely payload size or exact artifact recoverability. Its confidence interval describes these 12 deliberately adversarial task families; it is an engineering regression gate, not a population-level claim about every production prompt.

## Hypotheses

1. **H1 — non-inferiority:** balanced-mode task pass rate is no more than 5 percentage points below off mode.
2. **H2 — efficiency:** balanced mode reduces mean provider input tokens.
3. **H3 — graceful recovery:** treatment failures do not concentrate in facts that require exact recovery from compressed evidence.
4. **Null/adverse hypothesis:** compression removes or obscures decisive evidence, causing more omissions, decoy selection, arithmetic errors, or incorrect conflict resolution.

## Experimental unit and assignment

The experimental unit is one `(task, repetition)` pair. Both arms use:

- identical effective prompt bytes, verified by SHA-256;
- identical evidence files and a pair-stable absolute workspace path embedded in the prompt, preventing session CWD restoration from redirecting relative evidence reads;
- identical Hermes executable, model, provider, reasoning level, and user configuration;
- a fresh session per arm;
- a fresh disposable copy of the evidence workspace per arm, recreated at that pair-stable path and removed after the complete process group exits;
- adjacent execution in randomized arm order to limit backend drift.

The runner rejects a trial when the usage receipt reports a different model or provider, the process fails, or the response is not gradeable. Rejected trials are contaminated evidence, not quality failures.

## Easily degradable task classes

The committed synthetic suite contains 12 tasks, two in each category:

1. needle retrieval with confusable nearby facts;
2. multi-document synthesis with distributed constraints;
3. contradiction and recency resolution;
4. exact numeric reconciliation;
5. subtle code/configuration diagnosis;
6. long-list boundary and omission detection.

Each evidence workspace contains at least 12,000 characters, places decoys near true values, and distributes required facts across the beginning, middle, and end. Evidence is synthetic and may contain inert instruction-like text to verify that the agent follows the experiment prompt rather than evidence-embedded instructions.

## Metrics

### Primary metric — answer quality

Binary deterministic answer-quality pass: every required factual, numerical, diagnostic, recency, and completeness assertion matches exactly and no forbidden decoy value is emitted. This is the metric used to decide whether Token Terminator preserves quality. Token savings are secondary and cannot compensate for a quality loss.

### Secondary metrics

- fraction of required assertions passed;
- provider input-token delta and reduction percentage;
- total-token delta;
- tool-call count;
- malformed-response rate;
- control wins, treatment wins, and ties within matched pairs.

Token counts come from Hermes' canonical session accounting. They represent total session burden, including auxiliary calls, rather than a primary-model-only counter. This remains a symmetric secondary measure across arms, but a provider fallback after the first accounted call may not be distinguishable from the session aggregate.

### Guardrails

- provider/model mismatch;
- subprocess failure or timeout;
- missing usage receipt;
- malformed JSON;
- forbidden decoy values;
- treatment-only failures involving recovery-dependent facts.
- control-arm pass rate below 80%, which means the suite has not demonstrated assay sensitivity and cannot support a non-inferiority decision.

## Sample and decision rule

- Stage 1 starts with 12 tasks × 3 repetitions = **36 matched pairs / 72 answer runs**, as requested.
- Stage 1 is a quality checkpoint, not a final non-inferiority claim. The predeclared decision-grade extension is 12 tasks × 6 repetitions = **72 matched pairs / 144 answer runs**; the same results file resumes without rerunning the first 36 pairs.
- Arm order is randomized per pair using a committed seed.
- Results are not considered decision-grade before all 72 uncontaminated pairs complete. At 36 pairs the report is labelled `checkpoint_complete` and exposes answer-quality results without declaring victory.
- Task-clustered paired bootstrap resampling produces a 95% confidence interval for the treatment-minus-control pass-rate delta. Whole task families, not individual repeated runs, are resampled so repetitions are not treated as independent tasks.
- **Non-inferior:** lower confidence bound is at least `-0.05`.
- **Assay sensitivity:** control answer-quality pass rate is at least 80%; both arms failing cannot be mislabeled as equivalent.
- **Efficiency win:** the upper bound of the paired 95% bootstrap interval for treatment-minus-control input tokens is below zero.
- **Keep balanced on this challenge suite:** both conditions hold and no guardrail shows a treatment-specific safety pattern. Production quality still requires continued monitoring and human review of any treatment-only failure.
- Otherwise, inspect failed categories and either narrow the transformation or improve recovery behavior before rerunning the complete fixed suite.

Do not stop early because interim results look good. A provisional report may be generated for operational debugging, but it must remain labelled `collecting` until the target pair count is reached.

Contaminated arms are automatically retried on the next run. The append-only history remains intact, and analysis prefers the latest clean replacement over a contaminated attempt. Extending from three to six repetitions preserves every existing pair's arm order because randomization is seeded independently from the pair ID.

## Cost and privacy

The default route is `openai-codex` with the configured OAuth subscription, so expected marginal API cost is $0. The full experiment makes 144 model runs and takes substantial wall-clock time. No model judge is required: committed deterministic graders are primary. Human blind review can be added after the fixed run as a calibration layer.

Prompts, corpora, and expected answers are synthetic. Run outputs are written beneath `.quality-ab/`, excluded from Git, and should not be mixed with normal user sessions (`--source tool` is used where the Hermes CLI surface supports it).

## Commands

```bash
# Validate fixture integrity without provider calls.
python scripts/quality_ab.py validate --suite benchmarks/quality_ab/suite.json

# Preview the immutable paired execution plan.
python scripts/quality_ab.py plan --suite benchmarks/quality_ab/suite.json

# Collect six complete pairs, resuming an existing result file.
python scripts/quality_ab.py run \
  --suite benchmarks/quality_ab/suite.json \
  --results .quality-ab/results.jsonl \
  --model gpt-5.6-sol \
  --provider openai-codex \
  --reasoning high \
  --max-pairs 6

# Report labels the first 36 pairs as a quality checkpoint. A final decision
# remains unavailable until the suite is deliberately extended to 72 pairs.
python scripts/quality_ab.py analyze \
  --suite benchmarks/quality_ab/suite.json \
  --results .quality-ab/results.jsonl
```

The runner never changes live Hermes configuration. Each subprocess receives its arm through an environment override.