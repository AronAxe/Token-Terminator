from __future__ import annotations

import runpy
from pathlib import Path

from rtk_hermes_plus._version import __version__


def test_release_archive_paths_reject_absolute_traversal_and_drive_prefixes():
    verifier = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py")
    )
    safe_name = verifier["_safe_name"]

    assert safe_name("package/module.py")
    assert not safe_name("../escape.py")
    assert not safe_name("/absolute.py")
    assert not safe_name("C:/absolute.py")
    assert not safe_name("C:drive-relative.py")
    assert not safe_name(r"C:\absolute.py")


def test_release_guard_rejects_tracked_operational_artifacts(tmp_path, monkeypatch):
    verifier = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py")
    )
    (tmp_path / ".git").mkdir()
    private = tmp_path / "$HOME" / ".claude" / "projects" / "private.jsonl"
    private.parent.mkdir(parents=True)
    private.write_text("private", encoding="utf-8")
    (tmp_path / "safe.py").write_text("", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = b"$HOME/.claude/projects/private.jsonl\0safe.py\0"

    monkeypatch.setattr(
        verifier["subprocess"], "run", lambda *args, **kwargs: Completed()
    )
    problems = verifier["inspect_tracked_tree"](tmp_path)

    assert any("operational path" in problem for problem in problems)
    assert any("operational payload" in problem for problem in problems)


def test_release_docs_reference_current_version():
    root = Path(__file__).resolve().parents[1]
    version = __version__
    readme = (root / "README.md").read_text(encoding="utf-8")
    migration = (root / "MIGRATION.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"Token Terminator {version}" in readme
    assert f"@v{version}" in readme
    assert f"Token Terminator {version}" in migration
    assert f"@v{version}" in migration
    assert f"## {version} -" in changelog
