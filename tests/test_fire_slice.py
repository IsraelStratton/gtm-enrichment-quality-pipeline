"""Tests for scripts/fire_slice.py and the slice sample data. No network."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fire_slice as fs  # noqa: E402

NOW = datetime(2026, 11, 23, 1, 22, 3, 456000, tzinfo=timezone.utc)
REQUIRED = {
    "lead_id", "company_name", "domain", "industry", "employee_count", "hq_country",
    "enquiry", "intent", "priority", "route", "owner_team", "reason",
    "decision", "approved_by", "approved_at",
}


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


def test_sample_leads_have_every_field():
    leads = fs.load_leads()
    assert len(leads) == 3
    for lead in leads:
        assert REQUIRED <= set(lead), lead["lead_id"]
        assert lead["decision"] in {"approved", "changed"}


def test_sample_leads_are_company_level_and_made_up():
    leads = fs.load_leads()
    for lead in leads:
        assert lead["domain"].endswith(".example"), lead["domain"]
        assert re.fullmatch(r"reviewer-\d{2}", lead["approved_by"])
    text = fs.LEADS_FILE.read_text(encoding="utf-8")
    assert "@" not in text, "no email addresses in slice data"
    assert not re.search(r"\+?\d[\d ()-]{7,}\d", text.replace("2026-11-23", "")), "no phone numbers"


def test_payload_adds_run_id_target_and_sent_at():
    lead = fs.load_leads()[0]
    p = fs.build_payload(lead, "make", NOW)
    assert p["event"] == "lead.approved"
    assert p["target"] == "make"
    assert p["run_id"] == "slice-make-20261123T012203Z-L-0001"
    assert p["sent_at"] == "2026-11-23T01:22:03.456Z"
    assert p["company_name"] == lead["company_name"]


def test_payload_never_carries_a_recipient():
    """The owner's address lives in each tool, so a payload cannot redirect the email."""
    for lead in fs.load_leads():
        p = fs.build_payload(lead, "n8n", NOW)
        assert not any(k in p for k in ("to", "email", "owner_email", "recipient"))


def test_pick_lead_by_id_and_default():
    leads = fs.load_leads()
    assert fs.pick_lead(leads, None)["lead_id"] == "L-0001"
    assert fs.pick_lead(leads, "L-0003")["company_name"] == "Copperleaf Energy"
    with pytest.raises(fs.ConfigError):
        fs.pick_lead(leads, "L-9999")


def test_n8n_urls_default_to_localhost():
    assert fs.resolve_url("n8n", None, {}, test=True) == "http://localhost:5678/webhook-test/gtm-v2-approved-lead"
    assert fs.resolve_url("n8n", None, {}, test=False) == "http://localhost:5678/webhook/gtm-v2-approved-lead"
    assert fs.resolve_url("n8n", None, {"N8N_BASE_URL": "http://n8n.local:5678/"}, test=False) == (
        "http://n8n.local:5678/webhook/gtm-v2-approved-lead"
    )


def test_make_and_zapier_urls_come_from_env_or_cli():
    env = {"SLICE_URL_MAKE": "https://hook.eu2.make.com/abc123secret"}
    assert fs.resolve_url("make", None, env, test=False) == env["SLICE_URL_MAKE"]
    assert fs.resolve_url("zapier", "https://hooks.zapier.com/x", {}, test=False) == "https://hooks.zapier.com/x"
    with pytest.raises(fs.ConfigError, match="SLICE_URL_ZAPIER"):
        fs.resolve_url("zapier", None, {}, test=False)


def test_mask_url_hides_remote_tokens_but_not_localhost():
    assert fs.mask_url("https://hook.eu2.make.com/abcdefghijklmnop") == "https://hook.eu2.make.com/...mnop"
    local = "http://localhost:5678/webhook/gtm-v2-approved-lead"
    assert fs.mask_url(local) == local


def test_main_pass_and_fail_exit_codes(capsys):
    ok = lambda url, json, timeout: FakeResponse(200, '{"message":"Workflow was started"}')  # noqa: E731
    bad = lambda url, json, timeout: FakeResponse(404, "not registered")  # noqa: E731
    assert fs.main(["--target", "n8n", "--test"], post=ok) == 0
    assert "PASS HTTP 200" in capsys.readouterr().out
    assert fs.main(["--target", "n8n", "--test"], post=bad) == 1
    assert "FAIL HTTP 404" in capsys.readouterr().out


def test_main_config_error_and_dry_run(capsys, monkeypatch):
    monkeypatch.delenv("SLICE_URL_MAKE", raising=False)
    monkeypatch.setattr(fs, "load_dotenv", lambda *a, **k: None)
    assert fs.main(["--target", "make"]) == 2
    assert "SLICE_URL_MAKE" in capsys.readouterr().out
    assert fs.main(["--target", "zapier", "--dry-run", "--lead", "L-0002"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["lead_id"] == "L-0002" and printed["target"] == "zapier"
