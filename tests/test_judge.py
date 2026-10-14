"""Tests for the fake judge: determinism, bounds, config resolution."""
import pytest

from evals.judge import (
    JudgeConfig,
    fake_judge_score,
    resolve_judge_config,
    score_with_judge,
)


CRITERIA = [
    "The response offers a refund within the 30-day policy and stays polite.",
    "The response mentions the order number.",
]
OUTPUT = (
    "Happy to help! Our policy offers a full refund within 30 days. "
    "Your order number 84721 is confirmed."
)


def test_fake_judge_is_deterministic():
    first = fake_judge_score(OUTPUT, CRITERIA, threshold=4.0)
    second = fake_judge_score(OUTPUT, CRITERIA, threshold=4.0)
    assert first.to_dict() == second.to_dict()


def test_fake_judge_scores_within_bounds():
    result = fake_judge_score(OUTPUT, CRITERIA, threshold=4.0)
    assert 0.0 <= result.score <= 10.0
    for crit in result.criteria:
        assert 0.0 <= crit.score <= 10.0
    assert len(result.criteria) == len(CRITERIA)


def test_fake_judge_threshold_decides_pass():
    low = fake_judge_score(OUTPUT, CRITERIA, threshold=0.0)
    high = fake_judge_score(OUTPUT, CRITERIA, threshold=10.1)
    assert low.passed is True
    assert high.passed is False


def test_fake_judge_empty_criteria_scores_perfect():
    result = fake_judge_score(OUTPUT, [], threshold=5.0)
    assert result.score == 10.0
    assert result.passed is True


def test_fake_judge_keyword_detail_is_explainable():
    result = fake_judge_score(OUTPUT, ["The response mentions the order number."], threshold=4.0)
    crit = result.criteria[0]
    assert "order" in crit.matched_keywords
    assert "number" in crit.matched_keywords
    # every significant word is either matched or missing, never both or neither
    assert set(crit.matched_keywords).isdisjoint(crit.missing_keywords)


def test_score_with_judge_dispatches_fake():
    result = score_with_judge(OUTPUT, CRITERIA, JudgeConfig(mode="fake"), threshold=4.0)
    assert result.mode == "fake"


def test_resolve_judge_config_fake_flag():
    assert resolve_judge_config(fake=True).mode == "fake"


def test_resolve_judge_config_env_var(monkeypatch):
    monkeypatch.setenv("EVAL_FAKE_JUDGE", "1")
    monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
    assert resolve_judge_config().mode == "fake"


def test_resolve_judge_config_none_without_key(monkeypatch):
    monkeypatch.delenv("EVAL_FAKE_JUDGE", raising=False)
    monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
    assert resolve_judge_config() is None


def test_resolve_judge_config_real(monkeypatch):
    monkeypatch.delenv("EVAL_FAKE_JUDGE", raising=False)
    monkeypatch.setenv("EVAL_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("EVAL_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("EVAL_LLM_MODEL", "test-model")
    config = resolve_judge_config()
    assert config.mode == "real"
    assert config.base_url == "https://example.com/v1"
    assert config.model == "test-model"
