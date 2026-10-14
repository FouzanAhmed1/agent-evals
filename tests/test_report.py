"""Tests for the HTML report generator."""
from evals.judge import JudgeConfig
from evals.models import EvalCase
from evals.report import generate_report
from evals.runner import run_suite


def test_report_contains_case_names_and_pass_rate(tmp_path):
    cases = [
        EvalCase(name="alpha-case", input="hi", contains=["hi"]),
        EvalCase(name="beta-case", input="hi", contains=["nope-never-there"]),
    ]
    result = run_suite(cases, lambda prompt: "hi", suite_name="report-suite",
                       agent_name="demo", workers=2, retries=0)
    path = generate_report(result, tmp_path / "report.html")
    content = path.read_text(encoding="utf-8")

    assert "<html" in content.lower()
    assert "alpha-case" in content
    assert "beta-case" in content
    assert "50.0%" in content  # one of two cases passed
    assert "report-suite" in content
    assert "nope-never-there" in content  # failed check detail is shown
    assert "<details>" in content  # expandable failure details
    # self-contained: no external stylesheets or scripts
    assert 'rel="stylesheet"' not in content
    assert 'src="http' not in content


def test_report_escapes_agent_output(tmp_path):
    cases = [EvalCase(name="xss", input="hi", contains=["hi"])]
    result = run_suite(cases, lambda prompt: "<script>alert(1)</script>hi",
                       workers=1, retries=0)
    content = generate_report(result, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_report_with_judge_scores(tmp_path):
    cases = [EvalCase(name="judged", input="hello", contains=["hello"],
                      judge_criteria=["The response includes a friendly greeting."],
                      judge_threshold=1.0)]
    result = run_suite(cases, lambda prompt: "hello there, friendly greeting included",
                       judge_config=JudgeConfig(mode="fake"),
                       workers=1, retries=0)
    content = generate_report(result, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "judged" in content
    assert "100.0%" in content
