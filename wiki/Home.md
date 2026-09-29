# Token Terminator Wiki

**Keep the evidence. Terminate the redundant tokens.**

## v0.11.0 · Context, learning & observability

Token Terminator is an exact-recoverable context optimization layer: use it as
portable middleware, or select it as the sole Hermes ContextEngine. This release
adds full-history ownership, externally learned omission-risk policies and an
Observatory for per-profile input/output accounting. The unshipped 0.10.0 milestone
is included in 0.11.0; 0.9.0 was the previous published version.

| Start here | What you will find |
| --- | --- |
| [Quick Start](Quick-Start) | Install the release and choose your integration mode |
| [Architecture](Architecture) | Two modes, one context owner; purpose-first call isolation |
| [Context Engine](Context-Engine) | Replace upstream LCM/compressor selection without patching Hermes |
| [Learned Policy](Learned-Policy) | Train, validate and explicitly approve an omission-risk policy |
| [Dashboard](Dashboard) | localhost:7474 and the Hermes Desktop bottom-bar counter |
| [Configuration](Configuration) | Environment variables, limits and optional features |
| [Vault and Exact Recovery](Vault-and-Exact-Recovery) | Backing evidence, retention and expansion |
| [Release 0.11.0](Release-0.11.0) | Complete release notes and validation boundaries |

![Two modes, one context owner](https://raw.githubusercontent.com/AronAxe/Token-Terminator/v0.11.0/docs/assets/architecture.svg)

## Defaults and guarantees

Installation does not select an engine, enable a Desktop component, start a server
or train/activate a policy. JEV, Context IR and learned-policy deployment remain
opt-in. Embeddings, reranking, helpers, tokenizer work and internal JEV calls bypass
conversational reduction. Caller-owned requests remain unchanged.

ContextEngine and IR accept only strictly smaller complete requests measured with
the actual target tokenizer **and** character counts, with exact evidence available
for recovery. Legacy middleware alone can use its established character gate when
no exact tokenizer is available. Counts are not hidden provider billing framing.
Missing storage, unsupported scopes or failed verification pass through rather
than silently discard evidence. Protected-history overflow may still require
host/provider refusal; persistent evidence pins require capacity planning.

## Before enabling advanced features

Read [Security and Trust Model](Security-and-Trust-Model),
[Migration and Rollback](Migration-and-Rollback) and
[Troubleshooting](Troubleshooting). Rate-card values are API equivalents, not
subscription discounts; generated output is not measured output savings. Synthetic
learning/engine tests do not establish production answer quality or service economics.

Python release: **0.11.0** · Rust interoperability companion: **0.11.0** ·
First-party runtime adapter: **Hermes Agent**. The Rust crate is not the Python runtime.

## Release history

[0.11.0](Release-0.11.0) · [0.9.0](Release-0.9.0) ·
[0.8.2](Release-0.8.2) · [0.8.1](Release-0.8.1) · [0.8.0](Release-0.8.0) ·
[0.7.0](Release-0.7.0) · [0.6.0](Release-0.6.0) · [0.5.2](Release-0.5.2) ·
[0.5.1](Release-0.5.1). The [0.10.0 milestone](Release-0.10.0) was not published separately.
