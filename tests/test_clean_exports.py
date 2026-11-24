"""The wrap, item 4: every committed workflow export is clean (scripts/clean_exports.py).

CI runs these on every push; scripts/prepush_check.py runs the same check on the commit being pushed.
Samples of private-looking values are built at run time, so this file passes its own scan.
"""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import clean_exports as ce  # noqa: E402

AT = "@"
COLUMNS = ["written_by", "run_id", "lead_id", "company_name", "domain", "route", "priority",
           "owner_team", "decision", "approved_by", "approved_at", "sent_at", "received_at"]


def load(rel):
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def test_every_committed_export_is_clean():
    assert ce.check_all(ce.tree_reader()) == []


def test_every_json_file_under_n8n_and_slice_is_an_export_the_check_covers():
    listed = {f for fs in ce.EXPORTS.values() for f in fs} | ce.NOT_EXPORTS
    assert [p for p in ce.tracked_json() if p not in listed] == []
    assert all((REPO / p).is_file() for p in listed)
    ignored = subprocess.run(["git", "check-ignore", "-q", "n8n/workflow-v2-quote-desk.local.json"], cwd=REPO, check=False)
    assert ignored.returncode == 0, "filled-in local copies stay out of git"


def test_no_value_from_the_local_env_or_private_list_is_in_any_export():
    """Skipped in CI, which has neither file."""
    private = ce.private_values()
    if not private:
        pytest.skip("no local .env or .prepush-private.local")
    assert ce.check_all(ce.tree_reader(), private) == []


N8N = "n8n/workflow-v2.json"


def node(wf, name):
    return next(n for n in wf["nodes"] if n["name"] == name)


@pytest.mark.parametrize("change, words", [
    (lambda w: node(w, "Claude Routing Step")["credentials"]["httpHeaderAuth"].update(id="Ab3dE6gH9jK2mN5p"), "a credential ID"),
    (lambda w: node(w, "Quarantine Table")["parameters"]["dataTableId"].update(value="7xYzAb3dE6gH9jK2"), "a data table ID"),
    (lambda w: w.update(id="Ab3dE6gH9jK2mN5p", meta={"instanceId": "x"}), "instance data at the top: id, meta"),
    (lambda w: node(w, "Done Message")["parameters"].update(jsCode="// mail someone" + AT + "gmail.com"), "an email address"),
    (lambda w: node(w, "Done Message")["parameters"].update(jsCode="// gtm-v2-quote-desk-x1" + AT + "example.com"), "a Salesforce username of this build"),
    (lambda w: node(w, "HubSpot Batch Upsert")["parameters"].update(url="https://acme-dev-ed.develop.my.salesforce.com/x"), "a Salesforce host"),
    (lambda w: node(w, "Done Message")["parameters"].update(jsCode="// https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123"), "a Google Sheets ID"),
    (lambda w: node(w, "Done Message")["parameters"].update(jsCode="// x-api-key sk-ant-" + "api03-AbCdEfGhIjKlMnOp"), "a Claude API key"),
    (lambda w: node(w, "Done Message")["parameters"].update(jsCode="// org 00D" + "Aj000000AbCd"), "a Salesforce org, user or agent ID"),
])
def test_the_n8n_check_catches_each_kind_of_leak(change, words):
    wf = load(N8N)
    change(wf)
    found = ce.export_findings("n8n", json.dumps(wf))
    assert any(words in f for f in found), found


def test_the_make_check_catches_a_real_hook_connection_or_webhook_address():
    bp = load("slice/make/slice-scenario.blueprint.json")
    assert ce.export_findings("make", json.dumps(bp)) == []
    for change, words in (
        (lambda b: b["flow"][0]["parameters"].update(hook=1000005), "an ID where a placeholder belongs"),
        (lambda b: b["flow"][1]["parameters"].update(oAuthAccount=1000006), "an ID where a placeholder belongs"),
        (lambda b: b["flow"][1]["mapper"].update(url="https://hook.eu2.make.com/abcdef123456"), "a Make webhook address"),
    ):
        changed = copy.deepcopy(bp)
        change(changed)
        assert any(words in f for f in ce.export_findings("make", json.dumps(changed)))


def test_the_zapier_check_catches_an_id_a_hook_or_an_address():
    z = load("slice/zapier/zap-builds.json")
    for change, words in (
        (lambda d: d["zaps"][0].update(zap_id=1000001), "an ID where a placeholder belongs"),
        (lambda d: d["zaps"][2]["steps"][0]["settings"][0].update(value="https://hooks.zapier.com/hooks/catch/1000002/abcdef/"), "a Zapier webhook address"),
        (lambda d: d["zaps"][1]["steps"][1]["settings"][0].update(value="owner+gtm-slice" + AT + "gmail.com"), "an email address"),
    ):
        changed = copy.deepcopy(z)
        change(changed)
        assert any(words in f for f in ce.export_findings("zapier", json.dumps(changed)))


