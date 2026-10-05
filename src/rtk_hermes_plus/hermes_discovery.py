"""Install a narrow, backed-up repair for the known Hermes TT discovery race.

Never runs on import. The affected host publishes half-loaded directory modules;
no hook inside that module can synchronize a reader that arrives before its code
runs. The explicit installer therefore patches the host loader, for TT only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
from pathlib import Path

_KNOWN_SOURCE_SHA256 = frozenset(
    {
        "402d3fd6f6077c344f15713ac3b793fbccbe0602181bceff7a23690270e3ff35",
    }
)
_MARKER = "# BEGIN TOKEN TERMINATOR DISCOVERY REPAIR 1"
_PATCH = """

# BEGIN TOKEN TERMINATOR DISCOVERY REPAIR 1
# Narrow compatibility repair: only TT's user-directory ContextEngine loads.
# Installed with an exact-source guard and adjacent original-file backup.
import functools as _tt_functools
import hashlib as _tt_hashlib
import threading as _tt_threading

_tt_loader_original = load_plugin_module
_tt_loader_guard = _tt_threading.Lock()
_tt_loader_locks = {}
_tt_loader_active = set()


@_tt_functools.wraps(_tt_loader_original)
def load_plugin_module(module_name, plugin_dir, *, parents, logger,
                       synthetic_namespace=None):
    if (synthetic_namespace != "_hermes_user_context_engine"
            or Path(plugin_dir).name != "token-terminator"):
        return _tt_loader_original(module_name, plugin_dir, parents=parents,
                                   logger=logger,
                                   synthetic_namespace=synthetic_namespace)
    # The upstream synthetic name contains only the slug. Separate profile homes
    # must not reuse the first profile's imported module (or its sibling modules).
    identity = str(Path(plugin_dir).resolve())
    suffix = _tt_hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    namespace = synthetic_namespace + "_tt_" + suffix
    scoped_name = namespace + ".token-terminator"
    with _tt_loader_guard:
        lock = _tt_loader_locks.setdefault(scoped_name, _tt_threading.RLock())
    if not lock.acquire(timeout=10):
        logger.warning("Token Terminator initialization still busy; retry discovery")
        return None
    try:
        # A same-thread recursive discovery must not consume its own half-module.
        if scoped_name in _tt_loader_active:
            return None
        _tt_loader_active.add(scoped_name)
        try:
            return _tt_loader_original(scoped_name, plugin_dir, parents=parents,
                                       logger=logger,
                                       synthetic_namespace=namespace)
        finally:
            _tt_loader_active.discard(scoped_name)
    finally:
        lock.release()
# END TOKEN TERMINATOR DISCOVERY REPAIR 1
"""


def patched_source(source: str) -> str:
    """Return the repair only for the reviewed host implementation."""
    normalized = source.replace("\r\n", "\n")
    if _MARKER in normalized:
        if (
            normalized.endswith(_PATCH)
            and hashlib.sha256(normalized[: -len(_PATCH)].encode("utf-8")).hexdigest()
            in _KNOWN_SOURCE_SHA256
        ):
            return normalized
        raise ValueError("unrecognized modification to Hermes discovery repair")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if digest not in _KNOWN_SOURCE_SHA256:
        raise ValueError(
            "Hermes plugin_loader.py is not the reviewed affected version; "
            "left unchanged. Review its concurrency handling before selecting TT."
        )
    result = normalized + _PATCH
    compile(result, "plugin_loader.py", "exec")
    return result


def repair_hermes_discovery(loader_path: Path | None = None) -> dict:
    """Explicit install-time repair. Preserve original bytes for rollback."""
    if loader_path is None:
        try:
            spec = importlib.util.find_spec("plugins.plugin_loader")
        except (ImportError, ValueError, AttributeError):
            spec = None
        if spec is None or not spec.origin:
            return {"state": "hermes_not_installed", "changed": False}
        loader_path = Path(spec.origin)
    path = Path(loader_path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError("refusing a symlinked Hermes loader")
    before = path.read_bytes()
    source = before.decode("utf-8")
    after = patched_source(source).encode("utf-8")
    if _MARKER in source:
        return {"state": "already_repaired", "changed": False}
    backup = path.with_name(path.name + ".tt-before-0.11.2")
    if backup.is_symlink():
        raise ValueError("refusing a symlinked Hermes backup")
    try:
        with backup.open("xb") as handle:
            handle.write(before)
    except FileExistsError:
        if backup.read_bytes() != before:
            raise ValueError("existing Hermes loader backup differs; left unchanged")
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".tt-loader-", delete=False
        ) as handle:
            temp_name = handle.name
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, path.stat().st_mode)
        if path.read_bytes() != before:
            raise ValueError("Hermes loader changed during repair; retry after review")
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
    return {
        "state": "repaired",
        "changed": True,
        "path": str(path),
        "backup": str(backup),
        "restart_required": True,
    }
