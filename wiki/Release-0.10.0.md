# v0.10.0 — ContextEngine (unreleased candidate)

This release is **prepared, not published**. v0.9.0 stays unchanged. No production
Hermes configuration is changed by this pull request.

- Selectable supported Hermes ContextEngine and a non-mutating profile installer.
- Full available history in exact pinned sources; session-scoped discovery/recovery.
- Bounded batched JEV relevance/guard/salience using existing provider/key routing.
- Existing Context IR and complete-request exact-token/character acceptance.
- Conservative protection, explicit failures, retry/async lifecycle ownership.
- Middleware-only mode retained; no new generative summarizer or graph rewrite.

The pinned real-Hermes smoke exercises discovery, the actual engine factory (with
built-in construction forbidden), CLI/web shared options, host selection and tool
injection, actual middleware dispatch and exact recovery. Unit tests cover old
facts returning after fifty turns, integrity, provider failures, constraints,
complete-request gates and separate sessions.

The offline benchmark's quality-preserving middleware control uses 70554 / 74251
final tokens across five tasks; TT ContextEngine uses 31934 / 32100 (54.74% / 56.77%
fewer). Both preserve all tested task evidence. The engine uses two fixture JEV
batches versus one and more local time. Legacy age-collapse arms are shorter but
fail the old-evidence goldens. This is not live-model quality or measured JEV cost.
LCM + TT has no reproduced baseline and is explicitly omitted, not simulated.

Read [Context Engine](Context-Engine), [Configuration](Configuration),
[Security](Security-and-Trust-Model), and [Migration](Migration-and-Rollback).
Known limits: no forced fit for arbitrary protected history, host transcript memory
growth, persistent vault pins, literal rather than semantic archive-only retrieval,
pre-middleware hard limits/stateful native routes, and no LCM archive import.
