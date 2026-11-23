#!/usr/bin/env python3
"""Build the routing workflows from version 1 and the routing engine: one per CRM target.

  n8n/workflow-v2.json             chapter 2: writes to HubSpot
  n8n/workflow-v2-salesforce.json  chapter 4: the same workflow, writing to Salesforce

The two files differ only in what names the target (the workflow name, the form path and
wording, the target the Code nodes pass to the engine) and in the one write node. A test
checks that. Both are made by this script, never edited by hand:
  - the upload, the CSV step, the data rules and the quarantine come from version 1
    (n8n/workflow.json), unchanged, so the rules node is byte-for-byte the tested one;
  - every Code node that needs the engine gets engine/routing.js pasted in whole, so n8n
    runs exactly the code pytest tests;
  - credentials are named but carry no ID. n8n matches them by name and type on import,
    so the file holds no instance ID and imports as it is;
  - the Salesforce file holds a placeholder for the org's My Domain host, which is private.
    --local writes n8n/workflow-v2-salesforce.local.json (ignored by git) with the host from
    .env (SALESFORCE_DOMAIN), for import into n8n.

  python scripts/build_n8n_routing.py           # write both files
  python scripts/build_n8n_routing.py --check   # exit 1 if either file is out of date
  python scripts/build_n8n_routing.py --local   # also write the filled-in Salesforce copy

Exit codes: 0 done (or up to date), 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V1 = REPO / "n8n" / "workflow.json"
ENGINE = REPO / "engine" / "routing.js"
OUTPUT = REPO / "n8n" / "workflow-v2.json"
ENV = REPO / ".env"

NAME = "GTM v2 chapter 2: route leads with approval"
FORM_PATH = "gtm-v2-route-leads"
SALESFORCE_API_VERSION = "v64.0"
SALESFORCE_HOST_PLACEHOLDER = "YOUR-MY-DOMAIN.my.salesforce.com"
SALESFORCE_HOST_RE = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.my\.salesforce\.com$"
TARGETS = {
    "hubspot": {
        "output": REPO / "n8n" / "workflow-v2.json",
        "name": NAME,
        "form_path": FORM_PATH,
        "label": "HubSpot",
        "write_node": "HubSpot Batch Upsert",
        "webhook_prefix": "",
    },
    "salesforce": {
        "output": REPO / "n8n" / "workflow-v2-salesforce.json",
        "local": REPO / "n8n" / "workflow-v2-salesforce.local.json",
        "name": "GTM v2 chapter 4: route leads with approval (Salesforce)",
        "form_path": "gtm-v2-route-leads-salesforce",
        "label": "Salesforce",
        "write_node": "Salesforce Upsert",
        "webhook_prefix": "salesforce ",
    },
}
MODEL = "claude-haiku-5-5"
ANTHROPIC_VERSION = "2026-10-21"
# The skins folder is mounted read-only into the n8n container (scripts/n8n_docker.sh).
PLAYBOOK_PATH = "/home/node/gtm-skins/lead-routing/lead-routing-playbook/SKILL.md"
CREDENTIALS = {
    "claude": {"httpHeaderAuth": {"id": None, "name": "Claude key gtm-pipeline-v2"}},
    "hubspot": {"httpHeaderAuth": {"id": None, "name": "HubSpot Service Key"}},
    # n8n's general OAuth2 login with the client-credentials grant, not n8n's Salesforce login,
    # which asks for the "full" scope (fixed in n8n's code). See docs/v2/control-sheet.md.
    "salesforce": {"oAuth2Api": {"id": None, "name": "Salesforce gtm-pipeline (client credentials)"}},
    "postgres": {"postgres": {"id": None, "name": "GTM v2 run log (Postgres)"}},
}
EXPORT_MARKER = "// ---------------------------------------------------------------- exports (not pasted into n8n)"
NS = uuid.UUID("8a5c2f1e-6d3b-4e0a-9c7f-2b1d4e6f8a90")  # fixed, so the build is the same every time

ENTRIES = {
    "Build Requests": """
