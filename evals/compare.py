"""Compare two results.json files: per-case score deltas and status transitions."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def load_results(path: Union[str, Path]) -> Dict[str, Any]:
    """Load a results.json file as a dict, tolerating unknown schemas."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load results file {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise ValueError(f"{path} does not look like a results.json (no 'cases' list)")
    return data


def _case_score(case: Dict[str, Any]) -> Optional[float]:
    """Score used for deltas: judge score when judged, else pass=1/fail=0.

    Returns None when the case errored or has no usable score.
    """
    judge = case.get("judge") or {}
    if isinstance(judge.get("score"), (int, float)):
        return float(judge["score"])
    status = case.get("status")
    if status == "pass":
        return 1.0
    if status == "fail":
        return 0.0
    return None


@dataclass
class CaseDelta:
    name: str
    status_a: Optional[str]
    status_b: Optional[str]
    score_a: Optional[float]
    score_b: Optional[float]
    delta: Optional[float]  # score_a - score_b
    classification: str  # improved, regressed, unchanged, newly_passing,
    # newly_failing, only_in_a, only_in_b


def _classify(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> str:
    if a is None:
        return "only_in_b"
    if b is None:
        return "only_in_a"
    sa, sb = a.get("status"), b.get("status")
    if sa == "pass" and sb != "pass":
        return "newly_passing"
    if sa != "pass" and sb == "pass":
        return "newly_failing"
    score_a, score_b = _case_score(a), _case_score(b)
    if score_a is None or score_b is None:
        return "unchanged"
    if score_a > score_b:
        return "improved"
    if score_a < score_b:
        return "regressed"
    return "unchanged"


@dataclass
class Comparison:
    """Result of comparing run A against run B (deltas are A minus B)."""

    name_a: str
    name_b: str
    deltas: List[CaseDelta] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {
            "total": len(self.deltas),
            "improved": 0,
            "regressed": 0,
            "unchanged": 0,
            "newly_passing": 0,
            "newly_failing": 0,
            "only_in_a": 0,
            "only_in_b": 0,
        }
        for d in self.deltas:
            counts[d.classification] += 1
        return counts

    def by_class(self, classification: str) -> List[CaseDelta]:
        return [d for d in self.deltas if d.classification == classification]

    def sorted_by_regression(self) -> List[CaseDelta]:
        """Deltas sorted by biggest regression first; unscored cases last."""
        return sorted(
            self.deltas,
            key=lambda d: (d.delta is None, d.delta if d.delta is not None else 0.0),
        )


def compare_results(
    a: Dict[str, Any],
    b: Dict[str, Any],
    name_a: str = "run-a",
    name_b: str = "run-b",
) -> Comparison:
    """Compare two loaded results dicts. Cases present in only one file are
    reported as only_in_a / only_in_b instead of raising."""
    cases_a = {c.get("name"): c for c in a.get("cases", [])}
    cases_b = {c.get("name"): c for c in b.get("cases", [])}
    names = sorted(set(cases_a) | set(cases_b))
    comparison = Comparison(name_a=name_a, name_b=name_b)
    for name in names:
        ca, cb = cases_a.get(name), cases_b.get(name)
        score_a = _case_score(ca) if ca else None
        score_b = _case_score(cb) if cb else None
        delta: Optional[float] = None
        if score_a is not None and score_b is not None:
            delta = round(score_a - score_b, 3)
        comparison.deltas.append(
            CaseDelta(
                name=name,
                status_a=ca.get("status") if ca else None,
                status_b=cb.get("status") if cb else None,
                score_a=score_a,
                score_b=score_b,
                delta=delta,
                classification=_classify(ca, cb),
            )
        )
    return comparison


def compare_files(
    path_a: Union[str, Path],
    path_b: Union[str, Path],
) -> Comparison:
    """Load two results files and compare them (deltas are A minus B)."""
    a = load_results(path_a)
    b = load_results(path_b)
    return compare_results(a, b, name_a=str(path_a), name_b=str(path_b))
