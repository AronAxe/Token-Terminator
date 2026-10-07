# Token Terminator v0.11.3 — Hermes Codex 900k aliases

Fixes tokenizer lookup for `gpt-6.1-sol-900k` and supported provider-qualified
forms, including `openai-codex/gpt-6.1-sol-900k` and
`openai-codex:gpt-6.1-sol-900k`.

Hermes' `-900k` suffix selects a larger context window; it is not a separate
model tokenizer. TT now resolves eligible aliases to their base model for token
measurement only. The outgoing request's model string, selected window, retry
binding, original history and provider routing stay unchanged. No new tokenizer
mapping, API key, paid call or weakened acceptance rule is introduced.

The alias resolver follows the reviewed Hermes eligibility rules across the
supported model families and dated snapshots, rather than removing arbitrary
suffixes. Unknown namespaces, unsupported bases and malformed suffixes are not
reinterpreted. Upstream tokenizer mappings and explicit configuration retain
precedence; an alias never supplies a tokenizer its base model does not support.

Regression coverage includes the actual Sol-900k names through JEV selection,
complete-request token reduction, protected wording, exact source recovery,
unchanged request model and the retained 900,000-token engine window. Additional
checks compare eligible aliases with Hermes' own pure alias resolver and cover
older supported GPT models. These are offline fixture checks, not a new live
answer-quality benchmark.

Upgrade using the Python environment actually running your Hermes backend:

```bash
python -m pip install --upgrade 'git+https://github.com/AronAxe/Token-Terminator.git@v0.11.3'
```

Existing v0.11.2 engine installations do not need a new tokenizer override or a
repeat of the loader repair for this fix. Restart the affected idle backend once
through its usual supervisor so it imports the updated package. Keep the chosen
`-900k` model. This release does not change your running configuration or restart
agents as a side effect of publication.

The v0.11.2 discovery repair is unchanged. The Rust companion is version-aligned
only. Previous tags, Terminator artwork and schematics are unchanged.
