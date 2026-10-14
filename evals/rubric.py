"""Deterministic rubric checks: contains, regex, not_contains."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .models import EvalCase


def evaluate_checks(output: str, case: EvalCase) -> Tuple[List[str], List[Dict[str, str]]]:
    """Run every deterministic check in the case rubric against the output.

    Returns (passed, failed) where passed is a list of check labels and failed
    is a list of {"check": label, "detail": explanation} dicts.
    """
    passed: List[str] = []
    failed: List[Dict[str, str]] = []

    for needle in case.contains:
        label = f"contains:{needle!r}"
        if needle in output:
            passed.append(label)
        else:
            failed.append({"check": label, "detail": f"expected substring not found: {needle!r}"})

    for pattern in case.regex:
        label = f"regex:{pattern!r}"
        if re.search(pattern, output):
            passed.append(label)
        else:
            failed.append({"check": label, "detail": f"pattern did not match any part of the output: {pattern!r}"})

    for needle in case.not_contains:
        label = f"not_contains:{needle!r}"
        if needle not in output:
            passed.append(label)
        else:
            failed.append({"check": label, "detail": f"forbidden substring was present: {needle!r}"})

    return passed, failed
