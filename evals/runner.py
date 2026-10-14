"""Suite runner: concurrent execution, retries, scoring, results.json."""
from __future__ import annotations

import concurrent.futures
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Union

from .judge import JudgeConfig, JudgeError, score_with_judge
from .models import CaseResult, EvalCase, SuiteResult
from .rubric import evaluate_checks

AgentFn = Callable[[str], str]

DEFAULT_JUDGE_THRESHOLD = 6.0


def run_case(
    case: EvalCase,
    agent: AgentFn,
    *,
    retries: int = 2,
    judge_config: Optional[JudgeConfig] = None,
    judge_threshold: float = DEFAULT_JUDGE_THRESHOLD,
) -> CaseResult:
    """Run one case: call the agent (with retries), then score it."""
    output: Optional[str] = None
    attempts = 0
    latency_ms = 0.0
    last_error: Optional[Exception] = None

    for _ in range(max(0, retries) + 1):
        attempts += 1
        start = time.perf_counter()
        try:
            output = agent(case.input)
        except Exception as exc:  # noqa: BLE001 - agent errors are recorded, not raised
            latency_ms += (time.perf_counter() - start) * 1000.0
            last_error = exc
            continue
        latency_ms += (time.perf_counter() - start) * 1000.0
        last_error = None
        break

    latency_ms = round(latency_ms, 1)

    if last_error is not None:
        return CaseResult(
            name=case.name,
            input=case.input,
            output=None,
            status="error",
            checks_passed=[],
            checks_failed=[],
            judge=None,
            latency_ms=latency_ms,
            attempts=attempts,
            error=f"{type(last_error).__name__}: {last_error}",
        )

    if not isinstance(output, str):
        return CaseResult(
            name=case.name,
            input=case.input,
            output=None,
            status="error",
            checks_passed=[],
            checks_failed=[],
            judge=None,
            latency_ms=latency_ms,
            attempts=attempts,
            error=f"agent returned {type(output).__name__}, expected str",
        )

    checks_passed, checks_failed = evaluate_checks(output, case)

    judge_result = None
    if case.judge_criteria and judge_config is not None:
        threshold = case.judge_threshold if case.judge_threshold is not None else judge_threshold
        try:
            judge_result = score_with_judge(output, case.judge_criteria, judge_config, threshold)
        except JudgeError as exc:
            return CaseResult(
                name=case.name,
                input=case.input,
                output=output,
                status="error",
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                judge=None,
                latency_ms=latency_ms,
                attempts=attempts,
                error=f"judge failed: {exc}",
            )

    status = "pass"
    if checks_failed or (judge_result is not None and not judge_result.passed):
        status = "fail"

    return CaseResult(
        name=case.name,
        input=case.input,
        output=output,
        status=status,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        judge=judge_result,
        latency_ms=latency_ms,
        attempts=attempts,
        error=None,
    )


def run_suite(
    cases: List[EvalCase],
    agent: AgentFn,
    *,
    suite_name: str = "suite",
    agent_name: str = "agent",
    workers: int = 4,
    retries: int = 2,
    judge_config: Optional[JudgeConfig] = None,
    judge_threshold: float = DEFAULT_JUDGE_THRESHOLD,
) -> SuiteResult:
    """Run all cases concurrently with a thread pool, preserving case order."""
    ordered: List[Optional[CaseResult]] = [None] * len(cases)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_to_index = {
            pool.submit(
                run_case,
                case,
                agent,
                retries=retries,
                judge_config=judge_config,
                judge_threshold=judge_threshold,
            ): i
            for i, case in enumerate(cases)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            ordered[future_to_index[future]] = future.result()

    return SuiteResult(
        suite_name=suite_name,
        agent_name=agent_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        judge_mode=judge_config.mode if judge_config else "off",
        cases=[r for r in ordered if r is not None],
    )


def write_results(result: SuiteResult, path: Union[str, Path]) -> Path:
    """Write the suite result to results.json."""
    path = Path(path)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
