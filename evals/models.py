"""Data models for agent-evals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalCase:
    """A single eval case loaded from a YAML suite."""

    name: str
    input: str
    contains: List[str] = field(default_factory=list)
    regex: List[str] = field(default_factory=list)
    not_contains: List[str] = field(default_factory=list)
    judge_criteria: List[str] = field(default_factory=list)
    judge_threshold: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "input": self.input,
            "contains": self.contains,
            "regex": self.regex,
            "not_contains": self.not_contains,
            "judge_criteria": self.judge_criteria,
            "judge_threshold": self.judge_threshold,
        }


@dataclass
class CriterionScore:
    criterion: str
    score: float
    matched_keywords: List[str]
    missing_keywords: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion,
            "score": self.score,
            "matched_keywords": self.matched_keywords,
            "missing_keywords": self.missing_keywords,
        }


@dataclass
class JudgeResult:
    mode: str  # "fake" or "real"
    score: float
    threshold: float
    passed: bool
    criteria: List[CriterionScore]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "criteria": [c.to_dict() for c in self.criteria],
        }


@dataclass
class CaseResult:
    name: str
    input: str
    output: Optional[str]
    status: str  # "pass", "fail", or "error"
    checks_passed: List[str]
    checks_failed: List[Dict[str, str]]
    judge: Optional[JudgeResult]
    latency_ms: float
    attempts: int
    error: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "judge": self.judge.to_dict() if self.judge else None,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "error": self.error,
        }


@dataclass
class SuiteResult:
    suite_name: str
    agent_name: str
    timestamp: str
    judge_mode: str  # "fake", "real", or "off"
    cases: List[CaseResult]

    def summary(self) -> Dict[str, Any]:
        total = len(self.cases)
        passed = sum(1 for c in self.cases if c.status == "pass")
        failed = sum(1 for c in self.cases if c.status == "fail")
        errors = sum(1 for c in self.cases if c.status == "error")
        pass_rate = round(100.0 * passed / total, 1) if total else 0.0
        latencies = [c.latency_ms for c in self.cases]
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": pass_rate,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
            "judge_mode": self.judge_mode,
            "summary": self.summary(),
            "cases": [c.to_dict() for c in self.cases],
        }
