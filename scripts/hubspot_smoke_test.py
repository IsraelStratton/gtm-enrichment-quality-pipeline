#!/usr/bin/env python3
"""HubSpot service-key smoke test: company search by domain, then create or update.

Proves the DQ-04 path end to end before the n8n workflow is built:
search by domain -> create if absent / update if present -> read back.
Uses a synthetic .example domain, so it never touches a real company.

Run locally (needs network access and HUBSPOT_SERVICE_KEY in .env):

  python scripts/hubspot_smoke_test.py              # full test
  python scripts/hubspot_smoke_test.py --search-only
  python scripts/hubspot_smoke_test.py --archive    # delete the test company afterwards

Exit codes: 0 pass, 1 HubSpot/network failure, 2 configuration error.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://api.hubapi.com"
DEFAULT_DOMAIN = "gtm-pipeline-smoke-test.example"
DEFAULT_NAME = "GTM Pipeline Smoke Test Co"
COMPANIES = "/crm/v3/objects/companies"
READ_PROPERTIES = ["name", "domain", "description", "hs_lastmodifieddate"]
RETRY_STATUSES = {429, 500, 502, 503, 504}

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TLD = re.compile(r"^[a-z]{2,63}$")


class HubSpotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class AmbiguousMatch(Exception):
    """More than one HubSpot company has the same domain: refuse to guess which to update."""


def normalise_domain(raw: str) -> str:
    """Normalise a domain as described in docs/rules.md (used by DQ-02 and DQ-03)."""
    d = raw.strip().lower()
    d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", d)
    d = re.split(r"[/?#]", d, maxsplit=1)[0].split(":", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    return d.rstrip(".")


def is_valid_domain(domain: str) -> bool:
    """DQ-02 check on an already-normalised domain."""
    labels = domain.split(".")
    return (
        0 < len(domain) <= 253
        and len(labels) >= 2
        and all(_LABEL.match(label) for label in labels)
        and bool(_TLD.match(labels[-1]))
    )


def _retry_delay(resp: requests.Response, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return float(retry_after)
    return float(2**attempt)


def _explain(resp: requests.Response) -> str:
    if resp.status_code == 401:
        return ("Service key rejected (401). Check that HUBSPOT_SERVICE_KEY holds the "
                "gtm-pipeline key and that it hasn't been revoked or rotated.")
    if resp.status_code == 403:
        return ("Missing scope (403). The service key needs crm.objects.companies.read "
                "and crm.objects.companies.write.")
    try:
        detail = resp.json().get("message", "")
    except ValueError:
        detail = resp.text[:200]
    return f"HubSpot returned HTTP {resp.status_code}: {detail}".rstrip(": ")


class HubSpotClient:
    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL,
                 session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        self._sleep = sleep
        self.max_retries = max_retries

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries + 1):
            resp = self.session.request(method, url, json=json, timeout=30)
            if resp.status_code in RETRY_STATUSES and attempt < self.max_retries:
                self._sleep(_retry_delay(resp, attempt))
                continue
            break
        if resp.status_code >= 400:
            raise HubSpotError(resp.status_code, _explain(resp))
        return resp.json() if resp.content else {}

    def search_by_domain(self, domain: str) -> list[dict]:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "domain", "operator": "EQ", "value": domain},
            ]}],
            "properties": READ_PROPERTIES,
            "limit": 10,
        }
        return self._request("POST", f"{COMPANIES}/search", json=body).get("results", [])

    def create(self, properties: dict) -> dict:
        return self._request("POST", COMPANIES, json={"properties": properties})

    def update(self, company_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"{COMPANIES}/{company_id}", json={"properties": properties})

    def get(self, company_id: str) -> dict:
        props = ",".join(READ_PROPERTIES)
        return self._request("GET", f"{COMPANIES}/{company_id}?properties={props}")

    def archive(self, company_id: str) -> None:
        self._request("DELETE", f"{COMPANIES}/{company_id}")


def upsert_by_domain(client: HubSpotClient, domain: str, properties: dict) -> tuple[str, dict]:
    """DQ-04: update the company that already has this domain, otherwise create one."""
    matches = client.search_by_domain(domain)
    if len(matches) > 1:
        ids = ", ".join(m["id"] for m in matches)
        raise AmbiguousMatch(f"{len(matches)} companies share domain {domain} (ids {ids})")
    if matches:
        return "update", client.update(matches[0]["id"], properties)
    return "create", client.create({**properties, "domain": domain})


def wait_until_searchable(client: HubSpotClient, domain: str, company_id: str,
                          timeout_s: float = 30, interval_s: float = 2,
                          sleep: Callable[[float], None] = time.sleep) -> float | None:
    """Poll search until a just-created company shows up. Returns seconds waited, or None."""
    waited = 0.0
    while True:
        if any(m["id"] == company_id for m in client.search_by_domain(domain)):
            return waited
        if waited >= timeout_s:
            return None
        sleep(interval_s)
        waited += interval_s


def run_smoke_test(client: HubSpotClient, domain: str, name: str, *, search_only: bool = False,
                   archive: bool = False, record_url: Callable[[str], str] | None = None,
                   stamp: str | None = None, out: Callable[[str], None] = print,
                   sleep: Callable[[float], None] = time.sleep) -> int:
    out(f"Searching HubSpot companies for domain {domain} ...")
    if search_only:
        matches = client.search_by_domain(domain)
        out(f"PASS read scope: {len(matches)} match(es) "
            f"{[m['id'] for m in matches] if matches else ''}".rstrip())
        return 0

    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        action, record = upsert_by_domain(
            client, domain, {"name": name, "description": f"gtm-pipeline smoke test {stamp} (create/first)"})
    except AmbiguousMatch as exc:
        out(f"FAIL {exc}. Merge or archive the extras in HubSpot, then re-run.")
        return 1
    company_id = record["id"]
    out(f"{action.upper()} company id {company_id}")

    if action == "create":
        out("Waiting for the new company to appear in search (HubSpot indexes writes asynchronously) ...")
        lag = wait_until_searchable(client, domain, company_id, sleep=sleep)
        if lag is None:
            out("FAIL company not searchable after 30s. The record exists. Re-run in a minute "
                "to exercise the update path; until then DQ-04 would create a duplicate.")
            return 1
        out(f"Searchable after ~{lag:.0f}s")
        try:
            action, record = upsert_by_domain(
                client, domain, {"name": name, "description": f"gtm-pipeline smoke test {stamp} (update)"})
        except AmbiguousMatch as exc:
            out(f"FAIL {exc}")
            return 1
        if action != "update" or record["id"] != company_id:
            out(f"FAIL second upsert did {action} on id {record['id']}, expected update on {company_id}")
            return 1
        out(f"UPDATE company id {company_id}")
        expected = f"gtm-pipeline smoke test {stamp} (update)"
    else:
        expected = f"gtm-pipeline smoke test {stamp} (create/first)"

    stored = client.get(company_id).get("properties", {})
    if stored.get("description") != expected or stored.get("domain") != domain:
        out(f"FAIL read-back mismatch: domain={stored.get('domain')!r} "
            f"description={stored.get('description')!r}")
        return 1
    out("PASS search by domain -> create/update -> read back")
    if record_url:
        out(f"View: {record_url(company_id)}")

    if archive:
        client.archive(company_id)
        out(f"Archived company id {company_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--search-only", action="store_true", help="read scope only, no writes")
    parser.add_argument("--archive", action="store_true", help="delete the test company at the end")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    token = os.environ.get("HUBSPOT_SERVICE_KEY", "").strip()
    if not token:
        print("HUBSPOT_SERVICE_KEY is not set. Copy .env.example to .env and add the key.",
              file=sys.stderr)
        return 2
    domain = normalise_domain(args.domain)
    if not is_valid_domain(domain):
        print(f"--domain {args.domain!r} is not a valid domain (DQ-02).", file=sys.stderr)
        return 2

    portal_id = os.environ.get("HUBSPOT_PORTAL_ID", "").strip()
    app_host = os.environ.get("HUBSPOT_APP_HOST", "app.hubspot.com").strip()
    record_url = (lambda cid: f"https://{app_host}/contacts/{portal_id}/record/0-2/{cid}") if portal_id else None

    client = HubSpotClient(token, os.environ.get("HUBSPOT_BASE_URL", DEFAULT_BASE_URL).strip())
    try:
        return run_smoke_test(client, domain, args.name, search_only=args.search_only,
                              archive=args.archive, record_url=record_url)
    except HubSpotError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"FAIL network error: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
