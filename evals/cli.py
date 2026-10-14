"""Command line interface for agent-evals."""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from .compare import compare_files
from .judge import resolve_judge_config
from .loader import SuiteLoadError, load_suite
from .markdown import markdown_for_compare, markdown_for_run, write_markdown
from .report import generate_compare_report, generate_report
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
    run.add_argument("--repeat", type=int, default=1,
                     help="run each case this many times to detect flakiness (default: 1)")
    run.add_argument("--format", default="html", choices=["html", "md"],
                     help="with --report, also write a Markdown summary: writes the .md next to the report, or use --output to choose the path")
    run.add_argument("--output", default=None,
                     help="path for the Markdown summary when --format md is used")

    cmp = sub.add_parser("compare", help="compare two results.json files from prior runs")
    cmp.add_argument("run_a", help="first results.json (deltas are A minus B)")
    cmp.add_argument("run_b", help="second results.json")
    cmp.add_argument("--report", default=None, help="write a self-contained HTML comparison report here")
    cmp.add_argument("--format", default="html", choices=["html", "md"],
                     help="with --report, also write a Markdown comparison summary: writes the .md next to the report, or use --output to choose the path")
    cmp.add_argument("--output", default=None,
                     help="path for the Markdown summary when --format md is used")
    return parser


def _markdown_path(report: str | None, output: str | None, fallback: str) -> str:
    """Resolve where the Markdown summary goes: --output wins, else the .md
    sibling of --report, else a fallback derived from the results file."""
    if output:
        return output
    if report:
        return str(Path(report).with_suffix(".md"))
    return fallback


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
        repeat=args.repeat,
    )

    write_results(result, args.results)
    if args.report:
        generate_report(result, args.report)
    md_text = None
    if args.format == "md":
        md_path = _markdown_path(args.report, args.output, str(Path(args.results).with_suffix(".md")))
        md_text = markdown_for_run(result)
        write_markdown(md_text, md_path)
        print(f"markdown: {md_path}")

    s = result.summary()
    print(f"suite: {suite_name}  agent: {args.agent}")
    print(f"cases: {s['total']}  passed: {s['passed']}  failed: {s['failed']}  errors: {s['errors']}")
    if s["flaky"]:
        print(f"flaky: {s['flaky']}")
    print(f"pass rate: {s['pass_rate']}%  avg latency: {s['avg_latency_ms']} ms  p95: {s['p95_latency_ms']} ms")
    print(f"est. cost: ${s['total_cost_usd']:.4f}  tokens: {s['total_tokens']}")
    print(f"results: {args.results}" + (f"  report: {args.report}" if args.report else ""))
    return 0 if s["failed"] == 0 and s["errors"] == 0 else 1


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        comparison = compare_files(args.run_a, args.run_b)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    s = comparison.summary
    print(f"compare: {args.run_a} vs {args.run_b} (deltas are A minus B)")
    print(f"improved: {s['improved']}  regressed: {s['regressed']}  unchanged: {s['unchanged']}")
    print(f"newly passing: {s['newly_passing']}  newly failing: {s['newly_failing']}  "
          f"only in one run: {s['only_in_a'] + s['only_in_b']}")

    for d in comparison.sorted_by_regression():
        if d.delta is None:
            print(f"  {d.name}: n/a ({d.classification.replace('_', ' ')})")
        else:
            print(f"  {d.name}: {d.delta:+.1f} ({d.classification.replace('_', ' ')})")

    if args.report:
        generate_compare_report(comparison, args.report)
        print(f"report: {args.report}")
    if args.format == "md":
        md_path = _markdown_path(args.report, args.output, "compare.md")
        write_markdown(markdown_for_compare(comparison), md_path)
        print(f"markdown: {md_path}")
    return 0 if s["newly_failing"] == 0 else 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "compare":
        return cmd_compare(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
