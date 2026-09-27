# Release 0.9.0 — optional Context IR

This release adds the [Context IR](Context-IR) compiler after the existing deterministic Token Terminator pipeline and optional Jev gate. It is **OFF by default** and uses no new API key.

Homogeneous record arrays can use a shared schema and positional rows, with typed dictionaries when measured worthwhile. Repeated unprotected prose can use exact templates/spans. Arbitrary prose is not converted into inferred graphs. Existing mechanisms, tool actions and database schema remain in place.

Jev attention is reused from one provider batch through either OpenRouter or direct TypeSafe. Salience/guard scores never become facts. Protected instructions/current wording and exact evidence remain guarded, and IR requires strict full-request tokenizer and character savings including its legend and source references.

Evidence is transactionally pinned, source-verified and recoverable through ordinary `artifact_get` paging. Vault reads now detect corruption. Missing tokenizer, recovery, source evidence, safe format or valid scores causes a no-op/fail-open result.

Enable with `TOKEN_TERMINATOR_CONTEXT_IR=true` in a compiler-enabled mode. Disable by unsetting it or setting it to `false`; no database downgrade or key migration is needed. [Configuration](Configuration) lists the bounds.

The three-arm offline suite reports synthetic-score results with exact-token counts, visible-data golden answer checks and recovery checks. It is not live Jev accuracy or LLM non-inferiority evidence. A paid `--live` harness exists but is not run in CI. Review those limits before adopting the feature in production.
