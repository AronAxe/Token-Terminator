"""Deterministic concurrent discovery tests; never patch the live Hermes loader."""

import concurrent.futures
import hashlib
import logging
import os
import sys
import threading
import types
from pathlib import Path

import pytest

from rtk_hermes_plus import hermes_discovery as repair

# The minimal fixture reproduces the same cache-before-exec ordering. Integration
# CI supplies the actual pinned Hermes source instead through TT_HERMES_LOADER.
_FIXTURE = """import importlib.util
import sys
from pathlib import Path

def load_plugin_module(module_name, plugin_dir, *, parents, logger, synthetic_namespace=None):
    cached = sys.modules.get(module_name)
    if cached is not None and getattr(cached, "__file__", None):
        return cached
    spec = importlib.util.spec_from_file_location(module_name, plugin_dir / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        return None
    return mod
"""


@pytest.fixture
def loader_source(monkeypatch):
    source_path = os.environ.get("TT_HERMES_LOADER")
    source = Path(source_path).read_text(encoding="utf-8") if source_path else _FIXTURE
    if source_path:
        # Do not whitelist an arbitrary host in the integration test.
        assert (
            hashlib.sha256(source.encode()).hexdigest() in repair._KNOWN_SOURCE_SHA256
        )
        isolation = types.ModuleType("hermes_cli.plugin_isolation")
        isolation.in_process_import_refusal = lambda _: None
        monkeypatch.setitem(sys.modules, "hermes_cli.plugin_isolation", isolation)
    else:
        monkeypatch.setattr(
            repair,
            "_KNOWN_SOURCE_SHA256",
            {hashlib.sha256(source.encode()).hexdigest()},
        )
    return source


def make_loader(tmp_path, source):
    module = types.ModuleType("fixture_host_loader")
    module.__file__ = str(tmp_path / "plugin_loader.py")
    exec(  # noqa: S102 - exact reviewed host source or literal test fixture
        compile(repair.patched_source(source), module.__file__, "exec"), module.__dict__
    )
    return module


def load(module, directory):
    return module.load_plugin_module(
        "_hermes_user_context_engine.token-terminator",
        directory,
        parents=(),
        logger=logging.getLogger("discovery-test"),
        synthetic_namespace="_hermes_user_context_engine",
    )


def plugin(tmp_path, name, body):
    directory = tmp_path / name / "token-terminator"
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text(body, encoding="utf-8")
    return directory


def test_concurrent_reader_waits_until_initialization_finishes(
    tmp_path, monkeypatch, loader_source
):
    module = make_loader(tmp_path, loader_source)
    control = types.ModuleType("tt_test_load_control")
    control.started, control.release = threading.Event(), threading.Event()
    monkeypatch.setitem(sys.modules, control.__name__, control)
    directory = plugin(
        tmp_path,
        "default",
        "from tt_test_load_control import started, release\nstarted.set()\nassert release.wait(5)\nREADY = True\n",
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(load, module, directory)
        assert control.started.wait(5)
        second = pool.submit(load, module, directory)
        try:
            with pytest.raises(concurrent.futures.TimeoutError):
                second.result(timeout=0.05)
        finally:
            control.release.set()
        a, b = first.result(timeout=5), second.result(timeout=5)
    assert a is b and a.READY


def test_many_simultaneous_requests_return_complete_module(tmp_path, loader_source):
    module = make_loader(tmp_path, loader_source)
    directory = plugin(
        tmp_path, "default", "import time\ntime.sleep(.03)\nREADY = 42\n"
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        modules = list(pool.map(lambda _: load(module, directory), range(64)))
    assert all(m is modules[0] and m.READY == 42 for m in modules)


def test_profiles_with_same_slug_use_different_modules(tmp_path, loader_source):
    module = make_loader(tmp_path, loader_source)
    a = plugin(tmp_path, "default", 'PROFILE = "default"\n')
    b = plugin(tmp_path, "brain", 'PROFILE = "brain"\n')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda d: load(module, d), [a, b]))
    assert first.PROFILE == "default" and second.PROFILE == "brain"
    assert first is not second
    assert first.__name__ != second.__name__


def test_failed_initialization_can_be_retried(tmp_path, loader_source):
    module = make_loader(tmp_path, loader_source)
    directory = plugin(tmp_path, "default", 'raise RuntimeError("fixture")\n')
    assert load(module, directory) is None
    (directory / "__init__.py").write_text('READY = "recovered successfully"\n')
    assert load(module, directory).READY == "recovered successfully"


def test_recursive_discovery_does_not_expose_partial_module(
    tmp_path, monkeypatch, loader_source
):
    module = make_loader(tmp_path, loader_source)
    control = types.ModuleType("tt_test_recursive")
    directory = plugin(
        tmp_path,
        "default",
        "from tt_test_recursive import again\nassert again() is None\nREADY = True\n",
    )
    control.again = lambda: load(module, directory)
    monkeypatch.setitem(sys.modules, control.__name__, control)
    assert load(module, directory).READY


def test_other_plugins_use_original_loader_unchanged(tmp_path, loader_source):
    module = make_loader(tmp_path, loader_source)
    seen = []
    module._tt_loader_original = lambda *a, **kw: seen.append((a, kw)) or "original"
    assert (
        module.load_plugin_module("other", tmp_path, parents=(), logger=None)
        == "original"
    )
    assert seen[0][0] == ("other", tmp_path)


def test_installer_backup_and_idempotency(tmp_path, loader_source):
    path = tmp_path / "plugin_loader.py"
    before = loader_source.replace("\n", "\r\n").encode()
    path.write_bytes(before)
    result = repair.repair_hermes_discovery(path)
    assert result["changed"]
    assert Path(result["backup"]).read_bytes() == before
    installed = path.read_bytes()
    assert repair.repair_hermes_discovery(path)["state"] == "already_repaired"
    assert path.read_bytes() == installed
    assert not list(tmp_path.glob(".tt-loader-*"))


def test_unknown_host_is_not_modified(tmp_path):
    path = tmp_path / "plugin_loader.py"
    path.write_text("unrelated = True\n")
    with pytest.raises(ValueError, match="not the reviewed"):
        repair.repair_hermes_discovery(path)
    assert path.read_text() == "unrelated = True\n"
    assert len(list(tmp_path.iterdir())) == 1


def test_modified_repair_is_rejected(loader_source):
    patched = repair.patched_source(loader_source)
    with pytest.raises(ValueError, match="unrecognized"):
        repair.patched_source(patched + "\n# another change\n")


def test_changed_host_with_intact_repair_suffix_is_not_approved(loader_source):
    patched = repair.patched_source(loader_source)
    with pytest.raises(ValueError, match="unrecognized"):
        repair.patched_source("# host changed\n" + patched)


def test_backup_symlink_is_refused(tmp_path, loader_source):
    path = tmp_path / "plugin_loader.py"
    path.write_text(loader_source)
    target = tmp_path / "other.txt"
    target.write_text("unrelated")
    backup = path.with_name(path.name + ".tt-before-0.11.2")
    try:
        backup.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this Windows account")
    with pytest.raises(ValueError, match="symlinked Hermes backup"):
        repair.repair_hermes_discovery(path)
    assert path.read_text() == loader_source
    assert target.read_text() == "unrelated"
