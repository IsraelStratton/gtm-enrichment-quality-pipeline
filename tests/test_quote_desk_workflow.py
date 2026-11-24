"""Chapter 5, the quote desk workflow (n8n/workflow-v2-quote-desk.json): how it is built, what it can
reach, that nothing in it can send to a customer (KB-137 B6), that Salesforce changes only after a
person's decision, and what its Code nodes do when run in order on the demo quotes
(tests/n8n_desk_harness.js) with fake Salesforce, Claude and Gmail replies."""
import base64
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
import build_n8n_quote_desk as build  # noqa: E402
from routing_engine import Engine  # noqa: E402
from test_quote_desk import AS_OF, CASES, PRODUCTS, answer, labelled_triage, sf_record  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

WF_PATH = REPO / "n8n/workflow-v2-quote-desk.json"
WF = json.loads(WF_PATH.read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}
PLAYBOOK = (REPO / "skins/quote-desk/quote-desk-playbook/SKILL.md").read_text(encoding="utf-8")
RESULTS = json.loads((REPO / "skins/quote-desk/eval/results.json").read_text(encoding="utf-8"))
INBOX = "desk.owner@example.com"
DEMO = [c for c in CASES.values() if c["demo"]]
ALLOWED_TYPES = {
    "n8n-nodes-base.formTrigger", "n8n-nodes-base.form", "n8n-nodes-base.readWriteFile", "n8n-nodes-base.extractFromFile",
    "n8n-nodes-base.httpRequest", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.splitInBatches", "n8n-nodes-base.postgres",
}


def successors(name):
    for outputs in WF["connections"].get(name, {}).get("main", []):
        for link in outputs:
            yield link["node"]


def reachable(start, avoid=()):
    seen, todo = set(), [start]
    while todo:
        n = todo.pop()
        for s in successors(n):
            if s not in seen and s not in avoid:
                seen.add(s)
                todo.append(s)
    return seen


def test_the_file_is_up_to_date_and_built_for_the_kept_design():
    assert subprocess.run([sys.executable, "scripts/build_n8n_quote_desk.py", "--check"], cwd=REPO, capture_output=True).returncode == 0
    assert build.DESIGN == RESULTS["kept"] == "one_prompt"
    assert "Claude Policy Checker" not in NODES and "Claude Message Drafter" not in NODES


def test_every_code_node_runs_the_tested_engines_in_full():
    routing_src = build.routing.engine_source()
    for name in ("Build Requests", "Check Triage", "Build Queue", "Build Approver Message", "Apply Decisions", "Build Owner Messages", "Build Decision Log"):
        js = NODES[name]["parameters"]["jsCode"]
        assert js.startswith(routing_src) and "function checkTriage(" in js and "require(" not in js, name


def test_no_credential_id_and_no_org_host_in_the_file():
    text = WF_PATH.read_text(encoding="utf-8")
    assert all(c["id"] is None for n in WF["nodes"] for c in (n.get("credentials") or {}).values())
    hosts = {urlsplit(n["parameters"]["url"]).hostname for n in WF["nodes"] if n["type"].endswith("httpRequest")}
    assert hosts == {build.routing.SALESFORCE_HOST_PLACEHOLDER.lower(), "api.anthropic.com", "www.googleapis.com", "gmail.googleapis.com"}
    assert ".my.salesforce.com" in text and not re.search(r"[a-z0-9-]+\.(develop\.)?my\.salesforce\.com", text.replace(build.routing.SALESFORCE_HOST_PLACEHOLDER, ""))
    assert "webhookId" not in NODES[build.TARGET["trigger"]]


# ---------------------------------------------------------------- B6: nothing can send to a customer


def test_only_known_node_types_are_in_the_workflow():
    """No email, chat, SMS or outbound node of any kind: the only way out is the HTTP calls checked below."""
    assert {n["type"] for n in WF["nodes"]} <= ALLOWED_TYPES


