"""Tests for the suite runner: concurrency, retries, results.json schema."""
import json
import threading

import pytest

from evals.judge import JudgeConfig
from evals.models import EvalCase
from evals.runner import run_case, run_suite, write_results


def make_cases(n, **kwargs):
    defaults = dict(input="hello", contains=["hello"])
    defaults.update(kwargs)
    return [EvalCase(name=f"case-{i}", **defaults) for i in range(n)]


def test_concurrency_executes_all_cases():
    seen = []
    lock = threading.Lock()

    def agent(prompt):
        with lock:
            seen.append(prompt)
        return "hello world"

    cases = make_cases(12)
    result = run_suite(cases, agent, workers=4, retries=0)
    assert len(result.cases) == 12
    assert all(c.status == "pass" for c in result.cases)
    assert sorted(seen) == ["hello"] * 12
    # order is preserved despite concurrent execution
    assert [c.name for c in result.cases] == [f"case-{i}" for i in range(12)]


def test_retry_flaky_agent_succeeds():
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "hello there"

    case = EvalCase(name="flaky", input="hello", contains=["hello"])
    result = run_case(case, flaky, retries=2)
    assert result.status == "pass"
    assert result.attempts == 2
    assert result.output == "hello there"
    assert result.error is None


def test_retry_exhausted_marks_error():
    calls = {"n": 0}

    def always_fails(prompt):
        calls["n"] += 1
        raise ValueError("always broken")

    case = EvalCase(name="broken", input="hello")
    result = run_case(case, always_fails, retries=2)
    assert result.status == "error"
    assert result.attempts == 3  # initial try + 2 retries
    assert result.output is None
    assert "ValueError" in result.error
    assert calls["n"] == 3


def test_non_string_output_is_error():
    case = EvalCase(name="weird", input="hello")
    result = run_case(case, lambda prompt: {"not": "a string"}, retries=0)
    assert result.status == "error"
    assert "expected str" in result.error


def test_results_json_schema(tmp_path):
    cases = [
        EvalCase(name="ok", input="hi", contains=["hi"]),
        EvalCase(name="bad", input="hi", contains=["missing-needle"]),
    ]
    judge_config = JudgeConfig(mode="fake")
    result = run_suite(
        cases,
        lambda prompt: "hi there",
        suite_name="schema-suite",
        agent_name="test-agent",
        workers=2,
        retries=0,
        judge_config=judge_config,
    )
    path = write_results(result, tmp_path / "results.json")
    data = json.loads(path.read_text())

    assert data["suite_name"] == "schema-suite"
    assert data["agent_name"] == "test-agent"
    assert data["judge_mode"] == "fake"
    assert "timestamp" in data
    summary = data["summary"]
    for key in ("total", "passed", "failed", "errors", "pass_rate", "avg_latency_ms"):
        assert key in summary
    assert summary["total"] == 2
    assert summary["passed"] == 1 and summary["failed"] == 1

    by_name = {c["name"]: c for c in data["cases"]}
    ok = by_name["ok"]
    for key in ("name", "input", "output", "status", "checks_passed",
                "checks_failed", "judge", "latency_ms", "attempts", "error"):
        assert key in ok, f"missing key {key}"
    assert ok["status"] == "pass"
    assert by_name["bad"]["status"] == "fail"
    assert by_name["bad"]["checks_failed"][0]["check"] == "contains:'missing-needle'"
    assert by_name["bad"]["judge"] is None  # no criteria configured
    assert isinstance(ok["latency_ms"], float)
    assert ok["attempts"] == 1


def test_judge_runs_when_criteria_configured(tmp_path):
    case = EvalCase(
        name="judged",
        input="hi",
        contains=["hi"],
        judge_criteria=["The response is friendly and says hi."],
        judge_threshold=1.0,
    )
    result = run_case(case, lambda prompt: "hi, friendly greeting here", judge_config=JudgeConfig(mode="fake"))
    assert result.judge is not None
    assert result.judge.mode == "fake"
    assert 0.0 <= result.judge.score <= 10.0
    assert result.judge.passed is True
    assert result.status == "pass"
    assert len(result.judge.criteria) == 1
