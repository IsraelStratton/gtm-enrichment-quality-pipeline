#!/usr/bin/env python3
"""The rules page and the workflow, kept in step (KB-137 A4.1): a push fails when they disagree, either way.

The rules page is docs/rules.md. Every workflow file with a "DQ Checks" node runs those rules: version 1
(n8n/workflow.json) and the two routing workflows that copy its rules node unchanged. For each one:

  the rule table      every rule on the page is in the workflow, and every rule the workflow checks is
                      on the page. A rule is a "// DQ-nn:" comment in the DQ Checks code, followed by the
                      reason codes that part of the code records. A Block rule's codes go in reasonCodes
                      (the row is quarantined); a Flag rule's go in flags (the row still loads). The codes
                      under each comment must be exactly the page's codes for the rules it names, of the
                      page's type, and no code may be recorded outside a rule's part
  the Route rule      DQ-04 says the write is an upsert keyed on clay_domain_key: the workflow's write
                      must use that key (Clay_Domain_Key__c, its Salesforce twin, on Salesforce)
  the quarantine      the page's quarantine columns are exactly what Format Quarantine writes and what the
                      Quarantine Table node maps

So removing a rule, renaming a code, or turning a Block into a Flag on either side fails the check.
scripts/prepush_check.py runs it on the commit being pushed, and tests/test_rules_sync.py in CI.

  python scripts/rules_sync.py            # the working tree
  python scripts/rules_sync.py --ref HEAD # a commit

Exit codes: 0 in step, 1 a finding, 2 could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playbook_bar import git_reader, tree_reader  # noqa: E402

RULES_PAGE = "docs/rules.md"
WORKFLOWS = ["n8n/workflow.json", "n8n/workflow-v2.json", "n8n/workflow-v2-salesforce.json"]
Reader = Callable[[str], "str | None"]

RULE_ROW = re.compile(r"^\|\s*(DQ-\d+)\s*\|(.*)\|\s*$")
CODE_CELL = re.compile(r"`([A-Z][A-Z0-9_]+)`")
RULE_COMMENT = re.compile(r"^\s*//\s*((?:DQ-\d+)(?:\s*(?:/|,|and)\s*DQ-\d+)*)\s*:")
PUSH = re.compile(r"\b(reasonCodes|flags)\.push\(\s*'([A-Z][A-Z0-9_]+)'\s*\)")
KIND = {"reasonCodes": "Block", "flags": "Flag"}


def parse_rules_page(text: str) -> dict:
    """The rule table and the quarantine columns, as the page states them."""
    rules = {}
    table = text.split("## Rule table", 1)[1].split("\n## ", 1)[0] if "## Rule table" in text else ""
    for line in table.splitlines():
        m = RULE_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        # | ID | Check | Type | Outcome | Reason code |
        kind = cells[1] if len(cells) > 1 else ""
        codes = set(CODE_CELL.findall(cells[3])) if len(cells) > 3 else set()
        rules[m.group(1)] = {"type": kind, "codes": codes}
    columns = []
    if "## Quarantine data table" in text:
        section = text.split("## Quarantine data table", 1)[1].split("\n## ", 1)[0]
        columns = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.M)
    return {"rules": rules, "quarantine_columns": columns}


def parse_rules_code(js: str) -> tuple[list[dict], list[str]]:
    """The rule parts of the DQ Checks code: [{ids, codes: {code: kind}}], and codes recorded outside any part."""
    parts, stray, current = [], [], None
    for line in js.splitlines():
        m = RULE_COMMENT.match(line)
        if m:
            current = {"ids": re.findall(r"DQ-\d+", m.group(1)), "codes": {}}
            parts.append(current)
            continue
        for target, code in PUSH.findall(line):
            if current is None:
                stray.append(code)
            else:
                current["codes"][code] = KIND[target]
    return parts, stray


def _node(wf: dict, name: str) -> dict | None:
    return next((n for n in wf.get("nodes", []) if n.get("name") == name), None)


def upsert_on_domain_key(wf: dict) -> bool:
    """DQ-04: HubSpot's batch upsert with idProperty clay_domain_key, or Salesforce's upsert on Clay_Domain_Key__c."""
    for n in wf.get("nodes", []):
        url = (n.get("parameters") or {}).get("url", "")
        if n.get("type") != "n8n-nodes-base.httpRequest":
            continue
        if url.endswith("/sobjects/Account/Clay_Domain_Key__c"):
            return True
        if url.endswith("/crm/v3/objects/companies/batch/upsert"):
            # The body is built in a Code node upstream: version 1's own, or the routing engine's.
            return any("idProperty: 'clay_domain_key'" in (m.get("parameters") or {}).get("jsCode", "")
                       for m in wf["nodes"] if m.get("type") == "n8n-nodes-base.code")
    return False


def check_workflow(rel: str, wf: dict, page: dict) -> list[str]:
    f = []
    rules = page["rules"]
    dq = _node(wf, "DQ Checks")
    if dq is None:
        return [f"{rel}: has no DQ Checks node"]
    parts, stray = parse_rules_code(dq["parameters"].get("jsCode", ""))
    in_code = {rid for p in parts for rid in p["ids"]}
    for rid, rule in sorted(rules.items()):
        if rule["type"] in ("Block", "Flag") and rid not in in_code:
            f.append(f"{rel}: {rid} is on the rules page but the workflow does not check it")
    for rid in sorted(in_code - set(rules)):
        f.append(f"{rel}: the workflow checks {rid}, which is not on the rules page")
    for rid in sorted(in_code & set(rules)):
        if rules[rid]["type"] not in ("Block", "Flag"):
            f.append(f"{rel}: the workflow checks {rid} in the rules node, but the page says it is a {rules[rid]['type']} rule")
    for p in parts:
        named = [rid for rid in p["ids"] if rid in rules]
        expected = {code: rules[rid]["type"] for rid in named for code in rules[rid]["codes"]}
        label = " / ".join(p["ids"])
        for code in sorted(set(expected) - set(p["codes"])):
            f.append(f"{rel}: the page gives {label} the code {code}, which the workflow does not record there")
        for code in sorted(set(p["codes"]) - set(expected)):
            f.append(f"{rel}: the workflow records {code} under {label}, which the page does not give it")
        for code in sorted(set(p["codes"]) & set(expected)):
            if p["codes"][code] != expected[code]:
                f.append(f"{rel}: {code} is a {expected[code]} code on the page, but the workflow records it as a {p['codes'][code]}")
    for code in stray:
        f.append(f"{rel}: the workflow records {code} outside any rule's part of the code")
    for rid in [rid for rid, r in rules.items() if r["type"] == "Route"]:
        if not upsert_on_domain_key(wf):
            f.append(f"{rel}: {rid} says the write is an upsert keyed on clay_domain_key, but the workflow's write step does not upsert on it")
    fmt, table = _node(wf, "Format Quarantine"), _node(wf, "Quarantine Table")
    cols = page["quarantine_columns"]
    if fmt is None or table is None:
        f.append(f"{rel}: has no Format Quarantine or Quarantine Table node")
    else:
        body = fmt["parameters"].get("jsCode", "").split("json: {", 1)[-1].split("}", 1)[0]
        written = re.findall(r"^\s*([a-z_]+)\s*:", body, re.M)
        mapped = list((table["parameters"].get("columns") or {}).get("value", {}))
        for name, have in (("Format Quarantine", written), ("Quarantine Table", mapped)):
            for c in [c for c in cols if c not in have]:
                f.append(f"{rel}: the quarantine column {c} is on the rules page but {name} does not write it")
            for c in [c for c in have if c not in cols]:
                f.append(f"{rel}: {name} writes the quarantine column {c}, which is not on the rules page")
    return f


def check_all(read: Reader) -> list[str]:
    text = read(RULES_PAGE)
    if text is None:
        return [f"{RULES_PAGE} is missing"]
    page = parse_rules_page(text)
    if not page["rules"]:
        return [f"{RULES_PAGE}: no rule table found under '## Rule table'"]
    if not page["quarantine_columns"]:
        return [f"{RULES_PAGE}: no quarantine columns found under '## Quarantine data table'"]
    out = []
    for rel in WORKFLOWS:
        wf_text = read(rel)
        if wf_text is None:
            out.append(f"{rel} is missing")
            continue
        out += check_workflow(rel, json.loads(wf_text), page)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", help="check a commit (for example HEAD) instead of the working tree")
    args = ap.parse_args(argv)
    try:
        findings = check_all(git_reader(args.ref) if args.ref else tree_reader())
    except (KeyError, TypeError, ValueError) as e:
        print(f"CANNOT RUN {type(e).__name__}: {e}")
        return 2
    for x in findings:
        print(f"FAIL {x}")
    if not findings:
        print(f"PASS the rules page and the {len(WORKFLOWS)} workflows with the data rules agree, both ways")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
