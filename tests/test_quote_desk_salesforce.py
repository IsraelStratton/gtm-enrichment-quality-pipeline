"""Chapter 5, the Salesforce side of the quote desk: the setup file, the seed plan, the org check's
rules and the run check, all without the org (fakes stand in for Salesforce and the log)."""
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import check_desk_run as check  # noqa: E402
import n8n_publish_routing as publish  # noqa: E402
import salesforce_quote_desk_check as org  # noqa: E402
import seed_quotes as seed  # noqa: E402
from salesforce_client import LOGINS, ConfigError, settings_from_env  # noqa: E402

SETUP = json.loads((REPO / "salesforce/quote-desk-setup.json").read_text(encoding="utf-8"))
CASES = json.loads((REPO / "skins/quote-desk/cases.json").read_text(encoding="utf-8"))["cases"]
GUIDE = (REPO / "docs/v2/chapter-5-build.md").read_text(encoding="utf-8")


def test_the_guide_is_written_from_the_setup_file():
    for f in SETUP["custom_fields"]:
        assert f"`{f['api_name'].removesuffix('__c')}`" in GUIDE and f["label"] in GUIDE
    for value in (SETUP["permission_set"]["label"], SETUP["permission_set"]["api_name"], SETUP["desk_profile"]["label"],
                  SETUP["desk_profile"]["cloned_from"], SETUP["external_client_app"]["name"], SETUP["n8n_credential"]["name"],
                  SETUP["sharing"]["opportunity_sharing_rule"]["label"], SETUP["opportunity_name_prefix"], SETUP["admin_cli_alias"]):
        assert value in GUIDE, value
    for key in SETUP["env_keys"]:
        assert key in GUIDE


def test_the_desk_has_its_own_login_and_never_the_routing_one(tmp_path):
    assert LOGINS["desk"] == tuple(SETUP["env_keys"])
    env = tmp_path / ".env"
    env.write_text("SALESFORCE_DOMAIN=org-1.develop.my.salesforce.com\nSALESFORCE_CLIENT_ID=routing-id\nSALESFORCE_CLIENT_SECRET=routing-secret\n")
    with pytest.raises(ConfigError, match="SALESFORCE_DESK_CLIENT_ID, SALESFORCE_DESK_CLIENT_SECRET"):
        settings_from_env(env, "desk")
    env.write_text(env.read_text() + "SALESFORCE_DESK_CLIENT_ID=desk-id\nSALESFORCE_DESK_CLIENT_SECRET=desk-secret\n")
    assert settings_from_env(env, "desk")["client_id"] == "desk-id"
    assert settings_from_env(env, "routing")["client_id"] == "routing-id"


def test_the_permission_set_grants_no_create_or_delete_and_edits_three_fields():
    ps = SETUP["permission_set"]
    assert ps["object_permissions"] == {"Quote": ["Read", "Edit"], "Opportunity": ["Read"], "Account": ["Read"], "Product2": ["Read"], "Pricebook2": ["Read"]}
    assert set(ps["object_permissions_never"]) == {"Create", "Delete", "View All", "Modify All"}
    assert ps["field_permissions_edit"] == ["Status", "GTM_Desk_Reason__c", "GTM_Desk_Stamp__c"]
    assert {f["api_name"] for f in SETUP["custom_fields"] if f["desk_access"] == "edit"} == {"GTM_Desk_Reason__c", "GTM_Desk_Stamp__c"}


def test_the_seed_plan_writes_only_made_up_company_data_for_the_demo_cases():
    items = seed.plan(seed.demo_cases(), date(2026, 11, 24))
    assert [i["case_id"] for i in items] == [c["case_id"] for c in CASES if c["demo"]]
    for it in items:
        assert it["account_domain"].endswith(".example") and it["opportunity"]["Name"].startswith(SETUP["opportunity_name_prefix"])
        assert it["quote"]["Status"] == "Needs Review" and it["quote"]["GTM_Desk_Stamp__c"] is None
        assert not set(it["quote"]) & {"ContactId", "Email", "Phone", "Fax"}
        assert set(it["quote"]) <= {f["api_name"] for f in SETUP["custom_fields"]} | {"Name", "Status", "ExpirationDate", "BillingCountry"}
        assert all(l["product"] in seed.PRODUCTS for l in it["lines"])
    q9 = next(i for i in items if i["case_id"] == "Q-0009")
    assert q9["quote"]["ExpirationDate"] is None and q9["quote"]["GTM_Payment_Terms_Days__c"] is None
    q3 = next(i for i in items if i["case_id"] == "Q-0003")
    assert q3["quote"]["ExpirationDate"] == "2027-01-23" and q3["opportunity"]["CloseDate"] == "2027-01-08"
    assert seed.soql_text("O'Brien") == "'O\\'Brien'"


