"""The chapter 2 n8n workflow (n8n/workflow-v2.json): how it is built, what it can reach, and
what its Code nodes do when run in order on the demo file (tests/n8n_harness.js)."""
import csv
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
import build_n8n_routing as build  # noqa: E402

WF = json.loads((REPO / "n8n/workflow-v2.json").read_text(encoding="utf-8"))
V1 = json.loads((REPO / "n8n/workflow.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}
V1_NODES = {n["name"]: n for n in V1["nodes"]}
PLAYBOOK = (REPO / "skins/lead-routing/lead-routing-playbook/SKILL.md").read_text(encoding="utf-8")
ROUTES = re.findall(r"^\| `([a-z_]+)` \|", PLAYBOOK.split("## Routes\n", 1)[1].split("\n## ", 1)[0], re.M)
ENQUIRIES = {r["lead_id"]: r for r in csv.DictReader((REPO / "skins/lead-routing/enquiries.csv").open(encoding="utf-8"))}
RUN_ROWS = list(csv.DictReader((REPO / "skins/lead-routing/sample_run.csv").open(encoding="utf-8")))

ALLOWED_TYPES = {
    "n8n-nodes-base.formTrigger", "n8n-nodes-base.form", "n8n-nodes-base.extractFromFile", "n8n-nodes-base.code",
    "n8n-nodes-base.if", "n8n-nodes-base.dataTable", "n8n-nodes-base.readWriteFile", "n8n-nodes-base.splitInBatches",
    "n8n-nodes-base.httpRequest", "n8n-nodes-base.postgres",
}


def test_file_is_made_by_the_build_script_and_is_up_to_date():
    assert build.render(build.build()) == (REPO / "n8n/workflow-v2.json").read_text(encoding="utf-8")
    assert set(WF) == {"name", "nodes", "connections", "settings"}
    assert WF["settings"] == {"executionOrder": "v1"}


def test_nothing_in_the_workflow_can_send_to_anyone():
    """No email, chat or outbound webhook node; HTTP only to Claude and HubSpot."""
    assert {n["type"] for n in WF["nodes"]} <= ALLOWED_TYPES
    hosts = {urlsplit(n["parameters"]["url"]).hostname for n in WF["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"}
    assert hosts == {"api.anthropic.com", "api.hubapi.com"}


def test_credentials_are_named_with_no_instance_id():
    found = {}
    for n in WF["nodes"]:
        for cred_type, cred in (n.get("credentials") or {}).items():
            assert cred["id"] is None, n["name"]
            found[n["name"]] = (cred_type, cred["name"])
    assert found == {
        "Claude Routing Step": ("httpHeaderAuth", "Claude key gtm-pipeline-v2"),
        "HubSpot Batch Upsert": ("httpHeaderAuth", "HubSpot Service Key"),
        "Log Proposals": ("postgres", "GTM v2 run log (Postgres)"),
        "Log Decisions": ("postgres", "GTM v2 run log (Postgres)"),
        "Read Run Summary": ("postgres", "GTM v2 run log (Postgres)"),
    }


def test_version_1_nodes_are_unchanged():
    for name in ("Extract CSV", "DQ Checks", "Pass or Fail", "Format Quarantine", "Quarantine Table"):
        assert NODES[name]["parameters"] == V1_NODES[name]["parameters"], name
        assert NODES[name]["type"] == V1_NODES[name]["type"], name


def test_every_engine_node_runs_the_same_tested_engine():
    engine = build.engine_source()
    with_engine = [n for n in WF["nodes"] if n["type"] == "n8n-nodes-base.code" and "function parsePlaybook" in n["parameters"]["jsCode"]]
    assert {n["name"] for n in with_engine} == {"Build Requests", "Check Proposal", "Build Review", "Apply Decisions", "Build Decision Log"}
    for n in with_engine:
        assert n["parameters"]["jsCode"].startswith(engine), n["name"]
    assert "module.exports" not in json.dumps(WF)


def test_routing_rules_come_only_from_the_playbook_file():
    """A3.1: no route code anywhere in the workflow; the playbook is read from disk on every run."""
    text = json.dumps(WF)
    for route in ROUTES:
        assert route not in text, route
    read = NODES["Read Playbook"]
    assert read["parameters"]["fileSelector"] == build.PLAYBOOK_PATH
    assert read["executeOnce"] and NODES["Playbook Text"]["executeOnce"]
    mounted = build.PLAYBOOK_PATH.replace("/home/node/gtm-skins/", "skins/")
    assert (REPO / mounted).is_file()
    script = (REPO / "scripts/n8n_docker.sh").read_text(encoding="utf-8")
    assert '-v "$REPO/skins:$SKINS_IN_N8N:ro"' in script and 'SKINS_IN_N8N="/home/node/gtm-skins"' in script


def test_n8n_is_published_on_this_mac_only():
    """Israel's yes, 23/11/2026: no other device on the network can reach the form or the webhook."""
    script = (REPO / "scripts/n8n_docker.sh").read_text(encoding="utf-8")
    ports = [line.strip() for line in script.splitlines() if line.strip().startswith("-p ")]
    assert ports == ["-p 127.0.0.1:5678:5678 \\"]


def reachable(start, skip):
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        for branch in WF["connections"].get(name, {}).get("main", []):
            for link in branch:
                if link["node"] not in seen and link["node"] != skip:
                    seen.add(link["node"])
                    todo.append(link["node"])
    return seen


def test_no_path_reaches_hubspot_without_the_review_page():
    assert "HubSpot Batch Upsert" in reachable("Upload CSV", skip=None)
    assert "HubSpot Batch Upsert" not in reachable("Upload CSV", skip="Review Page")
    assert "Log Proposals" not in reachable("Review Page", skip=None)  # proposals are logged before the review


def test_loop_and_form_wiring():
    loop = WF["connections"]["Loop Over Leads"]["main"]
    assert [b[0]["node"] for b in loop] == ["Build Review", "Stamp Start"]  # done, then loop
    assert WF["connections"]["Check Proposal"]["main"][0][0]["node"] == "Loop Over Leads"
    trigger = NODES["Upload CSV"]
    assert trigger["typeVersion"] == NODES["Review Page"]["typeVersion"] == NODES["Done"]["typeVersion"] == 2.5
    assert trigger["parameters"]["options"]["path"] == build.FORM_PATH
    assert trigger["parameters"]["formFields"]["values"][0]["fieldName"] == "CSV_File"
    assert V1_NODES["Extract CSV"]["parameters"]["binaryPropertyName"] == "CSV_File"
    # The trigger ships with no webhookId, or n8n's import overwrites the Form Path with a new one.
    assert "webhookId" not in trigger
    assert all(NODES[n].get("webhookId") for n in ("Review Page", "Done"))
    assert NODES["Review Page"]["parameters"]["jsonOutput"].startswith("={{ $('Build Review')")
    claude = NODES["Claude Routing Step"]
    assert claude["onError"] == "continueRegularOutput" and claude["retryOnFail"]
    assert claude["parameters"]["headerParameters"]["parameters"] == [{"name": "anthropic-version", "value": "2026-10-21"}]


def fake_answer(lead_id):
    """A Claude reply that follows the drafted labels: attacks flagged, at 0.5."""
    e = ENQUIRIES[lead_id]
    attack = e["case_type"] == "attack"
    flags = ["possible_injection"] if attack else (["spam"] if e["case_type"] == "spam" else [])
    if lead_id == "L-0025":
        flags = ["unclear"]
    body = {"intent": e["expected_intent"].split("|")[0], "route": e["expected_route"].split("|")[-1],
            "priority": e["expected_priority"].split("|")[0], "reason": "Made-up reason for the harness.",
            "confidence": 0.5 if attack else 0.9, "flags": flags}
    return {"statusCode": 200, "headers": {"request-id": f"req_{lead_id}"},
            "body": {"id": "msg_x", "type": "message", "model": "claude-haiku-5-5", "stop_reason": "end_turn",
                     "content": [{"type": "text", "text": json.dumps(body)}], "usage": {"input_tokens": 3400, "output_tokens": 100}}}


def harness(upsert="ok"):
    payload = {"workflow": str(REPO / "n8n/workflow-v2.json"), "rows": RUN_ROWS, "playbook": PLAYBOOK,
               "answers": {r["lead_id"]: fake_answer(r["lead_id"]) for r in RUN_ROWS if r["lead_id"] in ENQUIRIES},
               "execution_id": "501", "upsert": upsert}
    out = subprocess.run(["node", str(REPO / "tests/n8n_harness.js")], input=json.dumps(payload),
                         capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@needs_node
def test_demo_file_runs_through_every_code_node():
    r = harness()
    # The data rules (version 1) stop the two seeded rows.
    failed = {d["company_name"]: d["_dq_reason_codes"] for d in r["dq"] if not d["_dq_pass"]}
    assert failed == {"Saltmarsh Imports": "INVALID_DOMAIN", "Northwind Freight (copy)": "DUPLICATE_IN_BATCH"}
    assert len(r["quarantine"]) == 2 and r["quarantine"][0]["run_id"] == "501"
    # One request per clean row, with the lead id and enquiry carried from the CSV.
    assert len(r["requests"]) == 12 and r["requests"][0]["quarantined"] == 2
    assert {q["lead"]["lead_id"] for q in r["requests"]} == {x["lead_id"] for x in RUN_ROWS} - {"L-9001", "L-9002"}
    assert all(q["decision_id"].startswith("D-n8n501-") for q in r["requests"])
    # Guard rails: the attack rows are flagged, and so is the row with no headcount.
    flagged = {p["lead_id"] for p in r["proposals"] if p["needs_review"]}
    assert {"L-0034", "L-0036", "L-0025"} <= flagged
    assert all(p["latency_ms"] is not None and p["playbook_version"] == "1.0.0" for p in r["proposals"])
    # The review page has one required choice per proposal, flagged rows first.
    rows = [f for f in r["review"]["form_fields"] if f.get("fieldType") == "dropdown"]
    assert len(rows) == 12 and rows[0]["fieldLabel"].startswith("Check:")
    # Decisions: flagged rows rejected, one changed, the rest approved; a stamp on every write.
    applied = r["applied"]
    actions = [d["action"] for d in applied["decisions"]]
    assert actions.count("changed") == 1 and actions.count("rejected") == len(flagged)
    writes = applied["hubspot"]["inputs"]
    assert len(writes) == 12 - len(flagged)
    assert all(w["properties"]["gtm_decision_stamp"].startswith("gtm-v2 D-n8n501-") for w in writes)
    assert all(" by reviewer-01 | " in w["properties"]["gtm_decision_stamp"] for w in writes)
    assert {w["properties"]["gtm_routing_status"] for w in writes} == {"approved", "changed"}
    # The decision log records the HubSpot ids, and the done page reads the cost back.
    log = r["log"]
    assert log["summary"]["written"] == len(writes) and log["summary"]["failed"] == 0
    assert all(row["crm_record_id"] for row in log["rows"] if row["action"] != "rejected")
    assert f"Written to HubSpot: {len(writes)}" in r["done"]["message"] and "US$0.004700" in r["done"]["message"]


@needs_node
def test_a_failed_hubspot_write_is_logged_as_failed():
    r = harness(upsert="fail")
    assert r["log"]["summary"]["failed"] == len(r["applied"]["hubspot"]["inputs"]) > 0
    assert all("Property values were not valid" in x["crm_error"] for x in r["log"]["rows"] if x["action"] != "rejected")
    assert r["done"]["title"] == "Routing run finished with failures"


@needs_node
def test_postgres_nodes_read_fields_the_code_nodes_produce():
    r = harness()
    assert "proposals" in r["review"] and NODES["Log Proposals"]["parameters"]["options"]["queryReplacement"] == "={{ JSON.stringify($json.proposals) }}"
    assert "rows" in r["log"] and "run_id" in r["log"]
    for name, fn in (("Log Proposals", "log_proposals"), ("Log Decisions", "log_decisions")):
        assert f"gtm_v2.{fn}($1::jsonb)" in NODES[name]["parameters"]["query"]
    sql = (REPO / "db/run_log.sql").read_text(encoding="utf-8")
    for key in ("decision_id", "playbook_sha256", "needs_review", "latency_ms"):
        assert all(key in p for p in r["proposals"]) and key in sql
    for key in ("action", "chosen_route", "approver", "stamp", "crm_write_status"):
        assert all(key in x for x in r["log"]["rows"]) and key in sql
