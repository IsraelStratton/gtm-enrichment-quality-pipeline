#!/usr/bin/env python3
"""Check a finished routing run against its log and, optionally, HubSpot.

  python scripts/check_run.py --latest                    # the newest run in the log
  python scripts/check_run.py --run n8n-123 --hubspot     # A1.1: count the writes, find a stamp on each in HubSpot
  python scripts/check_run.py --decision D-n8n123-04      # A1.2: one query from a stamp to its full record
  python scripts/check_run.py --stamp "gtm-v2 D-n8n123-04 | ..."

What it checks for a run:
  - every proposal has a person's decision (approved, changed or rejected);
  - every decision that led to a write carries a stamp naming the decision, model, playbook,
    action, reviewer and time, and every rejected one has none;
  - a changed row keeps both what the AI proposed and what the person chose (A1.3);
  - with --hubspot: each written company in HubSpot carries the same stamp, route, priority
    and status as the log, and no rejected row carries this run's stamp.

It reads the log through the pipeline login (views only) and HubSpot with the read scope.
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
    out.append((not failed, f"{len(writes) - len(failed)} of {len(writes)} writes reached HubSpot"
                + "".join(f"; {r['lead_id']}: {r['crm_error']}" for r in failed)))
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
    group.add_argument("--stamp", help="a whole stamp copied from a HubSpot record")
    ap.add_argument("--hubspot", action="store_true", help="also read each written company back from HubSpot")
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
        try:
            results += check_hubspot(records)
        except Exception as e:
            print(f"CANNOT RUN HubSpot: {type(e).__name__}: {e}")
            return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
