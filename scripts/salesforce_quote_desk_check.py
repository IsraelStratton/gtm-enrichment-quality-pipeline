#!/usr/bin/env python3
"""Check the org against salesforce/quote-desk-setup.json, signed in as the quote desk is.

It signs in with the client-credentials flow of "GTM v2 quote desk (n8n)", the same login n8n uses
for chapter 5, and checks:
  1. the sign-in works, its scope is API access only, and it runs as the GTM Quote Desk user
     (Salesforce's identity URL; the username matches the pattern and, when set, SALESFORCE_DESK_USER);
  2. the API version the workflow calls is offered;
  3. every custom field on Quote exists with the type, length and external-ID setting in the file;
  4. the desk can read every demo quote with its lines, its opportunity's amount and close date,
     and its account's name, through the workflow's own query (engine/quotes.js DESK_SOQL);
  5. the desk can edit a quote's status and the two desk fields, proved by writing one quote's own
     current values back to it (nothing changes);
  6. what it cannot do: create or delete a quote; edit any other GTM field on a quote; see a
     quote's contact, email, phone or fax at all; create, edit or delete opportunities, accounts,
     products, price books, price book entries or quote lines; touch leads, contacts or cases.
     Salesforce lets anyone who can edit a quote change its lines once they can see price books
     (found 24/11/2026), so the quote-line rule is checked on its own.

  python scripts/salesforce_quote_desk_check.py

The values come from .env (SALESFORCE_DOMAIN, SALESFORCE_DESK_CLIENT_ID, SALESFORCE_DESK_CLIENT_SECRET,
SALESFORCE_DESK_USER) and are never printed. Exit codes: 0 every check passed, 1 a check failed,
2 could not run.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salesforce_client import API_VERSION, ConfigError, SalesforceClient, SalesforceError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SETUP = json.loads((REPO / "salesforce" / "quote-desk-setup.json").read_text(encoding="utf-8"))
CASES = json.loads((REPO / "skins" / "quote-desk" / "cases.json").read_text(encoding="utf-8"))
USER = SETUP["desk_user"]
DESK_NAME = f"{USER['first_name']} {USER['last_name']}"
USERNAME_RE = re.compile(USER["username_pattern"], re.IGNORECASE)
EDIT = set(SETUP["standard_fields_edited"]["Quote"]) | {f["api_name"] for f in SETUP["custom_fields"] if f["desk_access"] == "edit"}
NEVER_SEEN = SETUP["fields_never_read"]["Quote"]
READ_ONLY_OBJECTS = ["Opportunity", "Account", "Product2", "Pricebook2", "PricebookEntry", "QuoteLineItem"]
NO_ACCESS_OBJECTS = ["Lead", "Contact", "Case"]
Result = tuple[bool, str]


def desk_soql() -> str:
    out = subprocess.run(["node", "-e", "process.stdout.write(require(process.argv[1]).DESK_SOQL)", str(REPO / "engine" / "quotes.js")],
                         capture_output=True, text=True, check=True)
    return out.stdout


def check_sign_in(token: dict, identity: dict, expected_user: str | None) -> list[Result]:
    scopes = set(token.get("scope", "").split())
    out = [(scopes == {"api"}, f"sign-in works; scope is {' '.join(sorted(scopes)) or '(none)'} (allowed: api only)")]
    name_ok = identity.get("display_name") == DESK_NAME and bool(USERNAME_RE.match(identity.get("username") or ""))
    if expected_user:
        name_ok = name_ok and (identity.get("username") or "").lower() == expected_user.lower()
    out.append((name_ok and identity.get("active") is True, f"runs as {identity.get('display_name')}, active {identity.get('active')}"
                + ("" if name_ok else f" (expected {DESK_NAME}, username like {USER['username_pattern']})")))
    return out


def check_fields(describe: dict) -> list[Result]:
    fields = {f["name"]: f for f in describe["fields"]}
    out = []
    for spec in SETUP["custom_fields"]:
        f = fields.get(spec["api_name"])
        if f is None:
            out.append((False, f"Quote.{spec['api_name']} is missing, or the desk cannot read it"))
            continue
        problems = []
        if f["type"] != spec["describe_type"]:
            problems.append(f"type {f['type']}, not {spec['describe_type']}")
        if "length" in spec and f.get("length") != spec["length"]:
            problems.append(f"length {f.get('length')}, not {spec['length']}")
        if "precision" in spec and (f.get("precision"), f.get("scale")) != (spec["precision"], spec["scale"]):
            problems.append(f"precision {f.get('precision')},{f.get('scale')}, not {spec['precision']},{spec['scale']}")
        if spec.get("external_id") and not (f.get("externalId") and f.get("unique")):
            problems.append("not a unique external ID")
        want_edit = spec["api_name"] in EDIT
        if bool(f.get("updateable")) != want_edit:
            problems.append("the desk can edit it" if f.get("updateable") else "the desk cannot edit it")
        out.append((not problems, f"Quote.{spec['api_name']}: {', '.join(problems) if problems else 'as specified'}"))
    status = fields.get("Status")
    values = {v["value"] for v in (status or {}).get("picklistValues", []) if v.get("active")}
    need = set(SETUP["status_values"].values())
    out.append((bool(status) and status.get("updateable") and need <= values,
                f"Quote.Status: the desk can edit it, and it offers {', '.join(sorted(need & values)) or 'none'} of {', '.join(sorted(need))}"))
    hidden = [n for n in NEVER_SEEN if n in fields]
    out.append((not hidden, "the desk cannot see a quote's contact, email, phone or fax" + (f" (but it sees {', '.join(hidden)})" if hidden else "")))
    return out


def check_quote_object(describe: dict) -> Result:
    ok = describe.get("queryable") and describe.get("updateable") and not describe.get("createable") and not describe.get("deletable")
    return (bool(ok), f"Quote: read and edit only (create {describe.get('createable')}, delete {describe.get('deletable')})")


def check_other_objects(describes: dict[str, dict | None]) -> list[Result]:
    out = []
    for name in READ_ONLY_OBJECTS:
        d = describes.get(name) or {}
        ok = bool(d.get("queryable")) and not (d.get("createable") or d.get("updateable") or d.get("deletable"))
        out.append((ok, f"{name}: read only (create {d.get('createable')}, edit {d.get('updateable')}, delete {d.get('deletable')})"))
    for name in NO_ACCESS_OBJECTS:
        d = describes.get(name)
        ok = d is None or not (d.get("queryable") or d.get("createable") or d.get("updateable") or d.get("deletable"))
        out.append((ok, f"{name}: no access" + ("" if ok else " (the desk has rights on it)")))
    return out


def check_queue(records: list[dict]) -> list[Result]:
    demo = {c["case_id"]: c for c in CASES["cases"] if c["demo"]}
    seen = {r.get("GTM_Case_Id__c"): r for r in records}
    missing = sorted(set(demo) - set(seen))
    out = [(not missing, f"the desk reads {len(set(demo) & set(seen))} of {len(demo)} demo quotes in Needs Review"
            + (f" (missing {', '.join(missing)})" if missing else ""))]
    full = [cid for cid, r in seen.items() if cid in demo and (r.get("QuoteLineItems") or {}).get("records")
            and (r.get("Opportunity") or {}).get("Amount") is not None and (r.get("Opportunity") or {}).get("CloseDate")
            and (r.get("Account") or {}).get("Name")]
    out.append((len(full) == len(set(demo) & set(seen)) and not missing,
                f"{len(full)} of them come with their lines, the opportunity's amount and close date, and the account's name"))
    lines = sum(len(c["lines"]) for c in demo.values())
    got = sum(len((seen[c].get("QuoteLineItems") or {}).get("records") or []) for c in demo if c in seen)
    out.append((got == lines, f"{got} of {lines} quote lines read"))
    return out


def edit_probe(sf: SalesforceClient, record: dict) -> Result:
    """Write one quote's own values back to it: proves the edit right and changes nothing."""
    body = {"Status": record["Status"], "GTM_Desk_Reason__c": record.get("GTM_Desk_Reason__c"), "GTM_Desk_Stamp__c": record.get("GTM_Desk_Stamp__c")}
    try:
        status, _ = sf.send("PATCH", f"/sobjects/Quote/{record['Id']}", body)
        return (status == 204, f"the desk can edit a quote's status and desk fields (wrote {record.get('GTM_Case_Id__c')}'s own values back, HTTP {status})")
    except SalesforceError as e:
        return (False, f"the desk cannot edit a quote: {e}")