class FakeCli:
    """Stands in for the sf CLI: `org display`, then each `api request rest` call with its body on stdin."""

    def __init__(self, replies, connected=True):
        self.replies, self.connected, self.calls = list(replies), connected, []

    def __call__(self, args, input=None, **kw):
        class Out:
            pass

        o = Out()
        if args[1:3] == ["org", "display"]:
            o.stdout = json.dumps({"status": 0, "result": {"connectedStatus": "Connected", "username": "admin@x.example"} if self.connected else {}})
        else:
            self.calls.append((args, input))
            o.stdout = self.replies.pop(0)
        return o


def test_the_seed_stops_without_a_live_cli_login(monkeypatch):
    monkeypatch.setattr(seed.shutil, "which", lambda name: "/usr/bin/sf")
    with pytest.raises(ConfigError, match="sf org login web --alias gtm-v2-admin"):
        seed.Admin("gtm-v2-admin", runner=FakeCli([], connected=False))


def test_the_admin_calls_go_through_the_cli_with_the_body_on_stdin_and_no_token(monkeypatch):
    monkeypatch.setattr(seed.shutil, "which", lambda name: "/usr/bin/sf")
    cli = FakeCli(["HTTP/1.1 201\ncontent-type: application/json\nserver: sfdcedge\n{\n    \"id\": \"01t1\",\n    \"success\": true\n}",
                   'HTTP/1.1 400\n\n[{"errorCode": "INVALID_FIELD", "message": "No such column"}]'])
    admin = seed.Admin("gtm-v2-admin", runner=cli)
    assert admin.call("POST", "/sobjects/Product2", {"Name": "x"}) == {"id": "01t1", "success": True}
    args, stdin = cli.calls[0]
    assert args[:4] == ["/usr/bin/sf", "api", "request", "rest"] and "--body" in args and args[args.index("--body") + 1] == "-"
    assert json.loads(stdin) == {"Name": "x"} and not any("Bearer" in a or "token" in a.lower() for a in args)
    with pytest.raises(seed.SalesforceError, match="INVALID_FIELD: No such column"):
        admin.call("GET", "/query?q=x")


# ---------------------------------------------------------------- the org check's rules


def describe_quote(**over):
    fields = []
    for f in SETUP["custom_fields"]:
        d = {"name": f["api_name"], "type": f["describe_type"], "updateable": f["desk_access"] == "edit"}
        if "length" in f:
            d["length"] = f["length"]
        if "precision" in f:
            d.update(precision=f["precision"], scale=f["scale"])
        if f.get("external_id"):
            d.update(externalId=True, unique=True)
        fields.append(d)
    fields.append({"name": "Status", "type": "picklist", "updateable": True,
                   "picklistValues": [{"value": v, "active": True} for v in ("Draft", "Needs Review", "In Review", "Approved", "Rejected")]})
    d = {"queryable": True, "updateable": True, "createable": False, "deletable": False, "fields": fields}
    d.update(over)
    return d


def test_a_quote_set_up_as_specified_passes_the_field_checks():
    assert all(ok for ok, _ in org.check_fields(describe_quote()))
    assert org.check_quote_object(describe_quote())[0]


@pytest.mark.parametrize("change, words", [
    (lambda d: d["fields"].__setitem__(4, dict(d["fields"][4], updateable=True)), "the desk can edit it"),
    (lambda d: d["fields"].append({"name": "Email", "type": "email"}), "but it sees Email"),
    (lambda d: d["fields"].pop(0), "GTM_Case_Id__c is missing"),
    (lambda d: d["fields"][-1].__setitem__("picklistValues", [{"value": "Draft", "active": True}]), "offers none of"),
])
def test_the_field_checks_fail_on_wider_reach_or_a_missing_field(change, words):
    d = describe_quote()
    change(d)
    failed = [text for ok, text in org.check_fields(d) if not ok]
    assert failed and any(words in t for t in failed)


def test_a_desk_that_can_create_or_delete_quotes_fails():
    assert not org.check_quote_object(describe_quote(createable=True))[0]
    assert not org.check_quote_object(describe_quote(deletable=True))[0]


def test_the_other_objects_must_be_read_only_or_out_of_reach():
    ro = {"queryable": True, "createable": False, "updateable": False, "deletable": False}
    good = {"Opportunity": ro, "Account": ro, "Product2": ro, "Pricebook2": ro, "PricebookEntry": ro, "QuoteLineItem": ro,
            "Lead": None, "Contact": None, "Case": None}
    assert all(ok for ok, _ in org.check_other_objects(good))
    bad = dict(good, Opportunity=dict(ro, updateable=True), Contact={"queryable": True})
    assert [t for ok, t in org.check_other_objects(bad) if not ok] == [
        "Opportunity: read only (create False, edit True, delete False)", "Contact: no access (the desk has rights on it)"]


