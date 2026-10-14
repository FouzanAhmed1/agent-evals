# agent-evals

A lightweight eval harness for LLM agents. You define test cases in YAML, hand it any Python callable shaped like `agent(input: str) -> str`, and it runs every case concurrently, scores each response against deterministic checks plus optional LLM-as-judge criteria, then writes `results.json` and a self-contained `report.html` you can open in any browser.

No frameworks, no build step, no database. Three pip packages total.

## How it works

```
suites/*.yaml  -->  loader  -->  runner  -->  results.json
                        |            |
                     rubric       judge (real or fake)
                     checks          |
                        v            v
                   report.html (inline CSS/JS, works offline)
```

- **loader** (`evals/loader.py`): parses a suite YAML file, validates every field up front (including compiling your regexes), and fails fast with a clear message instead of dying mid-run.
- **rubric** (`evals/rubric.py`): deterministic checks that always run. `contains` and `not_contains` are plain substring checks; `regex` uses `re.search`.
- **judge** (`evals/judge.py`): scores free-text criteria. Two modes:
  - `fake`: a deterministic keyword-coverage heuristic. Same input always gives the same score, zero network. Use this for tests, demos, and CI.
  - `real`: calls any OpenAI-compatible chat completions endpoint, configured through env vars.
- **runner** (`evals/runner.py`): executes cases with a `ThreadPoolExecutor` (configurable workers), retries each case on exception (default 2 retries), records latency, then combines check results and the judge score into a pass/fail per case. `--repeat N` runs each case N times to catch flakiness.
- **report** (`evals/report.py`): renders one HTML file with inline CSS and JS. No CDN, no build, no external requests. Shows the pass-rate summary, cost and latency cards (mean/p50/p95, slowest cases), a per-case table with flaky badges, and expandable details with input, output, and exactly which checks failed. Also renders comparison reports from `evals compare`.
- **compare** (`evals/compare.py`): diffs two `results.json` files into per-case score deltas (A minus B) with improved/regressed/unchanged/newly-passing/newly-failing classifications.
- **markdown** (`evals/markdown.py`): PR-comment-ready Markdown summaries for runs and comparisons (`--format md`).

## Setup on a fresh machine

```bash
git clone <this repo>
cd agent-evals
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` only if you want the real judge. For everything below, the fake judge is enough and needs no keys.

Run the tests:

```bash
pytest
```

## Usage

The agent is anything you can import as `module:callable`:

```bash
# customer-support suite, offline fake judge, HTML report
python -m evals run \
  --suite suites/support.yaml \
  --agent demos:support_agent \
  --fake-judge \
  --report report.html

# lead-triage suite
python -m evals run \
  --suite suites/lead_triage.yaml \
  --agent demos:lead_triage_agent \
  --fake-judge \
  --results lead_results.json \
  --report lead_report.html
```

Useful flags:

| Flag | Default | What it does |
| --- | --- | --- |
| `--suite` | (required) | Path to the suite YAML |
| `--agent` | (required) | Agent callable as `module:attribute` |
| `--results` | `results.json` | Where to write the JSON results |
| `--report` | none | Also write a self-contained HTML report here |
| `--workers` | 4 | Thread pool size |
| `--retries` | 2 | Retries per case when the agent raises |
| `--fake-judge` | off | Use the offline deterministic judge |
| `--no-judge` | off | Skip judge scoring entirely |
| `--judge-threshold` | 6.0 | Default pass threshold when a case does not set its own |
| `--repeat` | 1 | Run each case this many times to catch flakiness (see below) |
| `--format` | `html` | `md` also writes a PR-comment-ready Markdown summary |
| `--output` | none | Where to write the Markdown summary (`--format md`); defaults to the `.md` next to `--report` |

The command exits 0 when every case passes, 1 otherwise, so it works in CI as-is.

## Comparing runs

Saved `results.json` files are comparable. Point the `compare` command at two of them (deltas are A minus B) and you get a per-case score delta table, sorted by biggest regression, plus counts of improved, regressed, unchanged, newly passing, and newly failing cases. Cases that only exist in one file are listed instead of dropped.

```bash
python -m evals compare run-a.json run-b.json --report compare.html
```

The compare command exits 1 when anything is newly failing, so it also works as a CI gate. Add `--format md` (with optional `--output compare.md`) and you get a Markdown version for a PR comment, with top regressions, top improvements, and the newly failing/passing lists.

## Cost and latency tracking

Every run already measured wall-clock latency per case; now it is reported properly and token usage is tracked alongside:

- **Latency**: per-case `latency_ms` in `results.json`; the summary and report show mean, p50, and p95, plus a slowest-cases table.
- **Tokens and cost**: when the judge runs, the runner records `prompt_tokens`, `completion_tokens`, and an estimated `cost_usd` per case, with totals in the summary. The real judge reads actual usage from the API response and prices it from a small built-in price table (rough estimates, not billing). The fake judge reports deterministic simulated counts, so cost tracking works offline and stays stable in tests.

The report shows a P95 latency card and an estimated-cost card next to the pass-rate cards, and the run summary prints totals to the console.

## Flakiness detection

Some agents are nondeterministic. `--repeat N` runs every case N times (sequentially, so repeats are ordered deterministically) and records the pass rate across repeats:

```bash
python -m evals run --suite suites/support.yaml --agent demos:support_agent \
  --fake-judge --repeat 5 --report report.html
```

