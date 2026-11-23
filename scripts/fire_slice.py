#!/usr/bin/env python3
"""Fire one made-up approved lead at a slice webhook (chapter 3: n8n, Make or Zapier).

The same payload goes to every tool, so their runs can be compared row by row
in the tracking sheet. Each payload gets a run_id and a sent_at time; each tool
adds its own received_at when it writes the tracking row.

  python scripts/fire_slice.py --target n8n --test         # n8n test URL (editor listening)
  python scripts/fire_slice.py --target n8n                # n8n production URL (workflow published)
  python scripts/fire_slice.py --target make --lead L-0002
  python scripts/fire_slice.py --target n8n --dry-run      # print the payload, send nothing

Webhook URLs for Make and Zapier come from .env (SLICE_URL_MAKE, SLICE_URL_ZAPIER)
or --url. They are masked in the output and never committed.

Each webhook needs a key. The script sends it from .env (SLICE_KEY_N8N in the
X-Slice-Key header, SLICE_KEY_MAKE in Make's x-make-apikey header) and never
prints it. --no-key sends without one, to prove the webhook refuses the call.

Exit codes: 0 sent and accepted, 1 HTTP or network failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
LEADS_FILE = REPO / "slice" / "approved_leads.json"
TARGETS = ("n8n", "make", "zapier")
ENV_URL = {"n8n": "SLICE_URL_N8N", "make": "SLICE_URL_MAKE", "zapier": "SLICE_URL_ZAPIER"}
N8N_DEFAULT_BASE = "http://localhost:5678"
N8N_PATH = "gtm-v2-approved-lead"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
KEY_ENV = {"n8n": "SLICE_KEY_N8N", "make": "SLICE_KEY_MAKE"}
KEY_HEADER = {"n8n": "X-Slice-Key", "make": "x-make-apikey"}


class ConfigError(Exception):
    pass


def load_leads(path: Path = LEADS_FILE) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["leads"]


def pick_lead(leads: list[dict], lead_id: str | None) -> dict:
    if lead_id is None:
        return leads[0]
    for lead in leads:
        if lead["lead_id"] == lead_id:
            return lead
    raise ConfigError(f"no lead {lead_id!r}; choose from {', '.join(l['lead_id'] for l in leads)}")


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_payload(lead: dict, target: str, now: datetime) -> dict:
    """The slice input: the lead plus who it is for, a run id and the send time."""
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "event": "lead.approved",
        "run_id": f"slice-{target}-{stamp}-{lead['lead_id']}",
        "target": target,
        "sent_at": iso_utc(now),
        **lead,
    }


def resolve_url(target: str, cli_url: str | None, env: dict, test: bool) -> str:
    if cli_url:
        return cli_url
    if target == "n8n":
        base = env.get("N8N_BASE_URL") or N8N_DEFAULT_BASE
        return f"{base.rstrip('/')}/{'webhook-test' if test else 'webhook'}/{N8N_PATH}"
    url = env.get(ENV_URL[target])
    if not url:
        raise ConfigError(f"{ENV_URL[target]} is not set in .env; paste the {target} webhook URL there or pass --url")
    return url


def key_headers(target: str, env: dict, use_key: bool = True) -> dict:
    """The webhook key header for a target, or {} if it has none or --no-key is set."""
    name = KEY_ENV.get(target)
    if not use_key or not name or not env.get(name):
        return {}
    return {KEY_HEADER[target]: env[name]}


def mask_url(url: str) -> str:
    """Show enough to tell targets apart, never the whole token-bearing path."""
    parts = urlsplit(url)
    if parts.hostname in LOCAL_HOSTS:
        return url
    tail = parts.path.rstrip("/")[-4:]
    return f"{parts.scheme}://{parts.netloc}/...{tail}"


def send(url: str, payload: dict, headers: dict | None = None, post=requests.post) -> tuple[int, float, str]:
    started = time.perf_counter()
    resp = post(url, json=payload, headers=headers or {}, timeout=30)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return resp.status_code, elapsed_ms, (resp.text or "")[:300]


def main(argv: list[str] | None = None, post=requests.post) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, choices=TARGETS)
    ap.add_argument("--lead", help="lead_id from slice/approved_leads.json (default: the first)")
    ap.add_argument("--url", help="override the webhook URL")
    ap.add_argument("--test", action="store_true", help="n8n only: use the editor's test URL")
    ap.add_argument("--dry-run", action="store_true", help="print the payload and stop")
    ap.add_argument("--no-key", action="store_true", help="send without the webhook key (expect a refusal)")
    args = ap.parse_args(argv)

    load_dotenv(REPO / ".env")
    try:
        lead = pick_lead(load_leads(), args.lead)
        payload = build_payload(lead, args.target, datetime.now(timezone.utc))
        if args.dry_run:
            print(json.dumps(payload, indent=2))
            return 0
        env = dict(os.environ)
        url = resolve_url(args.target, args.url, env, args.test)
        headers = key_headers(args.target, env, use_key=not args.no_key)
    except (ConfigError, OSError, KeyError, ValueError) as e:
        print(f"CONFIG ERROR {e}")
        return 2

    print(f"Sending {payload['lead_id']} ({payload['company_name']}) to {args.target} at {mask_url(url)}")
    print(f"run_id {payload['run_id']}  sent_at {payload['sent_at']}")
    if headers:
        print(f"with key in header {next(iter(headers))}")
    elif args.target in KEY_ENV and not args.no_key:
        print(f"WARNING no key: {KEY_ENV[args.target]} is not set in .env")
    else:
        print("without a key")
    try:
        status, elapsed_ms, body = send(url, payload, headers=headers, post=post)
    except requests.RequestException as e:
        print(f"FAIL network error: {type(e).__name__}")
        return 1
    if 200 <= status < 300:
        print(f"PASS HTTP {status} in {elapsed_ms:.0f} ms  {body}")
        return 0
    print(f"FAIL HTTP {status} in {elapsed_ms:.0f} ms  {body}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
