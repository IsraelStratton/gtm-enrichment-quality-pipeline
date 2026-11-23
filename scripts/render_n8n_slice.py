#!/usr/bin/env python3
"""Make the importable n8n slice workflow from the public template, and optionally update n8n.

The template in slice/n8n/slice-workflow.json holds placeholders, so the public
repo never carries the tracker ID or any credential ID:

  SPREADSHEET_ID           <- SLICE_TRACKER_ID from .env
  GOOGLE_CREDENTIAL_ID     <- n8n credential "Google least reach gtm-pipeline" (Google OAuth2 API)
  SLICE_KEY_CREDENTIAL_ID  <- n8n credential "Slice webhook key (n8n)" (Header Auth)

Credential IDs are looked up in n8n by name (needs N8N_API_KEY), or read from
N8N_GOOGLE_CREDENTIAL_ID and N8N_SLICE_KEY_CREDENTIAL_ID in .env.

  python scripts/render_n8n_slice.py            # write slice/n8n/slice-workflow.local.json (git-ignored)
  python scripts/render_n8n_slice.py --update   # also replace the live workflow of the same name, and publish it

Exit codes: 0 done, 1 n8n API failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "slice" / "n8n" / "slice-workflow.json"
OUTPUT = REPO / "slice" / "n8n" / "slice-workflow.local.json"
SHEET_PLACEHOLDER = "SPREADSHEET_ID"
CREDENTIALS = {
    # placeholder: (credential name in n8n, credential type, .env override)
    "GOOGLE_CREDENTIAL_ID": ("Google least reach gtm-pipeline", "googleOAuth2Api", "N8N_GOOGLE_CREDENTIAL_ID"),
    "SLICE_KEY_CREDENTIAL_ID": ("Slice webhook key (n8n)", "httpHeaderAuth", "N8N_SLICE_KEY_CREDENTIAL_ID"),
}
CRED_PLACEHOLDER = "GOOGLE_CREDENTIAL_ID"
CRED_NAME, CRED_TYPE = CREDENTIALS[CRED_PLACEHOLDER][:2]
_SHEET_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")


class ConfigError(Exception):
    pass


def render(template: dict, tracker_id: str, credential_ids: dict[str, str]) -> dict:
    if not _SHEET_ID.match(tracker_id or ""):
        raise ConfigError("SLICE_TRACKER_ID is missing or does not look like a Google Sheets ID")
    wf = copy.deepcopy(template)
    filled = 0
    for node in wf["nodes"]:
        params = node.get("parameters", {})
        if SHEET_PLACEHOLDER in params.get("url", ""):
            params["url"] = params["url"].replace(SHEET_PLACEHOLDER, tracker_id)
            filled += 1
        for cred in (node.get("credentials") or {}).values():
            if cred.get("id") in CREDENTIALS:
                real = credential_ids.get(cred["id"])
                if not real or real in CREDENTIALS:
                    raise ConfigError(f"no n8n credential ID for {CREDENTIALS[cred['id']][0]!r}")
                cred["id"] = real
    if filled != 1:
        raise ConfigError(f"expected one tracker URL placeholder, found {filled}")
    return wf


def _api(base_url: str, api_key: str):
    base = f"{base_url.rstrip('/')}/api/v1"
    headers = {"X-N8N-API-KEY": api_key}
    return base, headers


def find_credential_id(base_url: str, api_key: str, name: str = CRED_NAME, cred_type: str = CRED_TYPE,
                       get=requests.get) -> str:
    base, headers = _api(base_url, api_key)
    resp = get(f"{base}/credentials", headers=headers, params={"limit": 100}, timeout=15)
    resp.raise_for_status()
    matches = [c for c in resp.json().get("data", []) if c.get("name") == name and c.get("type") == cred_type]
    if len(matches) != 1:
        raise ConfigError(f"expected one n8n credential named {name!r} of type {cred_type}, found {len(matches)}")
    return matches[0]["id"]


def update_live(base_url: str, api_key: str, wf: dict, session=requests) -> str:
    """Replace the live workflow with the same name, then publish it. Returns its ID."""
    base, headers = _api(base_url, api_key)
    resp = session.get(f"{base}/workflows", headers=headers, params={"name": wf["name"], "limit": 10}, timeout=15)
    resp.raise_for_status()
    found = [w for w in resp.json().get("data", []) if w.get("name") == wf["name"]]
    if len(found) != 1:
        raise ConfigError(f"expected one live workflow named {wf['name']!r}, found {len(found)}")
    wid = found[0]["id"]
    body = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    session.put(f"{base}/workflows/{wid}", headers=headers, json=body, timeout=30).raise_for_status()
    session.post(f"{base}/workflows/{wid}/activate", headers=headers, timeout=30).raise_for_status()
    return wid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true", help="replace the live workflow of the same name and publish it")
    args = ap.parse_args(argv)
    load_dotenv(REPO / ".env")
    base_url = os.environ.get("N8N_BASE_URL") or "http://localhost:5678"
    key = os.environ.get("N8N_API_KEY", "")
    try:
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        ids = {}
        for placeholder, (name, cred_type, env_name) in CREDENTIALS.items():
            ids[placeholder] = os.environ.get(env_name) or (
                find_credential_id(base_url, key, name, cred_type) if key else ""
            )
            if not ids[placeholder]:
                raise ConfigError(f"set N8N_API_KEY (to look credentials up) or {env_name} in .env")
        wf = render(template, os.environ.get("SLICE_TRACKER_ID", ""), ids)
    except (ConfigError, OSError, ValueError) as e:
        print(f"CONFIG ERROR {e}")
        return 2
    except requests.RequestException as e:
        print(f"FAIL n8n API: {type(e).__name__}")
        return 1
    OUTPUT.write_text(json.dumps(wf, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)} (git-ignored).")
    if args.update:
        try:
            wid = update_live(base_url, key, wf)
        except ConfigError as e:
            print(f"CONFIG ERROR {e}")
            return 2
        except requests.RequestException as e:
            print(f"FAIL n8n API: {type(e).__name__}")
            return 1
        print(f"Updated and published live workflow {wid}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
