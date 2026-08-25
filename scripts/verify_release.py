"""Verify built release archives contain no local or private payloads."""

from __future__ import annotations

import glob
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

FORBIDDEN_NAMES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".env",
)
FORBIDDEN_PARTS = ("__pycache__", ".venv", ".git", ".smoke-venv")
CONTENT_PATTERNS = {
    "windows_user_path": re.compile(rb"(?i)[A-Z]:[\\/]Users[\\/]"),
    "dropbox_path": re.compile(rb"(?i)[A-Z]:[\\/].{0,100}Dropbox[\\/]"),
    "secret_assignment": re.compile(
        rb"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"\r\n]{8,}"
    ),
}
FORBIDDEN_TRACKED_PATHS = ("$HOME/",)
FORBIDDEN_TRACKED_SUFFIXES = (".jsonl",)


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and re.match(r"^[A-Za-z]:", str(path)) is None
    )


def inspect_archive(path: Path) -> dict[str, object]:
    entries: list[tuple[str, bytes, bool]] = []
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                entries.append((info.filename, archive.read(info), False))
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile():
                    handle = archive.extractfile(member)
                    entries.append(
                        (member.name, handle.read() if handle else b"", False)
                    )
                else:
                    entries.append((member.name, b"", member.issym() or member.islnk()))

    problems: list[str] = []
    names = [name for name, _, _ in entries]
    for name, payload, is_link in entries:
        normalized = name.replace("\\", "/")
        if not _safe_name(normalized):
            problems.append(f"unsafe archive path: {name}")
        if is_link:
            problems.append(f"archive link not allowed: {name}")
        lower = normalized.lower()
        if any(part in lower.split("/") for part in FORBIDDEN_PARTS):
            problems.append(f"forbidden path component: {name}")
        if lower.endswith(FORBIDDEN_NAMES):
            problems.append(f"forbidden payload type: {name}")
        for label, pattern in CONTENT_PATTERNS.items():
            if pattern.search(normalized.encode("utf-8")):
                problems.append(f"{label} in archive path {name}")
            if pattern.search(payload):
                problems.append(f"{label} in {name}")

    if path.suffix == ".whl":
        required = (
            "rtk_hermes_plus/plugin.py",
            "rtk_hermes_plus/compiler.py",
            "rtk_hermes_plus/storage.py",
            ".dist-info/entry_points.txt",
            ".dist-info/METADATA",
        )
        for required_part in required:
            if not any(required_part in name for name in names):
                problems.append(f"missing wheel entry: {required_part}")
        entry_points = next(
            (
                payload
                for name, payload, _ in entries
                if name.endswith(".dist-info/entry_points.txt")
            ),
            b"",
        ).decode("utf-8", errors="replace")
        for expected in (
            "[console_scripts]",
            "token-terminator = rtk_hermes_plus.cli:main",
            "[hermes_agent.plugins]",
            "token-terminator = rtk_hermes_plus",
        ):
            if expected not in entry_points:
                problems.append(f"missing entry-point declaration: {expected}")
    else:
        required = (
            "/pyproject.toml",
            "/README.md",
            "/MIGRATION.md",
            "/LICENSE",
            "/scripts/smoke_hermes.py",
            "/scripts/verify_release.py",
            "/scripts/benchmark.py",
            "/scripts/quality_ab.py",
            "/docs/QUALITY_AB_EXPERIMENT.md",
            "/benchmarks/quality_ab/suite.json",
        )
        for required_part in required:
            if not any(name.endswith(required_part) for name in names):
                problems.append(f"missing sdist entry: {required_part}")

    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "entries": len(entries),
        "problems": problems,
    }


def inspect_tracked_tree(root: Path) -> list[str]:
    """Reject private operational artifacts even when archives omit them."""
    if not (root / ".git").exists():
        return []
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        return ["could not enumerate tracked repository files"]
    names = completed.stdout.decode("utf-8", errors="replace").split("\0")
    problems = []
    for name in names:
        normalized = name.replace("\\", "/")
        if not normalized or not (root / normalized).exists():
            continue
        if any(part in normalized for part in FORBIDDEN_TRACKED_PATHS):
            problems.append(f"forbidden tracked operational path: {name}")
        if normalized.lower().endswith(FORBIDDEN_TRACKED_SUFFIXES):
            problems.append(f"forbidden tracked operational payload: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    expanded = [match for arg in arguments for match in (glob.glob(arg) or [arg])]
    paths = [Path(arg) for arg in expanded]
    if not paths:
        print("usage: verify_release.py <wheel-or-sdist> [...]", file=sys.stderr)
        return 2
    results = [inspect_archive(path) for path in paths]
    tracked_problems = inspect_tracked_tree(Path.cwd())
    if tracked_problems:
        results[0]["problems"].extend(tracked_problems)
    print(json.dumps(results, indent=2, sort_keys=True))
    kinds = {"wheel" if path.suffix == ".whl" else "sdist" for path in paths}
    if kinds != {"wheel", "sdist"}:
        print(
            "error: verification requires at least one wheel and one sdist",
            file=sys.stderr,
        )
        return 1
    return int(any(result["problems"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
