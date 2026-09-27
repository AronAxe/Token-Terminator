"""One-time, branch-local documentation import; removed before feature commit."""
from pathlib import Path


def read(name):
    return Path(name).read_text(encoding="utf-8")


def write(name, value):
    Path(name).write_text(value, encoding="utf-8")


def section(text, heading, next_heading):
    return text.split(heading, 1)[1].split(next_heading, 1)[0].strip()


design = read("docs/CONTEXT_IR.md")
settings = section(design, "## Enable and configure", "## What the compiler can emit")
protection = section(design, "## Protection and supported request shapes", "## Exact evidence, provenance and progressive recovery")
evidence = section(design, "## Exact evidence, provenance and progressive recovery", "## Acceptance and token-accounting boundary")
acceptance = section(design, "## Acceptance and token-accounting boundary", "## Benchmark and quality boundary")

readme = read("README.md").replace("0.8.2", "0.9.0")
readme = readme.replace("0.9.0 supersedes 0.8.1", "0.9.0 supersedes 0.8.2")
readme = readme.replace("seven cooperating reduction paths", "eight cooperating reduction paths")
line = next(line for line in readme.splitlines() if line.startswith("7. an **optional Jev"))
readme = readme.replace(line, line.rstrip(".") + ";\n8. an **optional Context IR compiler** after Jev that compacts exact tables, typed dictionaries and reversible text spans, pins source evidence, and requires a smaller complete tokenizer-measured request.")
summary = '''## Context IR: optional, off by default (v0.9.0)

```text
raw context → existing deterministic TT + SkillGate
            → optional JEV selection/attention → optional Context IR
            → complete-request tokenizer gate → existing provider client
```

Enable with `TOKEN_TERMINATOR_CONTEXT_IR=true` in a compiler-enabled mode. Keep your existing optional `TOKEN_TERMINATOR_JEV=true` and selected OpenRouter or direct TypeSafe credential. **There is no IR API, model, or new key.** Without Jev, IR is a local lossless-format optimizer. With Jev configured, the same batch adds salience alongside relevance/guard; private source-hash-bound scores prioritize candidates. Missing scores skip candidates; Jev failure leaves the pre-IR request alone.

IR v1 recognizes homogeneous flat JSON record arrays (schema once, positional rows, optional typed string dictionaries) and reversible repeated-line spans/templates. It does not turn arbitrary prose into guessed relations or drop additional facts. Unsupported prose stays as it is. Row order, scalar types, numeric lexemes and exact source evidence are preserved; original formatting remains recoverable.

System/developer/tool authority and current user wording are not rewritten. With IR on, Jev also leaves the entire current user message, including memory fences, untouched. Conservative code/quote/value/constraint guards veto prose recoding; these are not a complete prompt-injection detector.

Every emitted `TTIR/1` block has pinned, hash-verified evidence and recovery through the existing `artifact_get` action with `offset`/`limit`. No recovery tool, unknown tokenizer, failed storage, unsafe source or no measured improvement means no IR. The raw source is the input to the IR stage; earlier TT recovery references remain unchanged.

**Measurement boundary:** the gate counts complete canonical provider-request JSON using the selected actual target tokenizer, including legends, real source IDs, roles, tools and other request fields. It requires strict token and character savings relative to TT + Jev immediately before IR. This is not a claim about hidden provider framing or billed prompt tokens. IR has no character-only fallback.

See [Context IR design and configuration](docs/CONTEXT_IR.md) and the [three-arm benchmark](benchmarks/context_ir/README.md). The benchmark uses synthetic scores and independent visible-data golden answers; it is not live Jev accuracy or LLM non-inferiority evidence. A paid live evaluator is opt-in.

'''
readme = readme.replace("## Metrics and experiments", summary + "## Metrics and experiments")
table_lines = [line for line in settings.splitlines() if line.startswith("| `TOKEN_TERMINATOR_CONTEXT_IR")]
marker = next(line for line in readme.splitlines() if line.startswith("| `TOKEN_TERMINATOR_JEV_MAX_STATE_CHARS`"))
readme = readme.replace(marker, marker + "\n" + "\n".join(table_lines))
write("README.md", readme)

notes = '''## 0.9.0 - 2026-09-28

- Added experimental **Context IR**, OFF by default: a local compiler after deterministic TT and optional Jev, without replacing native/temporal reduction, SkillGate, compaction, vaults or recovery.
- Added schema-once positional records, typed repeated-string dictionaries and reversible exact-line templates/spans. No invented prose relations, lossy summarizer, new graph architecture or extra API key.
- Reused one Jev batch for relevance/guard/salience; private scores bind to exact source hashes and positions. Missing/malformed probabilities skip candidates; high guard/salience retains explicit values. OpenRouter/direct TypeSafe routing is unchanged.
- Added bounded complete-request format search. IR requires strict actual-tokenizer and character savings including legends, tool schemas and real vault IDs; no tokenizer means no IR. Counts cover canonical request JSON, not hidden provider billing framing.
- Protected current user wording, system/developer/tool authority, code/quotations/values and constraints. With IR enabled, the entire current user message, including memory fences, stays untouched.
- Added atomic source insertion/exposure pinning and source-hash/position/IR validation. Normal exact-recovery reads reject corrupted content; schema version 2 stays rollback-compatible.
- Added content-free IR/Jev timing and provider-reported cost metrics, including Jev calls that do not remove context.
- Added adversarial/regression tests and a reproducible three-arm benchmark with independent visible-data golden answers and exact recovery. Offline results use fixture scores; live Jev economics and LLM quality remain opt-in and unclaimed.
- Updated README, configuration, migration, security, wiki sources and release metadata.

'''
changelog = read("CHANGELOG.md")
assert "## 0.9.0 -" not in changelog
write("CHANGELOG.md", changelog.replace("# Changelog\n\n", "# Changelog\n\n" + notes, 1))

