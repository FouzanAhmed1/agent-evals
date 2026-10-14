"""Generate a self-contained report.html (inline CSS/JS, no CDN, no build step)."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Union

from .models import SuiteResult

_CSS = """
:root { --bg: #f7f7f5; --card: #ffffff; --ink: #1c1c1e; --muted: #6b7280;
        --green: #15803d; --green-bg: #dcfce7; --red: #b91c1c; --red-bg: #fee2e2;
        --amber: #b45309; --amber-bg: #fef3c7; --line: #e5e7eb; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: var(--bg); color: var(--ink); margin: 0; padding: 24px; }
.wrap { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 20px; font-size: 14px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
         gap: 12px; margin-bottom: 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 14px 16px; }
.card .label { font-size: 12px; color: var(--muted); text-transform: uppercase;
               letter-spacing: 0.05em; }
.card .value { font-size: 24px; font-weight: 700; margin-top: 4px; }
.filters { margin: 0 0 12px; }
.filters button { border: 1px solid var(--line); background: var(--card);
                  border-radius: 999px; padding: 6px 14px; margin-right: 8px;
                  cursor: pointer; font-size: 13px; }
.filters button.active { background: var(--ink); color: #fff; border-color: var(--ink); }
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line);
         font-size: 14px; vertical-align: top; }
th { background: #fafafa; font-size: 12px; text-transform: uppercase;
     letter-spacing: 0.05em; color: var(--muted); }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         font-size: 12px; font-weight: 700; }