// ===== n8n node: Build Requests (run once for all items) =====
// One request per row that passed the data rules. The playbook is read from disk on every run.
const MODEL = '__MODEL__';
const pb = parsePlaybook($('Playbook Text').first().json.data);
const csvRows = $('Extract CSV').all().map((i) => i.json);
const checked = $('DQ Checks').all().map((i) => i.json);
const passed = checked.filter((r) => r._dq_pass === true);
const runId = `n8n-${$execution.id}`;
return passed.map((dq) => {
  const lead = leadFromRow(csvRows[dq._row_number - 1] || {}, dq);
  return {
    json: {
      run_id: runId,
      decision_id: decisionId(runId, lead.row_number),
      lead,
      request: buildRequest(pb, lead, MODEL),
      quarantined: checked.length - passed.length,
    },
  };
});
""",
    "Stamp Start": """
// ===== n8n node: Stamp Start (run once for each item) =====
return { json: Object.assign({}, $json, { started_ms: Date.now() }) };
""",
    "Check Proposal": """
// ===== n8n node: Check Proposal (run once for each item) =====
// The guard rails: schema, confidence bar, size and region rules, the code screen.
let start;
try { start = $('Stamp Start').item.json; } catch (e) { start = $('Stamp Start').first().json; }
const pb = parsePlaybook($('Playbook Text').first().json.data);
return {
  json: checkProposal(pb, start.lead, $json, {
    decision_id: start.decision_id,
    run_id: start.run_id,
    source: 'n8n',
    model: start.request.model,
    latency_ms: Date.now() - start.started_ms,
    now: new Date().toISOString(),
  }),
};
""",
    "Build Review": """
// ===== n8n node: Build Review (run once for all items) =====
const pb = parsePlaybook($('Playbook Text').first().json.data);
const proposals = $input.all().map((i) => i.json);
const leads = {};
let runId = '';
let quarantined = 0;
for (const i of $('Build Requests').all()) {
  leads[i.json.decision_id] = i.json.lead;
  runId = i.json.run_id;
  quarantined = i.json.quarantined;
}
const model = proposals.length ? proposals[0].model : '';
return [{
  json: {
    run_id: runId,
    proposals,
    flagged: proposals.filter((p) => p.needs_review).length,
    form_fields: buildReviewForm(pb, proposals, { run_id: runId, model, quarantined, leads, target: '__TARGET__' }),
  },
}];
""",
    "Apply Decisions": """
// ===== n8n node: Apply Decisions (run once for all items) =====
// Turns the person's choices into decisions, stamps, and __LABEL__ records for approved or changed rows only.
const pb = parsePlaybook($('Playbook Text').first().json.data);
const review = $('Build Review').first().json;
const leads = {};
for (const i of $('Build Requests').all()) leads[i.json.decision_id] = i.json.lead;
const out = applyDecisions(pb, review.proposals, leads, $input.first().json, { decided_at: new Date().toISOString(), target: '__TARGET__' });
return [{ json: Object.assign({ run_id: review.run_id }, out) }];
""",
    "Build Decision Log": """
// ===== n8n node: Build Decision Log (run once for all items) =====
const applied = $('Apply Decisions').first().json;
const wrote = applied.write.count > 0;
const rows = decisionLogRows(applied.decisions, wrote ? $input.first().json : null);
return [{ json: { run_id: applied.run_id, rows, summary: summariseDecisions(rows) } }];
""",
}

DONE_MESSAGE = """// ===== n8n node: Done Message (run once for all items) =====
// The cost comes back from the run log, which works it out from the price table.
const s = $input.first().json || {};
const d = $('Build Decision Log').first().json;
const m = d.summary;
const cost = s.total_cost_usd === undefined || s.total_cost_usd === null
  ? 'not found in the run log'
  : `US$${Number(s.total_cost_usd).toFixed(6)} for ${s.proposals} AI proposals, US$${Number(s.cost_per_decision_usd).toFixed(6)} each`;
