#!/usr/bin/env python3
"""Build the chapter 5 quote desk workflow: n8n/workflow-v2-quote-desk.json.

The design is the one the eval kept (skins/quote-desk/eval/results.json): one_prompt, one Claude
call per quote. The fixed chain and the agent team stay in engine/quotes.js and
scripts/quote_desk.py as the comparison; they are not in the workflow.

Made by this script, never edited by hand, like the routing workflows:
  - every Code node that needs the engine gets engine/routing.js (its shared helpers) and then
    engine/quotes.js pasted in whole, so n8n runs exactly the code pytest tests;
  - credentials are named but carry no ID; n8n matches them by name and type on import;
  - the org's My Domain host is private: the file holds a placeholder, and --local writes
    n8n/workflow-v2-quote-desk.local.json (ignored by git) with the host from .env.

The flow: a person presses Read the queue; the desk reads every quote in Needs Review from
Salesforce (its own read-mostly login); code checks the rules; Claude triages each quote; the
triage, calls and costs go to the run log; the approver gets a message with every exception and
a link to the review page; the person approves or rejects each quote with a reason; Salesforce
is updated with the status, reason and a stamp; each owner is told, with a draft customer reply;
the decisions go to the run log. Nothing is sent to a customer: every message goes to the build
account's own inbox, read from Google at run time.

  python scripts/build_n8n_quote_desk.py           # write the file
  python scripts/build_n8n_quote_desk.py --check   # exit 1 if the file is out of date
  python scripts/build_n8n_quote_desk.py --local   # also write the filled-in copy for import

Exit codes: 0 done (or up to date), 1 out of date, 2 could not build.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_n8n_routing as routing  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
QUOTES_JS = REPO / "engine" / "quotes.js"
OUTPUT = REPO / "n8n" / "workflow-v2-quote-desk.json"
LOCAL = REPO / "n8n" / "workflow-v2-quote-desk.local.json"
SETUP = REPO / "salesforce" / "quote-desk-setup.json"
TARGET = {
    "output": OUTPUT,
    "local": LOCAL,
    "name": "GTM v2 chapter 5: quote exceptions desk",
    "form_path": "gtm-v2-quote-desk",
    "trigger": "Start Quote Desk",
}
DESIGN = "one_prompt"
MODEL = routing.MODEL
PLAYBOOK_PATH = "/home/node/gtm-skins/quote-desk/quote-desk-playbook/SKILL.md"
IMPORT_START = "// ---------------------------------------------------------------- imports (not pasted into n8n"
IMPORT_END = "// ---------------------------------------------------------------- end of imports"
CREDENTIALS = {
    "claude": routing.CREDENTIALS["claude"],
    "postgres": routing.CREDENTIALS["postgres"],
    "desk": {"oAuth2Api": {"id": None, "name": "Salesforce quote desk (client credentials)"}},
    "google": {"googleOAuth2Api": {"id": None, "name": "Google least reach gtm-pipeline"}},
}
GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"
NS = uuid.UUID("3c7d9e2a-5b41-4f68-8a0d-6e2f1b9c4d73")  # fixed, so the build is the same every time

ENTRIES = {
    "Build Requests": """
// ===== n8n node: Build Requests (run once for all items) =====
// One request per quote in Needs Review. The rules are checked in code first; the playbook is read from disk on every run.
const MODEL = '__MODEL__';
const DESIGN = '__DESIGN__';
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const records = $('Read Quotes').first().json.records || [];
const today = new Date().toISOString().slice(0, 10);
const runId = `n8n-${$execution.id}`;
if (!records.length) return [{ json: { empty: true, run_id: runId } }];
return records.map((rec, i) => {
  const quote = quoteFromSalesforce(rec);
  const facts = checkQuoteRules(pb, quote, today);
  return {
    json: {
      empty: false,
      run_id: runId,
      decision_id: deskDecisionId(runId, i + 1),
      design: DESIGN,
      quote,
      facts,
      request: buildDeskRequest(pb, 'triage', quote, facts, MODEL),
    },
  };
});
""",
    "Stamp Start": """
// ===== n8n node: Stamp Start (run once for each item) =====
return { json: Object.assign({}, $json, { started_ms: Date.now(), called_at: new Date().toISOString() }) };
""",
    "Check Triage": """