def test_every_http_call_goes_to_one_of_five_known_endpoints():
    calls = {}
    for n in WF["nodes"]:
        if n["type"].endswith("httpRequest"):
            p = n["parameters"]
            calls[n["name"]] = (p["method"], urlsplit(p["url"]).path)
    assert calls == {
        "Read Quotes": ("GET", "/services/data/v64.0/query"),
        "Claude Triage Step": ("POST", "/v1/messages"),
        "Get Inbox": ("GET", "/oauth2/v3/userinfo"),
        "Send Approver Email": ("POST", "/gmail/v1/users/me/messages/send"),
        "Salesforce Update": ("PATCH", "/services/data/v64.0/composite/sobjects"),
        "Send Owner Message": ("POST", "/gmail/v1/users/me/messages/send"),
    }


def test_the_two_mail_steps_send_only_a_message_the_engine_built_for_the_own_inbox():
    for name, builder in (("Send Approver Email", "Build Approver Message"), ("Send Owner Message", "Build Owner Messages")):
        assert NODES[name]["parameters"]["jsonBody"] == "={{ JSON.stringify({ raw: $json.raw }) }}"
        assert NODES[name]["credentials"] == {"googleOAuth2Api": {"id": None, "name": "Google least reach gtm-pipeline"}}
        js = NODES[builder]["parameters"]["jsCode"].split("// ===== n8n node:")[1]
        assert "$('Get Inbox').first().json.email" in js and "buildRawEmail(inbox" in js or "buildOwnerMessages(pb, q.queue" in js
        assert not re.search(r"\b(Email|Phone|Contact)\b", js)


def test_the_claude_step_cannot_call_tools_or_send():
    js = NODES["Build Requests"]["parameters"]["jsCode"].split("// ===== n8n node:")[1]
    assert "buildDeskRequest(pb, 'triage'" in js and "'lead'" not in js


# ---------------------------------------------------------------- the person decides before Salesforce changes


def test_salesforce_changes_only_after_the_review_page():
    before = reachable(build.TARGET["trigger"], avoid={"Review Page"})
    assert "Salesforce Update" not in before and "Send Owner Message" not in before
    assert "Salesforce Update" in reachable("Review Page")
    assert [n for n in WF["nodes"] if n["type"].endswith("httpRequest") and n["parameters"]["method"] != "GET" and "salesforce" in n["parameters"]["url"]] == [NODES["Salesforce Update"]]


def test_the_desk_logs_in_with_its_own_salesforce_login_not_the_routing_one():
    for name in ("Read Quotes", "Salesforce Update"):
        assert NODES[name]["credentials"] == {"oAuth2Api": {"id": None, "name": "Salesforce quote desk (client credentials)"}}
    assert NODES["Read Quotes"]["parameters"]["queryParameters"]["parameters"][0]["value"].startswith("SELECT Id, GTM_Case_Id__c")


# ---------------------------------------------------------------- the Code nodes in order, on the demo quotes


@pytest.fixture(scope="module")
def records():
    eng = Engine(module="quotes")
    quotes = eng.batch([("caseToQuote", [c, PRODUCTS, AS_OF]) for c in DEMO])
    return [sf_record(q, f"0Q0{i:012d}") for i, q in enumerate(quotes)]


