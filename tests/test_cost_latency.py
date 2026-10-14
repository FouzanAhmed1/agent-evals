"""Tests for cost + latency tracking: per-case tokens/cost, aggregates, report."""
import json

import pytest

from evals.judge import JudgeConfig, estimate_cost, fake_judge_score
from evals.models import CaseResult, EvalCase, SuiteResult
from evals.report import generate_report
from evals.runner import run_suite


def _judged_cases():
    return [
        EvalCase(name="one", input="hi", contains=["hi"],
                 judge_criteria=["The response is friendly and says hi."],
                 judge_threshold=1.0),
        EvalCase(name="two", input="hi", contains=["hi"],
                 judge_criteria=["The response is friendly and says hi."],
                 judge_threshold=1.0),
    ]


def test_fake_judge_tokens_are_deterministic_and_nonzero():
    first = fake_judge_score("hi friendly", ["The response is friendly."], 1.0)
    second = fake_judge_score("hi friendly", ["The response is friendly."], 1.0)
    assert first.prompt_tokens == second.prompt_tokens > 0
    assert first.completion_tokens == second.completion_tokens > 0
    assert first.cost_usd == second.cost_usd > 0
    d = first.to_dict()
    assert d["prompt_tokens"] > 0 and d["cost_usd"] > 0


def test_estimate_cost_uses_price_table():
    assert estimate_cost("gpt-4o-mini", 1000, 1000) == pytest.approx(0.00075)
    assert estimate_cost("unknown-model", 0, 0) == 0.0
    assert estimate_cost("unknown-model", 1000, 0) > 0  # fallback price applies


def test_latency_and_cost_recorded_on_results():
    result = run_suite(
        _judged_cases(),
        lambda prompt: "hi, friendly greeting here",
        workers=2,
        retries=0,
        judge_config=JudgeConfig(mode="fake"),
    )
    for c in result.cases:
        assert isinstance(c.latency_ms, float)
        assert c.latency_ms >= 0.0
        assert c.prompt_tokens > 0
        assert c.completion_tokens > 0
        assert c.cost_usd > 0
    s = result.summary()
    expected_tokens = sum(c.prompt_tokens + c.completion_tokens for c in result.cases)
    assert s["total_tokens"] == expected_tokens
    assert s["total_cost_usd"] == pytest.approx(
        sum(c.cost_usd for c in result.cases)
    )


def _latency_suite(values):
    cases = [
        CaseResult(name=f"c{i}", input="x", output="x", status="pass",
                   checks_passed=[], checks_failed=[], judge=None,
                   latency_ms=v, attempts=1, error=None)
        for i, v in enumerate(values)
    ]
    return SuiteResult(suite_name="s", agent_name="a", timestamp="t",
                       judge_mode="off", cases=cases)


def test_latency_aggregates_mean_p50_p95():
    s = _latency_suite([1.0, 2.0, 3.0, 4.0, 5.0]).summary()
    assert s["mean_latency_ms"] == 3.0
    assert s["p50_latency_ms"] == 3.0
    assert s["p95_latency_ms"] == 5.0
    assert s["avg_latency_ms"] == 3.0  # backwards-compatible alias


def test_latency_aggregates_empty_suite():
    s = _latency_suite([]).summary()
    assert s["mean_latency_ms"] == 0.0
    assert s["p50_latency_ms"] == 0.0
    assert s["p95_latency_ms"] == 0.0
    assert s["total_cost_usd"] == 0.0
    assert s["total_tokens"] == 0


def test_results_json_contains_latency_and_cost(tmp_path):
    from evals.runner import write_results
    result = run_suite(
        _judged_cases(),
        lambda prompt: "hi, friendly greeting here",
        workers=2,
        retries=0,
        judge_config=JudgeConfig(mode="fake"),
    )
    path = write_results(result, tmp_path / "results.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("mean_latency_ms", "p50_latency_ms", "p95_latency_ms",
                "total_tokens", "total_cost_usd"):
        assert key in data["summary"]
    case = data["cases"][0]
    for key in ("latency_ms", "prompt_tokens", "completion_tokens", "cost_usd"):
        assert key in case


def test_report_contains_cost_and_latency_stats(tmp_path):
    import time

    def slow_agent(prompt):
        time.sleep(0.01)
        return "hi, friendly greeting here"

    result = run_suite(
        _judged_cases(),
        slow_agent,
        workers=2,
        retries=0,
        judge_config=JudgeConfig(mode="fake"),
    )
    path = generate_report(result, tmp_path / "report.html")
    content = path.read_text(encoding="utf-8")
    assert "P95 latency" in content
    assert "Est. cost" in content
    assert "Slowest cases" in content
    assert "Judge tokens" in content