def main(argv: list[str] | None = None) -> int:
    expected_user = (dotenv_values(REPO / ".env").get("SALESFORCE_DESK_USER") or "").strip() or None
    try:
        sf = SalesforceClient.from_env(login="desk")
        token = sf.sign_in()
        results = check_sign_in(token, sf.identity(), expected_user)
        versions = sf.get("/services/data/")
        results.append((any(f"v{v['version']}" == API_VERSION for v in versions), f"API {API_VERSION} offered (newest v{versions[-1]['version']})"))
        quote_describe = sf.data("/sobjects/Quote/describe")
        results.append(check_quote_object(quote_describe))
        results += check_fields(quote_describe)
        describes = {n: sf.data(f"/sobjects/{n}/describe", ok_404=True) for n in READ_ONLY_OBJECTS + NO_ACCESS_OBJECTS}
        results += check_other_objects(describes)
        records = sf.query(desk_soql().replace("Status, ExpirationDate", "Status, GTM_Desk_Reason__c, GTM_Desk_Stamp__c, ExpirationDate", 1))
        results += check_queue(records)
        if records:
            results.append(edit_probe(sf, records[0]))
        else:
            results.append((False, "no quote in Needs Review to prove the edit right on: run scripts/seed_quotes.py --admin"))
    except ConfigError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except SalesforceError as e:  # Salesforce's code and message, never a value from .env
        print(f"CANNOT RUN {e}")
        return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    passed = sum(ok for ok, _ in results)
    print(f"{passed} of {len(results)} checks passed.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
