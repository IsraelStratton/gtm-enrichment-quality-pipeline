#!/usr/bin/env python3
"""Check the Salesforce developer org against salesforce/setup.json, signed in as the workflow is.

It signs in with the client-credentials flow (the same login n8n uses) and reads only:
  1. the sign-in works, its scope is API access only, and it runs as the integration user named
     in setup.json (read from Salesforce's identity URL), which cannot see profiles or permission
     sets at all (an administrator can). The profile and licence names themselves are not visible
     to this login: they are read in Setup;
  2. the API version the workflow calls is offered by the org;
  3. every custom field on Account exists with the type, length, picklist values and external-ID
     settings in setup.json, and the integration user can create and edit every field the
     engine writes;
  4. reach: the user can read, create and edit Accounts but cannot delete them; cannot create,
     edit or delete Leads, Contacts, Opportunities, Cases, Quotes or the rest of the core list;
     cannot create or delete Users (a new user needs ProfileId, which this login cannot see);
     can delete no data object (Account, the core list or any custom object); and can edit no
     other custom field on Account.

Salesforce also gives every user rights over their own items of about ninety platform objects
(posts, files, notes, list views, preferences, sessions, sharing rows on records they own), and
lets every user edit their own user record. No permission set controls these. The check lists
them for the record; it fails only if a data object is among them.

  python scripts/salesforce_setup_check.py

The values come from .env (SALESFORCE_DOMAIN, SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET)
and are never printed. Exit codes: 0 every check passed, 1 a check failed, 2 could not run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salesforce_client import API_VERSION, SETUP, ConfigError, SalesforceClient, SalesforceError  # noqa: E402

ALLOWED_SCOPES = {"api"}
USER = SETUP["integration_user"]
INTEGRATION_NAME = f"{USER['first_name']} {USER['last_name']}"
USERNAME_RE = re.compile(USER["username_pattern"], re.IGNORECASE)
# Objects that hold CRM data and are governed by object permissions. The permission set grants
# Account only; any right on these, or on any custom object, fails the check.
CORE_OBJECTS = ["Lead", "Contact", "Opportunity", "Case", "Quote", "Task", "Event", "Campaign",
                "Contract", "Order", "Product2", "Pricebook2", "Asset"]
# Seen by this login only if it is wider than the API-only integration profile allows.
SETUP_OBJECTS = ["Profile", "PermissionSet"]
# Engine field -> the describe name whose create/edit rights it needs (compound Billing Address -> its parts).
WRITTEN = [f["api_name"] for f in SETUP["custom_fields"]] + list(SETUP["standard_fields_written"])

Result = tuple[bool, str]


def check_sign_in(token: dict, identity: dict | None, sees_setup: dict[str, bool] | None = None) -> list[Result]:
    """identity: from Salesforce's identity URL. sees_setup: object name -> whether this login can query it."""
    scopes = set(token.get("scope", "").split())
    out = [(bool(scopes) and scopes <= ALLOWED_SCOPES, f"sign-in works; scope is {' '.join(sorted(scopes)) or '(none)'} (allowed: api only)")]
    if identity is None:
        out.append((False, "could not read who the sign-in runs as"))
        return out
    username = identity.get("username") or ""
    shown = re.sub(r"(?<=integration-)[^@]+", "…", username)
    out.append((identity.get("display_name") == INTEGRATION_NAME and bool(USERNAME_RE.match(username)) and identity.get("active") is True,
                f"runs as the integration user {identity.get('display_name')} ({shown}), "
                f"{'active' if identity.get('active') else 'not active'}"))
    seen = sorted(n for n, ok in (sees_setup or {}).items() if ok)
    out.append((sees_setup is not None and not seen,
                f"cannot see {' or '.join(SETUP_OBJECTS)} at all, as an API-only integration user should not "
                f"(an administrator can)" + (f" (but can see: {', '.join(seen)})" if seen else "")))
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


def is_data_object(name: str, obj: dict) -> bool:
    return name == "Account" or name == "User" or name in CORE_OBJECTS or bool(obj.get("custom")) or name.endswith("__c")


