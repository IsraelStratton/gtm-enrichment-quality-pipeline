#!/usr/bin/env python3
"""Write the chapter 5 demo quotes to the Salesforce developer org, or put them back in the queue.

  python scripts/seed_quotes.py --admin     # once, while Israel has the CLI signed in as the admin
  python scripts/seed_quotes.py --reset     # later, with the desk's own login: back to Needs Review
  python scripts/seed_quotes.py --plan      # print what would be written; touch nothing

--admin (chapter-5-build.md, part K). The desk user can read and decide quotes but cannot create
them, on purpose, so the made-up data is written once by the admin, through the Salesforce CLI
login Israel makes with `sf org login web --alias gtm-v2-admin` (as in INIT-164). This script
has the CLI make each call, so the admin's token never leaves the CLI. It writes:
  - the five products in salesforce/quote-desk-setup.json, each with a standard price;
  - one opportunity per demo case, named "GTM v2 quote desk: Q-00NN", on the made-up Account
    the case names (made in chapter 4), with the case's amount and close date;
  - one quote per demo case, matched on GTM_Case_Id__c, with its lines, in Needs Review.
Dates are counted from the day it runs (the case's days from as_of). No contact, no person.
Running it again puts the same values back; it deletes only the seeded quotes' own lines
before writing them again.

--reset uses the desk's login (SALESFORCE_DESK_*), which can change only a quote's status and the
two desk fields: it sets every demo quote back to Needs Review and clears the desk reason and
stamp, so a demo can be run again. It cannot change prices or dates.

Exit codes: 0 done, 1 Salesforce refused something, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salesforce_client import ConfigError, SalesforceClient, SalesforceError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SETUP = json.loads((REPO / "salesforce" / "quote-desk-setup.json").read_text(encoding="utf-8"))
CASES = json.loads((REPO / "skins" / "quote-desk" / "cases.json").read_text(encoding="utf-8"))
API = SETUP["api_version"]
PREFIX = SETUP["opportunity_name_prefix"]
STAGE = "Proposal/Price Quote"
PRODUCTS = {p["code"]: p for p in SETUP["products"]}


def demo_cases() -> list[dict]:
    return [c for c in CASES["cases"] if c["demo"]]


def soql_text(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def plan(cases: list[dict], today: date) -> list[dict]:
    """What the admin seed writes for each case. Pure: tested without Salesforce."""
    out = []
    for c in cases:
        at = lambda days: None if days is None else (today + timedelta(days=int(days))).isoformat()  # noqa: E731
        out.append({
            "case_id": c["case_id"],
            "account_domain": c["account_domain"],
            "opportunity": {"Name": f"{PREFIX} {c['case_id']}", "StageName": STAGE, "CloseDate": at(c["closes_in_days"]),
                            "Amount": c["opportunity_amount"]},
            "quote": {"Name": c["quote_name"], "GTM_Case_Id__c": c["case_id"], "Status": SETUP["status_values"]["intake"],
                      "ExpirationDate": at(c["expires_in_days"]), "BillingCountry": c["billing_country"] or None,
                      "GTM_Payment_Terms_Days__c": c["payment_terms_days"], "GTM_Term_Months__c": c["term_months"],
                      "GTM_Special_Terms__c": c["special_terms"] or None, "GTM_Rep_Note__c": c["rep_note"] or None,
                      "GTM_Desk_Reason__c": None, "GTM_Desk_Stamp__c": None},
            "lines": [{"product": l["product"], "Quantity": l["quantity"], "UnitPrice": l["unit_price"],
                       "Discount": l["discount_pct"] or None} for l in c["lines"]],
        })
    return out


class Admin:
    """The admin's REST calls, made by the Salesforce CLI itself (`sf api request rest`), so the
    admin's token never leaves the CLI: this script never sees it. Bodies go in on stdin, so no
    value is on a command line."""

    def __init__(self, alias: str, runner=subprocess.run):
        self.sf = shutil.which("sf")
        if not self.sf:
            raise ConfigError("the Salesforce CLI (sf) is not installed")
        self.alias, self.runner = alias, runner
        out = runner([self.sf, "org", "display", "--target-org", alias, "--json"], capture_output=True, text=True, check=False)
        try:
            result = json.loads(out.stdout).get("result") or {}
        except json.JSONDecodeError:
            result = {}
        if result.get("connectedStatus") != "Connected":
            raise ConfigError(f"the CLI has no live login called {alias}: Israel runs `sf org login web --alias {alias}` first")
        self.username = result.get("username") or ""  # kept for queries, never printed

    @staticmethod
    def parse(stdout: str) -> tuple[int, object]:
        """The CLI's --include output: a status line, the headers, then the body (CLI 2.159 puts no blank
        line between them, older ones do), so the body starts at the first line that opens JSON."""
        lines = stdout.replace("\r\n", "\n").split("\n")
        first = lines[0].split() if lines else []
        status = int(first[1]) if len(first) > 1 and first[1].isdigit() else 0
        start = next((i for i, line in enumerate(lines[1:], 1) if line.startswith(("{", "["))), len(lines))
        body = "\n".join(lines[start:])
        try:
            payload = json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            payload = body.strip()[:300]
        return status, payload

    def call(self, method: str, path: str, body=None, ok=(200, 201, 204)):
        args = [self.sf, "api", "request", "rest", f"/services/data/{API}{path}", "--target-org", self.alias, "--method", method, "--include"]
        if body is not None:
            args += ["--body", "-"]
        out = self.runner(args, input=json.dumps(body) if body is not None else None, capture_output=True, text=True, check=False)
        status, payload = self.parse(out.stdout)
        if status not in ok:
            err = payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], dict) else {}
            code = err.get("errorCode")
            raise SalesforceError(f"{method} {path.split('?')[0]}: {code + ': ' if code else ''}{err.get('message') or f'HTTP {status}'}"[:300], status, code)
        return payload

    def query(self, soql: str) -> list[dict]:
        return self.call("GET", f"/query?q={quote(soql)}")["records"]

    def one(self, soql: str) -> dict | None:
        rows = self.query(soql)
        return rows[0] if rows else None


def seed(admin: Admin, items: list[dict]) -> list[str]:
    done = []
    book = admin.one("SELECT Id, IsActive FROM Pricebook2 WHERE IsStandard = true")
    if not book:
        raise SalesforceError("the org has no standard price book")
    if not book["IsActive"]:
        admin.call("PATCH", f"/sobjects/Pricebook2/{book['Id']}", {"IsActive": True})
        done.append("standard price book switched on")
    entries = {}
    for code, p in PRODUCTS.items():
        prod = admin.one(f"SELECT Id FROM Product2 WHERE ProductCode = {soql_text(code)}")
        pid = prod["Id"] if prod else admin.call("POST", "/sobjects/Product2", {
            "Name": p["name"], "ProductCode": code, "IsActive": True,
            "Description": "Made up for the GTM v2 quote desk (chapter 5)."})["id"]
        entry = admin.one(f"SELECT Id, UnitPrice FROM PricebookEntry WHERE Pricebook2Id = {soql_text(book['Id'])} AND Product2Id = {soql_text(pid)}")
        if entry is None:
            entry = {"Id": admin.call("POST", "/sobjects/PricebookEntry", {"Pricebook2Id": book["Id"], "Product2Id": pid,
                                                                          "UnitPrice": p["list_price"], "IsActive": True})["id"]}
        elif float(entry["UnitPrice"]) != float(p["list_price"]):
            admin.call("PATCH", f"/sobjects/PricebookEntry/{entry['Id']}", {"UnitPrice": p["list_price"]})
        entries[code] = entry["Id"]
    done.append(f"{len(entries)} products with standard prices")
    for it in items:
        acct = admin.one(f"SELECT Id FROM Account WHERE Clay_Domain_Key__c = {soql_text(it['account_domain'])}")
        if not acct:
            raise SalesforceError(f"{it['case_id']}: no Account with Clay domain key {it['account_domain']} (made in chapter 4)")
        opp_fields = dict(it["opportunity"], AccountId=acct["Id"], Pricebook2Id=book["Id"])
        opp = admin.one(f"SELECT Id FROM Opportunity WHERE Name = {soql_text(it['opportunity']['Name'])}")
        if opp:
            admin.call("PATCH", f"/sobjects/Opportunity/{opp['Id']}", opp_fields)
            opp_id = opp["Id"]
        else:
            opp_id = admin.call("POST", "/sobjects/Opportunity", opp_fields)["id"]
        existing = admin.one(f"SELECT Id FROM Quote WHERE GTM_Case_Id__c = {soql_text(it['case_id'])}")
        if existing:
            qid = existing["Id"]
            admin.call("PATCH", f"/sobjects/Quote/{qid}", it["quote"])
            for line in admin.query(f"SELECT Id FROM QuoteLineItem WHERE QuoteId = {soql_text(qid)}"):
                admin.call("DELETE", f"/sobjects/QuoteLineItem/{line['Id']}")
        else:
            qid = admin.call("POST", "/sobjects/Quote", dict(it["quote"], OpportunityId=opp_id, Pricebook2Id=book["Id"]))["id"]
        for line in it["lines"]:
            body = {k: v for k, v in line.items() if k != "product" and v is not None}
            admin.call("POST", "/sobjects/QuoteLineItem", dict(body, QuoteId=qid, PricebookEntryId=entries[line["product"]]))
        done.append(f"{it['case_id']}: opportunity and quote with {len(it['lines'])} line(s), in {it['quote']['Status']}")
    return done


def reset(client: SalesforceClient, cases: list[dict]) -> list[str]:
    ids = ", ".join(soql_text(c["case_id"]) for c in cases)
    rows = client.query(f"SELECT Id, GTM_Case_Id__c FROM Quote WHERE GTM_Case_Id__c IN ({ids})")
    if not rows:
        return ["no demo quotes found: run --admin first"]
    records = [{"attributes": {"type": "Quote"}, "id": r["Id"], "Status": SETUP["status_values"]["intake"],
                "GTM_Desk_Reason__c": None, "GTM_Desk_Stamp__c": None} for r in rows]
    _, reply = client.send("PATCH", "/composite/sobjects", {"allOrNone": False, "records": records})
    bad = [r for r in reply if not r.get("success")]
    if bad:
        raise SalesforceError(f"{len(bad)} quote(s) not reset: {bad[0].get('errors')}"[:300])
    return [f"{len(rows)} demo quotes back in {SETUP['status_values']['intake']}, desk reason and stamp cleared"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--admin", action="store_true", help="write the products, opportunities and quotes (admin CLI login)")
    g.add_argument("--reset", action="store_true", help="put the demo quotes back in Needs Review (the desk's login)")
    g.add_argument("--plan", action="store_true", help="print what --admin would write; touch nothing")
    args = ap.parse_args(argv)
    items = plan(demo_cases(), date.today())
    try:
        if args.plan:
            print(json.dumps(items, indent=2))
            return 0
        lines = seed(Admin(SETUP["admin_cli_alias"]), items) if args.admin else reset(SalesforceClient.from_env(login="desk"), demo_cases())
    except ConfigError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except (SalesforceError, requests.RequestException) as e:  # messages carry Salesforce's code, never a token
        print(f"FAIL {e}")
        return 1
    for line in lines:
        print(f"DONE {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
