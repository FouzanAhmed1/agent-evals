"""LLM-as-judge scoring.

Two modes:

* fake (offline, deterministic): scores each criterion with a keyword-coverage
  heuristic. Same input always yields the same score, no network needed. This
  is what tests and demos use.
* real: calls an OpenAI-compatible chat completions endpoint configured via
  EVAL_LLM_API_KEY / EVAL_LLM_BASE_URL / EVAL_LLM_MODEL.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests

from .models import CriterionScore, JudgeResult


class JudgeError(RuntimeError):
    """Raised when the judge cannot produce a score."""


@dataclass
class JudgeConfig:
    mode: str  # "fake" or "real"
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


def resolve_judge_config(fake: bool = False) -> Optional[JudgeConfig]:
    """Decide which judge to use.

    Returns None when judging is unavailable (no API key and no fake mode),
    in which case the runner scores cases on deterministic checks only.
    """
    if fake or os.environ.get("EVAL_FAKE_JUDGE") == "1":
        return JudgeConfig(mode="fake")
    api_key = os.environ.get("EVAL_LLM_API_KEY")
    if not api_key:
        return None
    return JudgeConfig(
        mode="real",
        api_key=api_key,
        base_url=os.environ.get("EVAL_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model=os.environ.get("EVAL_LLM_MODEL", "gpt-4o-mini"),
    )


def score_with_judge(
    output: str,
    criteria: List[str],
    config: JudgeConfig,
    threshold: float,
) -> JudgeResult:
    if config.mode == "fake":
        return fake_judge_score(output, criteria, threshold)
    if config.mode == "real":
        return real_judge_score(output, criteria, config, threshold)
    raise JudgeError(f"unknown judge mode: {config.mode!r}")


# ---------------------------------------------------------------------------
# Fake judge: deterministic keyword-coverage heuristic.
# ---------------------------------------------------------------------------

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "that", "this", "from", "are",
    "is", "was", "were", "be", "been", "being", "to", "of", "in", "on", "at",
    "by", "as", "it", "its", "they", "them", "their", "you", "your", "we",
    "our", "us", "can", "will", "should", "would", "do", "does", "did", "not",
    "no", "so", "if", "then", "than", "too", "very", "just", "about", "into",
    "over", "after", "before", "when", "where", "which", "who", "what", "how",
    "why", "all", "any", "each", "other", "such", "only", "own", "same", "may",
    "might", "must", "shall", "also", "s", "t",
}


def _stem(word: str) -> str:
    """Tiny deterministic stemmer so 'offers' matches 'offer', etc."""
    for suffix in ("fulness", "fully", "ness", "ment", "tion", "ing", "ies", "ied", "ed", "ly", "ful", "es", "s"):
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            if suffix in ("ies", "ied"):
                return word[: -len(suffix)] + "y"
            return word[: -len(suffix)]
    return word


def _significant_words(text: str) -> List[Tuple[str, str]]:
    """Return (original, stem) for each meaningful word in the text."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    seen = set()
    result = []
    for word in words:
        stem = _stem(word)
        if len(stem) <= 2 or stem in STOPWORDS:
            continue
        if stem not in seen:
            seen.add(stem)
            result.append((word, stem))
    return result


def fake_judge_score(output: str, criteria: List[str], threshold: float) -> JudgeResult:
    output_stems = {stem for _, stem in _significant_words(output)}
    scored: List[CriterionScore] = []
    for criterion in criteria:
        words = _significant_words(criterion)
        if not words:
            scored.append(CriterionScore(criterion, 10.0, [], []))
            continue
        matched = [w for w, stem in words if stem in output_stems]
        missing = [w for w, stem in words if stem not in output_stems]
        score = round(10.0 * len(matched) / len(words), 1)
        scored.append(CriterionScore(criterion, score, matched, missing))
    overall = round(sum(c.score for c in scored) / len(scored), 1) if scored else 10.0
    return JudgeResult(
        mode="fake",
        score=overall,
        threshold=threshold,
        passed=overall >= threshold,
        criteria=scored,
    )


# ---------------------------------------------------------------------------
# Real judge: OpenAI-compatible chat completions endpoint.
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict eval judge. Score an agent's response against each "
    "criterion on a 0-10 scale (10 = fully satisfied, 0 = not satisfied at all). "
    "Respond with JSON only, exactly in this shape: "
    '{"scores": [{"criterion_index": 0, "score": 8.5}, ...]}. '
    "No prose, no markdown fences."
)


def real_judge_score(
    output: str,
    criteria: List[str],
    config: JudgeConfig,
    threshold: float,
) -> JudgeResult:
    if not config.api_key:
        raise JudgeError("EVAL_LLM_API_KEY is not set")

    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(criteria))
    user_prompt = (
        f"Criteria:\n{numbered}\n\nAgent response:\n{output}\n\n"
        "Score each criterion 0-10. JSON only."
    )
    try:
        resp = requests.post(
            f"{config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.model,
                "messages": [
                    {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise JudgeError(f"judge API request failed: {exc}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(_strip_code_fences(content))
        raw_scores = {int(s["criterion_index"]): float(s["score"]) for s in data["scores"]}
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise JudgeError(f"could not parse judge response: {exc}") from exc

    scored = []
    for i, criterion in enumerate(criteria):
        if i not in raw_scores:
            raise JudgeError(f"judge response missing score for criterion {i}")
        score = max(0.0, min(10.0, round(raw_scores[i], 1)))
        scored.append(CriterionScore(criterion, score, [], []))
    overall = round(sum(c.score for c in scored) / len(scored), 1) if scored else 10.0
    return JudgeResult(
        mode="real",
        score=overall,
        threshold=threshold,
        passed=overall >= threshold,
        criteria=scored,
    )


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()