A case whose pass rate is strictly between 0 and 1 is flagged **FLAKY**: it gets a distinct badge in the report table, its own section with a pass-rate distribution, and it counts against the run (the run fails unless every repeat passes). With the default `--repeat 1` nothing changes: no pass rates, no flaky section, same behavior as before.

## Markdown export

Both commands accept `--format md`, which writes a PR-comment-ready Markdown summary: the overall pass rate, total estimated cost, latency stats, the failing and flaky case lists with one-line reasons (and, for compare, the top regressions and improvements). `--report` still writes HTML; the Markdown goes to the `.md` next to it unless you pass `--output` to choose the path.

```bash
python -m evals run --suite suites/support.yaml --agent demos:support_agent \
  --fake-judge --report report.html --format md        # writes report.md too

python -m evals compare run-a.json run-b.json --format md --output pr-comment.md
```

With your own agent:

```python
# my_agent.py
def my_agent(user_input: str) -> str:
    ...  # call your LLM, RAG pipeline, whatever
    return response_text
```

```bash
python -m evals run --suite suites/support.yaml --agent my_agent:my_agent --fake-judge
```

## Suite YAML schema

```yaml
name: my-suite
cases:
  - name: refund_policy            # unique within the suite
    input: "How do I get a refund?"  # the string passed to agent(input)

    rubric:                        # all optional, all must pass
      contains: ["refund", "30 days"]     # substrings that must appear
      regex: ['order \d+']                # patterns that must match (re.search)
      not_contains: ["cannot help"]      # substrings that must NOT appear

    judge:                         # optional; skipped if no judge configured
      criteria:                    # free-text, scored 0-10 each, averaged
        - "The response offers a refund within the 30-day policy and stays polite."
      threshold: 4.0               # per-case pass threshold (default: --judge-threshold)
```

A case passes when every deterministic check passes **and** the judge score meets the threshold (when judging is on). If the agent raises on every retry, or returns something that is not a string, the case is marked `error` instead of `fail`.

## results.json schema

```json
{
  "suite_name": "customer-support",
  "agent_name": "demos:support_agent",
  "timestamp": "2026-10-14T04:00:00+00:00",
  "judge_mode": "fake",
  "summary": {
    "total": 5, "passed": 5, "failed": 0, "errors": 0, "flaky": 0,
    "pass_rate": 100.0, "avg_latency_ms": 0.1,
    "mean_latency_ms": 0.1, "p50_latency_ms": 0.1, "p95_latency_ms": 0.2,
    "total_tokens": 614, "total_cost_usd": 0.0001
  },
  "cases": [
    {
      "name": "refund_policy",
      "input": "...",
      "output": "...",
      "status": "pass",
      "checks_passed": ["contains:'refund'"],
      "checks_failed": [],
      "judge": {
        "mode": "fake", "score": 6.7, "threshold": 4.0, "passed": true,
        "prompt_tokens": 120, "completion_tokens": 12, "cost_usd": 0.00002,
        "criteria": [
          {"criterion": "...", "score": 6.7,
           "matched_keywords": ["refund"], "missing_keywords": ["polite"]}
        ]
      },
      "latency_ms": 0.2,
      "attempts": 1,
      "error": null,
      "prompt_tokens": 120, "completion_tokens": 12, "cost_usd": 0.00002,
      "repeat_runs": 1, "pass_rate": null, "flaky": false
    }
  ]
}
```

## Config and environment reference

| Variable | Needed for | Default |
| --- | --- | --- |
| `EVAL_FAKE_JUDGE=1` | fake judge without the CLI flag | unset |
| `EVAL_LLM_API_KEY` | real judge | unset (judge skipped with a warning) |
| `EVAL_LLM_BASE_URL` | real judge | `https://api.openai.com/v1` |
| `EVAL_LLM_MODEL` | real judge | `gpt-4o-mini` |

Precedence: `--no-judge` beats everything, then `--fake-judge` / `EVAL_FAKE_JUDGE=1`, then the real judge if `EVAL_LLM_API_KEY` is set, otherwise judge criteria are skipped and cases are scored on deterministic checks alone.

The fake judge is a keyword-coverage heuristic: it stems the significant words in each criterion and scores the fraction that appear in the response. It is deliberately simple and transparent (the report shows matched vs missing keywords per criterion), which makes it good for demos, tests, and CI, and a poor substitute for a real judge when you need actual quality judgments. Tune per-case `threshold` values to it accordingly.

## Project layout

```
evals/            # the harness package
  loader.py       # YAML suite loading and validation
  models.py       # EvalCase, CaseResult, SuiteResult dataclasses
  rubric.py       # contains / regex / not_contains checks
  judge.py        # fake and real (OpenAI-compatible) judges
  runner.py       # ThreadPoolExecutor execution, retries, results.json
  report.py       # self-contained HTML report
  cli.py          # python -m evals run ...
demos/            # stub agents (pure Python, offline)
suites/           # example suites: support.yaml, lead_triage.yaml
tests/            # pytest suite, no network access
```

## Notes and limits

- The real judge expects an OpenAI-compatible `/chat/completions` endpoint and asks the model to return JSON scores. If the model returns garbage, the case is marked `error` with the parse failure in the message.
- Retries only cover agent exceptions, not check or judge failures. A wrong answer fails fast; a crashing agent gets retried.
- Threads are used for IO-bound agents (typical LLM calls). If your agent is CPU-bound, lower `--workers`.