// ===== n8n node: Check Triage (run once for each item) =====
// The guard rails: the schema, the code rules the AI must repeat, fix-before-approve, the draft check, the screen.
let start;
try { start = $('Stamp Start').item.json; } catch (e) { start = $('Stamp Start').first().json; }
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const ctx = { decision_id: start.decision_id, run_id: start.run_id, design: start.design, model: start.request.model, source: 'n8n' };
const reply = readDeskReply(pb, 'triage', $json);
const call = deskCallRecord(ctx, 'triage_agent', 1, reply, Date.now() - start.started_ms, start.called_at);
const joined = designFinal(start.design, { triage: reply });
const proposal = checkTriage(pb, start.quote, start.facts, joined.final, joined.failure,
  Object.assign({}, ctx, { calls: [call], handoffs: [], now: new Date().toISOString() }));
return { json: { proposal, call } };
""",
    "Build Queue": """
// ===== n8n node: Build Queue (run once for all items) =====
// B7: the queue is ordered by the date at risk, then deal size. The review page and the log come from it.
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const items = $input.all().map((i) => i.json);
const queue = deskQueue(items.map((x) => x.proposal));
const calls = items.map((x) => x.call);
const runId = $('Build Requests').first().json.run_id;
const model = queue.length ? queue[0].model : '';
return [{
  json: {
    run_id: runId,
    design: '__DESIGN__',
    queue,
    flagged: queue.filter((p) => p.needs_review).length,
    form_fields: buildDeskReviewForm(pb, queue, { run_id: runId, design: '__DESIGN__', model }),
    log: { proposals: queue, calls, handoffs: [] },
  },
}];
""",
    "Build Approver Message": """
// ===== n8n node: Build Approver Message (run once for all items) =====
// B4: the approver gets every exception, the rule broken, the evidence and the proposal, with a link to the review page.
// The address is the connected Google account's own, with a tag: no quote field can change it.
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const q = $('Build Queue').first().json;
const inbox = $('Get Inbox').first().json.email;
const to = plusAddress(inbox, 'gtm-approver');
const msg = buildApproverMessage(pb, q.queue, { run_id: q.run_id, link: $execution.resumeFormUrl });
return [{ json: { to, subject: msg.subject, raw: buildRawEmail(inbox, to, msg.subject, msg.text) } }];
""",
    "Apply Decisions": """
// ===== n8n node: Apply Decisions (run once for all items) =====
// B5: approve or reject every quote, with the reason and a stamp. A quote that breaks a fix rule cannot be approved.
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const q = $('Build Queue').first().json;
const out = applyDeskDecisions(pb, q.queue, $input.first().json, { decided_at: new Date().toISOString() });
return [{ json: Object.assign({ run_id: q.run_id }, out) }];
""",
    "Build Owner Messages": """
// ===== n8n node: Build Owner Messages (run once for all items) =====
// B5 and B6: each owner is told the decision and the reason, with a draft customer reply to edit and send
// themselves. Only for quotes Salesforce saved. Every message goes to the build account's own inbox.
const pb = parseDeskPlaybook($('Playbook Text').first().json.data);
const q = $('Build Queue').first().json;
const applied = $('Apply Decisions').first().json;
const inbox = $('Get Inbox').first().json.email;
const saved = deskDecisionLogRows(applied.decisions, $input.first().json, {})
  .filter((r) => r.crm_write_status === 'written').map((r) => r.decision_id);
const messages = buildOwnerMessages(pb, q.queue, applied.decisions.filter((d) => saved.includes(d.decision_id)), inbox);
if (!messages.length) return [{ json: { skip: true } }];
return messages.map((m) => ({ json: { skip: false, decision_id: m.decision_id, to: m.to, subject: m.subject, raw: m.raw } }));
""",
    "Build Decision Log": """
// ===== n8n node: Build Decision Log (run once for all items) =====
const applied = $('Apply Decisions').first().json;
const sf = $('Salesforce Update').first().json;
const built = $('Build Owner Messages').all();
let sent = [];
try { sent = $('Send Owner Message').all(); } catch (e) { sent = []; }
const sends = {};
sent.forEach((s, i) => { const id = built[i] && built[i].json.decision_id; if (id) sends[id] = s.json; });
const rows = deskDecisionLogRows(applied.decisions, sf, sends);
return [{ json: { run_id: applied.run_id, rows, summary: summariseDesk(rows) } }];
""",
}

DONE_MESSAGE = """// ===== n8n node: Done Message (run once for all items) =====
// The cost comes back from the run log, which works it out from the price table.
const s = $input.first().json || {};
const d = $('Build Decision Log').first().json;
const m = d.summary;
let approver = 'not checked';
try {
  const a = $('Send Approver Email').first().json;
  approver = a && a.statusCode && a.statusCode < 300 ? 'sent' : 'NOT sent (the review page still works from this browser)';
} catch (e) { approver = 'not sent'; }
const cost = s.total_cost_usd === undefined || s.total_cost_usd === null
  ? 'not found in the run log'
  : `US$${Number(s.total_cost_usd).toFixed(6)} for ${s.quotes} quotes, US$${Number(s.cost_per_quote_usd).toFixed(6)} each`;
