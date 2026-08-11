import os
import subprocess
from unittest.mock import patch

from rtk_hermes_plus.compress import NativeCompressor, RecoveryStore, compact_text
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.metrics import Metrics


def config(tmp_path, **kwargs):
    values = {
        "native_min_chars": 1_000,
        "native_max_chars": 1_200,
        "recovery_dir": tmp_path / "recovery",
        "recovery_files": 2,
    }
    values.update(kwargs)
    return Config(**values)


def test_compact_text_collapses_repeated_lines():
    text = "start\n" + "same\n" * 20 + "end\n"
    compact = compact_text(text, 2_000)
    assert "[repeated ×20]" in compact
    assert len(compact) < len(text)


def test_compact_text_preserves_head_and_tail():
    lines = [f"line {i} {'x' * 30}" for i in range(300)]
    compact = compact_text("\n".join(lines), 1_000)
    assert "line 0" in compact
    assert "line 299" in compact
    assert "lines omitted" in compact
    assert len(compact) < 1_100


def test_recovery_store_permissions_and_rotation(tmp_path):
    metrics = Metrics()
    store = RecoveryStore(config(tmp_path), metrics)
    paths = [store.write("search_files", f"result {index}") for index in range(3)]
    existing = list((tmp_path / "recovery").glob("*.log"))
    assert len(existing) == 2
    assert paths[-1] in existing
    assert paths[-1].read_text(encoding="utf-8") == "result 2"
    if os.name != "nt":
        # Windows security is ACL-based; POSIX mode-bit assertions are not
        # meaningful there. Recovery files inherit the user's profile ACL.
        assert all((path.stat().st_mode & 0o777) == 0o600 for path in existing)
        assert (tmp_path / "recovery").stat().st_mode & 0o777 == 0o700


def test_balanced_compresses_large_search_and_saves_original(tmp_path):
    metrics = Metrics()
    compressor = NativeCompressor(config(tmp_path), metrics, None)
    raw = "\n".join(f"src/file.py:{i}: match {'x' * 30}" for i in range(500))
    output = compressor.transform(tool_name="search_files", args={}, result=raw)
    assert output is not None
    assert len(output) < len(raw)
    assert "full output:" in output
    assert metrics.snapshot()["native_compressed"] == 1


def test_balanced_leaves_read_file_unchanged(tmp_path):
    compressor = NativeCompressor(config(tmp_path), Metrics(), "/fake/rtk")
    assert (
        compressor.transform(
            tool_name="read_file", args={"path": "x.py"}, result="x" * 5_000
        )
        is None
    )


def test_aggressive_uses_rtk_read_when_smaller(tmp_path):
    cfg = config(tmp_path, mode="aggressive")
    compressor = NativeCompressor(cfg, Metrics(), "/fake/rtk")
    completed = subprocess.CompletedProcess(
        [], 0, stdout="def useful(): ...\n", stderr=""
    )
    with patch("subprocess.run", return_value=completed) as run:
        output = compressor.transform(
            tool_name="read_file",
            args={"path": "large.py", "cwd": str(tmp_path)},
            result="body\n" * 3_000,
        )
    assert output and "def useful" in output
    assert "full output:" in output
    run.assert_called_once()


def test_remote_native_output_is_not_compressed(monkeypatch, tmp_path):
    monkeypatch.setenv("TERMINAL_ENV", "ssh")
    compressor = NativeCompressor(config(tmp_path), Metrics(), None)
    raw = "match\n" * 3_000
    assert compressor.transform(tool_name="search_files", args={}, result=raw) is None


def test_small_native_output_is_untouched(tmp_path):
    compressor = NativeCompressor(config(tmp_path), Metrics(), None)
    assert (
        compressor.transform(tool_name="search_files", args={}, result="short") is None
    )


def test_metadata_cannot_turn_compression_into_larger_result(tmp_path):
    cfg = config(tmp_path, native_min_chars=1_000, native_max_chars=990)
    compressor = NativeCompressor(cfg, Metrics(), None)
    raw = "x" * 1_001
    assert compressor.transform(tool_name="search_files", args={}, result=raw) is None
