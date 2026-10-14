"""Tests for flakiness detection: --repeat runs, pass rates, FLAKY flag."""
import threading

from evals.models import EvalCase
from evals.report import generate_report
from evals.runner import run_suite


def alternating_agent_factory():
    """Stub agent whose answer alternates between good and bad on every call."""
    state = {"n": 0}
    lock = threading.Lock()

    def agent(prompt):
        with lock:
            state["n"] += 1
            n = state["n"]
        if n % 2 == 0:
            return "the completely wrong answer"
        return "hello, the right answer"

    return agent


CASES = [EvalCase(name="coinflip", input="hi", contains=["hello"])]


def test_flaky_case_flagged_with_repeat_4():
    result = run_suite(
        CASES, alternating_agent_factory(), workers=1, retries=0, repeat=4
    )
    case = result.cases[0]
    assert case.repeat_runs == 4
    assert case.pass_rate == 0.5
    assert case.flaky is True
    assert case.status == "fail"  # not all repeats passed
    assert result.summary()["flaky"] == 1


def test_stable_case_not_flagged_with_repeat():
    result = run_suite(
        CASES, lambda prompt: "hello there", workers=1, retries=0, repeat=4
    )
    case = result.cases[0]
    assert case.pass_rate == 1.0
    assert case.flaky is False
    assert case.status == "pass"
    assert result.summary()["flaky"] == 0


def test_single_run_behavior_unchanged():
    result = run_suite(CASES, alternating_agent_factory(), workers=1, retries=0)
    case = result.cases[0]
    assert case.repeat_runs == 1
    assert case.pass_rate is None
    assert case.flaky is False
    assert case.status == "pass"  # first call is the good one
    assert result.summary()["flaky"] == 0


def test_all_runs_erroring_stays_error():
    def broken(prompt):
        raise RuntimeError("boom")

    result = run_suite(
        [EvalCase(name="broke", input="hi")], broken, workers=1, retries=0, repeat=3
    )
    case = result.cases[0]
    assert case.status == "error"
    assert case.pass_rate == 0.0
    assert case.flaky is False


def test_report_marks_flaky_cases(tmp_path):
    result = run_suite(
        CASES, alternating_agent_factory(), workers=1, retries=0, repeat=4
    )
    path = generate_report(result, tmp_path / "report.html")
    content = path.read_text(encoding="utf-8")
    assert "FLAKY" in content
    assert "badge flaky" in content
    assert "Flakiness" in content
    # pass-rate distribution buckets are rendered
    assert "100%" in content and "0%" in content


def test_report_without_repeats_has_no_flaky_section(tmp_path):
    result = run_suite(CASES, alternating_agent_factory(), workers=1, retries=0)
    path = generate_report(result, tmp_path / "report.html")
    content = path.read_text(encoding="utf-8")
    assert "Flakiness" not in content