def test_the_sign_in_must_be_api_only_and_the_desk_user():
    ident = {"display_name": "GTM Quote Desk", "username": "gtm-v2-quote-desk-ab12@example.com", "active": True}
    assert all(ok for ok, _ in org.check_sign_in({"scope": "api"}, ident, "gtm-v2-quote-desk-ab12@example.com"))
    assert not org.check_sign_in({"scope": "api refresh_token"}, ident, None)[0][0]
    assert not org.check_sign_in({"scope": "api"}, dict(ident, display_name="GTM Integration"), None)[1][0]
    assert not org.check_sign_in({"scope": "api"}, ident, "gtm-v2-quote-desk-zz99@example.com")[1][0]


def test_the_queue_check_needs_every_demo_quote_with_its_lines():
    demo = [c for c in CASES if c["demo"]]
    recs = [{"GTM_Case_Id__c": c["case_id"], "Opportunity": {"Amount": 1, "CloseDate": "2027-01-01"}, "Account": {"Name": "x"},
             "QuoteLineItems": {"records": [{}] * len(c["lines"])}} for c in demo]
    assert all(ok for ok, _ in org.check_queue(recs))
    assert not org.check_queue(recs[1:])[0][0]


# ---------------------------------------------------------------- the run check


def record(**over):
    r = {"decision_id": "DQ-n8n9-01", "case_id": "Q-0003", "quote_id": "0Q0x", "design": "one_prompt", "model": "claude-haiku-5-5",
         "playbook_name": "quote-desk-playbook", "playbook_version": "1.0.0", "action": "approved", "approver": "reviewer-01",
         "decision_reason": "Three-year term.", "fix_needed": False, "crm_write_status": "written", "owner_message_status": "sent",
         "owner_message_id": "m1", "matches_proposal": True, "sf_status": "Approved"}
    r["stamp"] = (f"gtm-v2-desk {r['decision_id']} | one_prompt | claude-haiku-5-5 | quote-desk-playbook@1.0.0 | approved by reviewer-01 | 2026-11-24T05:00:00Z")
    r.update(over)
    return r


def test_a_clean_run_passes_the_log_checks():
    assert all(ok for ok, _ in check.check_log([record()]))


@pytest.mark.parametrize("over, words", [
    ({"action": None}, "0 of 1 quotes have a person's decision"),
    ({"approver": "someone else"}, "the stamp does not match"),
    ({"decision_reason": " "}, "0 of 1 decisions give the approver's reason"),
    ({"fix_needed": True}, "but Q-0003 was"),
    ({"crm_write_status": "failed", "crm_error": "locked"}, "0 of 1 decisions reached Salesforce"),
    ({"owner_message_id": None}, "0 of 1 owners of saved quotes were told"),
])
def test_the_log_checks_catch_each_fault(over, words):
    failed = [t for ok, t in check.check_log([record(**over)]) if not ok]
    assert any(words in t for t in failed), failed


def test_the_salesforce_check_compares_status_reason_and_stamp():
    r = record()

    class Fake:
        def __init__(self, q):
            self.q = q

        def data(self, path, ok_404=False):
            assert path.startswith("/sobjects/Quote/0Q0x?fields=")
            return self.q

    good = {"Status": "Approved", "GTM_Case_Id__c": "Q-0003", "GTM_Desk_Stamp__c": r["stamp"],
            "GTM_Desk_Reason__c": "Approved by reviewer-01: Three-year term. Rules broken: discount_over_10."}
    assert all(ok for ok, _ in check.check_salesforce([r], Fake(good)))
    assert not check.check_salesforce([r], Fake(dict(good, Status="Needs Review")))[-1][0]


def test_the_stamp_pattern_reads_a_real_stamp():
    m = check.STAMP.match(record()["stamp"])
    assert m and m["decision"] == "DQ-n8n9-01" and m["design"] == "one_prompt" and m["action"] == "approved"


def test_the_publish_script_knows_the_quote_desk():
    assert publish.TARGETS["quote_desk"]["form_path"] == "gtm-v2-quote-desk"
    assert publish.trigger_name("quote_desk") == "Start Quote Desk" and publish.trigger_name("hubspot") == "Upload CSV"
    wf = json.loads((REPO / "n8n/workflow-v2-quote-desk.json").read_text(encoding="utf-8"))
    body = publish.request_body(wf, None, "Start Quote Desk")
    assert re.match(r"^[0-9a-f-]{36}$", next(n for n in body["nodes"] if n["name"] == "Start Quote Desk")["webhookId"])