def run_harness(records, **over):
    payload = {"workflow": str(WF_PATH), "playbook": PLAYBOOK, "records": records, "execution_id": "9001", "inbox": INBOX,
               "answers": {c["case_id"]: answer(labelled_triage(c["case_id"])) for c in DEMO}, "sf_update": "ok", "gmail": "ok"}
    payload.update(over)
    out = subprocess.run(["node", str(REPO / "tests/n8n_desk_harness.js")], input=json.dumps(payload), capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def decode(raw):
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")


def test_the_demo_run_end_to_end(records):
    """Note: the harness runs on today's date, so the dates in sf_record (from as_of) may make a quote
    expired on a later day; the rules are then still checked by code, which is what is under test."""
    out = run_harness(records)
    s = out["stages"]
    queue = s["Build Queue"][0]["json"]["queue"]
    assert len(queue) == 8 and {p["run_id"] for p in queue} == {"n8n-9001"}
    log = s["Build Queue"][0]["json"]["log"]
    assert len(log["proposals"]) == 8 and len(log["calls"]) == 8 and log["handoffs"] == []
    approver = decode(s["Build Approver Message"][0]["json"]["raw"])
    assert approver.startswith("To: desk.owner+gtm-approver@example.com\r\n") and "http://localhost:5678/form-waiting/9001" in approver
    update = s["Apply Decisions"][0]["json"]["update"]["body"]["records"]
    assert {r["id"] for r in update} == {r["Id"] for r in records}
    rows = s["Build Decision Log"][0]["json"]["rows"]
    assert all(r["crm_write_status"] == "written" and r["owner_message_status"] == "sent" for r in rows)
    assert s["Build Decision Log"][0]["json"]["summary"]["owners_told"] == 8
    assert "Nothing was sent to a customer" in s["Done Message"][0]["json"]["message"]


def test_every_email_in_a_run_goes_to_the_own_inbox_even_when_a_quote_names_a_customer_address(records):
    eng = Engine(module="quotes")
    q19 = eng.call("caseToQuote", CASES["Q-0019"], PRODUCTS, AS_OF)  # its rep note asks to send the reply to the customer
    recs = records + [sf_record(q19, "0Q0999999999999")]
    answers = {c["case_id"]: answer(labelled_triage(c["case_id"])) for c in DEMO + [CASES["Q-0019"]]}
    out = run_harness(recs, answers=answers)
    assert len(out["emails"]) == 1 + 9
    for e in out["emails"]:
        to = decode(e["raw"]).split("\r\n", 1)[0]
        assert to in ("To: desk.owner+gtm-approver@example.com", "To: desk.owner+gtm-owner@example.com"), to
        assert "bellbird-telecom.example" not in to


def test_a_quote_salesforce_refuses_is_logged_failed_and_its_owner_is_not_told(records):
    out = run_harness(records, sf_update="partial")
    rows = out["stages"]["Build Decision Log"][0]["json"]["rows"]
    first = next(r for r in rows if r["quote_id"] == out["stages"]["Apply Decisions"][0]["json"]["update"]["ids"][0])
    assert first["crm_write_status"] == "failed" and "INSUFFICIENT_ACCESS" in first["crm_error"]
    assert first["owner_message_status"] == "failed" and len(out["emails"]) == 1 + 7


def test_when_salesforce_refuses_the_whole_update_nobody_is_told_and_the_log_says_why(records):
    out = run_harness(records, sf_update="fail")
    s = out["stages"]
    assert s["Build Owner Messages"] == [{"json": {"skip": True}}] and len(out["emails"]) == 1
    rows = s["Build Decision Log"][0]["json"]["rows"]
    assert all(r["crm_write_status"] == "failed" and "INVALID_SESSION_ID" in r["crm_error"] for r in rows)
    assert s["Done Message"][0]["json"]["title"] == "Quote desk finished with failures"


def test_the_reviewer_can_go_against_the_ai_and_the_log_shows_it(records):
    out = run_harness(records, choices={"Q-0005": ["Reject: send back to the owner", "Too large a discount for this quarter"]})
    rows = {r["case_id"]: r for r in out["stages"]["Build Decision Log"][0]["json"]["rows"]}
    assert rows["Q-0005"]["action"] == "rejected" and rows["Q-0005"]["matches_proposal"] is False
    assert rows["Q-0005"]["reason"] == "Too large a discount for this quarter"
    assert "went against the AI on 1" in out["stages"]["Done Message"][0]["json"]["message"]


def test_an_empty_queue_ends_on_its_own_page():
    out = run_harness([], answers={})
    assert out["empty"] is True
    assert successors("Any Quotes?") and list(WF["connections"]["Any Quotes?"]["main"][1])[0]["node"] == "Nothing to Do"
