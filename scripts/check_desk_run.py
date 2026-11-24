#!/usr/bin/env python3
"""Check a finished quote desk run against its log and, optionally, Salesforce.

  python scripts/check_desk_run.py --latest                 # the newest n8n run in the log
  python scripts/check_desk_run.py --run n8n-123 --salesforce
  python scripts/check_desk_run.py --stamp "gtm-v2-desk DQ-n8n123-04 | ..."   # one query from a stamp to its record
  python scripts/check_desk_run.py --handoffs py-20261124T015800Z-team-r1     # B3: the hand-offs of a run, with cost

What it checks for a run:
  - every quote triaged has a person's decision, approve or reject, with a reason;
  - every decision carries a stamp naming its decision, design, model, playbook, action, reviewer and time;
  - no quote that broke a fix rule was approved;
  - every decision reached Salesforce, and every owner of a saved quote was told (Gmail accepted
    the message and its id is in the log; the address is the build account's own, fixed in code);
  - with --salesforce: each quote in Salesforce carries the logged status, reason and stamp.

It reads the log through the pipeline login (views only) and Salesforce through the desk's own login.
Exit codes: 0 every check passed, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from setup_run_log import PASSWORD_KEY, connect, db_settings  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STAMP = re.compile(r"^gtm-v2-desk (?P<decision>DQ-[A-Za-z0-9]+-\d{2,}) \| (?P<design>one_prompt|fixed_chain|agent_team) \| (?P<model>[a-z0-9-]+) \| "
                   r"(?P<playbook>[a-z0-9-]+)@(?P<version>\d+\.\d+\.\d+) \| (?P<action>approved|rejected) by (?P<approver>.+) \| "
                   r"(?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$")
SF_FIELDS = ["Status", "GTM_Case_Id__c", "GTM_Desk_Reason__c", "GTM_Desk_Stamp__c"]


def rows(conn, sql: str, args: tuple) -> list[dict]:
    cur = conn.execute(sql, args)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def check_log(records: list[dict]) -> list[tuple[bool, str]]:
    out = []
    undecided = [r["case_id"] for r in records if r["action"] is None]
    out.append((not undecided, f"{len(records) - len(undecided)} of {len(records)} quotes have a person's decision"
                + (f" (waiting: {', '.join(undecided)})" if undecided else "")))
    decided = [r for r in records if r["action"]]
    good = 0
    for r in decided:
        m = STAMP.match(r["stamp"] or "")
        if (m and m["decision"] == r["decision_id"] and m["design"] == r["design"] and m["model"] == r["model"]
                and m["playbook"] == r["playbook_name"] and m["version"] == r["playbook_version"]
                and m["action"] == r["action"] and m["approver"] == r["approver"]):
            good += 1
        else:
            out.append((False, f"{r['case_id']}: the stamp does not match its log row"))
    out.append((good == len(decided), f"{good} of {len(decided)} decisions carry a matching stamp"))
    reasons = [r for r in decided if (r["decision_reason"] or "").strip()]
    out.append((len(reasons) == len(decided), f"{len(reasons)} of {len(decided)} decisions give the approver's reason"))
    bad = [r["case_id"] for r in decided if r["action"] == "approved" and r["fix_needed"]]
    out.append((not bad, "no quote that broke a fix rule was approved" + (f" (but {', '.join(bad)} was)" if bad else "")))
    failed = [r for r in decided if r["crm_write_status"] != "written"]
    out.append((not failed, f"{len(decided) - len(failed)} of {len(decided)} decisions reached Salesforce"
                + "".join(f"; {r['case_id']}: {r['crm_error']}" for r in failed)))
    saved = [r for r in decided if r["crm_write_status"] == "written"]
    told = [r for r in saved if r["owner_message_status"] == "sent" and r["owner_message_id"]]
    out.append((len(told) == len(saved), f"{len(told)} of {len(saved)} owners of saved quotes were told (Gmail message id logged)"))
    against = [r["case_id"] for r in decided if r["matches_proposal"] is False]
    print(f"  For the record: the approver went against the AI on {len(against)} quote(s){': ' + ', '.join(against) if against else ''}.")
    return out


def check_salesforce(records: list[dict], client=None) -> list[tuple[bool, str]]:
    if client is None:
        from salesforce_client import SalesforceClient

        client = SalesforceClient.from_env(login="desk")
    decided = [r for r in records if r["crm_write_status"] == "written"]
    same = 0
    out = []
    for r in decided:
        q = client.data(f"/sobjects/Quote/{r['quote_id']}?fields={','.join(SF_FIELDS)}", ok_404=True) or {}
        ok = (q.get("Status") == r["sf_status"] and q.get("GTM_Desk_Stamp__c") == r["stamp"]
              and (r["decision_reason"] or "") in (q.get("GTM_Desk_Reason__c") or "") and q.get("GTM_Case_Id__c") == r["case_id"])
        same += ok
        if not ok:
            out.append((False, f"{r['case_id']}: the quote in Salesforce does not match the log"))
    out.append((same == len(decided), f"Salesforce: {same} of {len(decided)} quotes carry the logged status, reason and stamp"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", help="run id, such as n8n-123")
    g.add_argument("--latest", action="store_true", help="the newest n8n run in the log")
    g.add_argument("--stamp", help="a whole stamp copied from a quote in Salesforce")
    g.add_argument("--handoffs", metavar="RUN", help="list a run's hand-offs with their tokens and cost")
    ap.add_argument("--salesforce", action="store_true", help="also read each decided quote back from Salesforce")
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    password = os.environ.get(PASSWORD_KEY, "")
    if not password:
        print(f"CANNOT RUN {PASSWORD_KEY} is not in .env; run scripts/setup_run_log.py first")
        return 2
    try:
        with connect(db_settings(), password) as conn:
            if args.stamp:
                m = STAMP.match(args.stamp.strip())
                if not m:
                    print("CANNOT RUN that is not a gtm-v2-desk stamp")
                    return 2
                found = rows(conn, "select * from gtm_v2.desk_record where decision_id = %s", (m["decision"],))
                if not found:
                    print(f"FAIL no log row for {m['decision']}")
                    return 1
                print(f"select * from gtm_v2.desk_record where decision_id = '{m['decision']}';")
                for k, v in found[0].items():
                    print(f"  {k:22} {v}")
                return 0
            if args.handoffs:
                hs = rows(conn, "select h.*, s.designs, s.quotes from gtm_v2.handoff_record h join gtm_v2.desk_run_summary s using (run_id) "
                                "where h.run_id = %s order by h.handoff_id", (args.handoffs,))
                print(f"select * from gtm_v2.handoff_record join gtm_v2.desk_run_summary using (run_id) where run_id = '{args.handoffs}';")
                for h in hs:
                    print(f"  {h['handoff_id']:28} {h['from_agent']:>15} -> {h['to_agent']:15} conf {h['confidence']}  "
                          f"{h['input_tokens']} in / {h['output_tokens']} out  US${h['cost_usd']}  asked: {h['asked'][:70]}")
                print(f"{len(hs)} hand-offs in run {args.handoffs}.")
                return 0 if hs else 1
            run_id = args.run or (rows(conn, "select run_id from gtm_v2.desk_run_summary where source = 'n8n' order by started_at desc nulls last limit 1", ())
                                  or [{"run_id": None}])[0]["run_id"]
            if not run_id:
                print("FAIL no n8n quote desk run in the log yet")
                return 1
            records = rows(conn, "select * from gtm_v2.desk_record where run_id = %s order by queue_position nulls last, case_id", (run_id,))
            summary = rows(conn, "select * from gtm_v2.desk_run_summary where run_id = %s", (run_id,))
    except Exception as e:  # database errors: the type and message, never a value from .env
        print(f"CANNOT RUN {type(e).__name__}: {str(e).replace(password, '<hidden>')}")
        return 2
    if not records:
        print(f"FAIL nothing logged for run {run_id}")
        return 1
    s = summary[0]
    print(f"Run {run_id}: {s['quotes']} quotes ({s['flagged']} flagged, {s['fix_first']} to fix first), approved {s['approved']}, "
          f"rejected {s['rejected']}, written {s['written']}, failed {s['failed']}, owners told {s['owners_told']}. "
          f"Cost US${s['total_cost_usd']} (US${s['cost_per_quote_usd']} a quote), design {s['designs']}, model {s['models']}, playbook {s['playbooks']}.")
    results = check_log(records)
    if args.salesforce:
        try:
            results += check_salesforce(records)
        except Exception as e:  # SalesforceError and ConfigError carry no value from .env
            print(f"CANNOT RUN Salesforce: {type(e).__name__}: {e}")
            return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
