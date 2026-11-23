#!/usr/bin/env python3
"""Run the AI routing step on a file of enquiries, with the same engine n8n uses.

This is the AI step on its own: playbook, request, Claude, guard rails, run log. It does not
ask a person and writes nothing to HubSpot; the n8n workflow does those. Use it to prove the
step, to compare playbook versions, and (from chapter 6) as the base of the eval.

  python scripts/route_leads.py --file skins/lead-routing/enquiries.csv
  python scripts/route_leads.py --file skins/lead-routing/enquiries.csv --only L-0034,L-0036
  python scripts/route_leads.py --file skins/lead-routing/enquiries.csv --log     # also write the run log

The Claude key is read from .env (ANTHROPIC_API_KEY) and never printed. When the file has
expected labels (enquiries.csv does), each row is marked against them. This is a quick check,
not the eval: the grader and the model comparison are chapter 6.

Exit codes: 0 done, 1 an API or database failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from routing_engine import PLAYBOOK, REPO, Engine, EngineError, Ref, read_playbook  # noqa: E402

DEFAULT_MODEL = "claude-haiku-5-5"
PRICES = REPO / "pricing" / "claude_prices.json"
EXPORTS = REPO / "exports"


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def call_claude(client, request: dict) -> tuple[dict, int]:
    """One Messages call. Returns the result in the engine's HTTP shape, and the time taken in ms."""
    import anthropic

    started = time.perf_counter()
    try:
        message = client.messages.create(**request)
        http = {"statusCode": 200, "headers": {"request-id": message._request_id}, "body": message.to_dict()}
    except anthropic.APIStatusError as e:
        http = {"error": {"message": e.message, "status": e.status_code}}
    except anthropic.APIConnectionError as e:
        http = {"error": {"message": f"connection error: {type(e).__name__}"}}
    return http, round((time.perf_counter() - started) * 1000)


