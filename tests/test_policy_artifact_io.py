"""Policy approval hashes must identify identical disk bytes on every platform."""

import hashlib
import json

import pytest

from rtk_hermes_plus import learned_policy


@pytest.mark.parametrize("exclusive_fallback", [False, True])
def test_policy_hash_covers_disk_bytes_despite_platform_text_translation(
    tmp_path, monkeypatch, exclusive_fallback
):
    original_fdopen = learned_policy.os.fdopen

    def translating_text_fdopen(fd, mode, *args, **kwargs):
        # Simulate Windows newline translation even on a Linux test runner.
        if "b" not in mode:
            kwargs["newline"] = "\r\n"
        return original_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(learned_policy.os, "fdopen", translating_text_fdopen)
    if exclusive_fallback:

        def no_links(*args, **kwargs):
            raise PermissionError("links unavailable")

        monkeypatch.setattr(learned_policy.os, "link", no_links)
    value = {"question": "Does café evidence preserve the exact value?", "p": 0.125}
    path = tmp_path / "policy.json"
    digest = learned_policy.write_private_json(path, value)
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    assert digest == hashlib.sha256(raw).hexdigest()
    assert json.loads(raw) == value
    assert not list(tmp_path.glob(".tt-policy-*"))
    with pytest.raises(ValueError, match="already exists"):
        learned_policy.write_private_json(path, value)