def test_the_n8n_cleaner_keeps_what_n8n_imports_and_drops_what_belongs_to_one_instance():
    raw = {
        "id": "Ab3dE6gH9jK2mN5p", "versionId": "v", "active": False, "meta": {"instanceId": "i"}, "pinData": {},
        "shared": [{"project": {"name": "Owner <someone" + AT + "gmail.com>"}}], "tags": [], "staticData": None,
        "name": "A workflow", "settings": {"executionOrder": "v1", "errorWorkflow": "Zz9yXx8wWv7uUt6s"},
        "connections": {"Start": {"main": [[{"node": "Write", "type": "main", "index": 0}]]}},
        "nodes": [
            {"id": "random-1", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
            {"id": "random-2", "name": "Write", "type": "n8n-nodes-base.httpRequest", "webhookId": "random-3",
             "credentials": {"googleOAuth2Api": {"id": "Qw3eR5tY7uI9oP1a", "name": "Google least reach gtm-pipeline"}},
             "parameters": {"url": "https://sheets.googleapis.com/v4/spreadsheets/1AbCdEfGhIjKlMnOpQrStUvWxYz0123/values",
                            "dataTableId": {"__rl": True, "mode": "id", "value": "7xYzAb3dE6gH9jK2"}}},
        ],
    }
    wf = ce.clean_n8n(raw)
    assert set(wf) == {"name", "nodes", "connections", "settings"} and wf["settings"] == {"executionOrder": "v1"}
    assert ce.export_findings("n8n", json.dumps(wf)) == []
    write = node(wf, "Write")
    assert write["credentials"]["googleOAuth2Api"] == {"id": None, "name": "Google least reach gtm-pipeline"}
    assert "/spreadsheets/SPREADSHEET_ID/" in write["parameters"]["url"] and write["parameters"]["dataTableId"]["value"] == "DATA_TABLE_ID"
    assert ce.clean_n8n(raw) == wf, "the same input gives the same file"
    with_address = copy.deepcopy(raw)
    with_address["nodes"][0]["parameters"]["note"] = "send to someone" + AT + "gmail.com"
    assert ce.export_findings("n8n", json.dumps(ce.clean_n8n(with_address))) == ["an email address"], "an address is refused, not guessed at"


def test_the_zapier_cleaner_replaces_ids_hooks_addresses_and_private_values(tmp_path):
    raw = {"zaps": [{"id": 1000003, "title": "GTM v2 slice: approved lead (Zapier Pro)", "nodes": {"1": {
        "selected_api": "WebHookCLIAPI@1.0.6", "params": {"url": "https://hooks.zapier.com/hooks/catch/1000002/abcdef/"},
        "authentication_id": "1000004", "to": "owner+gtm-slice" + AT + "gmail.com", "key": "s3cret-key-value-123",
        "customer": "sales" + AT + "northwind-freight.example"}}}]}
    clean = ce.clean_zapier(raw, {".env SLICE_KEY_ZAPIER": "s3cret-key-value-123"})
    n = clean["zaps"][0]["nodes"]["1"]
    assert clean["zaps"][0]["id"] == "ZAP_1" and n["authentication_id"] == "ZAPIER_ID"
    assert n["params"]["url"] == "ZAPIER_HOOK_URL" and n["to"] == "OWNER_INBOX" and n["key"] == "SLICE_KEY_ZAPIER"
    assert n["customer"].endswith(".example") and n["selected_api"] == "WebHookCLIAPI@1.0.6"
    assert ce.write_clean("zapier", clean, tmp_path / "z.json", {}) == 0


def test_the_tracker_export_makes_the_sheet_the_slices_write_to():
    wf = load("slice/n8n/create-tracker-workflow.json")
    assert [n["type"] for n in wf["nodes"]] == ["n8n-nodes-base.manualTrigger", "n8n-nodes-base.httpRequest"]
    create = wf["nodes"][1]
    assert create["parameters"]["url"] == "https://sheets.googleapis.com/v4/spreadsheets"
    assert create["credentials"] == {"googleOAuth2Api": {"id": None, "name": "Google least reach gtm-pipeline"}}
    body = json.loads(create["parameters"]["jsonBody"])
    headings = [v["userEnteredValue"]["stringValue"] for v in body["sheets"][0]["data"][0]["rowData"][0]["values"]]
    assert headings == COLUMNS and body["sheets"][0]["properties"]["title"] == "rows"


def test_the_zapier_record_matches_the_guide_and_the_notes():
    z = load("slice/zapier/zap-builds.json")
    assert z["table"]["fields_in_order"] == COLUMNS
    steps = {zap["name"]: [s["app"] for s in zap["steps"]] for zap in z["zaps"]}
    assert steps == {
        "GTM v2 slice 1 of 2: approved lead to tracker": ["Zapier Forms", "Zapier Tables"],
        "GTM v2 slice 2 of 2: tracker row to owner email": ["Zapier Tables", "Email by Zapier"],
        "GTM v2 slice: approved lead (Zapier Pro)": ["Webhooks by Zapier", "Filter by Zapier", "Code by Zapier", "AI by Zapier",
                                                     "Human in the Loop", "Zapier Tables", "Email by Zapier"],
    }
    assert all(zap["state"] == "off" for zap in z["zaps"])
    guide = (REPO / "slice/zapier/BUILD.md").read_text(encoding="utf-8")
    code = next(s for s in z["zaps"][2]["steps"] if s["app"] == "Code by Zapier")["settings"][1]["value"]
    assert code in guide, "the Pro Zap's code is the guide's, word for word"
    mcp = z["mcp_server"]
    assert mcp["mode"].startswith("managed") and len(mcp["actions"]) == 1
    assert {"field": "written_by", "value": "claude-mcp"} in mcp["actions"][0]["fixed"]
    for zap in z["zaps"]:
        for s in zap["steps"]:
            for setting in s.get("settings", []):
                if setting["setting"] == "to":
                    assert setting["value"] == "OWNER_INBOX"


APPS = {"InterfacesCLIAPI": "Zapier Forms", "TableCLIAPI": "Zapier Tables", "ZapierMailCLIAPI": "Email by Zapier",
        "WebHookCLIAPI": "Webhooks by Zapier", "FilterAPI": "Filter by Zapier", "CodeCLIAPI": "Code by Zapier",
        "AICLIAPI": "AI by Zapier", "App226439CLIAPI": "Human in the Loop"}


def test_the_zapier_record_matches_zapiers_own_export():
    """The as-built record (zap-builds.json) against Zapier's export, cleaned (zapier-export.json): the same Zaps,
    the same steps in the same order, each step's app and action, and the Pro Zap's code word for word."""
    record, export = load("slice/zapier/zap-builds.json"), load("slice/zapier/zapier-export.json")
    assert [z["title"] for z in export["zaps"]] == [z["name"] for z in record["zaps"]]
    assert [z["id"] for z in export["zaps"]] == ["ZAP_1", "ZAP_2", "ZAP_3"]
    for rz, ez in zip(record["zaps"], export["zaps"]):
        assert ez["status"] == rz["state"] == "off"
        nodes = list(ez["nodes"].values())
        assert [APPS[n["selected_api"].split("@")[0]] for n in nodes] == [s["app"] for s in rz["steps"]]
        assert [n["action"] for n in nodes] == [s["action"] for s in rz["steps"]]
        assert [n["parent_id"] for n in nodes[1:]] == list(ez["nodes"])[:-1], "each step follows the one before"
    pro = export["zaps"][2]["nodes"]
    code = next(s for s in record["zaps"][2]["steps"] if s["app"] == "Code by Zapier")["settings"][1]["value"]
    assert " ".join(pro["ZAP_3_STEP_3"]["params"]["code"].split()) == " ".join(code.split())
    assert pro["ZAP_3_STEP_2"]["params"]["filter_criteria"][0]["value"] == "FILTER_VALUE"
    assert "http_x_slice_key" in pro["ZAP_3_STEP_2"]["params"]["filter_criteria"][0]["key"]
    hitl = pro["ZAP_3_STEP_5"]["params"]
    assert (hitl["denied_action"], hitl["timeout"], hitl["timeoutUnit"], hitl["allow_edit"]) == ("stop", "7", "days", True)
    prompt = next(s for s in record["zaps"][2]["steps"] if s["app"] == "AI by Zapier")["settings"]
    wording = next(x["value"] for x in prompt if x["setting"] == "prompt")
    built = re.sub(r"\{\{ZAP_3_STEP_3__(\w+)\}\}", r"{\1}", pro["ZAP_3_STEP_4"]["params"]["instructions"])
    assert built.endswith(wording) and built != wording, "the prompt as built has the guide's words after a stray field"


def test_zapiers_export_held_the_key_the_ids_and_the_address_and_the_clean_copy_holds_none():
    export = (REPO / "slice/zapier/zapier-export.json").read_text(encoding="utf-8")
    for placeholder in ("FILTER_VALUE", "OWNER_INBOX", "ZAP_3_STEP_1", "ZAPIER_ID"):
        assert placeholder in export
    assert ce.zapier_findings(json.loads(export)) == [] and ce.text_findings(export) == []
