"""Chapter 4: the Salesforce org check (scripts/salesforce_setup_check.py), the Salesforce side of
scripts/check_run.py, and the client's handling of .env. Fake Salesforce replies; no network."""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import check_run as cr  # noqa: E402
import salesforce_client as sc  # noqa: E402
import salesforce_setup_check as chk  # noqa: E402

SETUP = json.loads((REPO / "salesforce/setup.json").read_text(encoding="utf-8"))


def field_from_spec(spec, **over):
    f = {"name": spec["api_name"], "type": spec["describe_type"], "custom": True, "createable": True, "updateable": True,
         "length": spec.get("length", 0), "precision": spec.get("precision", 0), "scale": spec.get("scale", 0),
         "externalId": spec.get("external_id", False), "unique": spec.get("unique", False),
         "caseSensitive": spec.get("case_sensitive", False), "restrictedPicklist": spec.get("restricted", False),
         "picklistValues": [{"value": v["api_name"], "label": v["label"], "active": True} for v in spec.get("values", [])]}
    f.update(over)
    return f


def good_account():
    fields = [field_from_spec(s) for s in SETUP["custom_fields"]]
    fields += [{"name": n, "type": "string", "custom": False, "createable": True, "updateable": True} for n in SETUP["standard_fields_written"]]
    fields += [{"name": "Other_Field__c", "type": "string", "custom": True, "createable": False, "updateable": False},
               {"name": "Phone", "type": "phone", "custom": False, "createable": False, "updateable": False}]
    return {"name": "Account", "queryable": True, "createable": True, "updateable": True, "deletable": False, "fields": fields}


def good_global():
    objs = [{"name": "Account", "createable": True, "updateable": True, "deletable": False},
            {"name": "User", "createable": True, "updateable": True, "deletable": False}]
    objs += [{"name": n, "createable": False, "updateable": False, "deletable": False} for n in chk.CORE_OBJECTS]
    return {"sobjects": objs}


def good_user():
    """What the integration user's describe of User looks like: no ProfileId at all."""
    return {"name": "User", "createable": True, "updateable": True, "deletable": False,
            "fields": [{"name": n, "createable": True} for n in ("Username", "LastName", "Email", "Alias")]}


GOOD_IDENTITY = {"user_id": "005000000000001AAA", "username": "gtm-v2-integration-ab12@example.com",
                 "display_name": "GTM Integration", "active": True, "user_type": "STANDARD"}
SEES_NOTHING = {n: False for n in chk.SETUP_OBJECTS}


def passed(results):
    return all(ok for ok, _ in results)


# ------------------------------------------------------------------ the org check


def test_an_org_set_up_as_specified_passes():
    assert passed(chk.check_fields(good_account()))
    reach, record = chk.check_reach(good_account(), good_global(), good_user())
    assert passed(reach) and record == {"create_or_edit": [], "delete": []}


def test_the_sign_in_must_be_api_scope_only_and_the_integration_user():
    assert passed(chk.check_sign_in({"scope": "api"}, GOOD_IDENTITY, SEES_NOTHING))
    assert not passed(chk.check_sign_in({"scope": "api full refresh_token"}, GOOD_IDENTITY, SEES_NOTHING))
    assert not passed(chk.check_sign_in({"scope": "api"}, None, SEES_NOTHING))
    assert not passed(chk.check_sign_in({"scope": "api"}, GOOD_IDENTITY, None))


@pytest.mark.parametrize("change, words", [
    ({"display_name": "Israel Admin"}, "runs as the integration user"),
    ({"username": "someone@other.example"}, "runs as the integration user"),
    ({"active": False}, "not active"),
])
def test_a_sign_in_as_anyone_else_fails(change, words):
    results = chk.check_sign_in({"scope": "api"}, {**GOOD_IDENTITY, **change}, SEES_NOTHING)
    assert any(not ok and words in text for ok, text in results), results


def test_a_login_that_can_see_profiles_is_not_the_api_only_user():
    results = chk.check_sign_in({"scope": "api"}, GOOD_IDENTITY, {"Profile": True, "PermissionSet": False})
    assert any(not ok and "but can see: Profile" in text for ok, text in results), results


