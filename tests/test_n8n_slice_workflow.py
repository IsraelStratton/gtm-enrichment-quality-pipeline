"""Tests for the n8n slice workflow template, its owner-email code and the render script.

They keep the workflow on the least-reach design: one general Google login,
HTTP requests to three Google hosts only, the row written before the email,
and a recipient that never comes from the payload.
"""
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
import fire_slice  # noqa: E402
import render_n8n_slice as rn  # noqa: E402

TEMPLATE = json.loads((REPO / "slice/n8n/slice-workflow.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in TEMPLATE["nodes"]}
JS = (REPO / "slice/n8n/build_owner_email.js").read_text(encoding="utf-8")
COLUMNS = [
    "written_by", "run_id", "lead_id", "company_name", "domain", "route", "priority",
    "owner_team", "decision", "approved_by", "approved_at", "sent_at", "received_at",
]
ALLOWED_HOSTS = {"sheets.googleapis.com", "gmail.googleapis.com", "www.googleapis.com"}


def test_template_has_only_importable_keys_and_six_named_nodes():
    assert set(TEMPLATE) == {"name", "nodes", "connections", "settings"}
    assert list(NODES) == [
        "Approved lead in", "Shape tracking row", "Add tracking row",
        "Get owner inbox", "Build owner email", "Send owner email",
    ]
    assert TEMPLATE["settings"]["executionOrder"] == "v1"


def test_webhook_matches_the_fire_script_and_requires_the_key():
    hook = NODES["Approved lead in"]
    p = hook["parameters"]
    assert hook["type"] == "n8n-nodes-base.webhook"
    assert p["path"] == fire_slice.N8N_PATH
    assert p["httpMethod"] == "POST"
    assert p["responseMode"] == "onReceived"
    assert hook.get("webhookId")
    assert p["authentication"] == "headerAuth"
    assert hook["credentials"] == {"httpHeaderAuth": {"id": "SLICE_KEY_CREDENTIAL_ID", "name": "Slice webhook key (n8n)"}}


def test_only_the_general_google_login_and_three_google_hosts():
    for node in TEMPLATE["nodes"]:
        assert node["type"] not in {"n8n-nodes-base.gmail", "n8n-nodes-base.googleSheets"}
        allowed = {"httpHeaderAuth"} if node["name"] == "Approved lead in" else {"googleOAuth2Api"}
        for cred_type in node.get("credentials") or {}:
            assert cred_type in allowed, node["name"]
        if node["type"] == "n8n-nodes-base.httpRequest":
            p = node["parameters"]
            assert p["authentication"] == "predefinedCredentialType"
            assert p["nodeCredentialType"] == "googleOAuth2Api"
            assert urlsplit(p["url"]).hostname in ALLOWED_HOSTS, node["name"]
            assert node["credentials"]["googleOAuth2Api"]["id"] == rn.CRED_PLACEHOLDER


def test_template_holds_placeholders_not_real_ids():
    text = json.dumps(TEMPLATE)
    assert text.count(rn.SHEET_PLACEHOLDER) == 1
    assert not re.search(r"spreadsheets/[A-Za-z0-9_-]{30,}", text)


def test_row_is_written_before_the_email():
    targets = [c["node"] for c in TEMPLATE["connections"]["Shape tracking row"]["main"][0]]
    assert targets == ["Add tracking row", "Get owner inbox"]
    assert NODES["Add tracking row"]["position"][1] < NODES["Get owner inbox"]["position"][1]
    chain = TEMPLATE["connections"]
    assert chain["Get owner inbox"]["main"][0][0]["node"] == "Build owner email"
    assert chain["Build owner email"]["main"][0][0]["node"] == "Send owner email"


def test_tracking_columns_stay_in_step_across_set_node_append_body_readme_and_tracker():
    set_keys = re.findall(r'^\s*"(\w+)":', NODES["Shape tracking row"]["parameters"]["jsonOutput"], re.M)
    assert set_keys == COLUMNS
    append = NODES["Add tracking row"]["parameters"]["jsonBody"]
    assert re.findall(r"\$json\.(\w+)", append) == COLUMNS
    readme = (REPO / "slice/README.md").read_text(encoding="utf-8")
    line = next(l for l in readme.splitlines() if l.startswith("`written_by`"))
    assert re.findall(r"`(\w+)`", line) == COLUMNS
    build = (REPO / "slice/n8n/BUILD.md").read_text(encoding="utf-8")
    assert re.findall(r'"stringValue": "(\w+)"', build) == COLUMNS


def test_code_node_is_the_repo_file_and_recipient_never_comes_from_the_payload():
    node = NODES["Build owner email"]
    assert node["parameters"]["jsCode"] == JS
    assert node["parameters"]["mode"] == "runOnceForEachItem"
    assert "$input.item.json.email" in JS
    assert not re.search(r"body\.(to|email|owner_email|recipient)\b", JS)
    assert "@" not in JS.replace("'@'", "").replace("lastIndexOf('@')", "").replace("includes('@')", "")


def _run_js(inbox, row, lead):
    harness = (
        "const $input = { item: { json: %s } };\n"
        "const $ = (name) => ({ item: { json: name === 'Shape tracking row' ? %s : { body: %s } } });\n"
        "const result = (function () {\n%s\n})();\n"
        "console.log(JSON.stringify(result));\n"
    ) % (json.dumps({"email": inbox}), json.dumps(row), json.dumps(lead), JS)
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["json"]


def _decode(raw):
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_owner_email_decodes_to_the_plus_address_with_the_lead():
    lead = json.loads((REPO / "slice/approved_leads.json").read_text())["leads"][0]
    row = {c: lead.get(c, "") for c in COLUMNS}
    row.update(written_by="n8n", run_id="slice-n8n-20261123T020000Z-L-0001")
    out = _run_js("owner@example.com", row, lead)
    mime = _decode(out["raw"])
    assert mime.startswith("To: owner+gtm-slice@example.com\r\n")
    assert "Subject: Approved lead for Enterprise sales ANZ: Northwind Freight (high)\r\n" in mime
    assert "Run: slice-n8n-20261123T020000Z-L-0001" in mime
    assert "Made-up demo data." in mime


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_owner_email_encodes_non_ascii_subjects():
    row = {c: "x" for c in COLUMNS}
    row.update(company_name="Café Müller Logistik", owner_team="Mid-market sales", priority="low")
    out = _run_js("owner@example.com", row, {"industry": "x", "enquiry": "x", "reason": "x"})
    mime = _decode(out["raw"])
    subject_line = next(l for l in mime.split("\r\n") if l.startswith("Subject: "))
    assert subject_line.startswith("Subject: =?UTF-8?B?")
    encoded = subject_line[len("Subject: =?UTF-8?B?"):-2]
    assert base64.b64decode(encoded).decode("utf-8") == "Approved lead for Mid-market sales: Café Müller Logistik (low)"
    assert "Café Müller Logistik (x) is approved" in mime


IDS = {"GOOGLE_CREDENTIAL_ID": "CRED123", "SLICE_KEY_CREDENTIAL_ID": "KEY456"}


def test_render_fills_every_placeholder_without_touching_the_template():
    before = json.dumps(TEMPLATE)
    wf = rn.render(TEMPLATE, "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd", IDS)
    text = json.dumps(wf)
    assert rn.SHEET_PLACEHOLDER not in text
    assert not any(ph in text for ph in rn.CREDENTIALS)
    assert '"id": "KEY456"' in text and '"id": "CRED123"' in text
    assert "/spreadsheets/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd/values/" in text
    assert json.dumps(TEMPLATE) == before


@pytest.mark.parametrize("tracker,ids", [
    ("", IDS),
    ("short", IDS),
    ("1AbCdEfGhIjKlMnOpQrStUvWxYz", {"GOOGLE_CREDENTIAL_ID": "CRED123"}),
    ("1AbCdEfGhIjKlMnOpQrStUvWxYz", {"GOOGLE_CREDENTIAL_ID": "", "SLICE_KEY_CREDENTIAL_ID": "KEY456"}),
])
def test_render_refuses_missing_values(tracker, ids):
    with pytest.raises(rn.ConfigError):
        rn.render(TEMPLATE, tracker, ids)


def test_update_live_replaces_by_name_then_publishes():
    calls = []

    class R:
        def __init__(self, data=None):
            self._data = data or {}

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class S:
        def get(self, url, **kw):
            calls.append(("GET", url, kw.get("params")))
            return R({"data": [{"id": "WF1", "name": TEMPLATE["name"]}]})

        def put(self, url, **kw):
            calls.append(("PUT", url, sorted(kw["json"])))
            return R()

        def post(self, url, **kw):
            calls.append(("POST", url, None))
            return R()

    wf = rn.render(TEMPLATE, "1AbCdEfGhIjKlMnOpQrStUvWxYz", IDS)
    assert rn.update_live("http://localhost:5678", "k", wf, session=S()) == "WF1"
    assert [c[0] for c in calls] == ["GET", "PUT", "POST"]
    assert calls[1] == ("PUT", "http://localhost:5678/api/v1/workflows/WF1", ["connections", "name", "nodes", "settings"])
    assert calls[2][1].endswith("/workflows/WF1/activate")


def test_find_credential_id_needs_exactly_one_match():
    class R:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": self._data}

    one = [{"id": "A1", "name": rn.CRED_NAME, "type": rn.CRED_TYPE}, {"id": "B2", "name": "Other", "type": "x"}]
    assert rn.find_credential_id("http://localhost:5678", "k", get=lambda *a, **k: R(one)) == "A1"
    with pytest.raises(rn.ConfigError):
        rn.find_credential_id("http://localhost:5678", "k", get=lambda *a, **k: R(one + one))
