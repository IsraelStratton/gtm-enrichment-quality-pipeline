#!/usr/bin/env python3
"""Make the cost sheet (KB-137 A5) from the run log: what each AI decision costs, by model and by route.

Reads the run log through the pipeline login (gtm_v2_pipeline, which can read the views and nothing
else) and the two price files, and writes:

  docs/v2/cost-sheet.json   what the queries returned, and when
  docs/v2/cost-sheet.md     the sheet, made from that JSON and the price files alone

  python scripts/cost_sheet.py            # query the run log, write both files
  python scripts/cost_sheet.py --render   # remake the .md from the saved JSON (no database)

A test remakes the .md from the JSON and the price files and fails if they differ, so no figure on the
sheet is typed by hand (A5.1). Each price is printed with the date it was read and its source (A5.2).
The one vendor comparison is marked "not like for like" (A5.3).

Exit codes: 0 done, 1 a database failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[1]
CLAUDE_PRICES = REPO / "pricing" / "claude_prices.json"
AGENTFORCE_PRICES = REPO / "pricing" / "agentforce_list_prices.json"
SHEET_JSON = REPO / "docs" / "v2" / "cost-sheet.json"
SHEET_MD = REPO / "docs" / "v2" / "cost-sheet.md"
LIVE_MODEL = "claude-haiku-5-5"

QUERIES = {
    "routing_by_model": """
        select model, source, count(*) as decisions, sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens,
               sum(cost_usd) as total_cost_usd
        from gtm_v2.decision_record group by model, source order by model, source""",
    "routing_by_route": """
        select model, coalesce(proposed_route, '(no proposal)') as route, count(*) as decisions, sum(cost_usd) as total_cost_usd
        from gtm_v2.decision_record group by model, coalesce(proposed_route, '(no proposal)') order by model, route""",
    "routing_live_writes": """
        select model, count(*) as proposals, count(*) filter (where crm_write_status = 'written') as written,
               count(*) filter (where action = 'rejected') as rejected, sum(cost_usd) as total_cost_usd,
               string_agg(distinct crm_target, ', ' order by crm_target) filter (where crm_write_status = 'written') as crm_targets
        from gtm_v2.decision_record where source = 'n8n' group by model order by model""",
    "desk_by_design": """
        select design, model, source, count(*) as quotes, sum(calls) as calls, sum(cost_usd) as total_cost_usd
        from gtm_v2.desk_record group by design, model, source order by design, model, source""",
}


def plain(v):
    """Database values as JSON: numbers as exact strings, so the sheet rounds them once, the same way every time."""
    if isinstance(v, Decimal):
        return str(v)
    return v


def query(conn) -> dict:
    snap = {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "read_from": "the run log (schema gtm_v2) through the pipeline login gtm_v2_pipeline"}
    for key, sql in QUERIES.items():
        cur = conn.execute(sql)
        cols = [c.name for c in cur.description]
        snap[key] = [{c: plain(v) for c, v in zip(cols, row)} for row in cur.fetchall()]
    return snap


# ---------------------------------------------------------------- the sheet


def D(v) -> Decimal:
    return Decimal(str(v)) if v is not None else Decimal(0)


def usd(v: Decimal, places: int) -> str:
    return f"{v:.{places}f}"


def per(total, count) -> Decimal | None:
    return D(total) / D(count) if count else None


def where(source: str) -> str:
    return {"n8n": "n8n, live runs", "python": "Python, evals and proofs"}.get(source, source)


def render(snap: dict, prices: dict, agentforce: dict) -> str:
    L = [
        "# Cost sheet: what each AI decision costs",
        "",
        f"KB-137 A5. Made by `scripts/cost_sheet.py` on {snap['made_at']} from {snap['read_from']}, and from the two price "
        "files. **No figure on this page is typed by hand:** a test remakes it from [`cost-sheet.json`](cost-sheet.json) and "
        "the price files, and fails if they differ. The run log works out each call's cost from the prices below "
        "(`gtm_v2.model_prices`, loaded from `pricing/claude_prices.json`).",
        "",
        "## Prices used",
        "",
        f"Claude API list prices, {prices['currency']} {prices['unit']}.",
        "",
        "| Model | Input | Output | Long prompts | Read on | Source |",
        "|---|---|---|---|---|---|",
    ]
    for m, p in prices["models"].items():
        long = (f"over {p['long_prompt_over_tokens']:,} tokens in: {p['long_input']:.2f} / {p['long_output']:.2f}"
                if p["long_prompt_over_tokens"] else "no separate price")
        L.append(f"| `{m}` | {p['input']:.2f} | {p['output']:.2f} | {long} | {p['read_on']} | {p['source']} |")

    L += ["", "## Routing: cost per decision, by model", "",
          "One decision is one enquiry routed: one Claude call. Live runs are the n8n workflows of chapters 2 and 4; the "
          "Python runs are the evals and proofs (`scripts/route_leads.py`, `scripts/route_eval.py`).", "",
          "| Model | Runs | Decisions | Tokens per decision, in / out | Cost per decision (US$) | Total (US$) |",
          "|---|---|---|---|---|---|"]
    avg = {}
    for r in snap["routing_by_model"]:
        n = r["decisions"]
        L.append(f"| `{r['model']}` | {where(r['source'])} | {n} | {D(r['input_tokens']) / n:.0f} / {D(r['output_tokens']) / n:.0f} "
                 f"| {usd(per(r['total_cost_usd'], n), 8)} | {usd(D(r['total_cost_usd']), 6)} |")
    for m in sorted({r["model"] for r in snap["routing_by_model"]}):
        rows = [r for r in snap["routing_by_model"] if r["model"] == m]
        avg[m] = per(sum(D(r["total_cost_usd"]) for r in rows), sum(r["decisions"] for r in rows))

    L += ["", "## Routing: cost per decision, by model and route", "",
          "The route is the one the AI proposed. All runs, live and eval.", "",
          "| Model | Route | Decisions | Cost per decision (US$) | Total (US$) |", "|---|---|---|---|---|"]
    for r in snap["routing_by_route"]:
        L.append(f"| `{r['model']}` | `{r['route']}` | {r['decisions']} | {usd(per(r['total_cost_usd'], r['decisions']), 8)} "
                 f"| {usd(D(r['total_cost_usd']), 6)} |")

    L += ["", "## Routing, live runs: cost per record written", "",
          "Every proposal costs a call, including the ones a person rejects, so the cost per record written is above the "
          "cost per decision.", "",
          "| Model | Proposals | Written to a CRM | Rejected | AI cost per record written (US$) | CRMs |", "|---|---|---|---|---|---|"]
    live_cpd = None
    for r in snap["routing_live_writes"]:
        cpw = per(r["total_cost_usd"], r["written"])
        L.append(f"| `{r['model']}` | {r['proposals']} | {r['written']} | {r['rejected']} | {'n/a' if cpw is None else usd(cpw, 8)} "
                 f"| {r['crm_targets'] or '-'} |")
        if r["model"] == LIVE_MODEL:
            live_cpd = per(r["total_cost_usd"], r["proposals"])

    L += ["", "## Quote desk: cost per quote, by design and model", "",
          "One triage is one quote, whatever number of calls the design makes (chapter 5).", "",
          "| Design | Model | Runs | Quotes | Claude calls per quote | Cost per quote (US$) | Total (US$) |", "|---|---|---|---|---|---|---|"]
    for r in snap["desk_by_design"]:
        L.append(f"| `{r['design']}` | `{r['model']}` | {where(r['source'])} | {r['quotes']} | {D(r['calls']) / r['quotes']:.1f} "
                 f"| {usd(per(r['total_cost_usd'], r['quotes']), 8)} | {usd(D(r['total_cost_usd']), 6)} |")

    route_total = sum(D(r["total_cost_usd"]) for r in snap["routing_by_model"])
    desk_total = sum(D(r["total_cost_usd"]) for r in snap["desk_by_design"])
    L += ["", f"**All AI spend in the run log:** US${usd(route_total + desk_total, 4)}: routing US${usd(route_total, 4)} over "
          f"{sum(r['decisions'] for r in snap['routing_by_model'])} decisions, the quote desk US${usd(desk_total, 4)} over "
          f"{sum(r['quotes'] for r in snap['desk_by_design'])} triages."]

    L += ["", "## Comparison lines", ""]
    others = [m for m in avg if m != LIVE_MODEL and avg.get(LIVE_MODEL)]
    for m in others:
        L.append(f"- **Model choice.** On routing, `{m}` costs {avg[m] / avg[LIVE_MODEL]:.0f} times as much as `{LIVE_MODEL}` per "
                 f"decision (US${usd(avg[m], 8)} against US${usd(avg[LIVE_MODEL], 8)}, every run of each in the run log). The "
                 "chapter 6 eval found both meet the bar, so the live workflow keeps the cheaper one "
                 "([`results-1.0.0.md`](../../skins/lead-routing/eval/results-1.0.0.md)).")
    fc = agentforce["flex_credits"]
    credits = fc["credits_per_action"]["standard_or_custom_action"]
    action = D(credits) * D(fc["price_per_credit"])
    if live_cpd:
        L.append(f"- **A vendor's list price, not like for like.** One Agentforce action at Salesforce's list price "
                 f"({credits} Flex Credits at US${fc['price_per_credit']} each, US${usd(action, 2)}; read on {agentforce['read_on']}) "
                 f"costs about {action / live_cpd:.0f} times one live routing decision on `{LIVE_MODEL}` (US${usd(live_cpd, 8)}, "
                 "the n8n runs in the run log). **Not like for like:** an Agentforce action is billed per action whatever its "
                 "size, a routing decision by the tokens it uses; the work differs; and this build's Agentforce explainer "
                 "runs free in a developer org with no payment method. Sources: " + "; ".join(agentforce["sources"]) + ".")
    return "\n".join(L) + "\n"


def load_prices() -> tuple[dict, dict]:
    return (json.loads(CLAUDE_PRICES.read_text(encoding="utf-8")), json.loads(AGENTFORCE_PRICES.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--render", action="store_true", help="remake the .md from the saved JSON, with no database")
    args = ap.parse_args(argv)
    try:
        prices, agentforce = load_prices()
    except (OSError, json.JSONDecodeError) as e:
        print(f"CONFIG ERROR {e}")
        return 2
    if args.render:
        snap = json.loads(SHEET_JSON.read_text(encoding="utf-8"))
    else:
        from dotenv import load_dotenv
        from setup_run_log import PASSWORD_KEY, connect, db_settings

        load_dotenv(REPO / ".env")
        password = os.environ.get(PASSWORD_KEY, "")
        if not password:
            print(f"CONFIG ERROR {PASSWORD_KEY} is not in .env; run scripts/setup_run_log.py first")
            return 2
        try:
            with connect(db_settings(), password) as conn:
                snap = query(conn)
        except Exception as e:  # database errors: the type and message, never a value from .env
            print(f"FAIL run log: {type(e).__name__}: {e}")
            return 1
        SHEET_JSON.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    SHEET_MD.write_text(render(snap, prices, agentforce), encoding="utf-8")
    print(f"Wrote {SHEET_MD.relative_to(REPO)}" + ("" if args.render else f" and {SHEET_JSON.relative_to(REPO)}") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
