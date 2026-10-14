"""Tests for Markdown export: run summary and comparison summary."""
import json

from evals.cli import main
from evals.compare import compare_files, compare_results
from evals.judge import JudgeConfig
from evals.markdown import markdown_for_compare, markdown_for_run
from evals.models import EvalCase
from evals.runner import run_suite


def _run_result():
    cases = [
        EvalCase(name="good", input="hi", contains=["hi"]),
        EvalCase(name="bad", input="hi", contains=["never-there"]),
        EvalCase(name="judged", input="hi", contains=["hi"],
                 judge_criteria=["The response is friendly and says hi."],
                 judge_threshold=9.9),
    ]
    return run_suite(cases, lambda prompt: "hi", workers=2, retries=0,
                     judge_config=JudgeConfig(mode="fake"))


def test_markdown_run_has_key_sections_and_numbers():
    result = _run_result()
    md = markdown_for_run(result)
    s = result.summary()
    assert md.startswith("# Eval results:")
    assert f"**{s['pass_rate']}%**" in md
    assert f"({s['passed']}/{s['total']} passed" in md
    assert f"${s['total_cost_usd']:.4f}" in md
    assert "## Failing cases (2)" in md
    assert "`bad`" in md and "`judged`" in md
    # one-line reasons: failed check and judge score
    assert "never-there" in md
    assert "judge score" in md


def test_markdown_run_all_passing():
    cases = [EvalCase(name="good", input="hi", contains=["hi"])]
    result = run_suite(cases, lambda prompt: "hi", workers=1, retries=0)
    md = markdown_for_run(result)
    assert "All cases passed" in md
    assert "## Failing cases" not in md


def test_markdown_compare_sections():
    def case(name, status, score):
        judge = {"mode": "fake", "score": score, "threshold": 4.0,
                 "passed": score >= 4.0, "criteria": []}
        return {"name": name, "status": status, "judge": judge}

    a = {"cases": [case("reg", "pass", 4.0), case("imp", "pass", 9.0),
                   case("newfail", "fail", 0.0)]}
    b = {"cases": [case("reg", "pass", 8.0), case("imp", "pass", 6.0),
                   case("newfail", "pass", 7.0)]}
    comp = compare_results(a, b, name_a="new", name_b="old")
    md = markdown_for_compare(comp)
    assert md.startswith("# Eval comparison:")
    assert "**1** improved" in md
    assert "**1** regressed" in md
    assert "## Top regressions (2)" in md  # reg plus the newly failing case
    assert "`reg`: 8.0 -> 4.0 (delta -4.0)" in md
    assert "## Top improvements (1)" in md
    assert "`imp`: 6.0 -> 9.0 (delta +3.0)" in md
    assert "## Newly failing (1)" in md
    assert "`newfail`" in md


def test_run_cli_writes_md_next_to_report(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "name: md-suite\ncases:\n"
        "  - name: ok\n    input: hi\n    rubric:\n      contains: ['hi']\n",
        encoding="utf-8",
    )
    report = tmp_path / "report.html"
    rc = main(["run", "--suite", str(suite), "--agent", "demos:support_agent",
               "--fake-judge", "--results", str(tmp_path / "r.json"),
               "--report", str(report), "--format", "md"])
    assert rc == 0
    md_path = tmp_path / "report.md"
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "# Eval results: md-suite" in content
    assert "pass rate" in content


def test_run_cli_md_output_flag_chooses_path(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "name: md-suite\ncases:\n"
        "  - name: ok\n    input: hi\n    rubric:\n      contains: ['hi']\n",
        encoding="utf-8",
    )
    custom = tmp_path / "custom" / "notes.md"
    rc = main(["run", "--suite", str(suite), "--agent", "demos:support_agent",
               "--fake-judge", "--results", str(tmp_path / "r.json"),
               "--format", "md", "--output", str(custom)])
    assert rc == 0
    assert custom.exists()