def test_the_cli_output_is_read_with_or_without_a_blank_line_after_the_headers():
    assert seed.Admin.parse("HTTP/1.1 204\ndate: x\n") == (204, None)
    assert seed.Admin.parse("HTTP/1.1 200\ndate: x\n\n{\"a\": 1}") == (200, {"a": 1})
    assert seed.Admin.parse("HTTP/1.1 200\ndate: x\n[\n  1\n]") == (200, [1])


# ---------------------------------------------------------------- the metadata (parts B to D) and the user (part E)

import build_quote_desk_metadata as meta  # noqa: E402
import make_desk_user  # noqa: E402

SRC = REPO / "salesforce/quote-desk/force-app/main/default"


def test_the_metadata_is_made_from_the_setup_file_and_up_to_date():
    assert meta.main(["--check"]) == 0
    for f in SETUP["custom_fields"]:
        text = (SRC / f"objects/Quote/fields/{f['api_name']}.field-meta.xml").read_text(encoding="utf-8")
        assert f"<label>{f['label']}</label>" in text and f"<description>{f['description']}</description>" in text
        kind = {"Text": "Text", "Number": "Number", "Text Area (Long)": "LongTextArea"}[f["setup_type"]]
        assert f"<type>{kind}</type>" in text


def test_the_permission_set_metadata_grants_exactly_the_desks_reach():
    text = (SRC / "permissionsets/GTM_v2_Quote_Desk.permissionset-meta.xml").read_text(encoding="utf-8")
    edits = re.findall(r"<editable>true</editable>\s*<field>([^<]+)</field>", text)
    assert sorted(edits) == ["Quote.GTM_Desk_Reason__c", "Quote.GTM_Desk_Stamp__c", "Quote.Status"]
    for never in ("Quote.Email", "Quote.Phone", "Quote.Fax", "Quote.ContactId"):
        assert never not in text
    assert "<license>" not in text and "<userPermissions>" not in text
    objects = {obj: body for body, obj in re.findall(r"<objectPermissions>([\s\S]*?)<object>(\w+)</object>", text)}
    assert sorted(objects) == ["Account", "Opportunity", "Pricebook2", "Product2", "Quote"]
    for obj, body in objects.items():
        on = set(re.findall(r"<(\w+)>true</\1>", body))
        assert on == ({"allowRead", "allowEdit"} if obj == "Quote" else {"allowRead"}), obj


def test_the_two_profile_files_are_partial_on_purpose():
    admin = (SRC / "profiles/Admin.profile-meta.xml").read_text(encoding="utf-8")
    assert set(re.findall(r"<field>([^<]+)</field>", admin)) == {f"Quote.{f['api_name']}" for f in SETUP["custom_fields"]}
    assert "<userPermissions>" not in admin and "<objectPermissions>" not in admin
    desk = (SRC / "profiles/GTM v2 API only.profile-meta.xml").read_text(encoding="utf-8")
    assert re.findall(r"<name>(\w+)</name>", desk) == ["ApiEnabled", "ApiUserOnly"] and "<fieldPermissions>" not in desk


def test_the_layout_gets_one_desk_section_however_often_it_is_built():
    layout = (SRC / "layouts/Quote-Quote Layout.layout-meta.xml").read_text(encoding="utf-8")
    again = meta.with_desk_section(layout)
    assert again == layout and layout.count("<label>GTM v2 quote desk</label>") == 1
    assert all(f"<field>{f['api_name']}</field>" in layout for f in SETUP["custom_fields"])


def test_the_desk_username_is_made_to_the_pattern_and_kept_out_of_the_repo(tmp_path):
    name = make_desk_user.new_username()
    assert re.match(SETUP["desk_user"]["username_pattern"], name)
    env, private = tmp_path / ".env", tmp_path / "private"
    env.write_text("SALESFORCE_DESK_USER=\nOTHER=1\n")
    make_desk_user.save_username(name, env, private)
    make_desk_user.save_username(name, env, private)
    assert f"SALESFORCE_DESK_USER={name}\n" in env.read_text() and env.read_text().count("SALESFORCE_DESK_USER") == 1
    assert private.read_text().count(name) == 1


def test_quote_lines_the_desk_could_change_fail_the_check():
    """Found 24/11/2026: once price books are readable, Salesforce lets a user who can edit a quote change its lines."""
    ro = {"queryable": True, "createable": False, "updateable": False, "deletable": False}
    seen = {n: ro for n in org.READ_ONLY_OBJECTS}
    seen["QuoteLineItem"] = {"queryable": True, "createable": True, "updateable": True, "deletable": True}
    failed = [t for ok, t in org.check_other_objects(seen) if not ok]
    assert failed == ["QuoteLineItem: read only (create True, edit True, delete True)"]
