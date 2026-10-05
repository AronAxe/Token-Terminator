# GPT-6.1-Sol tokenizer compatibility

Upstream tiktoken's model-name lookup did not contain GPT-6.1-Sol at the time of this
repair. TT 0.11.1 consequently returned no token count and its ContextEngine exited
before JEV. Version 0.11.2 adds a local compatibility mapping for that exact model,
not a blanket rule for future GPT versions. The upstream library remains unmodified.

The supported provider prefixes are bare, openai/, openai:, openai-codex/ and
openrouter/openai/. Cache keys retain the original provider identity. A recognized
upstream tokenizer takes precedence over TT's compatibility mapping. Local explicit
encoding/Hugging Face configuration keeps its existing behavior.

## Empirical validation

`tests/fixtures/gpt61-token-counts.json` contains five synthetic public inputs and
actual responses from https://api.openai.com/v1/responses/input_tokens on 2026-10-05.
All content counts matched o200k_base, with a constant six-token message framing:

| Case | Provider | Local content | Framing |
|---|---:|---:|---:|
| English | 13 | 7 | 6 |
| Multilingual and emoji | 330 | 324 | 6 |
| Code and values | 633 | 627 | 6 |
| JSON records | 610 | 604 | 6 |
| Literal markers | 204 | 198 | 6 |

This is an empirically validated compatibility mapping, not an official upstream
model declaration or universal proof. No private conversations or generation calls
were involved. The runtime does not call a remote counter or need a new key.

TT reports `tiktoken:compat:gpt-6.1-sol:o200k_base` (with the normalized model for
qualified routes). Its gate measures complete canonical provider-request JSON;
provider-internal framing, image tokenization and invoices remain outside that
measurement claim. Strict token AND character decrease, protected context and
exact recovery are unchanged. The full pipeline regression must actually reach
JEV and reduce the request, not merely return a numeric count.

Reference: https://developers.openai.com/api/docs/guides/token-counting
