#!/usr/bin/env python3
"""INIT-164 (KB-138): build the Agentforce routing explainer locally, and prove it with five prompts.

  python scripts/agentforce_explainer.py prepare
      Copies salesforce/agentforce to salesforce/agentforce.local (git-ignored) and fills in the
      agent user's username from .env (SALESFORCE_EXPLAINER_AGENT_USER). The committed Agent
      Script holds a placeholder, so no org-specific value is in the repository. Every sf command
      for the explainer runs from the local copy.

  python scripts/agentforce_explainer.py prompts --target-org gtm-v2-admin
      Runs the five prompts in salesforce/agentforce/test-prompts.json against the activated,
      published agent, each in its own live preview session. A live preview of a service agent
      runs its actions as the agent user, so the answers come through the agent user's least
      access. Before and after each prompt, the Account is read through the chapter 4 integration
      login, to show that nothing changed. Each answer is graded with the prompt's checks. The
      transcript and grades are written to docs/v2/init-164-evidence/.

The admin CLI login (sf org login web) is Israel's, and he logs it out when the build is done.
Exit codes: 0 done (all five as expected), 1 a prompt was not as expected, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from salesforce_client import SalesforceClient, SalesforceError  # noqa: E402

PROJECT = REPO / "salesforce/agentforce"
LOCAL = REPO / "salesforce/agentforce.local"
AGENT = "GTM_Routing_Explainer"
SCRIPT = PROJECT / f"force-app/main/default/aiAuthoringBundles/{AGENT}/{AGENT}.agent"
PLACEHOLDER = "GTM_EXPLAINER_AGENT_USER"
ENV_KEY = "SALESFORCE_EXPLAINER_AGENT_USER"
PROMPTS = PROJECT / "test-prompts.json"
EVIDENCE = REPO / "docs/v2/init-164-evidence"
READ_BACK = ["Name", "GTM_Route__c", "GTM_Priority__c", "GTM_Routing_Status__c", "GTM_Decision_Stamp__c"]
HOST_RE = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.(my\.)?salesforce\.com|[a-z0-9-]+\.my\.site\.com", re.I)


def prepare(env_path: Path = REPO / ".env") -> Path:
    user = (dotenv_values(env_path).get(ENV_KEY) or "").strip()
    if not user:
        raise SystemExit(f"CANNOT RUN {ENV_KEY} is not in .env yet (the agent user's username)")
    if LOCAL.exists():
        shutil.rmtree(LOCAL)
    shutil.copytree(PROJECT, LOCAL, ignore=shutil.ignore_patterns(".sf", ".sfdx", "node_modules"))
    local_script = LOCAL / SCRIPT.relative_to(PROJECT)
    text = local_script.read_text(encoding="utf-8")
    if text.count(PLACEHOLDER) != 1:
        raise SystemExit(f"CANNOT RUN the Agent Script should hold the placeholder {PLACEHOLDER} once")
    local_script.write_text(text.replace(PLACEHOLDER, user), encoding="utf-8")
    return LOCAL


def sf(args: list[str], cwd: Path = LOCAL) -> dict:
    """Run an sf command with --json and return its result, or raise with its message."""
    done = subprocess.run(["sf", *args, "--json"], cwd=cwd, capture_output=True, text=True, timeout=300)
    try:
        out = json.loads(done.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"sf {' '.join(args[:3])}: no JSON reply: {done.stderr.strip()[:300]}")
    if out.get("status", 1) != 0:
        raise RuntimeError(f"sf {' '.join(args[:3])}: {out.get('name', '')}: {out.get('message', '')}"[:400])
    return out.get("result") or {}


def texts(value) -> list[str]:
    """The agent's words in an sf preview reply, wherever its JSON puts them."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("message", "text", "response") and isinstance(item, str) and item.strip():
                found.append(item.strip())
            else:
                found += texts(item)
    elif isinstance(value, list):
        for item in value:
            found += texts(item)
    return found


def grade(prompt: dict, answer: str, before: dict | None, after: dict | None) -> list[tuple[bool, str]]:
    low = answer.lower()
    checks = []
    for word in prompt.get("must_include", []):
        checks.append((word.lower() in low, f"says {word!r}"))
    if prompt.get("must_include_any"):
        checks.append((any(w.lower() in low for w in prompt["must_include_any"]), f"says one of {prompt['must_include_any']}"))
    for word in prompt.get("must_not_include", []):
        checks.append((word.lower() not in low, f"does not say {word!r}"))
    checks.append((before is not None and before == after, "the Account is unchanged"))
    return checks


def read_account(client: SalesforceClient, key: str) -> dict | None:
    record = client.account_by_key(key, READ_BACK)
    return {k: record.get(k) for k in READ_BACK} if record else None


def run_prompts(org: str) -> int:
    if not LOCAL.exists():
        prepare()
    prompts = json.loads(PROMPTS.read_text(encoding="utf-8"))["prompts"]
    client = SalesforceClient.from_env()
    results, all_ok = [], True
    for p in prompts:
        before = read_account(client, p["account_key"])
        session = sf(["agent", "preview", "start", "-o", org, "--api-name", AGENT])
        session_id = session.get("sessionId") or session.get("id")
        try:
            reply = sf(["agent", "preview", "send", "-o", org, "--api-name", AGENT, "--session-id", session_id, "-u", p["utterance"]])
        finally:
            try:
                sf(["agent", "preview", "end", "-o", org, "--api-name", AGENT, "--session-id", session_id])
            except RuntimeError:
                pass
        after = read_account(client, p["account_key"])
        answer = "\n".join(texts(reply))
        checks = grade(p, answer, before, after)
        ok = all(c for c, _ in checks)
        all_ok &= ok
        results.append({"id": p["id"], "kind": p["kind"], "requirement": p["requirement"], "utterance": p["utterance"],
                        "answer": HOST_RE.sub("<org host>", answer), "as_expected": ok,
                        "checks": [{"ok": c, "check": t} for c, t in checks], "account_before": before, "account_after": after})
        print(f"{'PASS' if ok else 'FAIL'} {p['id']} {p['kind']} ({p['requirement']}): {p['utterance']}")
        for c, t in checks:
            if not c:
                print(f"     not met: {t}")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = EVIDENCE / f"prompts-{stamp}.json"
    out.write_text(json.dumps({"agent": AGENT, "run_at_utc": stamp, "mode": "live preview of the activated agent, actions run as the agent user",
                               "all_as_expected": all_ok, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{sum(r['as_expected'] for r in results)} of {len(results)} as expected. Transcript: {out.relative_to(REPO)}")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="make the local deployable copy with the agent user filled in")
    pr = sub.add_parser("prompts", help="run the five test prompts against the activated agent")
    pr.add_argument("--target-org", required=True, help="the sf alias of Israel's admin login")
    args = ap.parse_args(argv)
    try:
        if args.command == "prepare":
            print(f"Local project ready: {prepare().relative_to(REPO)}")
            return 0
        return run_prompts(args.target_org)
    except (RuntimeError, SalesforceError) as e:
        print(f"CANNOT RUN {HOST_RE.sub('<org host>', str(e))}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
