#!/usr/bin/env python3
"""Put a routing workflow into the local n8n through its API, and check the live copy against the file.

  python scripts/n8n_publish_routing.py --target salesforce           # create or update, then publish
  python scripts/n8n_publish_routing.py --target hubspot              # bring chapter 2's live copy in step
  python scripts/n8n_publish_routing.py --target salesforce --check   # compare only; change nothing

What it does, so nothing is clicked by hand and nothing drifts:
  1. builds the workflow with scripts/build_n8n_routing.py (the Salesforce one with the org's
     host from .env, SALESFORCE_DOMAIN), exactly as the committed file plus that host;
  2. finds each credential the file names in n8n, by name and type, and fills in its ID. It
     never reads or sends a secret: n8n keeps those;
  3. creates the workflow, or updates the one with the same name, then publishes it. n8n
     registers no webhook for a trigger without a webhook ID, and the file ships the form trigger
     without one (n8n's editor import would copy a new ID over the Form Path). So the script
     keeps the live trigger's ID, or gives a new trigger a fresh one;
  4. checks the form answers at http://localhost:5678/form/<path>.
--check reads the live workflow and reports any node, setting or connection that differs
from the file (positions and IDs aside). n8n leaves out a parameter that equals the node's
default, so a key the file sets and n8n does not hold is taken as that default; every value
n8n does hold must equal the file's, and every Code node's JavaScript must match in full.

The n8n API key is read from .env (N8N_API_KEY) and never printed.
Exit codes: 0 done (or in step), 1 the live copy differs or a check failed, 2 could not run.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from pathlib import Path

import requests
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_n8n_routing as build  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
IGNORED_NODE_KEYS = {"id", "position", "webhookId"}


class N8n:
    def __init__(self, base: str, key: str):
        self.base = base.rstrip("/")
        self.headers = {"X-N8N-API-KEY": key, "accept": "application/json"}

    def call(self, method: str, path: str, body: dict | None = None):
        resp = requests.request(method, f"{self.base}/api/v1{path}", headers=self.headers, json=body, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f"n8n API {method} {path.split('?')[0]}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json() if resp.content else {}

    def all(self, path: str) -> list[dict]:
        items, cursor = [], None
        while True:
            page = self.call("GET", f"{path}?limit=100" + (f"&cursor={cursor}" if cursor else ""))
            items += page.get("data", [])
            cursor = page.get("nextCursor")
            if not cursor:
                return items


def with_credential_ids(wf: dict, credentials: list[dict]) -> dict:
    """Fill each node's credential ID from n8n, matched by name and type."""
    by_key = {(c["type"], c["name"]): c["id"] for c in credentials}
    out = copy.deepcopy(wf)
    missing = []
    for node in out["nodes"]:
        for cred_type, cred in (node.get("credentials") or {}).items():
            cid = by_key.get((cred_type, cred["name"]))
            if cid is None:
                missing.append(f"'{cred['name']}' ({cred_type}), used by {node['name']}")
            cred["id"] = cid
    if missing:
        raise LookupError("these n8n credentials do not exist yet: " + "; ".join(missing))
    return out


def comparable(wf: dict) -> dict:
    nodes = {}
    for n in wf["nodes"]:
        n = {k: v for k, v in n.items() if k not in IGNORED_NODE_KEYS}
        for cred in (n.get("credentials") or {}).values():
            cred.pop("id", None)
        nodes[n["name"]] = n
    return {"name": wf["name"], "nodes": nodes, "connections": wf["connections"],
            "executionOrder": (wf.get("settings") or {}).get("executionOrder")}


def matches(live, file) -> bool:
    """live as n8n holds it, file as built. n8n drops parameters that equal their default."""
    if isinstance(live, dict) and isinstance(file, dict):
        return all(k in file and matches(v, file[k]) for k, v in live.items())
    if isinstance(live, list) and isinstance(file, list):
        return len(live) == len(file) and all(matches(x, y) for x, y in zip(live, file))
    return live == file


