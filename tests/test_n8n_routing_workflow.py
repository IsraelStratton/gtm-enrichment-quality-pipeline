"""The routing workflows: chapter 2's (n8n/workflow-v2.json, HubSpot) and chapter 4's
(n8n/workflow-v2-salesforce.json): how they are built, what they can reach, that they differ
only in the write step, and what their Code nodes do when run in order on the demo file
(tests/n8n_harness.js)."""
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
WF_SF = json.loads((REPO / "n8n/workflow-v2-salesforce.json").read_text(encoding="utf-8"))
SF_NODES = {n["name"]: n for n in WF_SF["nodes"]}
SETUP = json.loads((REPO / "salesforce/setup.json").read_text(encoding="utf-8"))
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
    assert build.render(build.build("salesforce")) == (REPO / "n8n/workflow-v2-salesforce.json").read_text(encoding="utf-8")
    for wf in (WF, WF_SF):
        assert set(wf) == {"name", "nodes", "connections", "settings"}
        assert wf["settings"] == {"executionOrder": "v1"}
    assert build.main(["--check"]) == 0


@pytest.mark.parametrize("wf, crm_host", [(WF, "api.hubapi.com"), (WF_SF, build.SALESFORCE_HOST_PLACEHOLDER.lower())])
def test_nothing_in_the_workflow_can_send_to_anyone(wf, crm_host):
    """No email, chat or outbound webhook node; HTTP only to Claude and the one CRM."""
    assert {n["type"] for n in wf["nodes"]} <= ALLOWED_TYPES
    hosts = {urlsplit(n["parameters"]["url"]).hostname for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"}
    assert hosts == {"api.anthropic.com", crm_host}


def credentials_of(wf):
    found = {}
    for n in wf["nodes"]:
        for cred_type, cred in (n.get("credentials") or {}).items():
            assert cred["id"] is None, n["name"]
            found[n["name"]] = (cred_type, cred["name"])
    return found


def test_credentials_are_named_with_no_instance_id():
    shared = {
        "Claude Routing Step": ("httpHeaderAuth", "Claude key gtm-pipeline-v2"),
        "Log Proposals": ("postgres", "GTM v2 run log (Postgres)"),
        "Log Decisions": ("postgres", "GTM v2 run log (Postgres)"),
        "Read Run Summary": ("postgres", "GTM v2 run log (Postgres)"),
    }
    assert credentials_of(WF) == {**shared, "HubSpot Batch Upsert": ("httpHeaderAuth", "HubSpot Service Key")}
    # Salesforce: n8n's general OAuth2 login (client credentials), named as in salesforce/setup.json.
    assert credentials_of(WF_SF) == {**shared, "Salesforce Upsert": ("oAuth2Api", SETUP["n8n_credential"]["name"])}


def test_version_1_nodes_are_unchanged():
    for name in ("Extract CSV", "DQ Checks", "Pass or Fail", "Format Quarantine", "Quarantine Table"):
        assert NODES[name]["parameters"] == V1_NODES[name]["parameters"], name
        assert NODES[name]["type"] == V1_NODES[name]["type"], name


@pytest.mark.parametrize("wf", [WF, WF_SF])
def test_every_engine_node_runs_the_same_tested_engine(wf):
    engine = build.engine_source()
    with_engine = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.code" and "function parsePlaybook" in n["parameters"]["jsCode"]]
    assert {n["name"] for n in with_engine} == {"Build Requests", "Check Proposal", "Build Review", "Apply Decisions", "Build Decision Log"}
    for n in with_engine:
        assert n["parameters"]["jsCode"].startswith(engine), n["name"]
    assert "module.exports" not in json.dumps(wf)


def test_the_salesforce_workflow_differs_from_hubspot_only_in_the_write_step():
    """Chapter 4's claim, as a test: the same engine, the same rules, AI step, review and log.
    Take out the write node, swap the words that name the target, and the two files are equal."""
    hs_t, sf_t = build.TARGETS["hubspot"], build.TARGETS["salesforce"]

    engine = build.engine_source()  # the same in both; checked by the test above

    def without_write(wf, write_node):
        nodes = []
        for n in json.loads(json.dumps(wf["nodes"])):
            if n["name"] == write_node:
                continue
            code = n["parameters"].get("jsCode", "")
            if code.startswith(engine):
                n["parameters"]["jsCode"] = "<engine>" + code[len(engine):]
            nodes.append(n)
        return {**wf, "nodes": nodes}

    text = json.dumps(without_write(WF_SF, sf_t["write_node"]), sort_keys=True)
    for a, b in ((sf_t["name"], hs_t["name"]), (sf_t["form_path"], hs_t["form_path"]),
                 (build.node_id("salesforce Review Page webhook"), build.node_id("Review Page webhook")),
                 (build.node_id("salesforce Done webhook"), build.node_id("Done webhook")),
                 (sf_t["write_node"], hs_t["write_node"]), ("'salesforce'", "'hubspot'"), ("Salesforce", "HubSpot")):
        text = text.replace(a, b)
    assert json.loads(text) == without_write(WF, hs_t["write_node"])
    assert set(NODES) - {hs_t["write_node"]} == set(SF_NODES) - {sf_t["write_node"]}


def test_the_salesforce_write_is_an_external_id_upsert_after_the_review():
    w = SF_NODES["Salesforce Upsert"]
    p = w["parameters"]
    assert p["method"] == "PATCH" and p["genericAuthType"] == "oAuth2Api"
    url = urlsplit(p["url"])
    assert url.scheme == "https" and url.hostname == build.SALESFORCE_HOST_PLACEHOLDER.lower()
    assert url.path == f"/services/data/{SETUP['api_version']}/composite/sobjects/{SETUP['object']}/{SETUP['external_id_field']}"
    assert p["jsonBody"] == "={{ JSON.stringify($json.write.body) }}"
    assert p["options"]["response"]["response"] == {"fullResponse": True, "neverError": True}
    assert w["onError"] == "continueRegularOutput" and "retryOnFail" not in w
    assert "target: 'salesforce'" in SF_NODES["Apply Decisions"]["parameters"]["jsCode"]
    assert "target: 'salesforce'" in SF_NODES["Build Review"]["parameters"]["jsCode"]
    assert SF_NODES["Upload CSV"]["parameters"]["options"]["path"] == "gtm-v2-route-leads-salesforce"
    assert "webhookId" not in SF_NODES["Upload CSV"]
    assert SF_NODES["Review Page"]["webhookId"] != NODES["Review Page"]["webhookId"]


def test_the_local_copy_fills_in_only_the_host_and_is_ignored_by_git():
    host = "acme-dev-ed.develop.my.salesforce.com"
    local = build.build("salesforce", host)
    assert json.dumps(local).replace(host, build.SALESFORCE_HOST_PLACEHOLDER) == json.dumps(build.build("salesforce"))
    ignored = subprocess.run(["git", "check-ignore", "-q", "n8n/workflow-v2-salesforce.local.json"], cwd=REPO, check=False)
    assert ignored.returncode == 0
    assert re.match(build.SALESFORCE_HOST_RE, host) and not re.match(build.SALESFORCE_HOST_RE, "evil.example/x.my.salesforce.com")


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


def reachable(start, skip, wf=WF):
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        for branch in wf["connections"].get(name, {}).get("main", []):
            for link in branch:
                if link["node"] not in seen and link["node"] != skip:
                    seen.add(link["node"])
                    todo.append(link["node"])
    return seen


@pytest.mark.parametrize("wf, write_node", [(WF, "HubSpot Batch Upsert"), (WF_SF, "Salesforce Upsert")])
def test_no_path_reaches_the_crm_without_the_review_page(wf, write_node):
    assert write_node in reachable("Upload CSV", skip=None, wf=wf)
    assert write_node not in reachable("Upload CSV", skip="Review Page", wf=wf)
    assert "Log Proposals" not in reachable("Review Page", skip=None, wf=wf)  # proposals are logged before the review


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


def harness(upsert="ok", workflow="n8n/workflow-v2.json"):
    payload = {"workflow": str(REPO / workflow), "rows": RUN_ROWS, "playbook": PLAYBOOK,
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
    writes = applied["write"]["body"]["inputs"]
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
    assert r["log"]["summary"]["failed"] == r["applied"]["write"]["count"] > 0
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


SF = "n8n/workflow-v2-salesforce.json"


@needs_node
def test_demo_file_runs_through_the_salesforce_workflow():
    """The same demo file and the same reviewer: the same decisions, now as Salesforce Accounts."""
    hs, sf = harness(), harness(workflow=SF)
    assert sf["writeNode"] == "Salesforce Upsert" and hs["writeNode"] == "HubSpot Batch Upsert"
    assert [p["route"] for p in sf["proposals"]] == [p["route"] for p in hs["proposals"]]
    # The two runs read the real clock, and may fall either side of a second: compare without the time.
    when = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
    strip = lambda ds: [{k: when.sub("<time>", v) if isinstance(v, str) else v for k, v in d.items() if k != "crm_target"} for d in ds]  # noqa: E731
    assert strip(sf["applied"]["decisions"]) == strip(hs["applied"]["decisions"])
    records = sf["applied"]["write"]["body"]["records"]
    assert len(records) == len(hs["applied"]["write"]["body"]["inputs"]) == sf["applied"]["write"]["count"]
    assert all(r["GTM_Decision_Stamp__c"].startswith("gtm-v2 D-n8n501-") and " by reviewer-01 | " in r["GTM_Decision_Stamp__c"] for r in records)
    assert all(r["attributes"] == {"type": "Account"} and r["Clay_Domain_Key__c"] for r in records)
    log = sf["log"]
    assert log["summary"]["written"] == len(records) and log["summary"]["failed"] == 0
    assert all(row["crm_record_id"].startswith("001") and row["crm_target"] == "salesforce" for row in log["rows"] if row["action"] != "rejected")
    assert f"Written to Salesforce: {len(records)}" in sf["done"]["message"] and "Every Salesforce record written" in sf["done"]["message"]
    assert "Nothing is written to Salesforce until you submit" in sf["review"]["form_fields"][0]["html"]


@needs_node
def test_a_refused_salesforce_record_fails_only_its_row():
    r = harness(upsert="partial", workflow=SF)
    written = [x for x in r["log"]["rows"] if x["action"] != "rejected"]
    assert r["log"]["summary"]["failed"] == 1 and r["log"]["summary"]["written"] == len(written) - 1
    assert written[0]["crm_error"].startswith("INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST")
    assert r["done"]["title"] == "Routing run finished with failures"


@needs_node
def test_a_failed_salesforce_request_is_logged_as_failed():
    r = harness(upsert="fail", workflow=SF)
    assert r["log"]["summary"]["failed"] == r["applied"]["write"]["count"] > 0
    assert all("INVALID_FIELD: No such column" in x["crm_error"] for x in r["log"]["rows"] if x["action"] != "rejected")
