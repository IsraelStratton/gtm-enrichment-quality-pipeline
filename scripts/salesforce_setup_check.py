#!/usr/bin/env python3
"""Check the Salesforce developer org against salesforce/setup.json, signed in as the workflow is.

It signs in with the client-credentials flow (the same login n8n uses) and reads only:
  1. the sign-in works, its scope is API access only, and it runs as the API-only integration
     user, not a person's login;
  2. the API version the workflow calls is offered by the org;
  3. every custom field on Account exists with the type, length, picklist values and external-ID
     settings in setup.json, and the integration user can create and edit every field the
     engine writes;
  4. reach: the user can read, create and edit Accounts but cannot delete them, cannot create,
     edit or delete Leads, Contacts, Opportunities, Cases, Quotes, Users or the rest of the core
     list, can delete nothing at all, and can edit no other custom field on Account.

  python scripts/salesforce_setup_check.py

The values come from .env (SALESFORCE_DOMAIN, SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET)
and are never printed. Exit codes: 0 every check passed, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salesforce_client import API_VERSION, SETUP, ConfigError, SalesforceClient, SalesforceError  # noqa: E402

ALLOWED_SCOPES = {"api"}
INTEGRATION_PROFILE = SETUP["integration_user"]["profile"]
INTEGRATION_LICENCE = SETUP["integration_user"]["user_license"]
CORE_OBJECTS = ["Lead", "Contact", "Opportunity", "Case", "Quote", "User", "Task", "Event", "Campaign",
                "Contract", "Order", "Product2", "Pricebook2", "Asset"]
# Engine field -> the describe name whose create/edit rights it needs (compound Billing Address -> its parts).
WRITTEN = [f["api_name"] for f in SETUP["custom_fields"]] + list(SETUP["standard_fields_written"])

Result = tuple[bool, str]


def check_sign_in(token: dict, user: dict | None) -> list[Result]:
    scopes = set(token.get("scope", "").split())
    out = [(bool(scopes) and scopes <= ALLOWED_SCOPES, f"sign-in works; scope is {' '.join(sorted(scopes)) or '(none)'} (allowed: api only)")]
    if user is None:
        out.append((False, "could not read the signed-in user"))
        return out
    profile = (user.get("Profile") or {}).get("Name")
    licence = ((user.get("Profile") or {}).get("UserLicense") or {}).get("Name")
    out.append((profile == INTEGRATION_PROFILE and licence == INTEGRATION_LICENCE,
                f"runs as an API-only integration user (profile {profile}, licence {licence})"))
    return out


def check_version(versions: list[dict]) -> Result:
    offered = {f"v{v['version']}" for v in versions}
    return API_VERSION in offered, f"the org offers API {API_VERSION} (newest offered: v{max(versions, key=lambda v: float(v['version']))['version']})"


def check_fields(describe: dict) -> list[Result]:
    fields = {f["name"]: f for f in describe["fields"]}
    out = []
    for spec in SETUP["custom_fields"]:
        name = spec["api_name"]
        f = fields.get(name)
        if f is None:
            out.append((False, f"{name}: missing on Account"))
            continue
        problems = []
        if f["type"] != spec["describe_type"]:
            problems.append(f"type is {f['type']}, not {spec['describe_type']}")
        if "length" in spec and f.get("length") != spec["length"]:
            problems.append(f"length is {f.get('length')}, not {spec['length']}")
        if "precision" in spec and (f.get("precision"), f.get("scale")) != (spec["precision"], spec["scale"]):
            problems.append(f"precision and scale are {f.get('precision')},{f.get('scale')}, not {spec['precision']},{spec['scale']}")
        for key, flag in (("external_id", "externalId"), ("unique", "unique"), ("case_sensitive", "caseSensitive")):
            if key in spec and bool(f.get(flag)) != spec[key]:
                problems.append(f"{flag} is {bool(f.get(flag))}, not {spec[key]}")
        labels_differ = []
        if spec["setup_type"] == "Picklist":
            if not f.get("restrictedPicklist"):
                problems.append("the picklist is not restricted to its values")
            got = [v["value"] for v in f.get("picklistValues", []) if v.get("active", True)]
            want = [v["api_name"] for v in spec["values"]]
            if sorted(got) != sorted(want):
                problems.append(f"values are {got}, not {want}")
            got_labels = {v["value"]: v["label"] for v in f.get("picklistValues", [])}
            labels_differ = [v["api_name"] for v in spec["values"] if got_labels.get(v["api_name"]) not in (None, v["label"])]
        out.append((not problems, f"{name}: " + ("; ".join(problems) if problems else "as specified")
                    + (f" (labels still the codes for {len(labels_differ)} values; optional)" if labels_differ and not problems else "")))
    for name in WRITTEN:
        f = fields.get(name)
        ok = bool(f and f.get("createable") and f.get("updateable"))
        if not ok:
            out.append((False, f"{name}: the integration user cannot create and edit it (check the permission set's field access)"))
    if all(fields.get(n, {}).get("createable") and fields.get(n, {}).get("updateable") for n in WRITTEN):
        out.append((True, f"the integration user can create and edit all {len(WRITTEN)} fields the engine writes"))
    return out


def check_reach(account_describe: dict, global_describe: dict) -> tuple[list[Result], list[str]]:
    """Returns the checks and, for the record, the other objects the user can create or edit."""
    out = []
    a = account_describe
    out.append((bool(a.get("queryable") and a.get("createable") and a.get("updateable")),
                "Accounts: can read, create and edit"))
    out.append((not a.get("deletable"), "Accounts: cannot delete"))
    objects = {o["name"]: o for o in global_describe["sobjects"]}
    touched = [n for n in CORE_OBJECTS if n in objects and (objects[n].get("createable") or objects[n].get("updateable") or objects[n].get("deletable"))]
    out.append((not touched, f"cannot create, edit or delete {', '.join(CORE_OBJECTS)}" + (f" (but can: {', '.join(touched)})" if touched else "")))
    deletable = sorted(n for n, o in objects.items() if o.get("deletable"))
    out.append((not deletable, "can delete nothing in the org" + (f" (but can delete: {', '.join(deletable[:10])})" if deletable else "")))
    mine = {f["api_name"] for f in SETUP["custom_fields"]}
    extra_custom = sorted(f["name"] for f in a["fields"] if f.get("custom") and f.get("updateable") and f["name"] not in mine)
    out.append((not extra_custom, "can edit no other custom field on Account" + (f" (but can edit: {', '.join(extra_custom)})" if extra_custom else "")))
    others = sorted(n for n, o in objects.items() if n != "Account" and (o.get("createable") or o.get("updateable")))
    return out, others


def main(argv: list[str] | None = None) -> int:
    try:
        sf = SalesforceClient.from_env()
        token = sf.sign_in()
        try:
            users = sf.query(f"SELECT Id, Profile.Name, Profile.UserLicense.Name FROM User WHERE Id = '{token['user_id']}'") if token["user_id"] else []
        except SalesforceError as e:
            print(f"NOTE could not read the signed-in user: {e}")
            users = []
        results = check_sign_in(token, users[0] if users else None)
        results.append(check_version(sf.get("/services/data/")))
        account = sf.data("/sobjects/Account/describe")
        results += check_fields(account)
        reach, others = check_reach(account, sf.data("/sobjects/"))
        results += reach
    except ConfigError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except SalesforceError as e:
        print(f"CANNOT RUN {e}")
        return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    print(f"For the record: other objects this user can create or edit: {', '.join(others) if others else 'none'}.")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
