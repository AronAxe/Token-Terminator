"""Window aliases select the base tokenizer without changing the model route."""

import ast
import os
import re
import typing
from pathlib import Path
from types import SimpleNamespace

import pytest
import tiktoken

from rtk_hermes_plus.token_budget import (
    TokenBudgetAdapter,
    _compat_encoding,
    _tokenizer_alias_identity,
    _tokenizer_model_name,
)

BASES = (
    "gpt-5.4",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-6-astra",
    "gpt-6.1-sol",
    "gpt-daybreak-blue-latest",
    "gpt-5.6-sol-2026-07-09",
    "gpt-6-sol-2026-09-22",
)
PREFIXES = (
    "",
    "openai/",
    "openai:",
    "openai-codex/",
    "openai-codex:",
    "openrouter/openai/",
)
INVALID = (
    "gpt-5.5-900k",
    "gpt-6.1-sol-pro-900k",
    "gpt-6.1-sol-900k-900k",
    "gpt-6.1-sol-900k-extra",
    "gpt-6.1-sol-1m",
    "gpt-6.2-sol-900k",
    "gpt-6-sol-2026-09-22-extra-900k",
    "gpt-6-terra-900k",
    "other/gpt-6.1-sol-900k",
    "other:gpt-6.1-sol-900k",
    "llama-900k",
    "",
    "gpt-6.1-sol",
)


@pytest.mark.parametrize("base", BASES)
@pytest.mark.parametrize("prefix", PREFIXES)
def test_known_alias_resolves_only_for_tokenizer_lookup(base, prefix):
    alias = prefix + base + "-900k"
    assert _tokenizer_alias_identity(alias) == prefix + base
    assert _tokenizer_model_name(alias) == base


@pytest.mark.parametrize("name", INVALID)
def test_unknown_suffix_base_or_namespace_is_not_reinterpreted(name):
    assert _tokenizer_alias_identity(name) == name
    if name != "gpt-6.1-sol":
        assert _compat_encoding(name) == ""


def test_original_alias_is_preserved_in_measurement_and_cache(monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    adapter = TokenBudgetAdapter()
    adapter._tiktoken_attempted = True

    def unknown(_):
        raise KeyError("upstream model table predates Sol")

    adapter._tiktoken = SimpleNamespace(
        encoding_for_model=unknown, get_encoding=tiktoken.get_encoding
    )
    for model in (
        "gpt-6.1-sol",
        "gpt-6.1-sol-900k",
        "openai-codex:gpt-6.1-sol-900k",
    ):
        count = adapter.measure_text("same evidence", model=model)
        assert count.available and count.model == model
        assert model in adapter._encodings
    other = adapter.measure_text("same evidence", model="other/gpt-6.1-sol-900k")
    assert not other.available


@pytest.mark.parametrize("base", BASES)
def test_alias_uses_upstream_base_mapping_before_compatibility(base, monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    adapter = TokenBudgetAdapter()
    adapter._tiktoken_attempted = True
    observed = []
    selected = tiktoken.get_encoding("cl100k_base")

    def lookup(model):
        observed.append(model)
        assert model == base
        return selected

    adapter._tiktoken = SimpleNamespace(encoding_for_model=lookup)
    encoding, label = adapter._tiktoken_encoding("openai-codex/" + base + "-900k")
    assert encoding is selected and observed == [base]
    assert label == "tiktoken:model:" + base


@pytest.mark.parametrize(
    "base", ["gpt-5.4", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6.1-sol"]
)
def test_real_base_and_alias_count_same_text(base, monkeypatch):
    monkeypatch.delenv("TOKEN_TERMINATOR_TOKENIZER_JSON", raising=False)
    monkeypatch.delenv("TOKEN_TERMINATOR_TIKTOKEN_ENCODING", raising=False)
    adapter = TokenBudgetAdapter()
    text = "Exact 12.30; <|endoftext|>; code(x); café; 日本語; 🧪"
    original = adapter.measure_text(text, model=base)
    alias = adapter.measure_text(text, model=base + "-900k")
    assert original.available and alias.available
    assert original.tokens == alias.tokens


def test_alias_contract_matches_real_hermes_source():
    source = os.environ.get("TT_HERMES_MODEL_METADATA")
    if not source:
        pytest.skip("real Hermes alias contract runs in the dedicated integration job")
    wanted = {
        "CODEX_CONTEXT_VARIANT_SUFFIX",
        "_CODEX_900K_SNAPSHOT_BASES",
        "_CODEX_900K_ELIGIBLE_BASES",
        "_CODEX_900K_SNAPSHOT_RE",
        "_bare_codex_slug",
        "is_codex_900k_base",
        "_codex_variant_base",
        "strip_codex_context_variant_suffix",
    }
    parsed = ast.parse(Path(source).read_text(encoding="utf-8"))
    nodes, found = [], set()
    for node in parsed.body:
        if isinstance(node, ast.FunctionDef):
            names = {node.name}
        elif isinstance(node, ast.Assign):
            names = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
        else:
            continue
        if names & wanted:
            nodes.append(node)
            found.update(names & wanted)
    assert found == wanted, "Hermes alias contract changed; review rather than skipping"
    namespace = {"re": re, "Optional": typing.Optional}
    # Only the reviewed alias constants/pure functions, not host imports,
    # plugin bootstrap, credentials, metadata HTTP code, or live configuration.
    code = compile(ast.Module(body=nodes, type_ignores=[]), source, "exec")
    exec(code, namespace)  # noqa: S102 - reviewed host alias contract
    strip = namespace["strip_codex_context_variant_suffix"]
    for name in (*BASES, *INVALID):
        for candidate in (name, name + "-900k"):
            if not candidate.startswith(("other/", "other:")):
                assert _tokenizer_alias_identity(candidate) == strip(candidate)
    assert _tokenizer_alias_identity("gpt-6.1-sol-900k") == strip("gpt-6.1-sol-900k")
