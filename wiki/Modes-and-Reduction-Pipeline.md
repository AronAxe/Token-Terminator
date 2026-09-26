# Modes and Reduction Pipeline

Token Terminator uses one runtime mode to control which reduction paths are active.

| Mode | RTK terminal rewrite | Temporal delta | Native search/process | Native `read_file` | Request compiler | Optional Jev gate |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `balanced` | ✓ | ✓ | ✓ | — | ✓ | ✓* |
| `aggressive` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓* |
| `native` | — | — | ✓ | — | — | — |
| `terminal` | ✓ | — | — | — | — | — |
| `suggest` | measure only | — | — | — | — | — |
| `off` | — | — | — | — | — | — |

*Jev still requires `TOKEN_TERMINATOR_JEV=true` plus an API key. It is off by default even in `balanced` and `aggressive` modes. When enabled, it runs after the normal deterministic request-reduction phases; it never disables them.*

## Balanced

The default. It combines the broadest useful reduction set without applying aggressive structured reads.

## Aggressive

Adds large `read_file` reduction to the balanced pipeline. Use it when tool-output volume justifies the extra transformation path and exact recovery remains available to the model.

## Native

Disables RTK and request compilation. Useful when you only want deterministic large tool-result compression.

## Terminal

Only terminal rewriting is active.

## Suggest

Measures rewrite candidates without replacing the command.

## Off

No provider-visible optimization is attempted.

## Acceptance is per transformation

A mode only makes a path *eligible*. It does not force a reduction. Every candidate can still be rejected because it is not smaller, expands under the exact tokenizer, cannot be recovered safely, is malformed, violates backend constraints, or hits another fail-open condition.

This is why a healthy Token Terminator session can contain many untouched results.
