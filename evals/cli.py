"""Command line interface for agent-evals."""
from __future__ import annotations

import argparse
import importlib
import sys

from .judge import resolve_judge_config
from .loader import SuiteLoadError, load_suite
from .report import generate_report
from .runner import DEFAULT_JUDGE_THRESHOLD, run_suite, write_results


def load_agent(spec: str):
    """Import an agent callable from a 'module:attribute' spec."""
    if ":" not in spec:
        raise ValueError(
            f"agent spec {spec!r} must look like 'module:attribute', e.g. 'demos:support_agent'"
        )
    module_path, _, attr = spec.rpartition(":")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ValueError(f"could not import module {module_path!r}: {exc}") from exc
    try:
        agent = getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(f"module {module_path!r} has no attribute {attr!r}") from exc
    if not callable(agent):
        raise ValueError(f"{spec!r} is not callable")
    return agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Run an agent over a YAML eval suite and score it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a suite against an agent")
    run.add_argument("--suite", required=True, help="path to the suite YAML file")
    run.add_argument("--agent", required=True, help="agent callable as 'module:attribute'")
    run.add_argument("--results", default="results.json", help="where to write results.json (default: results.json)")
    run.add_argument("--report", default=None, help="also write a self-contained HTML report to this path")
    run.add_argument("--workers", type=int, default=4, help="thread pool size (default: 4)")
    run.add_argument("--retries", type=int, default=2, help="retries per case on exception (default: 2)")
    run.add_argument("--fake-judge", action="store_true", help="score judge criteria with the offline deterministic fake judge")
    run.add_argument("--no-judge", action="store_true", help="skip judge scoring even when criteria are configured")
    run.add_argument("--judge-threshold", type=float, default=DEFAULT_JUDGE_THRESHOLD,
                     help=f"default judge pass threshold when a case does not set one (default: {DEFAULT_JUDGE_THRESHOLD})")
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    try:
        agent = load_agent(args.agent)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        suite_name, cases = load_suite(args.suite)
    except SuiteLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.no_judge:
        judge_config = None
    else:
        judge_config = resolve_judge_config(fake=args.fake_judge)
        if judge_config is None and any(c.judge_criteria for c in cases):
            print(
                "warning: cases have judge criteria but no judge is configured "
                "(set EVAL_LLM_API_KEY or use --fake-judge); scoring checks only.",
                file=sys.stderr,
            )

    result = run_suite(
        cases,
        agent,
        suite_name=suite_name,
        agent_name=args.agent,
        workers=args.workers,
        retries=args.retries,
        judge_config=judge_config,
        judge_threshold=args.judge_threshold,
    )

    write_results(result, args.results)
    if args.report:
        generate_report(result, args.report)

    s = result.summary()
    print(f"suite: {suite_name}  agent: {args.agent}")
    print(f"cases: {s['total']}  passed: {s['passed']}  failed: {s['failed']}  errors: {s['errors']}")
    print(f"pass rate: {s['pass_rate']}%  avg latency: {s['avg_latency_ms']} ms")
    print(f"results: {args.results}" + (f"  report: {args.report}" if args.report else ""))
    return 0 if s["failed"] == 0 and s["errors"] == 0 else 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
