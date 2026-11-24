#!/usr/bin/env python3
"""Make the docs that describe the build from the files they describe (KB-137 A4.2, and the wrap's README).

  docs/v2/workflows.md   every workflow export (clean_exports.EXPORTS): a diagram and a numbered step list,
                         made from the workflow file alone. The diagram's numbers are the list's numbers
  README.md              only the parts between <!-- generated:NAME start --> and <!-- generated:NAME end -->:
                           rules     the data rules, from docs/rules.md (the page the workflows are checked against)
                           reach     what each workflow starts from, what it reaches, where a person decides
                           diagram   the chapter 2 routing workflow, from n8n/workflow-v2.json
                           steps     its step list
                           results   the routing eval with the attack line (A2.3) and the quote desk's
                                     three designs (B2), from the saved results.json files
                           costs     the cost table, from docs/v2/cost-sheet.json
                         Everything else in the README is written by hand.

So the README's diagram, its step list and its figures cannot drift from the files: tests/test_build_docs.py
remakes them and fails if they differ, and so does scripts/prepush_check.py on the commit being pushed.

  python scripts/build_docs.py           # write both files
  python scripts/build_docs.py --check   # exit 1 if either is out of date

Exit codes: 0 done (or up to date), 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_exports import EXPORTS  # noqa: E402
from playbook_bar import git_reader, tree_reader  # noqa: E402
from rules_sync import parse_rules_code  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
README = "README.md"
WORKFLOWS_MD = "docs/v2/workflows.md"
MAIN_WORKFLOW = "n8n/workflow-v2.json"
Reader = Callable[[str], "str | None"]

TITLES = {
    "n8n/workflow.json": ("Clean data into HubSpot (version 1)", "Chapter 1"),
    "n8n/workflow-v2.json": ("Lead routing with a person's approval, writing to HubSpot", "Chapter 2"),
    "n8n/workflow-v2-salesforce.json": ("The same routing, writing to Salesforce", "Chapter 4"),
    "n8n/workflow-v2-quote-desk.json": ("Quote exceptions desk", "Chapter 5"),
    "slice/n8n/slice-workflow.json": ("The slice in n8n: an approved lead, a tracking row, an email to the owner", "Chapter 3"),
    "slice/n8n/create-tracker-workflow.json": ("Make the tracker sheet (run once; each run makes another sheet)", "Chapter 3"),
    "slice/make/slice-scenario.blueprint.json": ("The slice in Make", "Chapter 3"),
    "slice/zapier/zap-builds.json": ("The slice in Zapier: ways 1 to 3", "Chapter 3"),
}
SYSTEMS = {
    "api.anthropic.com": "Claude API",
    "api.hubapi.com": "HubSpot",
    "your-my-domain.my.salesforce.com": "Salesforce",
    "sheets.googleapis.com": "Google Sheets",
    "gmail.googleapis.com": "Gmail",
    "www.googleapis.com": "Google account",
}
VERB = {"GET": "reads", "POST": "writes", "PATCH": "writes", "PUT": "writes", "DELETE": "deletes"}


# ---------------------------------------------------------------- n8n: graph, order, words


def n8n_edges(wf: dict) -> list[tuple[str, str, int, int]]:
    """(from, to, output index, number of outputs) for every connection."""
    out = []
    for src, kinds in wf["connections"].items():
        for branches in kinds.values():
            for i, branch in enumerate(branches):
                for link in branch:
                    out.append((src, link["node"], i, len(branches)))
    return out


def branch_label(node: dict, index: int, outputs: int) -> str:
    t = node["type"].rsplit(".", 1)[-1]
    if t == "if":
        return ["yes", "no"][index] if index < 2 else f"output {index + 1}"
    if t == "splitInBatches":
        return ["all done", "each one"][index] if index < 2 else f"output {index + 1}"
    return f"output {index + 1}" if outputs > 1 else ""


def run_order(wf: dict) -> tuple[list[str], set[tuple[str, str]]]:
    """The nodes in the order a run reaches them, and the edges that loop back.

    Depth first from each trigger; a node is listed once everything that feeds it (bar a loop's way back) is
    listed; at a fork, the branch with the smaller part of its own goes first (the quarantine before the main
    path, a loop's body before what follows it)."""
    names = [n["name"] for n in wf["nodes"]]
    edges = n8n_edges(wf)
    succ: dict[str, list[tuple[int, str]]] = {n: [] for n in names}
    for a, b, i, _ in edges:
        succ[a].append((i, b))
    incoming = {b for _, b, _, _ in edges}
    starts = [n for n in names if n not in incoming]
    back, state = set(), {}

    def dfs(n):
        state[n] = "open"
        for _, m in sorted(succ[n]):
            if state.get(m) == "open":
                back.add((n, m))
            elif m not in state:
                dfs(m)
        state[n] = "done"

    for s in starts:
        if s not in state:
            dfs(s)
    fwd = {n: [(i, m) for i, m in sorted(succ[n]) if (n, m) not in back] for n in names}

    def reach(n, seen=None):
        seen = set() if seen is None else seen
        for _, m in fwd[n]:
            if m not in seen:
                seen.add(m)
                reach(m, seen)
        return seen

    indeg = {n: 0 for n in names}
    for n in names:
        for _, m in fwd[n]:
            indeg[m] += 1
    order, stack = [], list(reversed(starts))
    while stack:
        n = stack.pop()
        order.append(n)
        ready = []
        for i, m in fwd[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append((i, m))
        if len(ready) > 1:
            others = {m: set().union(*({x} | reach(x) for _, x in ready if x != m)) for _, m in ready}
            own = {m: len(({m} | reach(m)) - others[m]) for _, m in ready}
            ready.sort(key=lambda im: (own[im[1]], im[0]))
        for _, m in reversed(ready):
            stack.append(m)
    order += [n for n in names if n not in order]
    return order, back


def short_type(node: dict) -> str:
    return node["type"].rsplit(".", 1)[-1]


def kind(node: dict) -> str:
    t = short_type(node)
    p = node.get("parameters") or {}
    if t in ("formTrigger", "webhook", "manualTrigger"):
        return "start"
    if t == "form":
        return "person" if p.get("operation") == "page" else "page"
    if t == "if":
        return "branch"
    if t in ("postgres", "dataTable"):
        return "store"
    if t == "httpRequest":
        return "ai" if urlsplit(p.get("url", "")).hostname == "api.anthropic.com" else "call"
    return "step"


def host_path(url: str) -> tuple[str, str]:
    u = urlsplit(url.replace("={{", "").strip())
    return (u.hostname or ""), u.path


def credential_names(node: dict) -> list[str]:
    return [c.get("name", "") for c in (node.get("credentials") or {}).values()]


def code_summary(js: str) -> str:
    lines = js.splitlines()
    engines = []
    if "function parsePlaybook" in js:
        engines.append("`engine/routing.js`")
    if "function parseDeskPlaybook" in js:
        engines.append("`engine/quotes.js`")
    said = []
    marker = next((i for i, line in enumerate(lines) if "===== n8n node:" in line), None)
    if marker is not None:
        for line in lines[marker + 1:]:
            s = line.strip()
            if not s.startswith("//"):
                break
            said.append(s.lstrip("/ ").strip())
    else:
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if not s.startswith("//"):
                break
            text = s.lstrip("/ ").strip().strip("─ ").strip()
            if text:
                said.append(text)
    parts, _ = parse_rules_code(js)
    if parts:
        text = "Runs the data rules " + ", ".join(rid for p in parts for rid in p["ids"]) + " on every row"
    elif said:
        text = " ".join(said).rstrip(".")
    else:
        added = re.search(r"Object\.assign\(\{\}, \$json, \{([^}]*)\}", js)
        reads = list(dict.fromkeys(re.findall(r"\$\('([^']+)'\)", js)))
        if added:
            text = "Adds " + ", ".join(f"`{k}`" for k in re.findall(r"(\w+):", added.group(1))) + " to each item"
        elif reads:
            text = "Works from " + (", ".join(reads[:-1]) + " and " + reads[-1] if len(reads) > 1 else reads[0])
        else:
            text = "A short Code step"
    if engines:
        text += ". Engine: " + " and ".join(engines)
    return text


IF_OPS = {"equals": "is", "gt": "is more than", "lt": "is less than", "true": "is true", "false": "is false", "notEquals": "is not"}


def describe(node: dict) -> str:
    t, p = short_type(node), node.get("parameters") or {}
    if t == "formTrigger":
        path = (p.get("options") or {}).get("path")
        where = f"a form at `/form/{path}`" if path else "a form"
        return f"Starts from {where}: \"{p.get('formTitle', '')}\". A person uploads or presses start"
    if t == "webhook":
        guard = ", and only with the key header" if p.get("authentication") == "headerAuth" else ""
        return f"Starts when a lead is sent to `{p.get('httpMethod', 'GET')} /webhook/{p.get('path', '')}`{guard}"
    if t == "manualTrigger":
        return "Started by hand in the n8n editor"
    if t == "form":
        if p.get("operation") == "page":
            src = re.search(r"\$\('([^']+)'\)", str(p.get("jsonOutput", "")))
            return ("**A person decides here.** The run waits until this page is submitted" +
                    (f"; its fields are built by {src.group(1)}" if src else ""))
        return "The closing page: what happened, read back from the run"
    if t == "extractFromFile":
        return {"csv": "Reads the uploaded file as CSV rows", "text": "Turns the file into text"}.get(p.get("operation"), "Reads a file")
    if t == "readWriteFile":
        return f"Reads `{p.get('fileSelector', '')}`, from the repo's skins folder, mounted read-only"
    if t == "splitInBatches":
        return f"Takes the items {p.get('batchSize', 1)} at a time, round the loop until all are done"
    if t == "if":
        conds = (p.get("conditions") or {}).get("conditions", [])
        words = []
        for c in conds:
            left = str(c.get("leftValue", "")).replace("={{", "").replace("}}", "").strip()
            op = (c.get("operator") or {}).get("operation", "")
            right = c.get("rightValue")
            single = (c.get("operator") or {}).get("singleValue") or op in ("true", "false")
            words.append(f"`{left}` {IF_OPS.get(op, op)}" + ("" if single and op in ("true", "false") or right in ("", None)
                                                             else f" `{str(right).lower() if isinstance(right, bool) else right}`"))
        return "Branches: yes if " + " and ".join(words)
    if t == "code":
        return code_summary(p.get("jsCode", ""))
    if t == "httpRequest":
        host, path = host_path(p.get("url", ""))
        system = SYSTEMS.get(host, host)
        creds = credential_names(node)
        signed = f", signed in as the n8n credential \"{creds[0]}\"" if creds else ""
        ai = " **The AI step:** one call, structured output, no tools." if host == "api.anthropic.com" else ""
        return f"{p.get('method', 'GET')} to {system} (`{host}{path}`){signed}.{ai}".replace("..", ".")
    if t == "postgres":
        fns = sorted(set(re.findall(r"gtm_v2\.\w+", p.get("query", ""))))
        return f"Run log: `{'`, `'.join(fns)}`, with the add-only login \"{(credential_names(node) or [''])[0]}\""
    if t == "dataTable":
        ref = p.get("dataTableId") or {}
        return f"Adds the row to the n8n data table `{ref.get('value', '')}` (found by name when published)"
    if t == "set":
        return "Shapes the tracking row from the lead"
    return t


SHAPE = {"start": ('(["', '"])'), "person": ('{{"', '"}}'), "page": ('(["', '"])'), "branch": ('{"', '"}'),
         "store": ('[("', '")]'), "call": ('[["', '"]]'), "ai": ('[["', '"]]'), "step": ('["', '"]')}
LEGEND = ("Thick border: a person decides. Dashed border: the AI step. Diamond: a yes-or-no branch. "
          "Cylinder: a log or a table. Double-sided box: a call to another system.")


def label(text: str) -> str:
    return text.replace('"', "'")


def n8n_diagram(wf: dict) -> str:
    order, back = run_order(wf)
    by = {n["name"]: n for n in wf["nodes"]}
    ids = {name: f"s{i}" for i, name in enumerate(order, 1)}
    lines = ["```mermaid", "flowchart TD"]
    for i, name in enumerate(order, 1):
        a, b = SHAPE[kind(by[name])]
        lines.append(f"  {ids[name]}{a}{i}. {label(name)}{b}")
    for src, dst, idx, outs in n8n_edges(wf):
        lab = branch_label(by[src], idx, outs)
        if (src, dst) in back:
            lab = (lab + ", " if lab else "") + "next one"
        arrow = f" -->|{lab}| " if lab else " --> "
        lines.append(f"  {ids[src]}{arrow}{ids[dst]}")
    person = [ids[n] for n in order if kind(by[n]) == "person"]
    ai = [ids[n] for n in order if kind(by[n]) == "ai"]
    lines += ["  classDef person stroke-width:4px", "  classDef ai stroke-dasharray: 6 4"]
    if person:
        lines.append(f"  class {','.join(person)} person")
    if ai:
        lines.append(f"  class {','.join(ai)} ai")
    lines.append("```")
    return "\n".join(lines)


def n8n_steps(wf: dict) -> str:
    order, back = run_order(wf)
    by = {n["name"]: n for n in wf["nodes"]}
    num = {name: i for i, name in enumerate(order, 1)}
    loops_to = {a: b for a, b in back}
    out = []
    for i, name in enumerate(order, 1):
        line = f"{i}. **{name}** ({short_type(by[name])}). {describe(by[name])}."
        if name in loops_to:
            line = line[:-1] + f". Then back to step {num[loops_to[name]]} for the next one."
        out.append(line.replace("..", "."))
    return "\n".join(out)


# ---------------------------------------------------------------- Make and Zapier


def make_steps(bp: dict) -> list[tuple[str, str]]:
    steps = []
    for m in bp["flow"]:
        mod, mapper = m["module"], m.get("mapper") or {}
        restore = (m.get("metadata") or {}).get("restore") or {}
        params = restore.get("parameters") or {}
        if mod == "gateway:CustomWebHook":
            steps.append(("Custom webhook", f"Starts when a lead is sent to the webhook \"{(params.get('hook') or {}).get('label', '')}\""))
        elif mod == "http:MakeRequest":
            host, path = host_path(mapper.get("url", ""))
            conn = (params.get("oAuthAccount") or {}).get("label", "")
            steps.append((f"HTTP: {SYSTEMS.get(host, host)}", f"{mapper.get('method', 'get').upper()} to `{host}{path}`, through the connection \"{conn}\""))
        elif mod == "util:ComposeTransformer":
            steps.append(("Compose a string", "Writes the email, addressed to the signed-in account's own inbox"))
        else:
            steps.append((mod, mod))
    return steps


def linear_diagram(names: list[str]) -> str:
    lines = ["```mermaid", "flowchart LR"]
    for i, n in enumerate(names, 1):
        lines.append(f"  s{i}[\"{i}. {label(n)}\"]")
    for i in range(1, len(names)):
        lines.append(f"  s{i} --> s{i + 1}")
    lines.append("```")
    return "\n".join(lines)


def zapier_section(z: dict) -> list[str]:
    out = []
    for zap in z["zaps"]:
        out += [f"#### Way {zap['way']}: {zap['name']} ({zap['plan']}, {zap['state']})", ""]
        out.append(linear_diagram([f"{s['app']}: {s['event']}" for s in zap["steps"]]))
        out.append("")
        for s in zap["steps"]:
            settings = "; ".join(f"{x['setting']}: {x['value']}" for x in s.get("settings", []) if "\n" not in x["value"])
            long = [x["setting"] for x in s.get("settings", []) if "\n" in x["value"]]
            extra = (f" The {' and '.join(long)} {'is' if len(long) == 1 else 'are'} in the file." if long else "")
            note = f" {s['note']}." if s.get("note") else ""
            out.append(f"{s['step']}. **{s['app']}, {s['event']}**. {settings}.{extra}{note}".replace("..", ".").replace(". .", "."))
        out.append("")
    mcp = z["mcp_server"]
    action = mcp["actions"][0]
    fixed = ", ".join(f"{f['field']} = `{f['value']}`" for f in action["fixed"])
    out += [f"#### Way {mcp['way']}: Zapier MCP", "",
            f"Mode: {mcp['mode']}. One action: {action['app']}, {action['action']}, with {fixed}; {action['ai_filled']} filled by "
            f"Claude. Client: {mcp['client']}.", "",
            f"Way {z['admin_on_paper']['way']}, the admin settings, is on paper: [`{z['admin_on_paper']['where']}`](../../{z['admin_on_paper']['where']}).", ""]
    return out


# ---------------------------------------------------------------- reach


def reach_row(rel: str, data: dict) -> dict:
    if rel.endswith(".blueprint.json"):
        steps = make_steps(data)
        hosts = [host_path(m.get("mapper", {}).get("url", "")) + ((m.get("mapper") or {}).get("method", "get").upper(),)
                 for m in data["flow"] if m["module"] == "http:MakeRequest"]
        return {"tool": "Make", "start": "a webhook", "reaches": systems_from([(h, method) for h, _, method in hosts]),
                "person": "before it: the lead arrives approved", "steps": len(steps)}
    if rel.endswith("zap-builds.json"):
        apps = sorted({s["app"] for zap in data["zaps"] for s in zap["steps"]})
        return {"tool": "Zapier", "start": "a form (Free) or a webhook with a key filter (Pro)",
                "reaches": "inside Zapier only: " + ", ".join(a for a in apps if a not in ("Filter by Zapier", "Code by Zapier")),
                "person": "Free: the approver fills in the form. Pro: Human in the Loop approves the AI's note",
                "steps": sum(len(z["steps"]) for z in data["zaps"])}
    by = data["nodes"]
    calls = []
    for n in by:
        p = n.get("parameters") or {}
        if short_type(n) == "httpRequest":
            calls.append((host_path(p.get("url", ""))[0], p.get("method", "GET")))
    extra = []
    if any(short_type(n) == "postgres" for n in by):
        extra.append("run log (add only)")
    if any(short_type(n) == "readWriteFile" for n in by):
        extra.append("playbook (read only)")
    if any(short_type(n) == "dataTable" for n in by):
        extra.append("n8n quarantine table")
    starts = [n for n in by if kind(n) == "start"]
    start = {"formTrigger": "a form", "webhook": "a webhook with a key", "manualTrigger": "by hand"}.get(short_type(starts[0]), "?") if starts else "?"
    persons = [n["name"] for n in by if kind(n) == "person"]
    if persons:
        person = " and ".join(persons)
    elif "create-tracker" in rel:
        person = "nobody needed: run once, by hand"
    elif rel.startswith("slice/"):
        person = "before it: the lead arrives approved"
    else:
        person = "nobody needed: no AI step; the data rules decide"
    return {"tool": "n8n", "start": start, "reaches": ", ".join(x for x in [systems_from(calls)] + extra if x),
            "person": person, "steps": len(by)}


def systems_from(calls: list[tuple[str, str]]) -> str:
    verbs: dict[str, set[str]] = {}
    for host, method in calls:
        verbs.setdefault(SYSTEMS.get(host, host), set()).add(VERB.get(method.upper(), method.lower()))
    order = ["Claude API", "HubSpot", "Salesforce", "Google Sheets", "Gmail", "Google account"]
    words = []
    for system in sorted(verbs, key=lambda s: order.index(s) if s in order else 99):
        v = verbs[system]
        if system == "Claude API":
            words.append("Claude API (asks)")
        elif system == "Gmail":
            words.append("Gmail (sends)")
        elif system == "Google account":
            words.append("Google account (reads its own address)")
        else:
            words.append(f"{system} ({' and '.join(sorted(v))})")
    return ", ".join(words)


def reach_table(read: Reader, prefix: str = "") -> str:
    lines = ["| Workflow | Tool | Steps | Starts from | Reaches | Where a person decides |", "|---|---|---|---|---|---|"]
    for files in EXPORTS.values():
        for rel in files:
            row = reach_row(rel, json.loads(read(rel)))
            title, chapter = TITLES[rel]
            lines.append(f"| [{chapter}: {title}]({prefix}{rel}) | {row['tool']} | {row['steps']} | {row['start']} | {row['reaches']} | {row['person']} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- the workflows page


def workflows_page(read: Reader) -> str:
    L = ["# The workflows, step by step", "",
         "Made by `scripts/build_docs.py` from the workflow files themselves; a test remakes this page and fails if it "
         "differs, so it cannot drift from what runs (KB-137 A4.2). The numbers in each diagram are the step numbers "
         "in its list. " + LEGEND, "",
         "A step marked \"Engine\" runs that engine file pasted in whole, so n8n runs exactly the code pytest tests. "
         "A step's words come from the file: the comment at the top of its code, or what its settings say.", "",
         "Every file here is a clean export: no credential, key, address, host, username or ID "
         "(`scripts/clean_exports.py`, checked on every push). Credentials and data tables are named, and found by name "
         "when the workflow is imported.", "",
         "## What each one starts from and reaches", "", reach_table(read, "../../"), ""]
    for rel in EXPORTS["n8n"]:
        wf = json.loads(read(rel))
        title, chapter = TITLES[rel]
        L += [f"## {chapter}: {title}", "", f"File: [`{rel}`](../../{rel}). Workflow name in n8n: \"{wf['name']}\".", "",
              n8n_diagram(wf), "", n8n_steps(wf), ""]
    bp = json.loads(read(EXPORTS["make"][0]))
    title, chapter = TITLES[EXPORTS["make"][0]]
    steps = make_steps(bp)
    L += [f"## {chapter}: {title}", "", f"File: [`{EXPORTS['make'][0]}`](../../{EXPORTS['make'][0]}). Scenario name: \"{bp['name']}\".", "",
          linear_diagram([s for s, _ in steps]), ""]
    L += [f"{i}. **{name}**. {what}." for i, (name, what) in enumerate(steps, 1)] + [""]
    z = json.loads(read(EXPORTS["zapier"][0]))
    title, chapter = TITLES[EXPORTS["zapier"][0]]
    L += [f"## {chapter}: {title}", "", f"File: [`{EXPORTS['zapier'][0]}`](../../{EXPORTS['zapier'][0]}), the as-built record "
          "(Zapier's own export is cleaned by `scripts/clean_exports.py zapier` when it is in hand).", ""]
    L += zapier_section(z)
    return "\n".join(L).rstrip() + "\n"


# ---------------------------------------------------------------- README parts


def rules_block(read: Reader) -> str:
    text = read("docs/rules.md")
    table = text.split("## Rule table", 1)[1].split("\n## ", 1)[0].strip()
    rows = [line for line in table.splitlines() if line.startswith("|")]
    return "\n".join(rows) + "\n\nFrom [`docs/rules.md`](docs/rules.md), the rules page. A test on every push fails if the page and a workflow disagree, either way."


def pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".0%", "%")


def results_block(read: Reader) -> str:
    from route_eval import grade

    live = json.loads(read("skins/lead-routing/eval/results.json"))
    old = json.loads(read("skins/lead-routing/eval/results-1.0.0.json"))
    bar = json.loads(read("skins/lead-routing/eval/bar.json"))["lines"]
    cols = [(f"{m} on playbook {live['playbook']['version']} (live)", live["models"][m]["summary"]) for m in live["models"]]
    cols += [(f"{m} on playbook {old['playbook']['version']}", old["models"][m]["summary"]) for m in old["models"]]
    rows = [("Route matches the label", "route_accuracy"), ("Intent matches the label", "intent_accuracy"),
            ("Priority matches the label", "priority_accuracy"), ("Rows that must be reviewed, flagged", "review_caught"),
            ("Attacks blocked", "attacks_blocked")]
    L = ["**Routing: the 40-row eval.** The same labelled enquiries through the same engine n8n runs, three rounds per "
         "model, graded against a bar fixed before the run.", "",
         "| Measure | Bar | " + " | ".join(c for c, _ in cols) + " |", "|---|---|" + "---|" * len(cols)]
    for name, key in rows:
        L.append(f"| {name} | {pct(bar[key]['min'])} | " + " | ".join(pct(s[key]) for _, s in cols) + " |")
    L.append("| Cost per decision (US$) | | " + " | ".join(f"{s['cost_per_decision_usd']:.5f}" for _, s in cols) + " |")
    L.append("| Meets the bar | | " + " | ".join("yes" if s["passes"] else "no" for _, s in cols) + " |")
    attack_rows = [r for r in live["models"][live["kept"]]["rows"] if r["case_type"] == "attack"]
    missed = sorted({r["lead_id"] for r in attack_rows if not grade(r, r)["blocked"]})
    s = live["models"][live["kept"]]["summary"]
    kinds = sorted({r["attack_kind"] for r in attack_rows})
    L += ["", f"**Kept: {live['kept']}.** {live['kept_reason']} Results: "
          "[`results.md`](skins/lead-routing/eval/results.md) (live) and [`results-1.0.0.md`](skins/lead-routing/eval/results-1.0.0.md) "
          "(the two models).", "",
          f"**Attacks (A2):** {len({r['lead_id'] for r in attack_rows})} attack rows of {len(kinds)} kinds, {live['rounds']} rounds each: "
          f"{s['attacks']} blocked, a block rate of {pct(s['attacks_blocked'])}, on the live playbook "
          f"{live['playbook']['version']} with {live['kept']}. "
          + ("Missed: none." if not missed else f"Missed: {', '.join(missed)}, listed on the results page.")
          + " Blocked means the planted text moved neither the route nor the priority, and the row still went to a person "
          "or was marked as spam.", ""]
    desk = json.loads(read("skins/quote-desk/eval/results.json"))
    designs = list(desk["designs"])
    drow = [("Action matches the label", "action_accuracy", lambda v: f"{v * 100:.0f}%"),
            ("Rules broken match exactly", "rules_exact", lambda v: f"{v * 100:.0f}%"),
            ("Attacks blocked", "attacks", str),
            ("Customer drafts pass the check", "drafts_pass_check", lambda v: f"{v * 100:.0f}%"),
            ("Cost per quote (US$)", "cost_per_quote_usd", lambda v: f"{v:.5f}"),
            ("Seconds per quote", "seconds_per_quote", lambda v: f"{v:.1f}"),
            ("Claude calls per quote", "calls_per_quote", lambda v: f"{v:.0f}"),
            ("Meets the bar", "passes", lambda v: "yes" if v else "no")]
    L += [f"**Quote desk: three designs on the same {desk['cases']} quotes (B2).** {desk['model']}, {desk['rounds']} rounds, "
          f"playbook {desk['playbook']['version']}; the bar was fixed before the first run.", "",
          "| Measure | " + " | ".join(designs) + " |", "|---|" + "---|" * len(designs)]
    for name, key, fmt in drow:
        L.append(f"| {name} | " + " | ".join(fmt(desk["designs"][d]["summary"][key]) for d in designs) + " |")
    cheapest = desk["designs"][desk["kept"]]["summary"]["cost_per_quote_usd"]
    others = [f"`{d}`, which also passed, cost {desk['designs'][d]['summary']['cost_per_quote_usd'] / cheapest:.1f} times as much"
              for d in designs if d != desk["kept"] and desk["designs"][d]["summary"]["passes"]]
    failed = [f"`{d}` missed the bar on {' and '.join(x.replace('_', ' ') for x in desk['designs'][d]['summary']['failed_lines'])}"
              for d in designs if not desk["designs"][d]["summary"]["passes"]]
    L += ["", f"**Kept: {desk['kept']}.** {desk['kept_reason']} "
          + "".join(f"{o}. " for o in others)
          + "".join(f"{x}. " for x in failed)
          + "Results: [`results.md`](skins/quote-desk/eval/results.md)."]
    return "\n".join(L)


def costs_block(read: Reader) -> str:
    snap = json.loads(read("docs/v2/cost-sheet.json"))
    D = lambda v: Decimal(str(v)) if v is not None else Decimal(0)  # noqa: E731
    live = next(r for r in snap["routing_live_writes"] if r["model"] == "claude-haiku-5-5")
    route_cpd = D(live["total_cost_usd"]) / live["proposals"]
    route_cpw = D(live["total_cost_usd"]) / live["written"]
    desk = next(r for r in snap["desk_by_design"] if r["design"] == "one_prompt" and r["source"] == "n8n")
    desk_cpq = D(desk["total_cost_usd"]) / desk["quotes"]
    by_model = {}
    for r in snap["routing_by_model"]:
        t, n = by_model.get(r["model"], (Decimal(0), 0))
        by_model[r["model"]] = (t + D(r["total_cost_usd"]), n + r["decisions"])
    avg = {m: t / n for m, (t, n) in by_model.items()}
    ratio = avg["claude-sonnet-5-5"] / avg["claude-haiku-5-5"]
    total = sum(D(r["total_cost_usd"]) for r in snap["routing_by_model"]) + sum(D(r["total_cost_usd"]) for r in snap["desk_by_design"])
    L = ["| Part | Plan | Fixed cost | One use costs |", "|---|---|---|---|",
         "| n8n | Community Edition, on this Mac | US$0 | No limit |",
         "| Run log | Supabase Postgres, on this Mac | US$0 | No limit |",
         "| Make | Free | US$0 | 5 credits a lead, of 1,000 a month |",
         "| Zapier | Free; the Pro trial for way 2 | US$0 | 1 task a lead on Free (100 a month); 4 on Pro |",
         "| HubSpot | Free portal | US$0 | Nothing per record |",
         "| Salesforce and Agentforce | Developer Edition, no payment method | US$0 | Nothing per record or agent action |",
         f"| Claude API, routing | Pay per call; workspace limit US$10 a month | US$0 | US${route_cpd:.5f} a decision (Haiku 5.5, live runs); "
         f"US${route_cpw:.5f} per record written |",
         f"| Claude API, quote desk | The same workspace | US$0 | US${desk_cpq:.5f} a quote (one prompt, live run) |",
         "", f"Sonnet 5.5 costs {ratio:.0f} times as much as Haiku 5.5 per routing decision. All AI spend in the run log to "
         f"{snap['made_at'][:10]}: US${total:.2f}, evals included. Per-call figures come from the run log through "
         "[`docs/v2/cost-sheet.md`](docs/v2/cost-sheet.md), made by script with each price's date and source. Nothing is "
         "scheduled: every workflow starts by hand and can sit switched off at no cost."]
    return "\n".join(L)


def readme_blocks(read: Reader) -> dict[str, str]:
    wf = json.loads(read(MAIN_WORKFLOW))
    return {
        "rules": rules_block(read),
        "reach": reach_table(read),
        "diagram": n8n_diagram(wf) + "\n\n" + LEGEND + " Made from [`n8n/workflow-v2.json`](n8n/workflow-v2.json) by "
                   "`scripts/build_docs.py`; every workflow is drawn in [`docs/v2/workflows.md`](docs/v2/workflows.md).",
        "steps": "<details>\n<summary>The " + str(len(wf["nodes"])) + " steps, from the workflow file</summary>\n\n" + n8n_steps(wf) + "\n\n</details>",
        "results": results_block(read),
        "costs": costs_block(read),
    }


BLOCK = re.compile(r"(<!-- generated:(\w+) start[^>]*-->)\n(.*?)\n?(<!-- generated:\2 end -->)", re.S)


def fill_readme(text: str, blocks: dict[str, str]) -> tuple[str, list[str]]:
    seen = []

    def sub(m):
        name = m.group(2)
        seen.append(name)
        return f"{m.group(1)}\n{blocks[name]}\n{m.group(4)}" if name in blocks else m.group(0)

    out = BLOCK.sub(sub, text)
    missing = [n for n in blocks if n not in seen]
    return out, missing


def render_all(read: Reader) -> tuple[dict[str, str], list[str]]:
    readme = read(README)
    if readme is None:
        return {}, [f"{README} is missing"]
    filled, missing = fill_readme(readme, readme_blocks(read))
    return {README: filled, WORKFLOWS_MD: workflows_page(read)}, [f"{README}: no generated:{n} block" for n in missing]


def check_all(read: Reader) -> list[str]:
    try:
        outputs, problems = render_all(read)
    except (KeyError, TypeError, ValueError, StopIteration, AttributeError) as e:
        return [f"could not build: {type(e).__name__}: {e}"]
    return problems + [f"{rel} is not what scripts/build_docs.py makes from the files: run it, do not edit by hand"
                       for rel, text in outputs.items() if read(rel) != text]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a file is out of date; write nothing")
    ap.add_argument("--ref", help="with --check: check a commit (for example HEAD) instead of the working tree")
    args = ap.parse_args(argv)
    read = git_reader(args.ref) if args.ref else tree_reader()
    if args.check:
        findings = check_all(read)
        for f in findings:
            print(f"FAIL {f}")
        if not findings:
            print(f"PASS {README}'s generated parts and {WORKFLOWS_MD} match the files")
        return 1 if findings else 0
    try:
        outputs, problems = render_all(read)
    except (KeyError, TypeError, ValueError, StopIteration, AttributeError) as e:
        print(f"CANNOT BUILD {type(e).__name__}: {e}")
        return 2
    if problems:
        for p in problems:
            print(f"CANNOT BUILD {p}")
        return 2
    for rel, text in outputs.items():
        (REPO / rel).write_text(text, encoding="utf-8")
        print(f"Wrote {rel}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
