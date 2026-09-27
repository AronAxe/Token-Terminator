# Context IR three-arm benchmark — v0.9.0

Reproduced locally on Python 3.13.5 / tiktoken 0.14.0, and in GitHub CI. Five synthetic tasks, two target tokenizers, three repeats: **90 arm evaluations, zero golden/evidence/recovery/protection failures**. Results are specific to these inputs and deterministic mocked JEV scores, not a representative production savings estimate.

**No live JEV or LLM requests were made.** Offline JEV cost is $0 because no API was called, not because the service is free. Mocked JEV timing is local execution, not network/model latency. Live price, latency and LLM answer-quality non-inferiority remain unmeasured.

## Complete-request token counts

Token sums are over the five tasks (not multiplied by repeats). Complete canonical provider-request JSON includes tool definitions, roles, IR legends and source IDs. Hidden provider framing is excluded. Model names here select tokenizers; they do not indicate model inference.

| Target tokenizer | Normal TT | TT + JEV | TT + JEV + IR | IR reduction vs JEV | Combined reduction vs TT |
|---|---:|---:|---:|---:|---:|
| gpt-4o | 22,674 | 16,159 | 7,144 | 55.79% | 68.49% |
| gpt-4 | 22,905 | 15,940 | 7,086 | 55.55% | 69.06% |

## Per-task results (gpt-4o tokenizer)

| Task | Normal TT | TT + JEV | TT + JEV + IR | Visible/golden/recovery checks |
|---|---:|---:|---:|---|
| temporal-confusable-entities | 5,035 | 3,732 | 1,532 | Pass |
| dependency-path | 4,374 | 3,071 | 1,181 | Pass |
| exact-values-and-negation | 5,621 | 4,318 | 1,211 | Pass |
| repeated-exact-spans | 3,914 | 2,611 | 793 | Pass |
| protected-code-quotation-control | 3,730 | 2,427 | 2,427 | Pass |

The protected-code/quotation control deliberately shows no incremental IR savings. Other cases exercise ordered temporal records, source-supplied dependency edges, exact values/negation and character-exact repeated spans. An independent reader solves tasks from visible data; it does not recover source content to manufacture a correct answer. Empty-evidence negative controls cannot pass.

## Latency and cost

Initial local warmed-tokenizer middleware medians (milliseconds):

| Tokenizer target | TT | TT + JEV | TT + JEV + IR |
|---|---:|---:|---:|
| gpt-4o | 10.388 | 13.285 | 21.203 |
| gpt-4 | 13.608 | 17.272 | 23.522 |

These are one-host measurements, not service benchmarks. `results.json` contains the separately reproduced CI timings, all raw trials and separate mocked JEV timing. Timings will vary by host. No provider token usage or dollar estimates are fabricated.

## Reproduce

```bash
python -m pip install -e '.[dev]'
python scripts/benchmark_context_ir.py --repeats 3
```

The benchmark uses the real runtime and isolated fresh vaults per arm. Deterministic compaction is enabled. To score full synthetic sources rather than silently skip them, JEV bounds are explicitly 64,000 candidate characters and 200,000 state characters; normal product defaults remain 12,000 / 60,000. The third arm adds salience to its existing JEV batch and keeps IR defaults. No benchmark settings alter production defaults. Fixture probabilities are uncalibrated; they test integration, not JEV predictive accuracy.

For an explicitly paid test with existing credentials:

```bash
python scripts/benchmark_context_ir.py --live \
  --model openai/gpt-4o --repeats 3 --max-answer-calls 4 \
  --output benchmarks/context_ir/live-results.json
```

The live run uses actual configured JEV and an OpenRouter LLM. It records provider-reported cost (or null), latency, golden answer failures and input tokens across every allowed recovery follow-up. Recovery is restricted to IDs already present in the arm and read-only artifact actions. Raw answers and keys are not persisted. This small corpus is a regression check, not a powered non-inferiority study. CI runs only the offline harness.

See [`results.json`](results.json) for all 90 observations and [`../../docs/CONTEXT_IR.md`](../../docs/CONTEXT_IR.md) for the compiler contract.
