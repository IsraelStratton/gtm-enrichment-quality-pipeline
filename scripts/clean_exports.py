#!/usr/bin/env python3
"""Clean exports (the wrap, item 4): what a committed workflow export may hold, and the cleaners that make one.

The repo is public. Every n8n workflow, the Make blueprint and the Zapier build record in EXPORTS is
checked on every push (tests/test_clean_exports.py in CI, and scripts/prepush_check.py on the commit
being pushed). An export holds no credential, key, address, org host, username, sheet ID or tool ID:

  every export   no email address but a reserved example one, and none of this build's Salesforce
                 usernames (gtm-v2-...@) even on an example domain; no Google client ID or secret; no
                 Claude, HubSpot or bearer key; no Salesforce host but the placeholder; no Salesforce
                 org, user or agent ID; no Google Sheets ID; no Make or Zapier webhook address
  n8n            only name, nodes, connections and settings at the top (no workflow ID, version,
                 instance, sharing, tags or pinned data); every credential named with an empty or
                 placeholder ID; every data table ID a placeholder
  Make           the webhook and connection are placeholders; no number of six digits or more
  Zapier         every ID a placeholder; no number of six digits or more
  on this Mac    no value from .env or .prepush-private.local (CI has neither file)

A placeholder is written in capitals (SPREADSHEET_ID, GOOGLE_CREDENTIAL_ID, QUARANTINE_DATA_TABLE_ID).
Each tool fills its own in at import time: n8n by name (scripts/n8n_publish_routing.py), the slice by
scripts/render_n8n_slice.py, Make and Zapier by hand in their editors.

  python scripts/clean_exports.py --check                         # every committed export
  python scripts/clean_exports.py n8n RAW.json OUT.json           # an n8n download or API read
  python scripts/clean_exports.py n8n-live "WORKFLOW NAME" OUT.json  # read it from the local n8n API
  python scripts/clean_exports.py zapier RAW.json OUT.json        # Zapier's "Download my Zap workflows" file

A cleaner replaces what it knows how to replace, then runs the same checks on its result and writes
nothing if anything is left. The Make blueprint has its own cleaner, scripts/scrub_make_blueprint.py.
Findings name the file and the kind of value, never the value.

Exit codes: 0 clean (or written), 1 findings, 2 could not run.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

EXPORTS = {
    "n8n": [
        "n8n/workflow.json",
        "n8n/workflow-v2.json",
        "n8n/workflow-v2-salesforce.json",
        "n8n/workflow-v2-quote-desk.json",
        "slice/n8n/slice-workflow.json",
        "slice/n8n/create-tracker-workflow.json",
    ],
    "make": ["slice/make/slice-scenario.blueprint.json"],
    "zapier": ["slice/zapier/zap-builds.json"],
}
# JSON files under n8n/ and slice/ that are data, not exports.
NOT_EXPORTS = {"slice/approved_leads.json"}

PLACEHOLDER = re.compile(r"^[A-Z][A-Z0-9_]*$")
SALESFORCE_PLACEHOLDER = "your-my-domain.my.salesforce.com"
N8N_TOP_KEYS = {"name", "nodes", "connections", "settings"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(r"@(?:[A-Za-z0-9-]+\.)*(example\.(com|org|net)|[A-Za-z0-9-]+\.example)$", re.I)
PATTERNS = {
    "a Salesforce username of this build": re.compile(r"gtm-v2-[A-Za-z0-9.-]*@"),
    "a Google OAuth client ID": re.compile(r"\d{6,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com"),
    "a Google OAuth client secret": re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    "a Claude API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    "a HubSpot key": re.compile(r"\bpat-[a-z]{2,3}\d?-[0-9a-f-]{20,}"),
    "a bearer token": re.compile(r"Bearer [A-Za-z0-9._~+/=-]{20,}"),
    "a Salesforce org, user or agent ID": re.compile(r"\b(?:00D|005|0Xx)[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b"),
    "a Google Sheets ID": re.compile(r"spreadsheets/(?:d/)?(?![A-Z][A-Z0-9_]*\b)[A-Za-z0-9_-]{20,}"),
    "a Make webhook address": re.compile(r"hook\.[a-z0-9]+\.make\.com/[A-Za-z0-9]+"),
    "a Zapier webhook address": re.compile(r"hooks\.zapier\.com/hooks/catch/\d+"),
}
SALESFORCE_HOST = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:my\.salesforce\.com|lightning\.force\.com)")
BIG_NUMBER = re.compile(r"(?<![\w.])\d{6,}(?![\w.])")
NS = uuid.UUID("6f1e2d3c-4b5a-4978-8a1b-2c3d4e5f6a7b")  # fixed, so a cleaned export is the same every time

Reader = Callable[[str], "str | None"]


def text_findings(text: str, private: dict[str, str] | None = None) -> list[str]:
    """What any export must never hold, by kind. `private` maps a label to a value (local runs only)."""
    out = []
    if any(not ALLOWED_EMAIL.search(m) for m in EMAIL.findall(text)):
        out.append("an email address")
    for label, pattern in PATTERNS.items():
        if pattern.search(text):
            out.append(label)
    if any(h.lower() != SALESFORCE_PLACEHOLDER for h in SALESFORCE_HOST.findall(text)):
        out.append("a Salesforce host")
    for label, value in (private or {}).items():
        if value and value in text:
            out.append(f"a private value ({label})")
    return out


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, node


def n8n_findings(wf: dict) -> list[str]:
    out = []
    extra = sorted(set(wf) - N8N_TOP_KEYS)
    if extra:
        out.append(f"instance data at the top: {', '.join(extra)}")
    for n in wf.get("nodes", []):
        for cred_type, cred in (n.get("credentials") or {}).items():
            cid = cred.get("id")
            if cid is not None and not PLACEHOLDER.match(str(cid)):
                out.append(f"node {n['name']}: a credential ID ({cred_type})")
            if not cred.get("name"):
                out.append(f"node {n['name']}: a credential with no name ({cred_type})")
        ref = (n.get("parameters") or {}).get("dataTableId")
        value = ref.get("value") if isinstance(ref, dict) else ref
        if value not in (None, "") and not PLACEHOLDER.match(str(value)):
            out.append(f"node {n['name']}: a data table ID")
    settings = wf.get("settings") or {}
    for key in ("errorWorkflow", "timeSavedPerExecution"):
        if key in settings:
            out.append(f"settings: {key}")
    return out


def make_findings(bp: dict) -> list[str]:
    out = []
    for path, value in _walk(bp):
        key = path.rsplit(".", 1)[-1]
        if key in {"hook", "oAuthAccount", "__IMTCONN__", "account", "connection"} and ".restore." not in f".{path}." \
                and not (isinstance(value, str) and PLACEHOLDER.match(value)):
            out.append(f"{path}: an ID where a placeholder belongs")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 100000:
            out.append(f"{path}: a number of six digits or more")
    return out


def zapier_findings(z: dict) -> list[str]:
    out = []
    for path, value in _walk(z):
        key = path.rsplit(".", 1)[-1].split("[")[0]
        if re.search(r"(^|_)id$|Id$", key) and value is not None and not (isinstance(value, str) and PLACEHOLDER.match(value)):
            out.append(f"{path}: an ID where a placeholder belongs")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 100000:
            out.append(f"{path}: a number of six digits or more")
    if BIG_NUMBER.search(json.dumps(z)):
        out.append("a number of six digits or more inside a text value")
    return out


STRUCTURE = {"n8n": n8n_findings, "make": make_findings, "zapier": zapier_findings}


def export_findings(kind: str, text: str, private: dict[str, str] | None = None) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ["not valid JSON"]
    return STRUCTURE[kind](data) + text_findings(text, private)


def check_all(read: Reader, private: dict[str, str] | None = None) -> list[str]:
    out = []
    for kind, files in EXPORTS.items():
        for rel in files:
            text = read(rel)
            if text is None:
                out.append(f"{rel}: missing")
                continue
            out += [f"{rel}: {f}" for f in export_findings(kind, text, private)]
    return out


def private_values() -> dict[str, str]:
    """The local .env values and the git-ignored private list, as scripts/prepush_check.py reads them."""
    from prepush_check import private_values as read

    return read()


# ---------------------------------------------------------------- cleaners


def clean_n8n(raw: dict) -> dict:
    """Keep what n8n needs to import a workflow, and nothing that belongs to one instance."""
    wf = {"name": raw["name"], "nodes": [], "connections": copy.deepcopy(raw.get("connections", {})),
          "settings": {"executionOrder": (raw.get("settings") or {}).get("executionOrder", "v1")}}
    for node in raw["nodes"]:
        n = copy.deepcopy(node)
        n["id"] = str(uuid.uuid5(NS, f"{raw['name']}/{n['name']}"))
        if "webhookId" in n:
            n["webhookId"] = str(uuid.uuid5(NS, f"{raw['name']}/{n['name']}/webhook"))
        for cred in (n.get("credentials") or {}).values():
            cred["id"] = None
        ref = (n.get("parameters") or {}).get("dataTableId")
        if isinstance(ref, dict) and ref.get("value"):
            ref["value"] = "DATA_TABLE_ID"
            ref.pop("cachedResultUrl", None)
        text = json.dumps(n)
        text = re.sub(r"(spreadsheets/(?:d/)?)[A-Za-z0-9_-]{20,}", r"\1SPREADSHEET_ID", text)
        wf["nodes"].append(json.loads(text))
    return wf


def clean_zapier(raw, private: dict[str, str] | None = None):
    """Zapier's export, with every ID, webhook address, email address and private value replaced."""
    values = sorted((v for v in (private or {}).values() if v), key=len, reverse=True)

    def scrub(node, key=""):
        if isinstance(node, dict):
            return {k: scrub(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [scrub(v, key) for v in node]
        if re.search(r"(^|_)id$|Id$", key) and node is not None and not isinstance(node, bool):
            return "ZAPIER_ID"
        if isinstance(node, int) and not isinstance(node, bool) and node >= 100000:
            return "ZAPIER_ID"
        if isinstance(node, str):
            for v in values:
                node = node.replace(v, "PRIVATE_VALUE_REMOVED")
            node = re.sub(r"https://hooks\.zapier\.com/hooks/catch/[\w/]+", "ZAPIER_HOOK_URL", node)
            node = EMAIL.sub(lambda m: m.group(0) if ALLOWED_EMAIL.search(m.group(0)) else "OWNER_INBOX", node)
            node = BIG_NUMBER.sub("ZAPIER_ID", node)
        return node

    return scrub(raw)


def write_clean(kind: str, data, out: Path, private: dict[str, str]) -> int:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    findings = export_findings(kind, text, private)
    if findings:
        for f in findings:
            print(f"REFUSED {f}")
        print("Nothing written: clean these by hand, then run the cleaner again.")
        return 1
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}: clean.")
    return 0


def read_live_n8n(name: str) -> dict:
    import requests
    from dotenv import dotenv_values

    env = dotenv_values(REPO / ".env")
    key = (env.get("N8N_API_KEY") or "").strip()
    base = (env.get("N8N_BASE_URL") or "http://localhost:5678").strip().rstrip("/")
    if not key:
        raise LookupError("N8N_API_KEY is not in .env")
    headers = {"X-N8N-API-KEY": key}
    found = [w for w in requests.get(f"{base}/api/v1/workflows?limit=250", headers=headers, timeout=15).json().get("data", [])
             if w["name"] == name]
    if len(found) != 1:
        raise LookupError(f"expected one n8n workflow named {name!r}, found {len(found)}")
    return requests.get(f"{base}/api/v1/workflows/{found[0]['id']}", headers=headers, timeout=15).json()


def tree_reader(root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        p = root / rel
        return p.read_text(encoding="utf-8") if p.exists() else None
    return read


def tracked_json(root: Path = REPO) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "n8n", "slice"],
                         cwd=root, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split() if p.endswith(".json"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="check every committed export")
    ap.add_argument("kind", nargs="?", choices=["n8n", "n8n-live", "zapier"])
    ap.add_argument("source", nargs="?", help="a raw export file, or for n8n-live the workflow's name")
    ap.add_argument("out", nargs="?", help="where to write the clean export")
    args = ap.parse_args(argv)
    try:
        private = private_values()
    except Exception as e:  # noqa: BLE001 - the check still runs without the local values
        print(f"NOTE local private values not read ({type(e).__name__}); checking patterns only")
        private = {}
    if args.check or not args.kind:
        findings = check_all(tree_reader(), private)
        unlisted = [p for p in tracked_json() if p not in {f for fs in EXPORTS.values() for f in fs} | NOT_EXPORTS]
        findings += [f"{p}: a JSON file under n8n/ or slice/ that is not in EXPORTS" for p in unlisted]
        for f in findings:
            print(f"FAIL {f}")
        if not findings:
            print(f"PASS {sum(len(v) for v in EXPORTS.values())} exports hold no credential, key, address, host, username or ID")
        return 1 if findings else 0
    if not (args.source and args.out):
        ap.error("give the source and the output file")
    try:
        if args.kind == "n8n-live":
            return write_clean("n8n", clean_n8n(read_live_n8n(args.source)), Path(args.out), private)
        raw = json.loads(Path(args.source).read_text(encoding="utf-8"))
        if args.kind == "n8n":
            return write_clean("n8n", clean_n8n(raw), Path(args.out), private)
        return write_clean("zapier", clean_zapier(raw, private), Path(args.out), private)
    except (LookupError, OSError, ValueError, KeyError) as e:
        print(f"CANNOT RUN {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