migration = read("MIGRATION.md")
migration = migration.replace("→ 0.8.2", "→ 0.9.0", 1).replace("Token Terminator 0.8.2 supersedes Token Terminator 0.8.1", "Token Terminator 0.9.0 supersedes Token Terminator 0.8.2", 1)
intro = '''## 0.8.2 → 0.9.0

Context IR is an optional local stage after the existing deterministic pipeline and Jev. It is OFF by default. Set `TOKEN_TERMINATOR_CONTEXT_IR=true` to enable guarded format optimization with a measured tokenizer and provider-visible recovery tool, in the existing `balanced` or `aggressive` modes.

No new API key or database schema is required. OpenRouter/direct TypeSafe configuration remains valid. Jev gains salience only when IR is on; no extra batch call is added. With IR on, the entire current user message, including memory fences, stays untouched. Missing scores cannot authorize compression.

After the v0.9.0 release is published, install its immutable tag with `<hermes-python> -m pip install --upgrade 'git+https://github.com/AronAxe/Token-Terminator.git@v0.9.0'`.

Disable only IR by unsetting its variable or setting it to `false`, then restarting the host. Roll back the package by reinstalling v0.8.2. Schema version 2 and ordinary artifact IDs/actions are retained. Do not delete the vault while transcripts reference it. Corrupted content now raises an error rather than being returned as exact evidence.

See [Context IR](docs/CONTEXT_IR.md) for limits and the canonical-request measurement boundary. The offline benchmark is not a live-model non-inferiority result.

'''
migration = migration.replace("## 0.8.1 → 0.8.2", intro + "## 0.8.1 → 0.8.2", 1)
write("MIGRATION.md", migration)

security = read("SECURITY.md").replace("Nothing is uploaded by the plugin.", "With Jev disabled (the default), the reduction pipeline makes no semantic-service upload. Opting into Jev creates the external-service boundary described below. Context IR itself is entirely local.")
security += "\n## Context IR evidence and authority boundary (v0.9.0)\n\n`TOKEN_TERMINATOR_CONTEXT_IR` defaults to `false` and adds no API or credential. Jev scores are untrusted attention signals, never facts. Missing, nonnumeric, nonfinite and out-of-range probabilities are rejected; errors expose types only, not external exception text.\n\n" + protection + "\n\n" + evidence + "\n\n" + acceptance + "\n\nThe optional live benchmark explicitly calls configured Jev and OpenRouter and validates read-only recovery calls against source IDs already in the request. Raw answers and keys are not persisted. CI never runs the live benchmark.\n"
write("SECURITY.md", security)

write("wiki/Context-IR.md", design.replace("../benchmarks/context_ir/README.md", "https://github.com/AronAxe/Token-Terminator/blob/main/benchmarks/context_ir/README.md"))
sidebar = read("wiki/_Sidebar.md").replace("- [Jev Semantic Context Gate](Jev-Semantic-Context-Gate)", "- [Jev Semantic Context Gate](Jev-Semantic-Context-Gate)\n- [Context IR](Context-IR)").replace("- [Release 0.8.2](Release-0.8.2)", "- [Release 0.9.0](Release-0.9.0)\n- [Release 0.8.2](Release-0.8.2)")
write("wiki/_Sidebar.md", sidebar)
configuration = read("wiki/Configuration.md")
configuration = configuration.replace("## Token budgeting", "## Context IR\n\n" + settings + "\n\nSee [Context IR](Context-IR) for formats, provenance and the strict whole-request acceptance gate.\n\n## Token budgeting")
write("wiki/Configuration.md", configuration)
home = read("wiki/Home.md")
home = home.replace("install v0.8.2", "install v0.9.0").replace("Python package/release: **v0.8.2**", "Python package/release: **v0.9.0**").replace("**token-terminator 0.8.2**", "**token-terminator 0.9.0**")
home = home.replace("## What v0.8.2 changes", "## What v0.9.0 adds\n\nv0.9.0 adds the optional [Context IR](Context-IR) compiler after deterministic TT and Jev. It is OFF by default, compacts existing records or exact repeated spans without inventing relations, and requires strict complete-request tokenizer savings plus pinned source evidence. The three-arm offline benchmark checks visible-data answers and recovery, not live-model non-inferiority. See [Release 0.9.0](Release-0.9.0).\n\n## What v0.8.2 changes")
write("wiki/Home.md", home)
