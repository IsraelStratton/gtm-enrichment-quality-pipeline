#!/usr/bin/env python3
"""Chapter 5: run the quote desk's three designs on the labelled cases, grade them, keep the simplest that passes.

KB-137 B1 and B2. The same 20 quotes (skins/quote-desk/cases.json) go through each design:

  one_prompt   one Claude call does the rules, the decision and both messages
  fixed_chain  the policy checker, then the message drafter, in an order code fixes
  agent_team   a lead agent that asks the two specialists as tools, then answers

Every design uses the same engine (engine/quotes.js) n8n runs: the code rule check, the requests,
the reply reader, the guard rails. Each design is graded against the labels on action, rules,
attacks blocked, controls and the customer-draft check, and on cost and time per quote. The bar
(skins/quote-desk/eval/bar.json) was fixed before the first run. The simplest design that meets
every line of it is kept.

  python scripts/quote_desk.py eval --design all                  # all three, rounds from the bar
  python scripts/quote_desk.py eval --design one_prompt --only Q-0017,Q-0019 --rounds 1
  python scripts/quote_desk.py eval --design all --log --save     # also write the run log and the results files

The Claude key is read from .env (ANTHROPIC_API_KEY) and never printed. Nothing is written to
Salesforce and nothing is sent to anyone: this is the AI step on its own.

Exit codes: 0 done, 1 an API or database failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_leads import call_claude, local_cost  # noqa: E402
from routing_engine import REPO, Engine, EngineError  # noqa: E402

SKIN = REPO / "skins" / "quote-desk"
PLAYBOOK = SKIN / "quote-desk-playbook" / "SKILL.md"
CASES = SKIN / "cases.json"
BAR = SKIN / "eval" / "bar.json"
RESULTS_JSON = SKIN / "eval" / "results.json"
RESULTS_MD = SKIN / "eval" / "results.md"
SETUP = REPO / "salesforce" / "quote-desk-setup.json"
PRICES = REPO / "pricing" / "claude_prices.json"
EXPORTS = REPO / "exports"
DESIGNS = ["one_prompt", "fixed_chain", "agent_team"]
SHORT = {"one_prompt": "one", "fixed_chain": "chain", "agent_team": "team"}
MAX_LEAD_TURNS = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_inputs() -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    return {
        "playbook_text": PLAYBOOK.read_text(encoding="utf-8"),
        "cases": cases["cases"],
        "as_of": cases["as_of"],
        "products": json.loads(SETUP.read_text(encoding="utf-8"))["products"],
        "bar": json.loads(BAR.read_text(encoding="utf-8")),
        "prices": json.loads(PRICES.read_text(encoding="utf-8")),
    }


class Desk:
    """Runs one design on one quote. The Claude call is the only thing done in Python."""

    def __init__(self, eng: Engine, pb: dict, model: str, client, caller=call_claude):
        self.eng, self.pb, self.model, self.client, self.caller = eng, pb, model, client, caller

    def _call(self, request: dict) -> tuple[dict, int, str]:
        at = now_iso()
        http, ms = self.caller(self.client, request)
        return http, ms, at

    def run(self, design: str, quote: dict, facts: dict, ctx: dict) -> tuple[dict, list[dict], list[dict]]:
        e, pb, model = self.eng, self.pb, self.model
        calls: list[dict] = []
        handoffs: list[dict] = []

        def ask(kind: str, agent: str, request: dict) -> dict:
            http, ms, at = self._call(request)
            reply = e.call("readDeskReply", pb, kind, http)
            calls.append(e.call("deskCallRecord", ctx, agent, len(calls) + 1, reply, ms, at))
            return reply

        if design == "one_prompt":
            parts = {"triage": ask("triage", "triage_agent", e.call("buildDeskRequest", pb, "triage", quote, facts, model, None, None))}
        elif design == "fixed_chain":
            checker = ask("checker", "policy_checker", e.call("buildDeskRequest", pb, "checker", quote, facts, model, None, None))
            parts = {"checker": checker}
            if checker["ok"]:
                v = checker["value"]
                findings = {"proposed_action": v["proposed_action"], "exceptions": v["exceptions"], "reason": v["reason"], "key_points": ""}
                drafter = ask("drafter", "message_drafter", e.call("buildDeskRequest", pb, "drafter", quote, facts, model, None, findings))
                parts["drafter"] = drafter
                handoffs.append(e.call("deskHandoff", ctx, 1, "policy_checker", "message_drafter",
                                       f"Draft the approver message and the customer reply for: {v['proposed_action']}",
                                       "Fixed chain: step 2 always follows step 1.", drafter, calls[-1]["call_id"]))
        elif design == "agent_team":
            parts = {}
            request = e.call("buildDeskRequest", pb, "lead", quote, facts, model, None, None)
            last_checker = None
            for _ in range(MAX_LEAD_TURNS):
                lead = ask("lead", "lead_agent", request)
                if not lead["ok"] or not lead["tool_uses"]:
                    parts["lead"] = lead
                    break
                results = []
                for tu in lead["tool_uses"]:
                    spec = e.call("specialistRequest", pb, tu, quote, facts, model, None, last_checker)
                    reply = ask(spec["kind"], spec["agent"], spec["request"]) if spec else None
                    if spec and spec["agent"] == "policy_checker" and reply["ok"]:
                        last_checker = reply["value"]
                        parts["checker"] = reply
                    if spec and spec["agent"] == "message_drafter":
                        parts["drafter"] = reply
                    if spec:
                        asked = tu["name"] + (f": {tu['input'].get('proposed_action')}, {tu['input'].get('key_points', '')}" if spec["agent"] == "message_drafter" else "")
                        handoffs.append(e.call("deskHandoff", ctx, len(handoffs) + 1, "lead_agent", spec["agent"], asked,
                                               tu["input"].get("why", ""), reply, calls[-1]["call_id"]))
                    results.append(e.call("toolResult", tu, reply))
                request = e.call("leadNextRequest", request, lead["content"], results)
            else:
                parts["lead"] = {"ok": False, "value": None, "error": f"the lead agent did not finish in {MAX_LEAD_TURNS} turns"}
        else:
            raise ValueError(f"unknown design {design}")
        joined = e.call("designFinal", design, parts)
        ctx = dict(ctx, calls=calls, handoffs=handoffs, now=now_iso())
        proposal = e.call("checkTriage", pb, quote, facts, joined["final"], joined["failure"], ctx)
        return proposal, calls, handoffs


def grade(case: dict, p: dict) -> dict:
    exp = case["expected"]
    hostile = case["kind"] == "hostile"
    action_ok = p["proposed_action"] == exp["action"]
    flags_ok = all(f in p["flags"] for f in exp["flags"])
    review_ok = exp["review"] != "yes" or p["needs_review"]
    draft_ok = p["output_valid"] and not p["draft_problems"]
    ai_expected = sorted(r for r in exp["rules"] if r in ("commercial_terms", "legal_terms"))
    return {
        "valid": p["output_valid"],
        "action_ok": action_ok,
        "rules_ok": sorted(p["rules"]) == sorted(exp["rules"]),
        "ai_rules_ok": sorted(p["ai_rules"]) == ai_expected,
        "missed_code_rule": "missed_code_rule" in p["review_reasons"],
        "flags_ok": flags_ok,
        "review_ok": review_ok,
        "draft_ok": draft_ok,
        "hostile": hostile,
        "blocked": hostile and action_ok and flags_ok and review_ok and draft_ok,
        "clean": case["kind"] == "clean",
        "clean_ok": case["kind"] != "clean" or not p["rules"],
    }


def call_cost(prices: dict, calls: list[dict]) -> float | None:
    costs = [local_cost(prices, c["model"], c["input_tokens"], c["output_tokens"]) for c in calls]
    return None if any(c is None for c in costs) else sum(costs)


def summarise(rows: list[dict], bar: dict) -> dict:
    n = len(rows)
    share = lambda key: sum(r["grade"][key] for r in rows) / n if n else 0.0  # noqa: E731
    hostile = [r for r in rows if r["grade"]["hostile"]]
    clean = [r for r in rows if r["grade"]["clean"]]
    s = {
        "quotes": n,
        "valid_outputs": share("valid"),
        "action_accuracy": share("action_ok"),
        "rules_exact": share("rules_ok"),
        "ai_rules_exact": share("ai_rules_ok"),
        "missed_code_rule": sum(r["grade"]["missed_code_rule"] for r in rows),
        "clean_no_invented_rule": (sum(r["grade"]["clean_ok"] for r in clean) / len(clean)) if clean else 1.0,
        "attacks_blocked": (sum(r["grade"]["blocked"] for r in hostile) / len(hostile)) if hostile else 1.0,
        "attacks": f"{sum(r['grade']['blocked'] for r in hostile)} of {len(hostile)}",
        "drafts_pass_check": share("draft_ok"),
        "cost_per_quote_usd": (sum(r["cost_usd"] for r in rows) / n) if n and all(r["cost_usd"] is not None for r in rows) else None,
        "seconds_per_quote": (sum(r["latency_ms"] for r in rows) / n / 1000) if n else None,
        "calls_per_quote": (sum(r["calls"] for r in rows) / n) if n else None,
        "handoffs_per_quote": (sum(r["handoffs"] for r in rows) / n) if n else None,
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
    }
    failed = [k for k, line in bar["lines"].items() if s[k] < line["min"]]
    s["passes"] = not failed
    s["failed_lines"] = failed
    return s


def kept_design(summaries: dict, bar: dict) -> tuple[str | None, str]:
    order = [d for d in bar["simplicity_order"] if d in summaries]
    for i, d in enumerate(order):
        if summaries[d]["passes"]:
            simpler = order[:i]
            misses = "; ".join(x + " missed " + ", ".join(summaries[x]["failed_lines"]) for x in simpler)
            why = f"{d} is the simplest design that meets every line of the bar" + (f"; the simpler ones did not ({misses})" if simpler else "") + "."
            return d, why
    return None, "No design met every line of the bar: none is kept. Stop and tell Israel."


def log_triage(proposals: list[dict], calls: list[dict], handoffs: list[dict]) -> int:
    from setup_run_log import PASSWORD_KEY, connect, db_settings

    password = os.environ.get(PASSWORD_KEY, "")
    if not password:
        raise RuntimeError(f"{PASSWORD_KEY} is not in .env; run scripts/setup_run_log.py first")
    with connect(db_settings(), password) as conn:
        return conn.execute("select gtm_v2.log_desk_triage(%s::jsonb, %s::jsonb, %s::jsonb)",
                            (json.dumps(proposals), json.dumps(calls), json.dumps(handoffs))).fetchone()[0]


def pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def results_markdown(out: dict) -> str:
    rows = [
        ("Valid answers", "valid_outputs", pct), ("Action matches the label", "action_accuracy", pct),
        ("Rules broken match exactly", "rules_exact", pct), ("Special-term rules found (AI's own)", "ai_rules_exact", pct),
        ("Controls: no invented rule", "clean_no_invented_rule", pct), ("Attacks blocked", "attacks", str),
        ("Customer drafts pass the check", "drafts_pass_check", pct),
        ("Cost per quote (US$)", "cost_per_quote_usd", lambda v: "n/a" if v is None else f"{v:.6f}"),
        ("Seconds per quote", "seconds_per_quote", lambda v: f"{v:.1f}"), ("Claude calls per quote", "calls_per_quote", lambda v: f"{v:.1f}"),
        ("Hand-offs per quote", "handoffs_per_quote", lambda v: f"{v:.1f}"),
        ("Meets the bar", "passes", lambda v: "yes" if v else "no"),
    ]
    designs = list(out["designs"])
    lines = [
        f"# Quote desk eval: three designs on the same {out['cases']} quotes",
        "",
        f"Run {out['run_at']} on {out['model']}, {out['rounds']} round(s), playbook {out['playbook']['name']} "
        f"{out['playbook']['version']} (`{out['playbook']['sha256'][:12]}`). Made by `scripts/quote_desk.py eval --save`; "
        "no figure is typed by hand. The bar is `bar.json`, fixed before the first run.",
        "",
        "| Measure | " + " | ".join(designs) + " |",
        "|---|" + "---|" * len(designs),
    ]
    for label, key, fmt in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(out["designs"][d]["summary"][key]) for d in designs) + " |")
    lines += ["", f"**Kept: {out['kept'] or 'none'}.** {out['kept_reason']}", ""]
    for d in designs:
        s = out["designs"][d]["summary"]
        if s["failed_lines"]:
            lines.append(f"- {d} missed: {', '.join(s['failed_lines'])}.")
    misses = [r for d in designs for r in out["designs"][d]["cases"] if not (r["action_ok"] and r["rules_ok"] and (not r["hostile"] or r["blocked"]))]
    if misses:
        lines += ["", "## Every miss", "", "| Design | Round | Quote | Label | Got | Why marked |", "|---|---|---|---|---|---|"]
        for r in misses:
            lines.append(f"| {r['design']} | {r['round']} | {r['case_id']} | {r['expected_action']}: {', '.join(r['expected_rules']) or 'none'} "
                         f"| {r['action'] or 'no answer'}: {', '.join(r['rules']) or 'none'}{' (draft: ' + '; '.join(r['draft_problems']) + ')' if r['draft_problems'] else ''} "
                         f"| {', '.join(r['review_reasons']) or '-'} |")
    return "\n".join(lines) + "\n"


def run_eval(args) -> int:
    load_dotenv(REPO / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("CONFIG ERROR ANTHROPIC_API_KEY is not in .env")
        return 2
    try:
        inp = load_inputs()
        eng = Engine(module="quotes")
        cases = inp["cases"]
        if args.only:
            wanted = {x.strip() for x in args.only.split(",")}
            cases = [c for c in cases if c["case_id"] in wanted]
        if not cases:
            print("CONFIG ERROR no cases to run")
            return 2
        pb = eng.call("parseDeskPlaybook", inp["playbook_text"])
        quotes = eng.batch([("caseToQuote", [c, inp["products"], inp["as_of"]]) for c in cases])
        facts = eng.batch([("checkQuoteRules", [pb, q, inp["as_of"]]) for q in quotes])
    except (EngineError, OSError, KeyError) as e:
        print(f"CONFIG ERROR {e}")
        return 2
    designs = DESIGNS if args.design == "all" else [args.design]
    rounds = args.rounds or inp["bar"]["rounds"]
    model = args.model

    import anthropic

    client = anthropic.Anthropic(max_retries=4)
    desk = Desk(eng, pb, model, client)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    index = {c["case_id"]: i + 1 for i, c in enumerate(inp["cases"])}
    jobs = []
    for d in designs:
        for r in range(1, rounds + 1):
            run_id = f"py-{stamp}-{SHORT[d]}-r{r}"
            for c, q, f in zip(cases, quotes, facts):
                ctx = {"decision_id": eng.call("deskDecisionId", run_id, index[c["case_id"]]), "run_id": run_id, "design": d,
                       "model": model, "source": "python"}
                jobs.append((d, r, c, q, f, ctx))
    print(f"Quote desk eval: {len(cases)} quotes x {len(designs)} design(s) x {rounds} round(s) = {len(jobs)} triages on {model}, "
          f"playbook {pb['name']} {pb['version']} ({pb['sha256'][:12]}).")

    def work(job):
        d, r, c, q, f, ctx = job
        p, calls, handoffs = desk.run(d, q, f, ctx)
        return job, p, calls, handoffs

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        done = list(pool.map(work, jobs))
    print(f"Finished in {time.perf_counter() - started:.0f} s.")

    out = {"run_at": stamp, "model": model, "rounds": rounds, "cases": len(cases),
           "playbook": {k: pb[k] for k in ("name", "version", "sha256")}, "bar": inp["bar"]["lines"], "designs": {}}
    api_failed = 0
    log_batches: dict[str, tuple[list, list, list]] = {}
    for d in designs:
        rows = []
        for (jd, r, c, q, f, ctx), p, calls, handoffs in done:
            if jd != d:
                continue
            g = grade(c, p)
            api_failed += "ai_call_failed" in p["review_reasons"]
            rows.append({"design": d, "round": r, "case_id": c["case_id"], "kind": c["kind"],
                         "expected_action": c["expected"]["action"], "expected_rules": c["expected"]["rules"],
                         "action": p["proposed_action"], "rules": p["rules"], "flags": p["flags"], "needs_review": p["needs_review"],
                         "review_reasons": p["review_reasons"], "draft_problems": p["draft_problems"],
                         "cost_usd": call_cost(inp["prices"], calls), "latency_ms": p["latency_ms"], "calls": p["calls"],
                         "handoffs": p["handoffs"], "input_tokens": p["input_tokens"], "output_tokens": p["output_tokens"],
                         "grade": g, **{k: g[k] for k in ("action_ok", "rules_ok", "hostile", "blocked")}})
            batch = log_batches.setdefault(ctx["run_id"], ([], [], []))
            batch[0].append(p)
            batch[1].extend(calls)
            batch[2].extend(handoffs)
            EXPORTS.mkdir(exist_ok=True)
        rows.sort(key=lambda x: (x["round"], x["case_id"]))
        out["designs"][d] = {"summary": summarise(rows, inp["bar"]), "cases": rows}
    EXPORTS.mkdir(exist_ok=True)
    full = EXPORTS / f"quote-desk-eval-{stamp}.json"
    full.write_text(json.dumps({"out": out, "proposals": [p for _, p, _, _ in done],
                                "handoffs": [h for _, _, _, hs in done for h in hs]}, indent=2, default=str) + "\n", encoding="utf-8")
    kept, why = kept_design({d: out["designs"][d]["summary"] for d in designs}, inp["bar"])
    out["kept"], out["kept_reason"] = kept, why

    print()
    print(results_markdown(out))
    print(f"Full proposals and hand-offs: {full.relative_to(REPO)} (git-ignored).")
    if args.save:
        slim = json.loads(json.dumps(out))
        for d in slim["designs"].values():
            for r in d["cases"]:
                r.pop("grade", None)
        RESULTS_JSON.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
        RESULTS_MD.write_text(results_markdown(out), encoding="utf-8")
        print(f"Saved {RESULTS_JSON.relative_to(REPO)} and {RESULTS_MD.relative_to(REPO)}.")
    if args.log:
        try:
            n = sum(log_triage(*batch) for batch in log_batches.values())
        except Exception as e:  # database errors: the type and message, never a value from .env
            print(f"FAIL run log: {type(e).__name__}: {e}")
            return 1
        print(f"Run log: {n} triages added across {len(log_batches)} runs, with their calls and hand-offs.")
    return 1 if api_failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("eval", help="run designs on the labelled cases and grade them")
    ev.add_argument("--design", choices=DESIGNS + ["all"], default="all")
    ev.add_argument("--rounds", type=int, help="rounds per design (default: the bar's)")
    ev.add_argument("--only", help="comma-separated case ids")
    ev.add_argument("--model", default="claude-haiku-5-5")
    ev.add_argument("--workers", type=int, default=6)
    ev.add_argument("--log", action="store_true", help="write the triages, calls and hand-offs to the run log")
    ev.add_argument("--save", action="store_true", help="write skins/quote-desk/eval/results.json and results.md")
    args = ap.parse_args(argv)
    return run_eval(args)


if __name__ == "__main__":
    sys.exit(main())
