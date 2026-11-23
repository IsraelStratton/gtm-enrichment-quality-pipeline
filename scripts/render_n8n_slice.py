#!/usr/bin/env python3
"""Make the importable n8n slice workflow from the public template.

The template in slice/n8n/slice-workflow.json holds two placeholders, so the
public repo never carries the tracker ID or a credential ID:

  SPREADSHEET_ID        <- SLICE_TRACKER_ID from .env
  GOOGLE_CREDENTIAL_ID  <- looked up in n8n by credential name (needs N8N_API_KEY),
                           or N8N_GOOGLE_CREDENTIAL_ID from .env

It writes slice/n8n/slice-workflow.local.json, which git ignores. Import that file
into n8n (Workflows, Import from File), then save and publish.

  python scripts/render_n8n_slice.py

Exit codes: 0 written, 2 configuration error.
"""
from __future__ import annotations

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
CRED_PLACEHOLDER = "GOOGLE_CREDENTIAL_ID"
CRED_NAME = "Google least reach gtm-pipeline"
CRED_TYPE = "googleOAuth2Api"
_SHEET_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")


class ConfigError(Exception):
    pass


def render(template: dict, tracker_id: str, credential_id: str) -> dict:
    if not _SHEET_ID.match(tracker_id or ""):
        raise ConfigError("SLICE_TRACKER_ID is missing or does not look like a Google Sheets ID")
    if not credential_id or credential_id == CRED_PLACEHOLDER:
        raise ConfigError("no n8n credential ID for the Google login")
    wf = copy.deepcopy(template)
    filled = 0
    for node in wf["nodes"]:
        params = node.get("parameters", {})
        if SHEET_PLACEHOLDER in params.get("url", ""):
            params["url"] = params["url"].replace(SHEET_PLACEHOLDER, tracker_id)
            filled += 1
        cred = (node.get("credentials") or {}).get(CRED_TYPE)
        if cred and cred.get("id") == CRED_PLACEHOLDER:
            cred["id"] = credential_id
    if filled != 1:
        raise ConfigError(f"expected one tracker URL placeholder, found {filled}")
    return wf


def find_credential_id(base_url: str, api_key: str, get=requests.get) -> str:
    resp = get(f"{base_url.rstrip('/')}/api/v1/credentials", headers={"X-N8N-API-KEY": api_key},
               params={"limit": 100}, timeout=15)
    resp.raise_for_status()
    matches = [c for c in resp.json().get("data", []) if c.get("name") == CRED_NAME and c.get("type") == CRED_TYPE]
    if len(matches) != 1:
        raise ConfigError(f"expected one n8n credential named {CRED_NAME!r} of type {CRED_TYPE}, found {len(matches)}")
    return matches[0]["id"]


def main() -> int:
    load_dotenv(REPO / ".env")
    try:
        template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        cred_id = os.environ.get("N8N_GOOGLE_CREDENTIAL_ID")
        if not cred_id:
            key = os.environ.get("N8N_API_KEY")
            if not key:
                raise ConfigError("set N8N_API_KEY (to look the credential up) or N8N_GOOGLE_CREDENTIAL_ID in .env")
            cred_id = find_credential_id(os.environ.get("N8N_BASE_URL") or "http://localhost:5678", key)
        wf = render(template, os.environ.get("SLICE_TRACKER_ID", ""), cred_id)
    except (ConfigError, OSError, ValueError, requests.RequestException) as e:
        print(f"CONFIG ERROR {e}")
        return 2
    OUTPUT.write_text(json.dumps(wf, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)} (git-ignored). Import it into n8n, then save and publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
