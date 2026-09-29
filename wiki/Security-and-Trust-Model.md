# Security and Trust Model

Token Terminator stores exact evidence locally because recovery is part of its
contract. A smaller prompt is never permission to discard backing evidence.

## Private storage and ownership

Plugin-owned data normally lives under `<HERMES_HOME>/token-terminator/`. The vault
can contain sensitive original messages, tool results, provenance and temporal
state. The separate ledger stores accounting and salted fingerprints, not prompt
text. Protect and back up both. Hermes' task-local profile home takes precedence
over the process launch home; explicit TT path overrides remain operator choices.

Middleware mode leaves the host context engine in place. Explicitly selecting TT
makes it the context owner, not the transcript store, memory system or provider
client. The host's full transcript remains intact. Session-scoped history recovery
requires membership and verified source hashes; the older general vault tool is
not redefined as a multi-tenant authorization service.

## Purpose before reduction

Only an authorized conversational request may enter context reduction. Native
auxiliary clients remain separate, and forwarded embedding, reranking, classifier,
helper, tokenizer and typed JEV service requests bypass. Internal JEV and counting
callbacks cannot recursively enter TT or overwrite the conversation binding.
A model name, inherited binding or prompt metadata is not authorization.

## Optional JEV external boundary

JEV is disabled by default. Enabling it sends bounded source regions, the current
query and relevant recent referents to the configured OpenRouter or direct TypeSafe
route. Existing provider keys are read from the environment, not logged or returned
by status tools. One selected JEV provider key is sufficient.

Middleware and ContextEngine have different segmentation contracts. The legacy
middleware can separately score fenced memory background; ContextEngine and IR
protect the whole current user message. See the [Context Engine](Context-Engine)
and [JEV gate](Jev-Semantic-Context-Gate) guides before enabling external transfer.
Relevance/guard/salience are probabilistic selection signals, not proof of truth.
Malformed or missing scores cannot grant omission authority.

## Optional external learning

Training requires an explicit independently labelled dataset and offline replay,
or explicit `--live --allow-external-data` consent. Live feature extraction sends
bounded dataset evidence to JEV; bounded development-error examples can go to the
chosen System-2 proposer. No automatic live-vault mining, export, self-labelling,
background training or model promotion is enabled.

Deployment is off by default. A policy is approved by path and SHA-256, bound to
its feature schema, scorer and evaluated targets, and evaluated as bounded numeric
JSON rather than executable/pickle content. It can veto otherwise eligible omissions,
not override protected or uncertain content. Invalid artifacts or features retain
evidence. Training artifacts themselves may contain sensitive information.
Call/row/volume/time limits are not a hard dollar ceiling, and finite holdout checks
are not a guarantee of real-model accuracy. See [Learned Policy](Learned-Policy).

## Final gate and recovery-safe retention

Changes operate on copies and require a smaller complete provider envelope.
ContextEngine and IR require exact target-tokenizer AND character savings, including
receipts, tools and source references. Legacy middleware may use its character gate
when no exact tokenizer is available. Counts are canonical request JSON, not hidden
provider billing framing. Protected-history overflow can remain unresolved and
still needs host/provider enforcement; later third-party rewrites need their own gate.

Source insertion and exposure pinning are transactional and read/hash-verified.
Pins protect promised evidence from ordinary pruning/reset/restart. Capacity failures
fail open instead of silently breaking recovery. Plan retention; deleting the vault
breaks recovery. Missing external LCM originals are not recreated or imported.

## Read-only dashboard boundary

The standalone server binds only to loopback on port 7474. It exposes bounded,
read-only accounting queries, not prompts, artifacts, keys or filesystem paths.
Host/Origin checks and restrictive browser headers reject cross-site access. It is
not authenticated against other users/processes on the same machine and must not be
publicly proxied. Missing/busy/corrupt or ambiguous stores are reported, not guessed.

The Desktop component uses Hermes' authenticated plugin API and active profile/
connection identity; it does not make cross-origin localhost requests. Native API
configuration cannot escape the authorized home. No refresh invokes a model.
Configured API-equivalent value is not verified cash or subscription savings.

## RTK trust boundary

RTK uses argument arrays and `shell=False`; remote terminal backends are disabled
by default. Pin `TOKEN_TERMINATOR_RTK_PATH` and protect the executable and its
parent directory against untrusted writes rather than relying on an unsafe PATH.

## Reporting vulnerabilities

Use a private GitHub security advisory rather than publishing sensitive evidence
in an issue. The repository [SECURITY.md](https://github.com/AronAxe/Token-Terminator/blob/v0.11.0/SECURITY.md)
contains the complete operational constraints and disclosure guidance.
