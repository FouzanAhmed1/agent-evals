"""Load eval suites from YAML files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Union

import yaml

from .models import EvalCase


class SuiteLoadError(ValueError):
    """Raised when a suite file is missing or malformed."""


def load_suite(path: Union[str, Path]) -> tuple[str, List[EvalCase]]:
    """Load a suite YAML file.

    Returns (suite_name, cases). Raises SuiteLoadError on any problem so the
    CLI can fail fast with a clear message instead of halfway through a run.
    """
    path = Path(path)
    if not path.is_file():
        raise SuiteLoadError(f"suite file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SuiteLoadError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SuiteLoadError(f"suite {path} must be a mapping at the top level")

    suite_name = data.get("name", path.stem)
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SuiteLoadError(f"suite {path} needs a non-empty 'cases' list")

    cases: List[EvalCase] = []
    seen_names = set()
    for i, raw in enumerate(raw_cases):
        case = _parse_case(raw, i, path)
        if case.name in seen_names:
            raise SuiteLoadError(f"suite {path}: duplicate case name '{case.name}'")
        seen_names.add(case.name)
        cases.append(case)
    return suite_name, cases


def _parse_case(raw: object, index: int, path: Path) -> EvalCase:
    where = f"suite {path}, case #{index}"
    if not isinstance(raw, dict):
        raise SuiteLoadError(f"{where} must be a mapping")

    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise SuiteLoadError(f"{where} needs a string 'name'")
    prompt = raw.get("input")
    if not isinstance(prompt, str):
        raise SuiteLoadError(f"{where} ('{name}') needs a string 'input'")

    rubric = raw.get("rubric") or {}
    if not isinstance(rubric, dict):
        raise SuiteLoadError(f"{where} ('{name}'): 'rubric' must be a mapping")

    contains = _str_list(rubric.get("contains"), f"{where} ('{name}'): 'contains'")
    regex = _str_list(rubric.get("regex"), f"{where} ('{name}'): 'regex'")
    not_contains = _str_list(rubric.get("not_contains"), f"{where} ('{name}'): 'not_contains'")

    for pattern in regex:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise SuiteLoadError(
                f"{where} ('{name}'): invalid regex {pattern!r}: {exc}"
            ) from exc

    judge = raw.get("judge") or {}
    if not isinstance(judge, dict):
        raise SuiteLoadError(f"{where} ('{name}'): 'judge' must be a mapping")
    criteria = _str_list(judge.get("criteria"), f"{where} ('{name}'): 'judge.criteria'")
    threshold = judge.get("threshold")
    if threshold is not None:
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise SuiteLoadError(
                f"{where} ('{name}'): 'judge.threshold' must be a number"
            )
        threshold = float(threshold)

    return EvalCase(
        name=name,
        input=prompt,
        contains=contains,
        regex=regex,
        not_contains=not_contains,
        judge_criteria=criteria,
        judge_threshold=threshold,
    )


def _str_list(value: object, where: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise SuiteLoadError(f"{where} must be a list of strings")
    return list(value)