def check_users(user_describe: dict) -> Result:
    """Creating a user needs ProfileId. A login that cannot see or set it cannot create users."""
    settable = {f["name"] for f in user_describe.get("fields", []) if f.get("createable")}
    ok = "ProfileId" not in settable and not user_describe.get("deletable")
    why = [] if ok else (["it can set ProfileId"] if "ProfileId" in settable else []) + (["it can delete them"] if user_describe.get("deletable") else [])
    return ok, ("cannot create or delete Users: a new user needs ProfileId, which this login cannot set"
                + (f" (but {' and '.join(why)})" if why else ""))


def check_reach(account_describe: dict, global_describe: dict, user_describe: dict | None = None) -> tuple[list[Result], dict[str, list[str]]]:
    """Returns the checks and, for the record, what Salesforce gives every user on their own items:
    {'create_or_edit': [...], 'delete': [...]} (Account and User left out)."""
    out = []
    a = account_describe
    out.append((bool(a.get("queryable") and a.get("createable") and a.get("updateable")),
                "Accounts: can read, create and edit"))
    out.append((not a.get("deletable"), "Accounts: cannot delete"))
    objects = {o["name"]: o for o in global_describe["sobjects"]}
    touched = [n for n in CORE_OBJECTS if n in objects and (objects[n].get("createable") or objects[n].get("updateable") or objects[n].get("deletable"))]
    out.append((not touched, f"cannot create, edit or delete {', '.join(CORE_OBJECTS)}" + (f" (but can: {', '.join(touched)})" if touched else "")))
    custom = sorted(n for n, o in objects.items() if (o.get("custom") or n.endswith("__c"))
                    and (o.get("createable") or o.get("updateable") or o.get("deletable")))
    out.append((not custom, "cannot create, edit or delete any custom object" + (f" (but can: {', '.join(custom)})" if custom else "")))
    if user_describe is not None:
        out.append(check_users(user_describe))
    deletable = sorted(n for n, o in objects.items() if o.get("deletable"))
    data_deletable = [n for n in deletable if is_data_object(n, objects[n])]
    out.append((not data_deletable, "can delete no data object (Account, User, the core list, any custom object)"
                + (f" (but can delete: {', '.join(data_deletable)})" if data_deletable else "")))
    mine = {f["api_name"] for f in SETUP["custom_fields"]}
    extra_custom = sorted(f["name"] for f in a["fields"] if f.get("custom") and f.get("updateable") and f["name"] not in mine)
    out.append((not extra_custom, "can edit no other custom field on Account" + (f" (but can edit: {', '.join(extra_custom)})" if extra_custom else "")))
    record = {"create_or_edit": sorted(n for n, o in objects.items() if n not in ("Account", "User") and not is_data_object(n, o)
                                       and (o.get("createable") or o.get("updateable"))),
              "delete": [n for n in deletable if n not in data_deletable]}
    return out, record


def main(argv: list[str] | None = None) -> int:
    try:
        sf = SalesforceClient.from_env()
        token = sf.sign_in()
        try:
            identity = sf.identity()
        except SalesforceError as e:
            print(f"NOTE could not read the identity URL: {e}")
            identity = None
        results = check_sign_in(token, identity, {n: sf.can_query(n) for n in SETUP_OBJECTS})
        results.append(check_version(sf.get("/services/data/")))
        account = sf.data("/sobjects/Account/describe")
        results += check_fields(account)
        reach, record = check_reach(account, sf.data("/sobjects/"), sf.data("/sobjects/User/describe"))
        results += reach
    except ConfigError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except SalesforceError as e:
        print(f"CANNOT RUN {e}")
        return 2
    for ok, text in results:
        print(f"{'PASS' if ok else 'FAIL'} {text}")
    print("For the record, Salesforce's own per-user rights (no permission set grants them; every user can edit their own user record):")
    print(f"  create or edit their own items of {len(record['create_or_edit'])} objects: {', '.join(record['create_or_edit']) or 'none'}.")
    print(f"  delete their own items of {len(record['delete'])} objects: {', '.join(record['delete']) or 'none'}.")
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
