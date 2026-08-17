import subprocess
from unittest.mock import patch

from rtk_hermes_plus.compress import NativeCompressor, RecoveryStore, compact_text
from rtk_hermes_plus.config import Config
from rtk_hermes_plus.metrics import Metrics


def config(tmp_path, **kwargs):
    values = {
        "native_min_chars": 1_000,
        "native_max_chars": 1_200,
        "db_path": tmp_path / "artifacts.sqlite3",
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
    assert len(compact) <= 1_000


def test_compact_text_hard_bounds_a_single_large_line():
    compact = compact_text("x" * 20_000, 1_000)
    assert len(compact) <= 1_000
    assert "lines omitted" in compact


def test_recovery_store_uses_content_addressing_and_exact_readback(tmp_path):
    metrics = Metrics()
    store = RecoveryStore(config(tmp_path), metrics)
    first = store.write("search_files", "result")
    duplicate = store.write("search_files", "result")
    assert first == duplicate
    assert first is not None
    assert store.store is not None
    assert store.store.get_artifact(first).content == "result"
    assert store.store.counts()["artifacts"] == 1


def test_balanced_compresses_large_search_and_saves_original(tmp_path):
    metrics = Metrics()
    compressor = NativeCompressor(config(tmp_path), metrics, None)
    raw = "\n".join(f"src/file.py:{i}: match {'x' * 30}" for i in range(500))
    output = compressor.transform(tool_name="search_files", args={}, result=raw)
    assert output is not None
    assert len(output) < len(raw)
    assert "full artifact=" in output
    assert metrics.snapshot()["native_compressed"] == 1


def test_native_mode_compresses_search_without_rtk(tmp_path):
    cfg = config(tmp_path, mode="native")
    compressor = NativeCompressor(cfg, Metrics(), None)
    raw = "match\n" * 3_000
    output = compressor.transform(tool_name="search_files", args={}, result=raw)
    assert output is not None
    assert len(output) < len(raw)


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
    assert "full artifact=" in output
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
    assert compressor.recovery.store is not None
    assert compressor.recovery.store.counts()["artifacts"] == 0


def test_compression_fails_open_when_exact_recovery_is_unavailable(
    tmp_path, monkeypatch
):
    compressor = NativeCompressor(config(tmp_path), Metrics(), None)
    monkeypatch.setattr(compressor.recovery, "write", lambda *_args, **_kwargs: None)
    raw = "match\n" * 3_000
    assert compressor.transform(tool_name="search_files", args={}, result=raw) is None
