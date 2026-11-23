#!/usr/bin/env python3
"""Check a finished routing run against its log and, optionally, the CRM it wrote to.

  python scripts/check_run.py --latest                    # the newest run in the log
  python scripts/check_run.py --run n8n-123 --hubspot     # A1.1: count the writes, find a stamp on each in HubSpot
  python scripts/check_run.py --latest --salesforce       # the same, for a run that wrote to Salesforce (chapter 4)
  python scripts/check_run.py --decision D-n8n123-04      # A1.2: one query from a stamp to its full record
  python scripts/check_run.py --stamp "gtm-v2 D-n8n123-04 | ..."

What it checks for a run:
  - every proposal has a person's decision (approved, changed or rejected);
  - every decision that led to a write carries a stamp naming the decision, model, playbook,
    action, reviewer and time, and every rejected one has none;
  - a changed row keeps both what the AI proposed and what the person chose (A1.3);
  - with --hubspot or --salesforce: the run wrote to that CRM; each written company (or
    Account) carries the same stamp, route, priority and status as the log; and no rejected
    row carries this run's stamp.

It reads the log through the pipeline login (views only), HubSpot with the read scope, and
Salesforce through the workflow's own login (salesforce_client.py), reading only.
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
STAMP = re.compile(r"^gtm-v2 (?P<decision>D-[A-Za-z0-9]+-\d{2,}) \| (?P<model>[a-z0-9-]+) \| (?P<playbook>[a-z0-9-]+)@(?P<version>\d+\.\d+\.\d+) \| "
                   r"(?P<action>approved|changed) by (?P<approver>.+) \| (?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$")
HUBSPOT_PROPS = ["name", "clay_domain_key", "gtm_route", "gtm_priority", "gtm_routing_status", "gtm_routing_confidence", "gtm_decision_stamp"]
SALESFORCE_FIELDS = ["Name", "Clay_Domain_Key__c", "GTM_Route__c", "GTM_Priority__c", "GTM_Routing_Status__c",
                     "GTM_Routing_Confidence__c", "GTM_Decision_Stamp__c"]
LABELS = {"hubspot": "HubSpot", "salesforce": "Salesforce"}


def rows(conn, sql: str, args: tuple) -> list[dict]:
    cur = conn.execute(sql, args)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def check_log(records: list[dict]) -> list[tuple[bool, str]]:
    out = []
    undecided = [r["decision_id"] for r in records if r["action"] is None]
    out.append((not undecided, f"{len(records) - len(undecided)} of {len(records)} proposals have a person's decision"
                + (f" (waiting: {', '.join(undecided[:3])}{' and more' if len(undecided) > 3 else ''})" if undecided else "")))
    writes = [r for r in records if r["action"] in ("approved", "changed")]
    good = 0
    for r in writes:
        m = STAMP.match(r["stamp"] or "")
        if (m and m["decision"] == r["decision_id"] and m["model"] == r["model"] and m["playbook"] == r["playbook_name"]
                and m["version"] == r["playbook_version"] and m["action"] == r["action"] and m["approver"] == r["approver"]):
            good += 1
        else:
            out.append((False, f"{r['decision_id']}: the stamp does not match its log row"))
    out.append((good == len(writes), f"{good} of {len(writes)} decisions that lead to a write carry a matching stamp"))
    rejected = [r for r in records if r["action"] == "rejected"]
    out.append((all(r["stamp"] is None and r["crm_write_status"] == "not_written" for r in rejected),
                f"{len(rejected)} rejected decisions carry no stamp and were not written"))
    changed = [r for r in records if r["action"] == "changed"]
    both = [r for r in changed if (r["proposed_route"], r["proposed_priority"]) != (r["chosen_route"], r["chosen_priority"])]
    out.append((len(both) == len(changed), f"{len(changed)} changed rows keep both values"
                + "".join(f"; {r['lead_id']}: AI {r['proposed_route']} {r['proposed_priority']}, person {r['chosen_route']} {r['chosen_priority']}" for r in changed)))
    failed = [r for r in writes if r["crm_write_status"] != "written"]
    targets = sorted({r.get("crm_target") or "hubspot" for r in writes}) or ["hubspot"]
    out.append((not failed, f"{len(writes) - len(failed)} of {len(writes)} writes reached {' and '.join(LABELS.get(t, t) for t in targets)}"
                + "".join(f"; {r['lead_id']}: {r['crm_error']}" for r in failed)))
    return out


def check_target(records: list[dict], target: str) -> list[tuple[bool, str]]:
    writes = [r for r in records if r["action"] in ("approved", "changed")]
    wrong = sorted({r.get("crm_target") or "hubspot" for r in writes} - {target})
    return [(not wrong, f"every write in this run went to {LABELS[target]}" + (f" (but some went to {', '.join(wrong)})" if wrong else ""))]


def check_salesforce(records: list[dict], client=None) -> list[tuple[bool, str]]:
    """The same checks as check_hubspot, on Accounts. client: a SalesforceClient (tests pass a fake)."""
    if client is None:
        from salesforce_client import SalesforceClient

        client = SalesforceClient.from_env()
    out = []
    written = [r for r in records if r["crm_write_status"] == "written"]
    stamped = 0
    for r in written:
        rec = client.account(r["crm_record_id"], SALESFORCE_FIELDS) or {}
        same = (rec.get("GTM_Decision_Stamp__c") == r["stamp"] and rec.get("GTM_Route__c") == r["chosen_route"]
                and rec.get("GTM_Priority__c") == r["chosen_priority"] and rec.get("GTM_Routing_Status__c") == r["action"]
                and rec.get("Clay_Domain_Key__c") == r["domain"])
        stamped += int(same)
        if not same:
            out.append((False, f"{r['lead_id']} (Salesforce {r['crm_record_id']}): the Account does not match the log"))
    out.append((stamped == len(written), f"Salesforce: {stamped} of {len(written)} written Accounts carry the logged stamp, route, priority and status"))
    leaked = 0
    for r in (x for x in records if x["action"] == "rejected"):
        rec = client.account_by_key(r["domain"], SALESFORCE_FIELDS)
        if rec is None:
            continue  # never in Salesforce at all
        if r["decision_id"] in (rec.get("GTM_Decision_Stamp__c") or ""):
            leaked += 1
            out.append((False, f"{r['lead_id']}: rejected, but Salesforce carries its stamp"))
    out.append((leaked == 0, "Salesforce: no rejected row carries this run's stamp"))
    return out


def check_hubspot(records: list[dict]) -> list[tuple[bool, str]]:
    from hubspot_smoke_test import DEFAULT_BASE_URL, HubSpotClient, HubSpotError

    token = os.environ.get("HUBSPOT_SERVICE_KEY", "").strip()
    if not token:
        return [(False, "HUBSPOT_SERVICE_KEY is not in .env")]
    client = HubSpotClient(token, os.environ.get("HUBSPOT_BASE_URL", DEFAULT_BASE_URL).strip())
    props = ",".join(HUBSPOT_PROPS)
    out = []
    written = [r for r in records if r["crm_write_status"] == "written"]
    stamped = 0
    for r in written:
        rec = client._request("GET", f"/crm/v3/objects/companies/{r['crm_record_id']}?properties={props}")["properties"]
        same = (rec.get("gtm_decision_stamp") == r["stamp"] and rec.get("gtm_route") == r["chosen_route"]
                and rec.get("gtm_priority") == r["chosen_priority"] and rec.get("gtm_routing_status") == r["action"])
        stamped += int(same)
        if not same:
            out.append((False, f"{r['lead_id']} (HubSpot {r['crm_record_id']}): the record does not match the log"))
    out.append((stamped == len(written), f"HubSpot: {stamped} of {len(written)} written companies carry the logged stamp, route, priority and status"))
    leaked = 0
    for r in (x for x in records if x["action"] == "rejected"):
        try:
            rec = client._request("GET", f"/crm/v3/objects/companies/{r['domain']}?idProperty=clay_domain_key&properties={props}")["properties"]
        except HubSpotError as e:
            if e.status == 404:
                continue  # never in HubSpot at all
            raise
        if r["decision_id"] in (rec.get("gtm_decision_stamp") or ""):
            leaked += 1
            out.append((False, f"{r['lead_id']}: rejected, but HubSpot carries its stamp"))
    out.append((leaked == 0, "HubSpot: no rejected row carries this run's stamp"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--run", help="run id, such as n8n-123 or py-20261123T054542Z")
    group.add_argument("--latest", action="store_true", help="the newest run in the log")
    group.add_argument("--decision", help="decision id from a stamp, such as D-n8n123-04")
    group.add_argument("--stamp", help="a whole stamp copied from a HubSpot company or a Salesforce Account")
    crm = ap.add_mutually_exclusive_group()
    crm.add_argument("--hubspot", action="store_true", help="also read each written company back from HubSpot")
    crm.add_argument("--salesforce", action="store_true", help="also read each written Account back from Salesforce")
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    password = os.environ.get(PASSWORD_KEY, "")
    if not password:
        print(f"CANNOT RUN {PASSWORD_KEY} is not in .env; run scripts/setup_run_log.py first")
        return 2
    try:
        with connect(db_settings(), password) as conn:
            if args.decision or args.stamp:
                decision = args.decision
                if args.stamp:
                    m = STAMP.match(args.stamp.strip())
                    if not m:
                        print("CANNOT RUN that is not a gtm-v2 stamp")
                        return 2
                    decision = m["decision"]
                record = rows(conn, "select * from gtm_v2.decision_record where decision_id = %s", (decision,))
                if not record:
                    print(f"FAIL no log row for {decision}")
                    return 1
                print(f"select * from gtm_v2.decision_record where decision_id = '{decision}';")
                for k, v in record[0].items():
                    print(f"  {k:22} {v}")
                return 0
            run_id = args.run or rows(conn, "select run_id from gtm_v2.run_summary order by started_at desc nulls last limit 1", ())[0]["run_id"]
            records = rows(conn, "select * from gtm_v2.decision_record where run_id = %s order by row_number", (run_id,))
            summary = rows(conn, "select * from gtm_v2.run_summary where run_id = %s", (run_id,))
    except Exception as e:  # database errors: the type and message, never a value from .env
        print(f"CANNOT RUN {type(e).__name__}: {str(e).replace(password, '<hidden>')}")
        return 2
    if not records:
        print(f"FAIL no proposals logged for run {run_id}")
        return 1
    s = summary[0]
    print(f"Run {run_id}: {s['proposals']} proposals ({s['flagged']} flagged), approved {s['approved']}, changed {s['changed']}, "
          f"rejected {s['rejected']}, written {s['written']}, failed {s['failed']}. Cost US${s['total_cost_usd']} "
          f"(US${s['cost_per_decision_usd']} a decision), models {s['models']}, playbook {s['playbooks']}.")
    results = check_log(records)
    if args.hubspot:
        results += check_target(records, "hubspot")
        try:
            results += check_hubspot(records)
        except Exception as e:
            print(f"CANNOT RUN HubSpot: {type(e).__name__}: {e}")
            return 2
    if args.salesforce:
        results += check_target(records, "salesforce")
        try:
            results += check_salesforce(records)
        except Exception as e:  # SalesforceError and ConfigError messages carry no value from .env
            print(f"CANNOT RUN Salesforce: {type(e).__name__}: {e}")
            return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
