# Learned omission policy: bounded synthetic regression

This benchmark runs **real CatBoost fitting and numeric deployment**, with deterministic
fixture JEV and System-2 proposal responses. No live model calls or private data are
used. It tests the implementation, not representative live accuracy or economics.

## Setup and outputs

Run `python scripts/benchmark_learned_policy.py --repeats 3 --output results.json`
after installing `.[learning]`. Complete trial observations and budget events are
written to the requested path; the committed `results.json` is a compact summary.
CI uploads the full output, with runtime-specific latency rather than claiming
hardware-independent timings. Tokenizer loading is warmed before trial timing.

The corpus contains 160 synthetic source-region experiments: 128 development rows
in 16 linked groups and 32 holdout rows in four groups, covering two generation
model identities. All queries concern a prior meeting-place decision. This is one
controlled task family, not a diverse production test set. Repeated distractor
prose and deliberately poor base gate responses create recoverable omission errors.
Labels and training token costs are synthetic; no actual target-model answer labels
were collected. All source hashes and split restrictions still apply.

The loop evaluates its initial three features, rejects one uninformative proposed
feature, then accepts a dependency feature. Questions are revised through the
actual feedback/proposal interface, but the fixture proposer is deterministic—not
a live LLM demonstration. Actual CatBoost heads learn harm and recovery costs from
those feature columns. Questions, threshold and weights are frozen before holdout.

## Local reference run (three repeats)

| Target tokenizer | Full request | Fixed gate / shadow | Learned active | Exact required spans: fixed / active |
| --- | ---: | ---: | ---: | ---: |
| GPT-4o | 8,150 | 1,716 | 3,325 | 0/8 / **8/8** |
| GPT-4 | 8,147 | 1,696 | 3,309 | 0/8 / **8/8** |

Each number is one complete request, not a sum over repetitions. Active preserves
all tested required spans while using **59.20% / 59.38% fewer tokens than full history**.
It is larger than the incorrectly pruned fixed-gate prompt, intentionally. Shadow
returns the fixed-gate request exactly and therefore does not repair its omissions.
Both shadow and active compute learned checks, but only active applies the veto.

Across 18 trials, every final request is non-enlarging, all protected boundary
messages remain exact, recovery succeeds, and identical retries add zero JEV calls.
Visible-span checks do not secretly recover evidence to manufacture a correct answer.
Counts measure canonical complete-request JSON under the actual target tokenizer,
including recovery schemas/references, not hidden provider framing or billed tokens.

Median local middleware times (off / shadow / active) were **115.442 / 218.422 /
203.154 ms** for GPT-4o and **149.159 / 256.958 / 249.049 ms** for GPT-4. These include
engine capture/storage but exclude real provider network/model latency. Off and active
use three fixture JEV batches per trial; shadow uses six because its baseline is
separate. Extra questions consume input/output even when call counts do not grow.

An induced exact-recovery append followed by complete-request remeasurement gives
**3,577 / 3,561 tokens** for the active arm. This is a controlled resend probe, not a
full live Hermes tool-call transaction or an end-to-end answer/recovery measurement.

## Learning checks and cost scope

Development grouped validation selected an operating point with 96/128 rows omitted,
zero observed harmful omissions, and 24,000 synthetic recovery-adjusted saved tokens.
The frozen holdout policy omitted 24/32 rows, with zero observed harmful omissions
and 6,000 synthetic net tokens saved. The intentionally weak fixed gate omitted
32/32, including eight required sources, and its annotated net saving was negative.
These are omission-experiment labels, not real LLM quality scores or claimed calibrated
risk. Per-target results and Brier values are in the committed summary.

The training loop made **36 fixture feature-batch calls and two fixture proposal
calls**, not one request per each of 160 rows. No paid calls were made. Fixture cost
metadata is zero; actual JEV/proposer cost is unknown. Provider cost absent in live
responses is reported as null, not inferred to be free.

Tests also flip holdout labels and prove the selected questions, weights, feature
ranges and threshold do not change. Grouped source/session/task overlaps, malformed
features, scorer/target changes, failed eligibility, unapproved hashes and out-of-range
features fail safely. This does not detect all paraphrase leakage or distribution shift.

## Existing off-mode regression

The original five-task engine benchmark is retained independently. A local one-repeat
run (40 arm evaluations) reproduced all pre-extension token totals exactly:

| Arm | GPT-4o: five tasks once | GPT-4: five tasks once |
| --- | ---: | ---: |
| Ordinary middleware | 19,002 | 20,088 |
| Middleware + JEV + IR | 12,962 | 13,598 |
| Quality-preserving middleware, age-collapse off | 70,554 | 74,251 |
| ContextEngine + JEV + IR, learned mode off | 31,934 | 32,100 |

The two age-collapse-on controls still fail those old-evidence checks; their smaller
prompts are not claimed as quality-preserving. The off-mode ContextEngine retains
all tested answers/targets. Existing pinned-Hermes CI repeats this suite independently.
No reproducible LCM implementation or new LCM comparison is introduced here.

No trained fixture model is shipped as a production policy. Use independent labelled
experiments, holdouts and shadow evaluation before reviewing a deployment artifact.
See [the training and safety guide](../../docs/LEARNED_POLICY.md).