const message = [
  `Decided ${m.decisions} quotes: approved ${m.approved}, rejected and sent back ${m.rejected}.`,
  `Salesforce updated: ${m.written}${m.failed ? `; failed ${m.failed}, the run log has the error` : ''}.`,
  `Owners told: ${m.owners_told}. Approver message: ${approver}.`,
  m.against_proposal ? `The approver went against the AI on ${m.against_proposal}.` : 'The approver agreed with every AI proposal.',
  `AI cost: ${cost}. Nothing was sent to a customer.`,
  `Run ${d.run_id}. Every quote carries a stamp; look it up in gtm_v2.desk_record.`,
].join(' ');
return [{ json: { title: m.failed ? 'Quote desk finished with failures' : 'Quote desk run complete', message } }];
"""


def node_id(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def desk_source() -> str:
    """routing.js before its exports (the shared helpers), then quotes.js without its imports and exports."""
    src = QUOTES_JS.read_text(encoding="utf-8")
    if src.count(IMPORT_START) != 1 or src.count(IMPORT_END) != 1 or src.count(routing.EXPORT_MARKER) != 1:
        raise ValueError("engine/quotes.js must have one imports block and one exports marker")
    head, rest = src.split(IMPORT_START)
    rest = rest.split(IMPORT_END, 1)[1]
    body = rest.split(routing.EXPORT_MARKER)[0]
    return routing.engine_source() + "\n// ======== engine/quotes.js ========\n" + head.rstrip() + "\n" + body.strip() + "\n"


def desk_soql() -> str:
    """The one query the desk runs, from the engine, where a test checks it reads no contact field."""
    out = subprocess.run(["node", "-e", "process.stdout.write(require(process.argv[1]).DESK_SOQL)", str(QUOTES_JS)],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0 or not out.stdout.startswith("SELECT "):
        raise ValueError(f"could not read DESK_SOQL from engine/quotes.js: {out.stderr.strip()[:200]}")
    return out.stdout


def fill(js: str) -> str:
    return js.replace("__MODEL__", MODEL).replace("__DESIGN__", DESIGN)


def code(name: str, position: list[int], js: str, each: bool = False, engine: bool = True) -> dict:
    n = routing.code_node(name, position, (desk_source() if engine else "") + fill(js), each=each)
    n["id"] = node_id(name)
    return n


def http(name: str, position: list[int], method: str, url: str, cred: str, body: str | None = None,
         full: bool = True, never_error: bool = True, query: dict | None = None, once: bool = False,
         on_error: str | None = "continueRegularOutput", retry: bool = False, headers: list | None = None) -> dict:
    cred_type = next(iter(CREDENTIALS[cred]))
    params: dict = {"method": method, "url": url}
    if cred_type == "googleOAuth2Api":
        params.update({"authentication": "predefinedCredentialType", "nodeCredentialType": "googleOAuth2Api"})
    else:
        params.update({"authentication": "genericCredentialType", "genericAuthType": cred_type})
    if query:
        params["sendQuery"] = True
        params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
    if headers:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": headers}
    if body is not None:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    options: dict = {"timeout": 120000 if cred == "claude" else 60000}
    if full:
        options["response"] = {"response": {"fullResponse": True, **({"neverError": True} if never_error else {})}}
    params["options"] = options
    n = {"id": node_id(name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": position,
         "credentials": copy.deepcopy(CREDENTIALS[cred]), "parameters": params}
    if once:
        n["executeOnce"] = True
    if on_error:
        n["onError"] = on_error
    if retry:
        n.update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000})
    return n


def postgres(name: str, position: list[int], query: str, replacement: str) -> dict:
    n = routing.postgres_node(name, position, query, replacement)
    n["id"] = node_id(name)
    return n


def form_page(name: str, position: list[int], params: dict) -> dict:
    return {"id": node_id(name), "name": name, "type": "n8n-nodes-base.form", "typeVersion": 2.5, "position": position,
            "webhookId": node_id(f"{name} webhook"), "parameters": params}


def if_node(name: str, position: list[int], left: str, op: dict, right) -> dict:
    return {"id": node_id(name), "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2, "position": position,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": ""}, "combinator": "and", "conditions": [{
                "id": node_id(f"{name} condition"), "leftValue": left, "rightValue": right, "operator": op}]}, "options": {}}}


def build(salesforce_host: str = routing.SALESFORCE_HOST_PLACEHOLDER) -> dict:
    setup = json.loads(SETUP.read_text(encoding="utf-8"))
    api = f"https://{salesforce_host}/services/data/{setup['api_version']}"
    soql = desk_soql()
    nodes = [
        {
            "id": node_id(TARGET["trigger"]), "name": TARGET["trigger"], "type": "n8n-nodes-base.formTrigger", "typeVersion": 2.5,
            "position": [0, 300],
            "parameters": {
                "formTitle": "GTM pipeline v2: quote exceptions desk",
                "formDescription": "Reads every quote in Needs Review from Salesforce. Code checks the deal desk rules, the AI triages each quote, and you approve or reject every one, with a reason, on the next page. Nothing in Salesforce changes before you do, and nothing is sent to a customer.",
                "formFields": {"values": [{"fieldLabel": "Queue", "fieldName": "queue", "fieldType": "dropdown", "requiredField": True,
                                           "fieldOptions": {"values": [{"option": "Quotes in Needs Review"}]}}]},
                "options": {"path": TARGET["form_path"], "buttonLabel": "Read the queue"},
            },
        },
        {
            "id": node_id("Read Playbook"), "name": "Read Playbook", "type": "n8n-nodes-base.readWriteFile", "typeVersion": 1.1,
            "position": [220, 300], "executeOnce": True,
            "parameters": {"operation": "read", "fileSelector": PLAYBOOK_PATH, "options": {"dataPropertyName": "data"}},
        },
        {
            "id": node_id("Playbook Text"), "name": "Playbook Text", "type": "n8n-nodes-base.extractFromFile", "typeVersion": 1.1,
            "position": [440, 300], "executeOnce": True,
            "parameters": {"operation": "text", "binaryPropertyName": "data", "destinationKey": "data", "options": {}},
        },
        http("Read Quotes", [660, 300], "GET", f"{api}/query", "desk", full=False, never_error=False, query={"q": soql}, once=True, on_error=None),
        code("Build Requests", [880, 300], ENTRIES["Build Requests"]),
        if_node("Any Quotes?", [1100, 300], "={{ $json.empty }}", {"type": "boolean", "operation": "false", "singleValue": True}, ""),
        form_page("Nothing to Do", [1320, 520], {"operation": "completion", "respondWith": "text", "completionTitle": "No quotes to decide",
                                                 "completionMessage": "There are no quotes in Needs Review. Nothing was changed.", "options": {}}),
        {
            "id": node_id("Loop Over Quotes"), "name": "Loop Over Quotes", "type": "n8n-nodes-base.splitInBatches", "typeVersion": 3,
            "position": [1320, 200], "parameters": {"batchSize": 1, "options": {}},
        },
        code("Stamp Start", [1540, 60], ENTRIES["Stamp Start"].lstrip(), each=True, engine=False),
        http("Claude Triage Step", [1760, 60], "POST", "https://api.anthropic.com/v1/messages", "claude",
             body="={{ JSON.stringify($json.request) }}", never_error=False, retry=True,
             headers=[{"name": "anthropic-version", "value": routing.ANTHROPIC_VERSION}]),
        code("Check Triage", [1980, 60], ENTRIES["Check Triage"], each=True),
        code("Build Queue", [1540, 340], ENTRIES["Build Queue"]),
        postgres("Log Triage", [1760, 340],
                 "select gtm_v2.log_desk_triage(($1::jsonb)->'proposals', ($1::jsonb)->'calls', ($1::jsonb)->'handoffs') as logged;",
                 "={{ JSON.stringify($json.log) }}"),
        http("Get Inbox", [1980, 340], "GET", USERINFO, "google", full=False, never_error=False, once=True, on_error=None),
        code("Build Approver Message", [2200, 340], ENTRIES["Build Approver Message"]),
        http("Send Approver Email", [2420, 340], "POST", GMAIL_SEND, "google", body="={{ JSON.stringify({ raw: $json.raw }) }}", once=True),
        form_page("Review Page", [2640, 340], {
            "operation": "page", "defineForm": "json", "jsonOutput": "={{ $('Build Queue').first().json.form_fields }}",
            "options": {"formTitle": "Decide the quotes in the queue",
                        "formDescription": "Quotes marked Check were flagged by the guard rails. Approve or reject every quote, with a reason. Rejected quotes go back to their owner.",
                        "buttonLabel": "Submit decisions"},
        }),
        code("Apply Decisions", [2860, 340], ENTRIES["Apply Decisions"]),
        http("Salesforce Update", [3080, 340], "PATCH", f"{api}/composite/sobjects", "desk", body="={{ JSON.stringify($json.update.body) }}"),
        code("Build Owner Messages", [3300, 340], ENTRIES["Build Owner Messages"]),
        if_node("Anything to Tell?", [3520, 340], "={{ $json.skip }}", {"type": "boolean", "operation": "false", "singleValue": True}, ""),
        http("Send Owner Message", [3740, 240], "POST", GMAIL_SEND, "google", body="={{ JSON.stringify({ raw: $json.raw }) }}"),
        code("Build Decision Log", [3960, 340], ENTRIES["Build Decision Log"]),
        postgres("Log Decisions", [4180, 340], "select gtm_v2.log_desk_decisions($1::jsonb) as logged;", "={{ JSON.stringify($json.rows) }}"),
        postgres("Read Run Summary", [4400, 340],
                 "select run_id, quotes, flagged, approved, rejected, written, failed, owners_told, against_proposal, calls, "
                 "input_tokens, output_tokens, total_cost_usd, cost_per_quote_usd, avg_latency_ms from gtm_v2.desk_run_summary where run_id = $1;",
                 "={{ $('Build Decision Log').first().json.run_id }}"),
        code("Done Message", [4620, 340], DONE_MESSAGE, engine=False),
        form_page("Done", [4840, 340], {"operation": "completion", "respondWith": "text", "completionTitle": "={{ $json.title }}",
                                        "completionMessage": "={{ $json.message }}", "options": {}}),
    ]

    def link(*targets):
        return [[{"node": t, "type": "main", "index": 0} for t in targets]]

    connections = {
        TARGET["trigger"]: {"main": link("Read Playbook")},
        "Read Playbook": {"main": link("Playbook Text")},
        "Playbook Text": {"main": link("Read Quotes")},
        "Read Quotes": {"main": link("Build Requests")},
        "Build Requests": {"main": link("Any Quotes?")},
        "Any Quotes?": {"main": link("Loop Over Quotes") + link("Nothing to Do")},  # true: there are quotes
        "Loop Over Quotes": {"main": link("Build Queue") + link("Stamp Start")},  # output 0 is done, 1 is loop
        "Stamp Start": {"main": link("Claude Triage Step")},
        "Claude Triage Step": {"main": link("Check Triage")},
        "Check Triage": {"main": link("Loop Over Quotes")},
        "Build Queue": {"main": link("Log Triage")},
        "Log Triage": {"main": link("Get Inbox")},
        "Get Inbox": {"main": link("Build Approver Message")},
        "Build Approver Message": {"main": link("Send Approver Email")},
        "Send Approver Email": {"main": link("Review Page")},
        "Review Page": {"main": link("Apply Decisions")},
        "Apply Decisions": {"main": link("Salesforce Update")},
        "Salesforce Update": {"main": link("Build Owner Messages")},
        "Build Owner Messages": {"main": link("Anything to Tell?")},
        "Anything to Tell?": {"main": link("Send Owner Message") + link("Build Decision Log")},
        "Send Owner Message": {"main": link("Build Decision Log")},
        "Build Decision Log": {"main": link("Log Decisions")},
        "Log Decisions": {"main": link("Read Run Summary")},
        "Read Run Summary": {"main": link("Done Message")},
        "Done Message": {"main": link("Done")},
    }
    return {"name": TARGET["name"], "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the workflow file is out of date")
    ap.add_argument("--local", action="store_true", help="also write the copy with the org's host from .env (ignored by git)")
    args = ap.parse_args(argv)
    try:
        text = routing.render(build())
        local = routing.render(build(routing.salesforce_host_from_env())) if args.local else None
    except (OSError, ValueError, KeyError) as e:
        print(f"CANNOT BUILD {e}")
        return 2
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"OUT OF DATE {OUTPUT.relative_to(REPO)}: run python scripts/build_n8n_quote_desk.py")
            return 1
        print("The quote desk workflow file is up to date.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)}: {len(json.loads(text)['nodes'])} nodes, design {DESIGN}.")
    if local is not None:
        LOCAL.write_text(local, encoding="utf-8")
        print(f"Wrote {LOCAL.relative_to(REPO)} with the org's host (ignored by git; import this one).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
