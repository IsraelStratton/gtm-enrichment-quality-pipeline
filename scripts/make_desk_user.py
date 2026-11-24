#!/usr/bin/env python3
"""Part E of docs/v2/chapter-5-build.md: make the API-only desk user and give it the permission set.

With the admin CLI login (alias gtm-v2-admin, signed in by Israel). Safe to run again: it finds the
user if it is already there.

  - checks a Salesforce licence is free first, and stops if not: it never buys one;
  - makes "GTM Quote Desk" on the profile "GTM v2 API only" (API only: no screens, no password),
    with a username gtm-v2-quote-desk-<4 random letters or digits>@example.com, and Israel's own
    email address, time zone and language copied inside the org from his admin user. Created
    through the API, so Salesforce sends no welcome or password email;
  - assigns the permission set "GTM v2 quote desk";
  - writes the username to .env (SALESFORCE_DESK_USER) and to .prepush-private.local, and prints
    neither it nor any ID.

  python scripts/make_desk_user.py

Exit codes: 0 done, 1 Salesforce refused or no licence is free, 2 could not run.
"""
from __future__ import annotations

import json
import re
import secrets
import string
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salesforce_client import ConfigError, SalesforceError  # noqa: E402
from seed_quotes import Admin, soql_text  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".env"
PRIVATE = REPO / ".prepush-private.local"
SETUP = json.loads((REPO / "salesforce" / "quote-desk-setup.json").read_text(encoding="utf-8"))
USER = SETUP["desk_user"]
ENV_KEY = "SALESFORCE_DESK_USER"


def new_username() -> str:
    tail = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    name = f"gtm-v2-quote-desk-{tail}@example.com"
    assert re.match(USER["username_pattern"], name)
    return name


def save_username(username: str, env: Path = ENV, private: Path = PRIVATE) -> None:
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(rf"^{ENV_KEY}=", text, re.M):
        text = re.sub(rf"^{ENV_KEY}=.*$", f"{ENV_KEY}={username}", text, flags=re.M)
    else:
        text += ("" if text.endswith("\n") or not text else "\n") + f"{ENV_KEY}={username}\n"
    env.write_text(text, encoding="utf-8")
    listed = private.read_text(encoding="utf-8") if private.exists() else ""
    if username not in listed:
        private.write_text(listed + ("" if listed.endswith("\n") or not listed else "\n")
                           + f"{username}  # chapter 5: the quote desk's Salesforce username\n", encoding="utf-8")


def main() -> int:
    try:
        admin = Admin(SETUP["admin_cli_alias"])
        profile = admin.one(f"SELECT Id FROM Profile WHERE Name = {soql_text(USER['profile'])}")
        if not profile:
            print(f"FAIL there is no profile named {USER['profile']} (part C)")
            return 1
        pset = admin.one(f"SELECT Id FROM PermissionSet WHERE Name = {soql_text(SETUP['permission_set']['api_name'])}")
        if not pset:
            print(f"FAIL there is no permission set {SETUP['permission_set']['api_name']} (part D)")
            return 1
        existing = admin.query(f"SELECT Id, Username, IsActive FROM User WHERE FirstName = {soql_text(USER['first_name'])} "
                               f"AND LastName = {soql_text(USER['last_name'])} AND ProfileId = {soql_text(profile['Id'])}")
        if len(existing) > 1:
            print(f"FAIL {len(existing)} users are called {USER['first_name']} {USER['last_name']}; keep one")
            return 1
        known = (dotenv_values(ENV).get(ENV_KEY) or "").strip() if ENV.exists() else ""
        if existing:
            user = existing[0]
            username = user["Username"]
            made = "found"
        else:
            lic = admin.one(f"SELECT TotalLicenses, UsedLicenses FROM UserLicense WHERE Name = {soql_text(USER['user_license'])}")
            if not lic or lic["UsedLicenses"] >= lic["TotalLicenses"]:
                print(f"FAIL no free {USER['user_license']} licence: stop and tell Israel (nothing is bought)")
                return 1
            me = admin.one(f"SELECT Email, TimeZoneSidKey, LocaleSidKey, EmailEncodingKey, LanguageLocaleKey FROM User "
                           f"WHERE Username = {soql_text(admin.username)}")
            username = known if known and re.match(USER["username_pattern"], known) else new_username()
            body = {"FirstName": USER["first_name"], "LastName": USER["last_name"], "Alias": USER["alias"], "Username": username,
                    "ProfileId": profile["Id"], **{k: me[k] for k in ("Email", "TimeZoneSidKey", "LocaleSidKey", "EmailEncodingKey", "LanguageLocaleKey")}}
            user = {"Id": admin.call("POST", "/sobjects/User", body)["id"], "IsActive": True}
            made = "made"
        assigned = admin.one(f"SELECT Id FROM PermissionSetAssignment WHERE AssigneeId = {soql_text(user['Id'])} "
                             f"AND PermissionSetId = {soql_text(pset['Id'])}")
        if not assigned:
            admin.call("POST", "/sobjects/PermissionSetAssignment", {"AssigneeId": user["Id"], "PermissionSetId": pset["Id"]})
        save_username(username)
    except ConfigError as e:
        print(f"CANNOT RUN {e}")
        return 2
    except (SalesforceError, requests.RequestException) as e:  # Salesforce's code and message, never a token
        print(f"FAIL {e}")
        return 1
    print(f"DONE user {USER['first_name']} {USER['last_name']} {made}, active {user.get('IsActive')}, on {USER['profile']}, "
          f"with {SETUP['permission_set']['label']} {'already ' if assigned else ''}assigned. "
          f"Username saved to .env ({ENV_KEY}) and .prepush-private.local; not printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