.badge.pass { background: var(--green-bg); color: var(--green); }
.badge.fail { background: var(--red-bg); color: var(--red); }
.badge.error { background: var(--amber-bg); color: var(--amber); }
.badge.flaky { background: #ede9fe; color: #6d28d9; }
.section { margin: 24px 0 12px; font-size: 18px; }
.bars { display: flex; gap: 6px; align-items: flex-end; height: 110px;
        background: var(--card); border: 1px solid var(--line); border-radius: 10px;
        padding: 14px; }
.bar { flex: 1; background: #2563eb; border-radius: 4px 4px 0 0; min-width: 24px;
       position: relative; }
.bar.flaky-bar { background: #7c3aed; }
.bar.zero-bar { background: #b91c1c; }
.bar-label { font-size: 11px; color: var(--muted); margin-top: 6px; text-align: center; }
details { margin-top: 8px; }
summary { cursor: pointer; color: #2563eb; font-size: 13px; }
pre { background: #111827; color: #e5e7eb; padding: 12px; border-radius: 8px;
      overflow-x: auto; font-size: 12.5px; white-space: pre-wrap; }
.fail-list { margin: 6px 0; padding-left: 18px; font-size: 13px; }
.fail-list li { margin-bottom: 4px; }
.judge-box { font-size: 13px; margin-top: 8px; }
.judge-box .crit { margin-bottom: 6px; }
.kw { font-family: monospace; background: #f3f4f6; padding: 1px 5px; border-radius: 4px; }
.footer { color: var(--muted); font-size: 12px; margin-top: 16px; }
"""

_JS = """
function setFilter(f) {
  document.querySelectorAll('.filters button').forEach(function(b) {
    b.classList.toggle('active', b.dataset.filter === f);
  });
  document.querySelectorAll('tbody tr.case-row').forEach(function(row) {
    row.style.display = (f === 'all' || row.dataset.status === f) ? '' : 'none';
  });
}
"""

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval report: {suite_name}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<h1>Eval report: {suite_name}</h1>
<p class="sub">agent <b>{agent_name}</b> &middot; {timestamp} &middot; judge mode: {judge_mode}</p>
<div class="cards">
  <div class="card"><div class="label">Pass rate</div><div class="value">{pass_rate}%</div></div>
  <div class="card"><div class="label">Passed</div><div class="value">{passed}</div></div>
  <div class="card"><div class="label">Failed</div><div class="value">{failed}</div></div>
  <div class="card"><div class="label">Errors</div><div class="value">{errors}</div></div>
  <div class="card"><div class="label">Total cases</div><div class="value">{total}</div></div>
  <div class="card"><div class="label">Avg latency</div><div class="value">{avg_latency} ms</div></div>
  <div class="card"><div class="label">P95 latency</div><div class="value">{p95_latency} ms</div></div>
  <div class="card"><div class="label">Est. cost</div><div class="value">${total_cost}</div></div>
</div>
{latency_section}
{flaky_section}
<div class="filters">
  <button data-filter="all" class="active" onclick="setFilter('all')">All</button>
  <button data-filter="pass" onclick="setFilter('pass')">Passed</button>
  <button data-filter="fail" onclick="setFilter('fail')">Failed</button>
  <button data-filter="error" onclick="setFilter('error')">Errors</button>
  <button data-filter="flaky" onclick="setFilter('flaky')">Flaky</button>
</div>
<table>
<thead><tr><th>Case</th><th>Status</th><th>Checks</th><th>Judge</th><th>Latency</th><th>Details</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p class="footer">Generated by agent-evals. Deterministic checks always run; the judge only runs when criteria are configured.</p>
</div>
<script>{js}</script>
</body>
</html>
"""

_ROW = """<tr class="case-row" data-status="{status}">
<td><b>{name}</b></td>
<td><span class="badge {badge_class}">{badge_label}</span></td>
<td>{checks_summary}</td>
<td>{judge_summary}</td>
<td>{latency} ms</td>
<td>{details}</td>
</tr>"""


def _details_html(case) -> str:
    parts = []
    parts.append(f"<b>Input</b><pre>{html.escape(case.input)}</pre>")
    if case.output is not None:
        parts.append(f"<b>Output</b><pre>{html.escape(case.output)}</pre>")
    if case.error:
        parts.append(f"<b>Error</b><pre>{html.escape(case.error)}</pre>")
    if case.checks_failed:
        items = "".join(
            f"<li><span class='kw'>{html.escape(f['check'])}</span><br>{html.escape(f['detail'])}</li>"
            for f in case.checks_failed
        )
        parts.append(f"<b>Failed checks</b><ul class='fail-list'>{items}</ul>")
    if case.judge is not None:
        crits = "".join(
            "<div class='crit'><b>{:.1f}/10</b> (threshold {:.1f}) - {}<br>"
            "<span style='color:#6b7280'>matched:</span> {} <span style='color:#6b7280'>missing:</span> {}</div>".format(
                c.score,
                case.judge.threshold,
                html.escape(c.criterion),
                ", ".join(f"<span class='kw'>{html.escape(w)}</span>" for w in c.matched_keywords) or "-",
                ", ".join(f"<span class='kw'>{html.escape(w)}</span>" for w in c.missing_keywords) or "-",
            )
            for c in case.judge.criteria
        )
        parts.append(
            f"<div class='judge-box'><b>Judge ({html.escape(case.judge.mode)}): "
            f"{case.judge.score:.1f}/10</b>{crits}</div>"
        )
    if case.checks_passed:
        items = "".join(f"<li><span class='kw'>{html.escape(c)}</span></li>" for c in case.checks_passed)
        parts.append(f"<b>Passed checks</b><ul class='fail-list'>{items}</ul>")
    inner = "".join(parts)
    return f"<details><summary>show input / output / failures</summary>{inner}</details>"


def _latency_section(result) -> str:
    """Slowest-cases section for the report."""
    ranked = sorted(result.cases, key=lambda c: c.latency_ms, reverse=True)[:5]
    if not ranked or ranked[0].latency_ms == 0:
        return ""
    rows = "".join(
        f"<tr><td><b>{html.escape(c.name)}</b></td>"
        f"<td><span class='badge {c.status}'>{c.status}</span></td>"
        f"<td>{c.latency_ms} ms</td>"
        f"<td>{c.prompt_tokens + c.completion_tokens} tokens</td></tr>"
        for c in ranked
    )
    return (
        "<h2 class='section'>Slowest cases</h2>"
        "<table><thead><tr><th>Case</th><th>Status</th>"
        "<th>Latency</th><th>Judge tokens</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _flaky_section(result) -> str:
    """Flaky-cases section plus pass-rate distribution (shown when repeats ran)."""
    repeated = any(c.repeat_runs > 1 for c in result.cases)
    if not repeated:
        return ""
    flaky = [c for c in result.cases if c.flaky]
    always = [c for c in result.cases if c.pass_rate == 1.0]
    never = [c for c in result.cases if c.pass_rate == 0.0]

    def bar(bucket, label):
        n = len(bucket)
        total = max(1, len(result.cases))
        height = max(4, int(80 * n / total))
        cls = "flaky-bar" if label == "flaky" else ("zero-bar" if label == "0%" else "")
        title = f"{label}: {n} case(s)"
        return (
            f"<div style='flex:1'><div class='bar {cls}' style='height:{height}px' "
            f"title='{html.escape(title)}'></div>"
            f"<div class='bar-label'>{html.escape(label)}<br><b>{n}</b></div></div>"
        )

    bars = "".join(
        [bar(always, "100%"), bar(flaky, "flaky"), bar(never, "0%")]
    )
    flaky_rows = "".join(
        f"<tr><td><b>{html.escape(c.name)}</b></td>"
        f"<td><span class='badge flaky'>FLAKY</span></td>"
        f"<td>{c.pass_rate * 100:.0f}% of {c.repeat_runs} repeats</td></tr>"
        for c in flaky
    )
    flaky_table = (
        "<table><thead><tr><th>Case</th><th>Flag</th><th>Pass rate</th></tr></thead>"
        f"<tbody>{flaky_rows}</tbody></table>"
        if flaky
        else "<p class='sub'>No flaky cases: every case passed or failed all of its repeats.</p>"
    )
    return (
        f"<h2 class='section'>Flakiness ({len(flaky)} flaky)</h2>"
        f"<div class='bars'>{bars}</div>"
        f"{flaky_table}"
    )


def _row_status(case) -> str:
    """Status used for filtering and badge: flaky cases get their own class."""
    return "flaky" if case.flaky else case.status


def generate_report(result: SuiteResult, path: Union[str, Path]) -> Path:
    """Render a SuiteResult as a single self-contained HTML file."""
    summary = result.summary()
    rows = []
    for case in result.cases:
        n_passed = len(case.checks_passed)
        n_failed = len(case.checks_failed)
        checks_summary = f"{n_passed} passed, {n_failed} failed"
        if case.judge is not None:
            mark = "pass" if case.judge.passed else "fail"
            judge_summary = f"<span class='badge {mark}'>{case.judge.score:.1f}/10</span>"
        else:
            judge_summary = "<span style='color:#6b7280'>n/a</span>"
        row_status = _row_status(case)
        badge_label = "FLAKY" if case.flaky else case.status
        rows.append(
            _ROW.format(
                status=html.escape(row_status),
                badge_class=html.escape(row_status),
                badge_label=html.escape(badge_label),
                name=html.escape(case.name),
                checks_summary=checks_summary,
                judge_summary=judge_summary,
                latency=case.latency_ms,
                details=_details_html(case),
            )
        )

    page = _HTML.format(
        css=_CSS,
        js=_JS,
        suite_name=html.escape(result.suite_name),
        agent_name=html.escape(result.agent_name),
        timestamp=html.escape(result.timestamp),
        judge_mode=html.escape(result.judge_mode),
        pass_rate=summary["pass_rate"],
        passed=summary["passed"],
        failed=summary["failed"],
        errors=summary["errors"],
        total=summary["total"],
        avg_latency=summary["avg_latency_ms"],
        p95_latency=summary["p95_latency_ms"],
        total_cost=f"{summary['total_cost_usd']:.4f}",
        latency_section=_latency_section(result),
        flaky_section=_flaky_section(result),
        rows="\n".join(rows),
    )
    path = Path(path)
    path.write_text(page, encoding="utf-8")
    return path


_COMPARE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval comparison: {name_a} vs {name_b}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<h1>Eval comparison</h1>
<p class="sub"><b>{name_a}</b> vs <b>{name_b}</b> &middot; deltas are A minus B</p>
<h2 class="section">Comparison summary</h2>
<div class="cards">
  <div class="card"><div class="label">Improved</div><div class="value">{improved}</div></div>
  <div class="card"><div class="label">Regressed</div><div class="value">{regressed}</div></div>
  <div class="card"><div class="label">Unchanged</div><div class="value">{unchanged}</div></div>
  <div class="card"><div class="label">Newly passing</div><div class="value">{newly_passing}</div></div>
  <div class="card"><div class="label">Newly failing</div><div class="value">{newly_failing}</div></div>
  <div class="card"><div class="label">Only in one run</div><div class="value">{only_one}</div></div>
</div>
<h2 class="section">Score deltas (biggest regression first)</h2>
<table>
<thead><tr><th>Case</th><th>Score A</th><th>Score B</th><th>Delta</th><th>Status</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p class="footer">Generated by agent-evals compare. Cases present in only one run have no delta.</p>
</div>
</body>
</html>
"""


def _fmt_score(value) -> str:
    return f"{value:.1f}" if value is not None else "n/a"


def generate_compare_report(comparison, path: Union[str, Path]) -> Path:
    """Render a Comparison as a self-contained HTML page.

    The delta table is sorted by biggest regression first; cases present in
    only one run are listed at the end with no delta.
    """
    s = comparison.summary
    rows = []
    for d in comparison.sorted_by_regression():
        if d.delta is None:
            delta_cell = "<span style='color:#6b7280'>n/a</span>"
        elif d.delta < 0:
            delta_cell = f"<span style='color:#b91c1c;font-weight:700'>{d.delta:+.1f}</span>"
        elif d.delta > 0:
            delta_cell = f"<span style='color:#15803d;font-weight:700'>{d.delta:+.1f}</span>"
        else:
            delta_cell = "0.0"
        cls = {
            "improved": "pass",
            "newly_passing": "pass",
            "regressed": "fail",
            "newly_failing": "fail",
            "only_in_a": "error",
            "only_in_b": "error",
        }.get(d.classification, "error")
        rows.append(
            "<tr><td><b>{name}</b></td><td>{sa}</td><td>{sb}</td>"
            "<td>{delta}</td><td><span class='badge {cls}'>{label}</span></td></tr>".format(
                name=html.escape(d.name),
                sa=_fmt_score(d.score_a),
                sb=_fmt_score(d.score_b),
                delta=delta_cell,
                cls=cls,
                label=html.escape(d.classification.replace("_", " ")),
            )
        )
    page = _COMPARE_HTML.format(
        css=_CSS,
        name_a=html.escape(comparison.name_a),
        name_b=html.escape(comparison.name_b),
        improved=s["improved"],
        regressed=s["regressed"],
        unchanged=s["unchanged"],
        newly_passing=s["newly_passing"],
        newly_failing=s["newly_failing"],
        only_one=s["only_in_a"] + s["only_in_b"],
        rows="\n".join(rows),
    )
    path = Path(path)
    path.write_text(page, encoding="utf-8")
    return path