const message = [
  `Written to __LABEL__: ${m.written} (approved ${m.approved}, changed ${m.changed}).`,
  `Rejected, not written: ${m.rejected}.`,
  m.failed ? `Failed to write: ${m.failed}; the run log has the error.` : 'No write failed.',
  `AI cost: ${cost}.`,
  `Run ${d.run_id}. Every __LABEL__ record written carries a stamp; look it up in gtm_v2.decision_record.`,
].join(' ');
return [{ json: { title: m.failed ? 'Routing run finished with failures' : 'Routing run complete', message } }];
"""


def node_id(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def engine_source() -> str:
    src = ENGINE.read_text(encoding="utf-8")
    if src.count(EXPORT_MARKER) != 1:
        raise ValueError("engine/routing.js must have exactly one exports marker")
    return src.split(EXPORT_MARKER)[0].rstrip() + "\n"


def code_node(name: str, position: list[int], js: str, each: bool = False) -> dict:
    params = {"jsCode": js}
    if each:
        params["mode"] = "runOnceForEachItem"
    return {"id": node_id(name), "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": position, "parameters": params}


def postgres_node(name: str, position: list[int], query: str, replacement: str) -> dict:
    return {
        "id": node_id(name), "name": name, "type": "n8n-nodes-base.postgres", "typeVersion": 2.6,
        "position": position, "executeOnce": True, "credentials": copy.deepcopy(CREDENTIALS["postgres"]),
        "parameters": {"operation": "executeQuery", "query": query, "options": {"queryReplacement": replacement}},
    }


def fill(js: str, target: str) -> str:
    return js.replace("__TARGET__", target).replace("__LABEL__", TARGETS[target]["label"])


def write_node(target: str, position: list[int], salesforce_host: str = SALESFORCE_HOST_PLACEHOLDER) -> dict:
    """The one node that differs between the targets: the CRM's batch upsert, after the review page."""
    t = TARGETS[target]
    common = {"id": node_id(t["write_node"]), "name": t["write_node"], "type": "n8n-nodes-base.httpRequest",
              "typeVersion": 4.2, "position": position, "credentials": copy.deepcopy(CREDENTIALS[target]),
              "onError": "continueRegularOutput"}
    options = {"response": {"response": {"fullResponse": True, "neverError": True}}, "timeout": 60000}
    body = "={{ JSON.stringify($json.write.body) }}"
    if target == "salesforce":
        # sObject Collections upsert on the external ID: up to 200 Accounts, each saved or refused
        # on its own (allOrNone false), answered in the order sent. n8n fetches and renews the
        # client-credentials token itself.
        url = f"https://{salesforce_host}/services/data/{SALESFORCE_API_VERSION}/composite/sobjects/Account/Clay_Domain_Key__c"
        params = {"method": "PATCH", "url": url, "authentication": "genericCredentialType", "genericAuthType": "oAuth2Api",
                  "sendBody": True, "specifyBody": "json", "jsonBody": body, "options": options}
    else:
        params = {"method": "POST", "url": "https://api.hubapi.com/crm/v3/objects/companies/batch/upsert",
                  "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                  "sendBody": True, "specifyBody": "json", "jsonBody": body, "options": options}
    return dict(common, parameters=params)


def build(target: str = "hubspot", salesforce_host: str = SALESFORCE_HOST_PLACEHOLDER) -> dict:
    t = TARGETS[target]
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    v1_nodes = {n["name"]: n for n in v1["nodes"]}
    engine = engine_source()

    def from_v1(name: str, position: list[int]) -> dict:
        n = copy.deepcopy(v1_nodes[name])
        n["position"] = position
        return n

    upload = from_v1("Upload CSV", [0, 300])
    upload["typeVersion"] = 2.5
    # No webhookId on purpose. On import, n8n's editor (2.10.3) gives a trigger that has one a
    # new ID and overwrites its Form Path with it; a trigger without one gets an ID and keeps
    # its path. Found on the first import, 23/11/2026.
    upload.pop("webhookId", None)
    upload["parameters"] = {
        "formTitle": "GTM pipeline v2: route leads",
        "formDescription": "Upload a company CSV with an enquiry column. The data rules run first, then the AI proposes a route for each clean row. You approve, change or reject every proposal on the next page. Nothing is written to " + t["label"] + " before you do.",
        "formFields": {"values": [{"fieldLabel": "CSV File", "fieldName": "CSV_File", "fieldType": "file",
                                   "requiredField": True, "acceptFileTypes": ".csv"}]},
        "options": {"path": t["form_path"], "buttonLabel": "Run the rules and the AI step"},
    }
    nodes = [
        upload,
        from_v1("Extract CSV", [220, 300]),
        from_v1("DQ Checks", [440, 300]),
        from_v1("Pass or Fail", [660, 300]),
        from_v1("Format Quarantine", [880, 520]),
        from_v1("Quarantine Table", [1100, 520]),
        {
            "id": node_id("Read Playbook"), "name": "Read Playbook", "type": "n8n-nodes-base.readWriteFile",
            "typeVersion": 1.1, "position": [880, 200], "executeOnce": True,
            "parameters": {"operation": "read", "fileSelector": PLAYBOOK_PATH, "options": {"dataPropertyName": "data"}},
        },
        {
            "id": node_id("Playbook Text"), "name": "Playbook Text", "type": "n8n-nodes-base.extractFromFile",
            "typeVersion": 1.1, "position": [1100, 200], "executeOnce": True,
            "parameters": {"operation": "text", "binaryPropertyName": "data", "destinationKey": "data", "options": {}},
        },
        code_node("Build Requests", [1320, 200], engine + ENTRIES["Build Requests"].replace("__MODEL__", MODEL)),
        {
            "id": node_id("Loop Over Leads"), "name": "Loop Over Leads", "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3, "position": [1540, 200], "parameters": {"batchSize": 1, "options": {}},
        },
        code_node("Stamp Start", [1760, 60], ENTRIES["Stamp Start"].lstrip(), each=True),
        {
            "id": node_id("Claude Routing Step"), "name": "Claude Routing Step", "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": [1980, 60], "credentials": copy.deepcopy(CREDENTIALS["claude"]),
            "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000, "onError": "continueRegularOutput",
            "parameters": {
                "method": "POST", "url": "https://api.anthropic.com/v1/messages",
                "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {"parameters": [{"name": "anthropic-version", "value": ANTHROPIC_VERSION}]},
                "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify($json.request) }}",
                "options": {"response": {"response": {"fullResponse": True}}, "timeout": 120000},
            },
        },
        code_node("Check Proposal", [2200, 60], engine + ENTRIES["Check Proposal"], each=True),
        code_node("Build Review", [1760, 340], engine + fill(ENTRIES["Build Review"], target)),
        postgres_node("Log Proposals", [1980, 340], "select gtm_v2.log_proposals($1::jsonb) as logged;",
                      "={{ JSON.stringify($json.proposals) }}"),
        {
            "id": node_id("Review Page"), "name": "Review Page", "type": "n8n-nodes-base.form", "typeVersion": 2.5,
            "position": [2200, 340], "webhookId": node_id(t["webhook_prefix"] + "Review Page webhook"),
            "parameters": {
                "operation": "page", "defineForm": "json",
                "jsonOutput": "={{ $('Build Review').first().json.form_fields }}",
                "options": {"formTitle": "Review the AI's routing proposals",
                            "formDescription": "Rows marked Check were flagged by the guard rails. Approve, change or reject every row. Rejected rows are not written.",
                            "buttonLabel": "Submit decisions"},
            },
        },
        code_node("Apply Decisions", [2420, 340], engine + fill(ENTRIES["Apply Decisions"], target)),
        {
            "id": node_id("Anything to Write?"), "name": "Anything to Write?", "type": "n8n-nodes-base.if",
            "typeVersion": 2, "position": [2640, 340],
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": ""}, "combinator": "and", "conditions": [{
                "id": node_id("Anything to Write? condition"), "leftValue": "={{ $json.write.count }}",
                "rightValue": 0, "operator": {"type": "number", "operation": "gt"}}]}, "options": {}},
        },
        write_node(target, [2860, 240], salesforce_host),
        code_node("Build Decision Log", [3080, 340], engine + ENTRIES["Build Decision Log"]),
        postgres_node("Log Decisions", [3300, 340], "select gtm_v2.log_decisions($1::jsonb) as logged;",
                      "={{ JSON.stringify($json.rows) }}"),
        postgres_node("Read Run Summary", [3520, 340],
                      "select run_id, proposals, flagged, approved, changed, rejected, written, failed, input_tokens, "
                      "output_tokens, total_cost_usd, cost_per_decision_usd, avg_latency_ms from gtm_v2.run_summary where run_id = $1;",
                      "={{ $('Build Decision Log').first().json.run_id }}"),
        code_node("Done Message", [3740, 340], fill(DONE_MESSAGE, target)),
        {
            "id": node_id("Done"), "name": "Done", "type": "n8n-nodes-base.form", "typeVersion": 2.5,
            "position": [3960, 340], "webhookId": node_id(t["webhook_prefix"] + "Done webhook"),
            "parameters": {"operation": "completion", "respondWith": "text",
                           "completionTitle": "={{ $json.title }}", "completionMessage": "={{ $json.message }}", "options": {}},
        },
    ]

    def link(*targets):
        return [[{"node": t, "type": "main", "index": 0} for t in targets]]

    connections = {
        "Upload CSV": {"main": link("Extract CSV")},
        "Extract CSV": {"main": link("DQ Checks")},
        "DQ Checks": {"main": link("Pass or Fail")},
        "Pass or Fail": {"main": link("Read Playbook") + link("Format Quarantine")},
        "Format Quarantine": {"main": link("Quarantine Table")},
        "Read Playbook": {"main": link("Playbook Text")},
        "Playbook Text": {"main": link("Build Requests")},
        "Build Requests": {"main": link("Loop Over Leads")},
        "Loop Over Leads": {"main": link("Build Review") + link("Stamp Start")},  # output 0 is done, 1 is loop
        "Stamp Start": {"main": link("Claude Routing Step")},
        "Claude Routing Step": {"main": link("Check Proposal")},
        "Check Proposal": {"main": link("Loop Over Leads")},
        "Build Review": {"main": link("Log Proposals")},
        "Log Proposals": {"main": link("Review Page")},
        "Review Page": {"main": link("Apply Decisions")},
        "Apply Decisions": {"main": link("Anything to Write?")},
        "Anything to Write?": {"main": link(t["write_node"]) + link("Build Decision Log")},
        t["write_node"]: {"main": link("Build Decision Log")},
        "Build Decision Log": {"main": link("Log Decisions")},
        "Log Decisions": {"main": link("Read Run Summary")},
        "Read Run Summary": {"main": link("Done Message")},
        "Done Message": {"main": link("Done")},
    }
    return {"name": t["name"], "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


def render(wf: dict) -> str:
    return json.dumps(wf, indent=2, ensure_ascii=False) + "\n"


def salesforce_host_from_env() -> str:
    from dotenv import dotenv_values

    host = (dotenv_values(ENV).get("SALESFORCE_DOMAIN") if ENV.exists() else None) or ""
    host = host.strip().removeprefix("https://").rstrip("/").lower()
    if not re.match(SALESFORCE_HOST_RE, host):
        raise ValueError("SALESFORCE_DOMAIN in .env must be the org's My Domain host, ending in .my.salesforce.com")
    return host


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if either workflow file is out of date")
    ap.add_argument("--local", action="store_true", help="also write the Salesforce copy with the org's host from .env (ignored by git)")
    args = ap.parse_args(argv)
    try:
        texts = {target: render(build(target)) for target in TARGETS}
        local = render(build("salesforce", salesforce_host_from_env())) if args.local else None
    except (OSError, ValueError, KeyError) as e:
        print(f"CANNOT BUILD {e}")
        return 2
    if args.check:
        stale = [t["output"].relative_to(REPO) for target, t in TARGETS.items()
                 if (t["output"].read_text(encoding="utf-8") if t["output"].exists() else "") != texts[target]]
        for path in stale:
            print(f"OUT OF DATE {path}: run python scripts/build_n8n_routing.py")
        if stale:
            return 1
        print("Both workflow files are up to date.")
        return 0
    for target, t in TARGETS.items():
        t["output"].write_text(texts[target], encoding="utf-8")
        print(f"Wrote {t['output'].relative_to(REPO)}: {len(json.loads(texts[target])['nodes'])} nodes.")
    if local is not None:
        TARGETS["salesforce"]["local"].write_text(local, encoding="utf-8")
        print(f"Wrote {TARGETS['salesforce']['local'].relative_to(REPO)} with the org's host (ignored by git; import this one).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
