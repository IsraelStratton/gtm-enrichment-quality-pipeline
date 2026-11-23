"""Tests for the cleaned Make blueprint and the scrubber that made it."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import scrub_make_blueprint as smb  # noqa: E402

BP = json.loads((REPO / "slice/make/slice-scenario.blueprint.json").read_text(encoding="utf-8"))
FLOW = BP["flow"]
COLUMNS = [
    "written_by", "run_id", "lead_id", "company_name", "domain", "route", "priority",
    "owner_team", "decision", "approved_by", "approved_at", "sent_at", "received_at",
]


def test_five_modules_in_guide_order():
    assert [m["module"] for m in FLOW] == [
        "gateway:CustomWebHook", "http:MakeRequest", "http:MakeRequest",
        "util:ComposeTransformer", "http:MakeRequest",
    ]
    assert [m["id"] for m in FLOW] == [1, 2, 3, 4, 5]


def test_http_modules_use_oauth_and_only_three_google_hosts():
    for m in FLOW:
        if m["module"] == "http:MakeRequest":
            assert m["parameters"]["oAuthAccount"] == "MAKE_CONNECTION_ID"
            assert urlsplit(m["mapper"]["url"]).hostname in {
                "sheets.googleapis.com", "www.googleapis.com", "gmail.googleapis.com"}


def test_private_identifiers_are_placeholders():
    text = json.dumps(BP)
    assert FLOW[0]["parameters"]["hook"] == "MAKE_HOOK_ID"
    assert "/spreadsheets/SPREADSHEET_ID/" in FLOW[1]["mapper"]["url"]
    assert not re.search(r"spreadsheets/[A-Za-z0-9_-]{30,}", text)
    assert not smb.EMAIL.search(text) and not smb.HOOK_URL.search(text)


def test_row_columns_match_the_tracker_and_make_writes_its_own_name():
    body = FLOW[1]["mapper"]["jsonStringBodyContent"]
    values = json.loads(re.sub(r"\{\{[^}]*\}\}", "x", body))["values"][0]
    assert len(values) == len(COLUMNS)
    assert body.startswith('{"values":[["make",')
    mapped = re.findall(r"\{\{1\.(\w+)\}\}", body)
    assert mapped == COLUMNS[1:-1]
    assert body.rstrip().endswith('"{{now}}"]]}')


def test_email_recipient_comes_from_google_not_the_payload():
    mime = FLOW[3]["mapper"]["value"]
    assert mime.startswith('To: {{replace(3.data.email; "@"; "+gtm-slice@")}}')
    assert not re.search(r"\{\{1\.(to|email|owner_email|recipient)\}\}", mime)
    assert "base64(4.value)" in FLOW[4]["mapper"]["jsonStringBodyContent"]


def test_scrubber_replaces_ids_and_refuses_private_data():
    raw = {"flow": [{"parameters": {"hook": 123, "oAuthAccount": "456"},
                     "mapper": {"url": "https://sheets.googleapis.com/v4/spreadsheets/1AbCdEfGhIjKlMnOpQrStUvWxYz012/values"}}]}
    out = smb.clean(raw)
    assert out["flow"][0]["parameters"] == {"hook": "MAKE_HOOK_ID", "oAuthAccount": "MAKE_CONNECTION_ID"}
    assert out["flow"][0]["mapper"]["url"].endswith("/spreadsheets/SPREADSHEET_ID/values")
    at = "@"
    with pytest.raises(smb.Refused):
        smb.clean({"note": "owner" + at + "gmail.com"})
    with pytest.raises(smb.Refused):
        smb.clean({"url": "https://hook.eu2.make.com/abcdef123456"})
