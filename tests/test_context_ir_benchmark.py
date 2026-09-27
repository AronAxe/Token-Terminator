from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def benchmark():
    path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_context_ir.py"
    spec = importlib.util.spec_from_file_location("tt_ir_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_golden_tasks_detect_missing_or_changed_evidence(benchmark):
    for case in benchmark.cases():
        evidence = benchmark.visible_evidence(case.source)
        assert benchmark.solve(case, evidence) == case.expected
        # A smaller empty prompt must not be mistaken for preserved quality.
        empty = [] if isinstance(evidence, list) else ""
        assert benchmark.solve(case, empty) != case.expected


def test_three_arm_report_is_honest_about_offline_scope(benchmark):
    report = benchmark.run(models=["gpt-4o"], repeats=1)
    assert report["summary"]["passed"]
    assert report["summary"]["arms_evaluated"] == 15
    assert report["mode"] == "offline-fixture-scores"
    for case in report["cases"]:
        arms = case["trials"][0]["arms"]
        assert arms[2]["final_input_tokens"] <= arms[1]["final_input_tokens"]
        assert all(arm["live_llm_quality"] == "not-run" for arm in arms)
        assert all(arm["jev_cost_usd"] == 0 for arm in arms)
        assert all(arm["golden_answer_pass"] for arm in arms)