def test_the_username_is_shown_without_its_random_part():
    text = " ".join(t for _, t in chk.check_sign_in({"scope": "api"}, GOOD_IDENTITY, SEES_NOTHING))
    assert "gtm-v2-integration-…@example.com" in text and "ab12" not in text


def test_the_api_version_must_be_offered():
    assert chk.check_version([{"version": "63.0"}, {"version": "64.0"}, {"version": "66.0"}])[0]
    assert not chk.check_version([{"version": "62.0"}, {"version": "63.0"}])[0]


@pytest.mark.parametrize("field, change, words", [
    ("GTM_Route__c", {"restrictedPicklist": False}, "not restricted"),
    ("GTM_Route__c", {"picklistValues": [{"value": "smb", "label": "SMB sales", "active": True}]}, "values are"),
    ("Clay_Domain_Key__c", {"externalId": False}, "externalId is False"),
    ("Clay_Domain_Key__c", {"unique": False}, "unique is False"),
    ("GTM_Decision_Stamp__c", {"length": 80}, "length is 80"),
    ("GTM_Routing_Confidence__c", {"scale": 2}, "precision and scale"),
    ("GTM_Routing_Reason__c", {"type": "string"}, "type is string"),
    ("GTM_Priority__c", {"updateable": False}, "cannot create and edit"),
])
def test_a_field_set_up_differently_fails_with_the_reason(field, change, words):
    account = good_account()
    for f in account["fields"]:
        if f["name"] == field:
            f.update(change)
    results = chk.check_fields(account)
    assert any(not ok and words in text for ok, text in results), results


def test_a_missing_field_fails():
    account = good_account()
    account["fields"] = [f for f in account["fields"] if f["name"] != "GTM_Decision_Stamp__c"]
    assert any(not ok and "missing on Account" in text for ok, text in chk.check_fields(account))


def test_picklist_labels_left_as_codes_pass_with_a_note():
    account = good_account()
    for f in account["fields"]:
        if f["name"] == "GTM_Route__c":
            for v in f["picklistValues"]:
                v["label"] = v["value"]
    results = chk.check_fields(account)
    assert passed(results) and any("labels still the codes" in text for _, text in results)


@pytest.mark.parametrize("change, words", [
    (lambda a, g: a.update(deletable=True), "Accounts: cannot delete"),
    (lambda a, g: next(o for o in g["sobjects"] if o["name"] == "Contact").update(createable=True), "but can: Contact"),
    (lambda a, g: next(o for o in g["sobjects"] if o["name"] == "Opportunity").update(deletable=True), "but can delete: Opportunity"),
    (lambda a, g: g["sobjects"].append({"name": "Invoice__c", "custom": True, "createable": False, "updateable": True, "deletable": False}),
     "but can: Invoice__c"),
    (lambda a, g: g["sobjects"].append({"name": "Invoice__c", "custom": True, "createable": False, "updateable": False, "deletable": True}),
     "but can delete: Invoice__c"),
    (lambda a, g: next(o for o in g["sobjects"] if o["name"] == "User").update(deletable=True), "but can delete: User"),
    (lambda a, g: next(f for f in a["fields"] if f["name"] == "Other_Field__c").update(updateable=True), "but can edit: Other_Field__c"),
])
def test_any_wider_reach_fails(change, words):
    account, objects = good_account(), good_global()
    change(account, objects)
    reach, _ = chk.check_reach(account, objects, good_user())
    assert any(not ok and words in text for ok, text in reach), reach


@pytest.mark.parametrize("change, words", [
    (lambda u: u["fields"].append({"name": "ProfileId", "createable": True}), "but it can set ProfileId"),
    (lambda u: u.update(deletable=True), "but it can delete them"),
])
def test_a_login_that_could_make_or_remove_users_fails(change, words):
    user = good_user()
    change(user)
    reach, _ = chk.check_reach(good_account(), good_global(), user)
    assert any(not ok and words in text for ok, text in reach), reach


