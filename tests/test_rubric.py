"""Tests for deterministic rubric checks."""
import pytest

from evals.models import EvalCase
from evals.rubric import evaluate_checks


def make_case(**kwargs):
    defaults = dict(name="c", input="in")
    defaults.update(kwargs)
    return EvalCase(**defaults)


def test_contains_pass():
    case = make_case(contains=["refund", "30 days"])
    passed, failed = evaluate_checks("You get a refund within 30 days.", case)
    assert not failed
    assert len(passed) == 2


def test_contains_fail():
    case = make_case(contains=["refund"])
    passed, failed = evaluate_checks("No soup for you.", case)
    assert not passed
    assert len(failed) == 1
    assert failed[0]["check"] == "contains:'refund'"
    assert "refund" in failed[0]["detail"]


def test_regex_pass():
    case = make_case(regex=[r"order \d{5}", r"(?i)shipped"])
    passed, failed = evaluate_checks("Your order 84721 has SHIPPED.", case)
    assert not failed
    assert len(passed) == 2


def test_regex_fail():
    case = make_case(regex=[r"order \d{5}"])
    passed, failed = evaluate_checks("Your order ABC has shipped.", case)
    assert not passed
    assert len(failed) == 1
    assert "did not match" in failed[0]["detail"]


def test_not_contains_pass():
    case = make_case(not_contains=["cannot", "impossible"])
    passed, failed = evaluate_checks("We can absolutely help.", case)
    assert not failed
    assert len(passed) == 2


def test_not_contains_fail():
    case = make_case(not_contains=["cannot"])
    passed, failed = evaluate_checks("We cannot help with that.", case)
    assert not passed
    assert len(failed) == 1
    assert "forbidden substring" in failed[0]["detail"]


def test_mixed_rubric_reports_each_check():
    case = make_case(
        contains=["refund"],
        regex=[r"\d+ days"],
        not_contains=["never"],
    )
    passed, failed = evaluate_checks("refund within 30 days, never a hassle.", case)
    assert len(passed) == 2  # contains + regex
    assert len(failed) == 1  # not_contains
    assert failed[0]["check"] == "not_contains:'never'"


def test_empty_rubric_passes_vacuously():
    case = make_case()
    passed, failed = evaluate_checks("anything", case)
    assert passed == [] and failed == []


def test_invalid_regex_rejected_at_load(tmp_path):
    from evals.loader import SuiteLoadError, load_suite

    suite = tmp_path / "bad.yaml"
    suite.write_text(
        "name: bad\ncases:\n"
        "  - name: c1\n    input: hi\n"
        "    rubric:\n      regex: ['([unclosed']\n"
    )
    with pytest.raises(SuiteLoadError, match="invalid regex"):
        load_suite(suite)
