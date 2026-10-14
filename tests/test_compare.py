"""Tests for run comparison: deltas, classifications, compare report."""
import json

import pytest

from evals.cli import main
from evals.compare import CaseDelta, compare_files, compare_results, load_results
from evals.report import generate_compare_report


def _case(name, status, score=None):
    case = {"name": name, "input": "hi", "output": "hi", "status": status,
            "checks_passed": [], "checks_failed": [], "judge": None,
            "latency_ms": 1.0, "attempts": 1, "error": None}
    if score is not None:
        case["judge"] = {"mode": "fake", "score": score, "threshold": 4.0,
                         "passed": score >= 4.0, "criteria": []}
    return case


def _write_results(tmp_path, filename, cases):
    payload = {"suite_name": "s", "agent_name": "a", "timestamp": "t",
               "judge_mode": "fake", "summary": {}, "cases": cases}
    path = tmp_path / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture()
def run_a_path(tmp_path):
    return _write_results(tmp_path, "run-a.json", [
        _case("up", "pass", 9.0),        # improved
        _case("down", "fail", 3.0),      # newly failing (was passing)
        _case("slip", "pass", 6.0),      # regressed score, still passing
        _case("same", "pass", 5.0),      # unchanged
        _case("fix", "pass"),            # newly passing (no judge either side)
        _case("new", "pass", 7.0),       # only in A
        _case("broke", "error"),         # errored in A, was passing in B
    ])


@pytest.fixture()
def run_b_path(tmp_path):
    return _write_results(tmp_path, "run-b.json", [
        _case("up", "pass", 8.0),
        _case("down", "pass", 8.0),
        _case("slip", "pass", 8.0),
        _case("same", "pass", 5.0),
        _case("fix", "fail"),
        _case("gone", "pass", 5.0),      # only in B
        _case("broke", "pass", 7.0),
    ])


def test_deltas_are_a_minus_b(run_a_path, run_b_path):
    comp = compare_files(run_a_path, run_b_path)
    by_name = {d.name: d for d in comp.deltas}
    assert by_name["up"].delta == pytest.approx(1.0)
    assert by_name["slip"].delta == pytest.approx(-2.0)
    assert by_name["same"].delta == pytest.approx(0.0)
    assert by_name["fix"].delta == pytest.approx(1.0)  # status fallback 1.0 - 0.0
    assert by_name["new"].delta is None
    assert by_name["gone"].delta is None
    assert by_name["down"].delta == pytest.approx(-5.0)


def test_classifications(run_a_path, run_b_path):
    comp = compare_files(run_a_path, run_b_path)
    by_name = {d.name: d for d in comp.deltas}
    assert by_name["up"].classification == "improved"
    assert by_name["slip"].classification == "regressed"
    assert by_name["same"].classification == "unchanged"
    assert by_name["fix"].classification == "newly_passing"
    assert by_name["down"].classification == "newly_failing"
    assert by_name["broke"].classification == "newly_failing"
    assert by_name["new"].classification == "only_in_a"
    assert by_name["gone"].classification == "only_in_b"


def test_summary_counts(run_a_path, run_b_path):
    comp = compare_files(run_a_path, run_b_path)
    s = comp.summary
    assert s == {"total": 8, "improved": 1, "regressed": 1, "unchanged": 1,
                 "newly_passing": 1, "newly_failing": 2,
                 "only_in_a": 1, "only_in_b": 1}


def test_sorted_by_biggest_regression(run_a_path, run_b_path):
    comp = compare_files(run_a_path, run_b_path)
    ordered = comp.sorted_by_regression()
    scored = [d for d in ordered if d.delta is not None]
    assert scored[0].name == "down"  # -5.0 is the biggest regression
    assert [d.delta for d in scored] == sorted(d.delta for d in scored)
    # unscored (only-in-one) cases sort last
    assert {d.name for d in ordered[-2:]} == {"new", "gone"}


def test_cases_missing_from_one_file_are_graceful():
    comp = compare_results({"cases": []}, {"cases": [_case("x", "pass", 5.0)]},
                           name_a="a", name_b="b")
    assert len(comp.deltas) == 1
    d = comp.deltas[0]
    assert isinstance(d, CaseDelta)
    assert d.classification == "only_in_b"
    assert d.status_a is None and d.status_b == "pass"


def test_compare_report_contains_comparison_section(tmp_path, run_a_path, run_b_path):
    comp = compare_files(run_a_path, run_b_path)
    path = generate_compare_report(comp, tmp_path / "compare.html")
    content = path.read_text(encoding="utf-8")
    assert "Comparison summary" in content
    assert "down" in content and "up" in content
    assert "newly failing" in content
    # biggest regression listed first in the delta table
    table = content.split("Score deltas")[1]
    assert table.index("down") < table.index("slip")
    assert "run-a.json" in content and "run-b.json" in content
    # self-contained: no external stylesheets or scripts
    assert 'rel="stylesheet"' not in content
    assert "src=\"http" not in content


def test_load_results_rejects_non_results(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": true}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_results(bad)


def test_compare_cli_writes_html_and_md(tmp_path, run_a_path, run_b_path):
    report = tmp_path / "compare.html"
    md_out = tmp_path / "compare-notes.md"
    rc = main(["compare", str(run_a_path), str(run_b_path),
               "--report", str(report), "--format", "md", "--output", str(md_out)])
    assert rc == 1  # newly failing cases -> nonzero exit
    assert report.exists()
    assert "Comparison summary" in report.read_text(encoding="utf-8")
    md = md_out.read_text(encoding="utf-8")
    assert "Top regressions" in md
    assert "Newly failing" in md


def test_compare_cli_exit_zero_when_nothing_newly_failing(tmp_path, run_b_path):
    rc = main(["compare", str(run_b_path), str(run_b_path)])
    assert rc == 0