def test_salesforce_own_item_rights_are_listed_for_the_record_not_failed():
    """Every Salesforce user may post, upload files, keep notes and list views, and delete their own
    ones. Describe marks those objects createable and deletable; no permission set controls them."""
    objects = good_global()
    objects["sobjects"] += [{"name": "ContentVersion", "createable": True, "updateable": False, "deletable": False},
                            {"name": "FeedItem", "createable": True, "updateable": True, "deletable": True},
                            {"name": "AccountShare", "createable": True, "updateable": True, "deletable": True},
                            {"name": "AuthSession", "createable": False, "updateable": False, "deletable": True}]
    reach, record = chk.check_reach(good_account(), objects, good_user())
    assert passed(reach), reach
    assert record == {"create_or_edit": ["AccountShare", "ContentVersion", "FeedItem"],
                      "delete": ["AccountShare", "AuthSession", "FeedItem"]}


def test_the_check_reads_the_fields_the_engine_writes():
    assert chk.WRITTEN == [f["api_name"] for f in SETUP["custom_fields"]] + list(SETUP["standard_fields_written"])


# ------------------------------------------------------------------ the client and .env


def test_missing_env_values_are_named_not_shown(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SALESFORCE_DOMAIN=acme.develop.my.salesforce.com\nSALESFORCE_CLIENT_ID=\n", encoding="utf-8")
    with pytest.raises(sc.ConfigError, match="SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET"):
        sc.settings_from_env(env)


def test_the_domain_must_be_a_my_domain_host(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SALESFORCE_DOMAIN=https://login.salesforce.com\nSALESFORCE_CLIENT_ID=a\nSALESFORCE_CLIENT_SECRET=b\n", encoding="utf-8")
    with pytest.raises(sc.ConfigError, match="My Domain"):
        sc.settings_from_env(env)
    env.write_text("SALESFORCE_DOMAIN=https://Acme-Dev-Ed.develop.my.salesforce.com/\nSALESFORCE_CLIENT_ID=a\nSALESFORCE_CLIENT_SECRET=b\n", encoding="utf-8")
    assert sc.settings_from_env(env)["host"] == "acme-dev-ed.develop.my.salesforce.com"


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.replies.pop(0)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.replies.pop(0)


def test_sign_in_uses_client_credentials_and_never_returns_the_token():
    session = FakeSession([FakeResponse(200, {"access_token": "SECRET-TOKEN", "scope": "api", "token_type": "Bearer",
                                              "id": "https://login.salesforce.com/id/00Dxx/005xx0000012345"})])
    info = sc.SalesforceClient("acme.my.salesforce.com", "the-id", "the-secret", session).sign_in()
    assert info == {"scope": "api", "user_id": "005xx0000012345", "token_type": "Bearer"}
    method, url, kw = session.calls[0]
    assert url == "https://acme.my.salesforce.com/services/oauth2/token" and kw["data"]["grant_type"] == "client_credentials"


def test_a_refused_sign_in_names_salesforce_error_not_the_secret():
    session = FakeSession([FakeResponse(400, {"error": "invalid_grant", "error_description": "no client credentials user enabled"})])
    with pytest.raises(sc.SalesforceError) as e:
        sc.SalesforceClient("acme.my.salesforce.com", "the-id", "the-secret", session).sign_in()
    assert "invalid_grant: no client credentials user enabled" in str(e.value) and "the-secret" not in str(e.value)


def test_identity_comes_from_the_identity_url_and_never_carries_the_token():
    token = {"access_token": "SECRET-TOKEN", "scope": "api", "token_type": "Bearer", "id": "https://login.salesforce.com/id/00Dxx/005xx0000012345"}
    who = {"user_id": "005xx0000012345", "organization_id": "00Dxx", "username": "gtm-v2-integration-ab12@example.com",
           "display_name": "GTM Integration", "active": True, "user_type": "STANDARD", "urls": {"rest": "..."}}
    session = FakeSession([FakeResponse(200, token), FakeResponse(200, who)])
    info = sc.SalesforceClient("acme.my.salesforce.com", "the-id", "the-secret", session).identity()
    assert info == {k: who[k] for k in ("user_id", "username", "display_name", "active", "user_type")}
    assert "SECRET-TOKEN" not in json.dumps(info)
    assert session.calls[1][1] == token["id"]


def test_an_object_this_login_cannot_see_reads_as_not_seen_and_other_errors_still_raise():
    token = {"access_token": "T", "scope": "api", "id": "https://login.salesforce.com/id/00Dxx/005xx"}
    not_supported = FakeResponse(400, [{"errorCode": "INVALID_TYPE", "message": "sObject type 'Profile' is not supported."}])
    client = sc.SalesforceClient("acme.my.salesforce.com", "i", "s", FakeSession([FakeResponse(200, token), not_supported]))
    assert client.can_query("Profile") is False
    client = sc.SalesforceClient("acme.my.salesforce.com", "i", "s", FakeSession([FakeResponse(200, token), FakeResponse(200, {"records": []})]))
    assert client.can_query("Profile") is True
    expired = FakeResponse(401, [{"errorCode": "INVALID_SESSION_ID", "message": "Session expired or invalid"}])
    client = sc.SalesforceClient("acme.my.salesforce.com", "i", "s", FakeSession([FakeResponse(200, token), expired]))
    with pytest.raises(sc.SalesforceError):
        client.can_query("Profile")


# ------------------------------------------------------------------ check_run --salesforce


def record(n, action, **over):
    r = {"decision_id": f"D-n8n9-{n:02d}", "lead_id": f"L-00{n:02d}", "domain": f"co{n}.example", "action": action,
         "chosen_route": "smb" if action != "rejected" else None, "chosen_priority": "low" if action != "rejected" else None,
         "stamp": f"gtm-v2 D-n8n9-{n:02d} | m | p@1.0.0 | {action} by r | 2026-11-24T01:00:00Z" if action != "rejected" else None,
         "crm_target": "salesforce", "crm_write_status": "written" if action != "rejected" else "not_written",
         "crm_record_id": f"001{n:015d}" if action != "rejected" else None}
    r.update(over)
    return r


class FakeSalesforce:
    def __init__(self, by_id=None, by_key=None):
        self.by_id, self.by_key = by_id or {}, by_key or {}

    def account(self, record_id, fields):
        return self.by_id.get(record_id)

    def account_by_key(self, domain, fields):
        return self.by_key.get(domain)


def as_account(r):
    return {"Clay_Domain_Key__c": r["domain"], "GTM_Route__c": r["chosen_route"], "GTM_Priority__c": r["chosen_priority"],
            "GTM_Routing_Status__c": r["action"], "GTM_Decision_Stamp__c": r["stamp"]}


def test_a_salesforce_run_whose_accounts_match_the_log_passes():
    recs = [record(1, "approved"), record(2, "changed"), record(3, "rejected")]
    fake = FakeSalesforce(by_id={r["crm_record_id"]: as_account(r) for r in recs if r["crm_record_id"]})
    results = cr.check_target(recs, "salesforce") + cr.check_salesforce(recs, fake)
    assert passed(results), results


def test_an_account_that_differs_from_the_log_fails():
    recs = [record(1, "approved")]
    acc = as_account(recs[0])
    acc["GTM_Route__c"] = "enterprise_anz"
    assert not passed(cr.check_salesforce(recs, FakeSalesforce(by_id={recs[0]["crm_record_id"]: acc})))


def test_a_rejected_row_carrying_the_run_stamp_fails():
    recs = [record(3, "rejected")]
    leaked = {"GTM_Decision_Stamp__c": "gtm-v2 D-n8n9-03 | m | p@1.0.0 | approved by r | 2026-11-24T01:00:00Z"}
    assert not passed(cr.check_salesforce(recs, FakeSalesforce(by_key={"co3.example": leaked})))


def test_a_run_that_wrote_to_hubspot_fails_the_salesforce_target_check():
    recs = [record(1, "approved", crm_target="hubspot")]
    ok, text = cr.check_target(recs, "salesforce")[0]
    assert not ok and "some went to hubspot" in text


def test_the_log_check_names_the_crm_the_writes_reached():
    recs = [dict(record(1, "approved"), model="m", playbook_name="p", playbook_version="1.0.0", approver="r",
                 proposed_route="smb", proposed_priority="low", crm_error=None)]
    assert any("writes reached Salesforce" in text for _, text in cr.check_log(recs))