def differences(live: dict, wanted: dict) -> list[str]:
    a, b = comparable(live), comparable(wanted)
    out = []
    if a["name"] != b["name"]:
        out.append("the workflow name")
    for name in sorted(set(a["nodes"]) | set(b["nodes"])):
        if name not in a["nodes"]:
            out.append(f"node {name}: missing in n8n")
        elif name not in b["nodes"]:
            out.append(f"node {name}: in n8n but not in the file")
        else:
            x, y = a["nodes"][name], b["nodes"][name]
            keys = sorted(k for k in set(x) | set(y) if not matches(x.get(k), y.get(k)))
            code = (x.get("parameters") or {}).get("jsCode") != (y.get("parameters") or {}).get("jsCode")
            if keys or code:
                out.append(f"node {name}: {', '.join(keys) or 'jsCode'} differ")
    if a["connections"] != b["connections"]:
        out.append("the connections")
    if a["executionOrder"] != b["executionOrder"]:
        out.append("the execution order setting")
    return out


def request_body(wanted: dict, live: dict | None, trigger: str = "Upload CSV") -> dict:
    """What is sent to n8n: the file's workflow, with the form trigger's webhook ID kept from the
    live copy or, for a trigger that has none, a new one (n8n registers no webhook without it)."""
    body = copy.deepcopy({k: wanted[k] for k in ("name", "nodes", "connections", "settings")})
    live_id = next((n.get("webhookId") for n in (live or {}).get("nodes", []) if n["name"] == trigger), None)
    next(n for n in body["nodes"] if n["name"] == trigger)["webhookId"] = live_id or str(uuid.uuid4())
    return body


def wanted_workflow(target: str) -> dict:
    if target == "salesforce":
        return build.build("salesforce", build.salesforce_host_from_env())
    return build.build(target)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", choices=sorted(build.TARGETS), required=True)
    ap.add_argument("--check", action="store_true", help="compare the live workflow with the file; change nothing")
    args = ap.parse_args(argv)
    env = dotenv_values(REPO / ".env")
    key = (env.get("N8N_API_KEY") or "").strip()
    base = (env.get("N8N_BASE_URL") or os.environ.get("N8N_BASE_URL") or "http://localhost:5678").strip()
    if not key:
        print("CANNOT RUN N8N_API_KEY is not in .env")
        return 2
    n8n = N8n(base, key)
    t = build.TARGETS[args.target]
    try:
        wanted = with_credential_ids(wanted_workflow(args.target), n8n.all("/credentials"))
        found = [w for w in n8n.all("/workflows") if w["name"] == t["name"]]
        if len(found) > 1:
            print(f"CANNOT RUN {len(found)} workflows in n8n are named '{t['name']}'; keep one")
            return 2
        live = n8n.call("GET", f"/workflows/{found[0]['id']}") if found else None
        if args.check:
            if live is None:
                print(f"NOT IN N8N '{t['name']}'")
                return 1
            diff = differences(live, wanted)
            for d in diff:
                print(f"DIFFERS {d}")
            print(f"{'In step' if not diff else 'Out of step'}: the live '{t['name']}' {'matches' if not diff else 'does not match'} "
                  f"{t['output'].relative_to(REPO)}{' (plus the org host from .env)' if args.target == 'salesforce' else ''}; "
                  f"{'published' if live.get('active') else 'not published'}.")
            return 0 if not diff and live.get("active") else 1
        body = request_body(wanted, live)
        if live is not None:
            saved = n8n.call("PUT", f"/workflows/{live['id']}", body)
            verb = "Updated"
        else:
            saved = n8n.call("POST", "/workflows", body)
            verb = "Created"
        n8n.call("POST", f"/workflows/{saved['id']}/activate", {})
        form = requests.get(f"{base}/form/{t['form_path']}", timeout=15)
        print(f"{verb} and published '{t['name']}' ({len(body['nodes'])} nodes). Form /form/{t['form_path']}: HTTP {form.status_code}.")
        return 0 if form.status_code == 200 else 1
    except (LookupError, ValueError) as e:
        print(f"CANNOT RUN {e}")
        return 2
    except (RuntimeError, requests.RequestException) as e:
        print(f"CANNOT RUN {str(e).replace(key, '<hidden>')}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