def local_cost(prices: dict, model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Cost of ONE request. The long-prompt price applies per request, never to a run's total."""
    p = prices["models"].get(model)
    if not p:
        return None
    if p["long_prompt_over_tokens"] and tokens_in > p["long_prompt_over_tokens"]:
        return (tokens_in * p["long_input"] + tokens_out * p["long_output"]) / 1e6
    return (tokens_in * p["input"] + tokens_out * p["output"]) / 1e6


def run_cost(prices: dict, model: str, proposals: list[dict]) -> float | None:
    costs = [local_cost(prices, model, p["input_tokens"], p["output_tokens"]) for p in proposals]
    return None if any(c is None for c in costs) else sum(costs)


def matches(expected: str, actual) -> bool | None:
    if not expected:
        return None
    return str(actual) in expected.split("|")


def review_matches(expected: str, needs_review: bool) -> bool | None:
    if expected not in ("yes", "no"):
        return None
    return (expected == "yes") == needs_review


def mark(v: bool | None) -> str:
    return "-" if v is None else ("ok" if v else "XX")


def log_run(proposals: list[dict], run_id: str) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from setup_run_log import PASSWORD_KEY, connect, db_settings

    password = os.environ.get(PASSWORD_KEY, "")
    if not password:
        raise RuntimeError(f"{PASSWORD_KEY} is not in .env; run scripts/setup_run_log.py first")
    with connect(db_settings(), password) as conn:
        n = conn.execute("select gtm_v2.log_proposals(%s::jsonb)", (json.dumps(proposals),)).fetchone()[0]
        cur = conn.execute("select * from gtm_v2.run_summary where run_id = %s", (run_id,))
        cols = [c.name for c in cur.description]
        row = cur.fetchone()
    summary = dict(zip(cols, row)) if row else {}
    summary["logged"] = n
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, type=Path, help="CSV with lead_id, company_name, domain, industry, employee_count, hq_city, hq_country, enquiry")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--only", help="comma-separated lead ids to run")
    ap.add_argument("--limit", type=int, help="run only the first N rows")
    ap.add_argument("--playbook", type=Path, default=PLAYBOOK, help="SKILL.md to route with (default: the skin's playbook)")
    ap.add_argument("--log", action="store_true", help="write the proposals to the run log (gtm_v2) and read the cost back")
    args = ap.parse_args(argv)

    load_dotenv(REPO / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("CONFIG ERROR ANTHROPIC_API_KEY is not in .env")
        return 2
    try:
        rows = read_rows(args.file)
        if args.only:
            wanted = {x.strip() for x in args.only.split(",")}
            rows = [r for r in rows if r.get("lead_id") in wanted]
        if args.limit:
            rows = rows[: args.limit]
        if not rows:
            print("CONFIG ERROR no rows to run")
            return 2
        eng = Engine()
        text = read_playbook(args.playbook)
        calls = [("parsePlaybook", [text])]
        for i, row in enumerate(rows, 1):
            calls.append(("leadFromRow", [row, None, i]))
        prepared = eng.batch(calls)
        pb, leads = prepared[0], prepared[1:]
        requests = eng.batch([("buildRequest", [pb, lead, args.model]) for lead in leads])
    except (EngineError, OSError) as e:
        print(f"CONFIG ERROR {e}")
        return 2

    import anthropic

    client = anthropic.Anthropic()
    run_id = "py-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Run {run_id}: {len(rows)} enquiries, model {args.model}, playbook {pb['name']} {pb['version']} ({pb['sha256'][:12]}).")
    checks = []
    for lead, request in zip(leads, requests):
        http, ms = call_claude(client, request)
        ctx = {
            "decision_id": eng.call("decisionId", run_id, lead["row_number"]),
            "run_id": run_id, "source": "python", "model": args.model, "latency_ms": ms,
            "now": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        checks.append(("checkProposal", [Ref(0), lead, http, ctx]))
    proposals = eng.batch([("parsePlaybook", [text])] + checks)[1:]

    prices = json.loads(PRICES.read_text(encoding="utf-8"))
    totals = {"route": [0, 0], "priority": [0, 0], "review": [0, 0]}
    print(f"\n{'lead':7} {'route':18} {'priority':8} {'conf':>5} {'ms':>6}  review  vs labels (route/priority/review)  why flagged")
    for row, p in zip(rows, proposals):
        got = [matches(row.get("expected_route", ""), p["route"]),
               matches(row.get("expected_priority", ""), p["priority"]),
               review_matches(row.get("expected_review", ""), p["needs_review"])]
        for key, v in zip(totals, got):
            if v is not None:
                totals[key][0] += int(v)
                totals[key][1] += 1
        conf = "" if p["confidence"] is None else f"{p['confidence']:.2f}"
        print(f"{p['lead_id']:7} {str(p['route']):18} {str(p['priority']):8} {conf:>5} {p['latency_ms']:>6}  "
              f"{'yes' if p['needs_review'] else 'no':6}  {'/'.join(mark(v) for v in got):34}  {'|'.join(p['review_reasons'])}")
    tokens_in = sum(p["input_tokens"] for p in proposals)
    tokens_out = sum(p["output_tokens"] for p in proposals)
    cost = run_cost(prices, args.model, proposals)
    print(f"\nTokens: {tokens_in} in, {tokens_out} out. Cost from pricing/claude_prices.json: "
          f"{'unknown model' if cost is None else f'US${cost:.6f} (US${cost / len(proposals):.8f} a decision)'}.")
    print(f"Flagged for review: {sum(p['needs_review'] for p in proposals)} of {len(proposals)}. "
          f"Invalid outputs: {sum(not p['output_valid'] for p in proposals)}.")
    if any(t[1] for t in totals.values()):
        print("Against the drafted labels: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in totals.items() if v[1]) + ".")

    EXPORTS.mkdir(exist_ok=True)
    out = EXPORTS / f"route-run-{run_id}.json"
    out.write_text(json.dumps({"run_id": run_id, "model": args.model, "playbook": {k: pb[k] for k in ("name", "version", "sha256")},
                               "proposals": proposals}, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {out.relative_to(REPO)} (git-ignored).")

    if args.log:
        try:
            s = log_run(proposals, run_id)
        except Exception as e:  # database errors: name only, never a value
            print(f"FAIL run log: {type(e).__name__}: {e}")
            return 1
        print(f"Run log: {s['logged']} proposals added. From gtm_v2.run_summary: {s.get('proposals')} proposals, "
              f"total US${s.get('total_cost_usd')}, US${s.get('cost_per_decision_usd')} a decision, "
              f"average {s.get('avg_latency_ms')} ms.")
    failed = sum("ai_call_failed" in p["review_reasons"] for p in proposals)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
