# ContextEngine benchmark — v0.10.0 candidate

Run `python scripts/benchmark_context_engine.py --repeats 3 --output results.full.json`.
The runner is offline-only: five synthetic tasks, each with task evidence followed
by fifty distracting conversation turns, two target tokenizers, four executable
arms, three repetitions: **120 arm evaluations**. A fifth requested arm, LCM + TT,
is explicitly **not reproduced**: the pinned upstream checkout contains no bundled
LCM implementation, and no external LCM commit/configuration was supplied. No fake
summary or simulated LCM number is substituted.

`results.json` records the local summary and per-case pass counts. The reproducible
runner/CI artifact records complete per-trial observations. Local runs were split
by tokenizer to fit the execution environment; each used three repetitions.
Tokenizers were warmed outside timing. Temporary stores were fresh per arm; the
engine's full-history capture, selection and request gate are included in timing.
The benchmark increases the candidate cap to 64000 and body cap to 200000 characters
for long structured fixtures; production defaults remain 12000 and 60000.

## Results

Token totals sum the five tasks once, rather than summing repeated measurements.
All counts include the complete canonical provider JSON and tools; engine totals
include the additional history-tool schema. They do not include hidden provider
framing. Golden checks use an independent reader of the model-visible data/IR,
not a vault-backed answer oracle.

| Tokenizer | Arm | Final tokens | Median local ms | Visible goldens |
|---|---|---:|---:|---:|
| GPT-4o | Default TT middleware (age-collapse on) | 19002 | 51.754 | 0/15 |
| GPT-4o | TT middleware + JEV + IR (age-collapse on) | 12962 | 83.949 | 0/15 |
| GPT-4o | TT middleware + JEV + IR (age-collapse off) | 70554 | 154.927 | 15/15 |
| GPT-4o | TT ContextEngine + JEV + IR | 31934 | 771.776 | 15/15 |
| GPT-4 | Default TT middleware (age-collapse on) | 20088 | 69.793 | 0/15 |
| GPT-4 | TT middleware + JEV + IR (age-collapse on) | 13598 | 96.058 | 0/15 |
| GPT-4 | TT middleware + JEV + IR (age-collapse off) | 74251 | 187.362 | 15/15 |
| GPT-4 | TT ContextEngine + JEV + IR | 32100 | 760.460 | 15/15 |

The engine reduces its complete raw request from 93499 to 31934 tokens (65.85%)
and from 98000 to 32100 (67.24%) respectively. Relative to the middleware arm that
also preserves the task evidence, final inputs are **54.74% / 56.77% smaller**.
This is not an equal-cost dominance claim: the engine uses **two fixture batches**
per request versus one for JEV middleware, and does substantially more local work.
Identical engine retries made zero new fixture JEV calls.

The very short legacy arms are **not quality-preserving wins** on this corpus.
Their existing six-turn deterministic age-collapse replaces old dialogue with
previews, so the complete target evidence is no longer model-visible or preserved
by a target-source reference in TT's output. This is not a claim that Hermes deleted
its persistent transcript, or that every legacy middleware use loses information.
The new engine disables that age-collapse path; ordinary middleware behavior is
unchanged. The age-collapse-off control separates that quality issue from token
reduction achieved by query-aware selection.

All 120 measured transformations were non-enlarging. The engine passed all 30
visible golden, exact-target and protected-boundary checks. Tests separately cover
fifty-turn return-to-topic, archive-only lexical recall, malformed JEV, corrupted
sources, complete-token veto, missing tools, disabled modes, retries and async
context propagation.

## Recovery, cost and what remains unmeasured

A deliberately induced one-page recovery probe checks a real registered recovery
action, page equality and the complete subsequent request size. It is **not** a
recovery secretly used to make a golden answer pass. Its median additional
re-send input was 6296 / 6324 tokens for the engine, versus 17014 / 17755 for the
quality-preserving middleware control. This is a new request's full input, not
just the returned page size; summing it with the first request captures replay
cost. Per-trial records include page length, continuation and local latency.
Actual models may need zero, one or more recoveries; that distribution is unknown.

No paid JEV or target-model call was made. Live JEV cost is `null`, not falsely
reported as a free service. Fixture payload characters and call counts are
reported; there is no verified JEV-tokenizer or price conversion. Local timings
exclude service network latency. These deterministic goldens establish preservation
on this corpus, **not** real-model comprehension of every IR or classifier accuracy.
There is no unbounded `--live` mode in this benchmark.
