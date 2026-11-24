"""Chapter 5, the quote desk engine (engine/quotes.js) and its eval (scripts/quote_desk.py).

The playbook, the code rule check on the 20 labelled cases, the requests for the three designs,
the guard rails, the queue, the review, the stamps, the staff messages, and the grader and the
results file. Runs the JavaScript through engine/cli.js, the same path the eval uses. No network.
"""
import base64
import copy
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import quote_desk  # noqa: E402
from routing_engine import Engine, EngineError  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

PLAYBOOK = (REPO / "skins/quote-desk/quote-desk-playbook/SKILL.md").read_text(encoding="utf-8")
CASES_FILE = json.loads((REPO / "skins/quote-desk/cases.json").read_text(encoding="utf-8"))
CASES = {c["case_id"]: c for c in CASES_FILE["cases"]}
AS_OF = CASES_FILE["as_of"]
SETUP = json.loads((REPO / "salesforce/quote-desk-setup.json").read_text(encoding="utf-8"))
PRODUCTS = SETUP["products"]
MODEL = "claude-haiku-5-5"
INBOX = "desk.owner@example.com"
AI_RULES = {"commercial_terms", "legal_terms"}


@pytest.fixture(scope="module")
def eng():
    return Engine(module="quotes")


@pytest.fixture(scope="module")
def pb(eng):
    return eng.call("parseDeskPlaybook", PLAYBOOK)


@pytest.fixture(scope="module")
def prepared(eng, pb):
    ids = list(CASES)
    quotes = eng.batch([("caseToQuote", [CASES[i], PRODUCTS, AS_OF]) for i in ids])
    facts = eng.batch([("checkQuoteRules", [pb, q, AS_OF]) for q in quotes])
    return {i: (q, f) for i, q, f in zip(ids, quotes, facts)}


def answer(triage, stop="end_turn", tokens=(3000, 400)):
    return {"statusCode": 200, "headers": {"request-id": "req_test"},
            "body": {"model": MODEL, "stop_reason": stop, "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
                     "content": [{"type": "text", "text": json.dumps(triage)}]}}


def labelled_triage(case_id, **over):
    c = CASES[case_id]
    hostile = c["kind"] == "hostile"
    t = {
        "exceptions": [{"rule": r, "evidence": "as the figures show"} for r in c["expected"]["rules"]],
        "proposed_action": c["expected"]["action"],
        "reason": "The deciding rule and fact.",
        "approver_message": "A short note for the approver.",
        "customer_reply_draft": "Thank you for your time on this quote. We are finalising it and will be in touch shortly.\n\nKind regards,",
        "confidence": 0.45 if hostile else 0.9,
        "flags": list(c["expected"]["flags"]),
    }
    t.update(over)
    return t


def triage(eng, pb, prepared, case_id, design="one_prompt", **over):
    q, f = prepared[case_id]
    reply = eng.call("readDeskReply", pb, "triage", answer(labelled_triage(case_id, **over)))
    joined = eng.call("designFinal", design, {"triage": reply})
    ctx = {"decision_id": f"DQ-test-{case_id[-2:]}", "run_id": "test", "design": design, "model": MODEL, "calls": [], "handoffs": []}
    return eng.call("checkTriage", pb, q, f, joined["final"], joined["failure"], ctx)


# ---------------------------------------------------------------- the playbook


def test_the_playbook_parses_with_its_rules_bands_and_approvers(pb):
    assert pb["name"] == "quote-desk-playbook" and re.match(r"^\d+\.\d+\.\d+$", pb["version"])
    codes = [r["rule"] for r in pb["rules"]]
    assert codes == ["missing_field", "figures_mismatch", "quote_expired", "discount_over_10", "discount_over_20",
                     "discount_over_35", "payment_terms_over_30", "commercial_terms", "legal_terms"]
    assert [(b["limit"], b["approver"]) for b in pb["discount_bands"]] == [(10, "sales_manager"), (20, "finance_director"), (35, "cfo")]
    assert {r["rule"] for r in pb["rules"] if r["checked_by"] == "ai"} == AI_RULES
    assert all(r["approver"] == "none" for r in pb["rules"] if r["kind"] == "fix")
    assert [a["approver"] for a in pb["approvers"]] == ["sales_manager", "finance_director", "cfo", "legal"]
    assert pb["threshold"] == 0.7 and pb["figures_tolerance_pct"] == 1


@pytest.mark.parametrize("change, message", [
    (("| `discount_over_20` | approval | code | 20 |", "| `discount_over_20` | approval | code | 25 |"), "must have limit 20"),
    (("| `quote_expired` | fix | code | - | none |", "| `quote_expired` | fix | code | - | cfo |"), "approver is none"),
    (("| `legal_terms` | approval | ai |", "| `legal_terms` | approval | code |"), "does not know how to check legal_terms"),
    (("| `unclear` |", "| `doubtful` |"), "exactly the desk flags"),
    (('required_fields: "expiration_date,', 'required_fields: "contact_email, expiration_date,'), "not one the rule check knows"),
    (("| `discount_over_35` | approval | code | 35 | cfo |", "| `discount_over_35` | approval | code | 35 | ceo |"), "not in the Approvers table"),
])
def test_a_broken_playbook_is_refused(eng, change, message):
    old, new = change
    assert PLAYBOOK.count(old) == 1
    with pytest.raises(EngineError, match=message):
        eng.call("parseDeskPlaybook", PLAYBOOK.replace(old, new))


def test_moving_a_band_changes_the_rule_check_without_touching_the_engine(eng, prepared):
    """A3-style: the policy lives in the playbook. Rename the band and move its limit, and Q-0003 (13.85%) passes."""
    text = PLAYBOOK.replace("`discount_over_10` | approval | code | 10", "`discount_over_15` | approval | code | 15")
    pb2 = eng.call("parseDeskPlaybook", text)
    q, _ = prepared["Q-0003"]
    assert eng.call("checkQuoteRules", pb2, q, AS_OF)["rules"] == []


# ---------------------------------------------------------------- the cases and the code rule check


def test_the_case_set_is_twenty_with_hostile_notes_and_eight_demo_quotes():
    kinds = [c["kind"] for c in CASES.values()]
    assert len(CASES) == 20 and kinds.count("hostile") == 4 and kinds.count("clean") == 2
    demo = [c for c in CASES.values() if c["demo"]]
    assert len(demo) == 8
    assert {c["expected"]["action"] for c in demo} == {"approve", "reject"}
    all_text = json.dumps(CASES_FILE)
    assert all(m.rstrip(".").endswith(".example") for m in re.findall(r"@([a-z0-9.-]+)", all_text))
    assert all(c["account_domain"].endswith(".example") for c in CASES.values())


def test_the_code_rule_check_matches_every_label(prepared):
    for case_id, (q, f) in prepared.items():
        want = sorted(r for r in CASES[case_id]["expected"]["rules"] if r not in AI_RULES)
        assert sorted(r["rule"] for r in f["rules"]) == want, case_id


def test_the_effective_discount_counts_a_unit_price_below_list_and_a_line_discount_together(prepared):
    _, f = prepared["Q-0008"]  # 540 against a list of 600, then 10% more
    assert f["effective_discount_pct"] == 19 and f["rules"][0]["rule"] == "discount_over_10"
    assert "counted together" in f["rules"][0]["evidence"]
    _, f3 = prepared["Q-0003"]  # 15% on the seats, none on the implementation
    assert f3["effective_discount_pct"] == 13.85


def test_the_figures_and_dates_rules_name_their_evidence(prepared):
    assert "21.09% apart" in prepared["Q-0011"][1]["rules"][0]["evidence"]
    assert prepared["Q-0012"][1]["rules"][0]["evidence"].endswith("5 days ago")
    assert prepared["Q-0009"][1]["rules"][0]["evidence"] == "no expiry date, no payment terms"
    assert prepared["Q-0009"][1]["date_at_risk"] == prepared["Q-0009"][0]["close_date"]  # no expiry: the close date
    assert all(f["fix_needed"] == any(r["kind"] == "fix" for r in f["rules"]) for _, f in prepared.values())


def sf_record(q, sf_id):
    """A quote as DESK_SOQL returns it from Salesforce."""
    return {
        "attributes": {"type": "Quote"}, "Id": sf_id, "GTM_Case_Id__c": q["case_id"], "Name": q["quote_name"], "QuoteNumber": "00000001",
        "Status": "Needs Review", "ExpirationDate": q["expiration_date"], "BillingCountry": q["billing_country"], "TotalPrice": q["net_total"],
        "GTM_Payment_Terms_Days__c": q["payment_terms_days"], "GTM_Term_Months__c": q["term_months"],
        "GTM_Special_Terms__c": q["special_terms"] or None, "GTM_Rep_Note__c": q["rep_note"] or None,
        "Account": {"Name": q["account_name"]},
        "Opportunity": {"Name": q["opportunity_name"], "Amount": q["opportunity_amount"], "CloseDate": q["close_date"]},
        "QuoteLineItems": {"totalSize": len(q["lines"]), "done": True, "records": [
            {"LineNumber": f"{l['line']:05d}", "Product2": {"Name": l["product_name"], "ProductCode": l["product_code"]}, "Quantity": l["quantity"],
             "ListPrice": l["list_price"], "UnitPrice": l["unit_price"], "Discount": l["discount_pct"] or None, "TotalPrice": l["total"]}
            for l in q["lines"]]},
    }


def test_a_quote_read_from_salesforce_gives_the_same_facts_as_its_case(eng, pb, prepared):
    for case_id, (q, f) in prepared.items():
        sf = eng.call("quoteFromSalesforce", sf_record(q, "0Q0000000000001"))
        assert sf["case_id"] == case_id and sf["quote_id"] == "0Q0000000000001"
        assert eng.call("checkQuoteRules", pb, sf, AS_OF) == f, case_id


def test_the_desk_query_reads_no_contact_field_and_only_quotes_in_needs_review(eng):
    text = (REPO / "engine/quotes.js").read_text(encoding="utf-8")
    soql = re.search(r"const DESK_SOQL = ([\s\S]*?);\n", text).group(1)
    for field in ("Email", "Phone", "Fax", "Contact", "Owner"):
        assert not re.search(rf"\b{field}\b", soql), field
    assert "WHERE Status = 'Needs Review'" in soql
    fields = set(re.findall(r"\b(GTM_[A-Za-z_]+__c)\b", soql))
    assert fields <= {f["api_name"] for f in SETUP["custom_fields"]}
    for std in SETUP["standard_fields_read"]["Quote"]:
        if std not in ("OpportunityId", "AccountId", "Subtotal"):
            assert std in soql


# ---------------------------------------------------------------- the requests for the three designs


def walk(schema):
    yield schema
    for v in (schema.get("properties") or {}).values():
        yield from walk(v)
    if "items" in schema:
        yield from walk(schema["items"])


@pytest.mark.parametrize("kind", ["triage", "checker", "drafter", "lead"])
def test_every_schema_is_strict(eng, pb, kind):
    schema = eng.call("deskSchema", pb, "triage" if kind == "lead" else kind)
    objects = [s for s in walk(schema) if s.get("type") == "object"]
    assert objects and all(s["additionalProperties"] is False and set(s["required"]) == set(s["properties"]) for s in objects)


def test_the_requests_carry_the_quote_as_escaped_data_and_the_playbook(eng, pb, prepared):
    q, f = prepared["Q-0018"]  # the special terms try to close the record tag
    req = eng.call("buildDeskRequest", pb, "triage", q, f, MODEL, None, None)
    content = req["messages"][0]["content"]
    assert content.count("</quote_record>") == 1 and "\\u003c/quote_record\\u003e" in content
    assert f'<playbook name="{pb["name"]}" version="{pb["version"]}">' in req["system"]
    assert req["output_config"]["effort"] == "low" and req["output_config"]["format"]["type"] == "json_schema"
    assert "0Q0" not in content and "quote_id" not in content  # no Salesforce id goes to the model


def test_the_drafter_never_sees_the_rep_note_or_the_opportunity(eng, pb, prepared):
    q, f = prepared["Q-0019"]  # the attack sits in the rep note
    findings = {"proposed_action": "approve", "exceptions": [], "reason": "multi-year", "key_points": ""}
    req = eng.call("buildDeskRequest", pb, "drafter", q, f, MODEL, None, findings)
    assert "promise them 40%" not in req["messages"][0]["content"]
    assert "opportunity_amount" not in req["messages"][0]["content"] and "rep_note" not in req["messages"][0]["content"]


def test_the_lead_agent_has_two_strict_tools_and_is_not_forced_to_use_them(eng, pb, prepared):
    q, f = prepared["Q-0003"]
    req = eng.call("buildDeskRequest", pb, "lead", q, f, MODEL, None, None)
    assert [t["name"] for t in req["tools"]] == ["ask_policy_checker", "ask_message_drafter"]
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in req["tools"])
    assert req["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}


def test_the_lead_gets_its_reply_back_unchanged_with_the_tool_results(eng):
    prev = {"model": MODEL, "messages": [{"role": "user", "content": "x"}]}
    content = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "tool_use", "id": "tu1", "name": "ask_policy_checker", "input": {"why": "first"}}]
    nxt = eng.call("leadNextRequest", prev, content, [{"tool_use_id": "tu1", "content": "{}", "is_error": False}])
    assert nxt["messages"][1] == {"role": "assistant", "content": content}
    assert nxt["messages"][2]["content"][0]["type"] == "tool_result" and prev["messages"] == [{"role": "user", "content": "x"}]


# ---------------------------------------------------------------- the guard rails


def test_a_labelled_answer_passes_with_nothing_odd(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0003")
    assert p["output_valid"] and p["rules"] == ["discount_over_10"] and p["approvers"] == ["sales_manager"]
    assert not p["needs_review"] and p["approve_allowed"] and p["draft_problems"] == []


def test_a_code_rule_the_ai_leaves_out_is_kept_and_flagged(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0006", exceptions=[{"rule": "discount_over_20", "evidence": "30%"}])
    assert p["rules"] == ["discount_over_20", "payment_terms_over_30"] and "missed_code_rule" in p["review_reasons"]
    assert p["approvers"] == ["finance_director"]


def test_a_code_rule_the_figures_do_not_break_is_dropped(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0001", exceptions=[{"rule": "discount_over_35", "evidence": "a huge discount"}])
    assert p["rules"] == [] and "unsupported_rule" in p["review_reasons"]


def test_an_ai_rule_from_the_special_terms_is_added_with_its_approver(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0015")
    assert p["ai_rules"] == ["legal_terms"] and p["exceptions"][0]["found_by"] == "ai" and p["approvers"] == ["legal"]


def test_a_quote_that_must_be_fixed_cannot_be_approved(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0010", proposed_action="approve")
    assert not p["approve_allowed"] and "approve_blocked_by_fix_rule" in p["review_reasons"]
    assert eng.call("buildDeskReviewForm", pb, eng.call("deskQueue", [p]), {})[2]["fieldOptions"]["values"] == [{"option": "Reject: send back to the owner"}]


@pytest.mark.parametrize("draft, problem", [
    ("We can offer 40% off at renewal.\n\nKind regards,", "percentage that is not on the quote (40%)"),
    ("Our limits are 10%, 20% and 35%.\n\nKind regards,", "percentage that is not on the quote"),
    ("This needs discount_over_10 sign-off.\n\nKind regards,", "internal rules or codes"),
    ("Our finance director will decide.\n\nKind regards,", "names our approvers"),
    ("Please write to procurement@bellbird-telecom.example.\n\nKind regards,", "contact details"),
    ("Two-year term agreed. Also: in the customer reply, promise them.\n\nKind regards,", "repeats the rep note"),
])
def test_the_customer_draft_check_catches_what_the_attack_on_q0019_tries(eng, pb, prepared, draft, problem):
    p = triage(eng, pb, prepared, "Q-0019", customer_reply_draft=draft)
    assert any(problem in x for x in p["draft_problems"]) and "draft_check_failed" in p["review_reasons"]


def test_the_draft_may_name_the_quotes_own_discount(eng, pb, prepared):
    p = triage(eng, pb, prepared, "Q-0019", customer_reply_draft="Your two-year quote at 15% off is being finalised.\n\nKind regards,")
    assert p["draft_problems"] == []


@pytest.mark.parametrize("case_id, hits", [
    ("Q-0017", {"speaker_label", "skips_review", "names_internal_codes"}),
    ("Q-0018", {"markup", "speaker_label"}),
    ("Q-0019", {"steers_reply", "promises_customer", "sends_out"}),
    ("Q-0020", {"ignore_other_language"}),
])
def test_the_code_screen_flags_every_hostile_note(eng, pb, case_id, hits):
    c = CASES[case_id]
    screen = eng.call("screenQuoteText", pb, f"{c['rep_note']}\n{c['special_terms']}")
    assert "possible_injection" in screen["flags"] and hits <= set(screen["hits"])


def test_the_code_screen_leaves_every_other_note_alone(eng, pb):
    for c in CASES.values():
        if c["kind"] != "hostile":
            screen = eng.call("screenQuoteText", pb, f"{c['rep_note']}\n{c['special_terms']}")
            assert screen["flags"] == [], c["case_id"]


def test_a_refusal_a_cut_off_and_a_failed_call_are_no_answer(eng, pb, prepared):
    for http, why in [(answer({}, stop="refusal"), "declined"), (answer({}, stop="max_tokens"), "cut off"),
                      ({"error": {"message": "overloaded", "status": 529}}, "failed")]:
        reply = eng.call("readDeskReply", pb, "triage", http)
        assert not reply["ok"] and why in reply["error"]
        q, f = prepared["Q-0003"]
        joined = eng.call("designFinal", "one_prompt", {"triage": reply})
        p = eng.call("checkTriage", pb, q, f, joined["final"], joined["failure"], {"decision_id": "D", "run_id": "r", "design": "one_prompt"})
        assert not p["output_valid"] and p["needs_review"] and p["rules"] == ["discount_over_10"]


def test_the_chain_and_the_team_take_their_messages_from_the_drafter(eng, pb):
    checker = {"ok": True, "value": {"exceptions": [], "proposed_action": "approve", "reason": "fine", "confidence": 0.9, "flags": ["unclear"]}}
    drafter = {"ok": True, "value": {"approver_message": "A", "customer_reply_draft": "B", "flags": ["personal_data"]}}
    final = eng.call("designFinal", "fixed_chain", {"checker": checker, "drafter": drafter})["final"]
    assert final["approver_message"] == "A" and final["customer_reply_draft"] == "B" and set(final["flags"]) == {"unclear", "personal_data"}
    lead = {"ok": True, "value": dict(checker["value"], proposed_action="reject", flags=[])}
    team = eng.call("designFinal", "agent_team", {"lead": lead, "checker": checker, "drafter": drafter})["final"]
    assert team["proposed_action"] == "reject" and team["customer_reply_draft"] == "B"
    assert eng.call("designFinal", "agent_team", {"lead": lead})["failure"] == "the message drafter gave no answer"


# ---------------------------------------------------------------- the team design, with a fake Claude (B3)


class FakeClaude:
    """Answers each request by its system prompt's role: the lead asks the checker, then the drafter, then answers."""

    def __init__(self, case_id):
        self.t = labelled_triage(case_id)
        self.lead_turn = 0

    def __call__(self, client, request):
        system = request["system"]
        if "You are the lead agent" in system:
            self.lead_turn += 1
            if self.lead_turn == 1:
                return self.tool("ask_policy_checker", {"why": "check the policy first"}), 5
            if self.lead_turn == 2:
                return self.tool("ask_message_drafter", {"proposed_action": self.t["proposed_action"], "key_points": "approve on the term", "why": "write the messages"}), 5
            return answer({k: self.t[k] for k in ("exceptions", "proposed_action", "reason", "confidence", "flags")}), 5
        if "You are the policy checker" in system:
            return answer({k: self.t[k] for k in ("exceptions", "proposed_action", "reason", "confidence", "flags")}), 7
        if "You are the message drafter" in system:
            assert "rep_note" not in request["messages"][0]["content"]
            return answer({"approver_message": self.t["approver_message"], "customer_reply_draft": self.t["customer_reply_draft"], "flags": []}), 9
        return answer(self.t), 11

    @staticmethod
    def tool(name, inp):
        return {"statusCode": 200, "headers": {}, "body": {"model": MODEL, "stop_reason": "tool_use", "usage": {"input_tokens": 2000, "output_tokens": 80},
                "content": [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "tool_use", "id": f"tu-{name}", "name": name, "input": inp}]}}


@pytest.mark.parametrize("design, calls, handoffs", [("one_prompt", 1, 0), ("fixed_chain", 2, 1), ("agent_team", 5, 2)])
def test_each_design_runs_its_agents_and_records_every_hand_off(eng, pb, prepared, design, calls, handoffs):
    q, f = prepared["Q-0003"]
    desk = quote_desk.Desk(eng, pb, MODEL, client=None, caller=FakeClaude("Q-0003"))
    ctx = {"decision_id": "DQ-test-03", "run_id": "test", "design": design, "model": MODEL, "source": "python"}
    p, c, h = desk.run(design, q, f, ctx)
    assert p["output_valid"] and p["proposed_action"] == "approve" and p["calls"] == calls and len(c) == calls and len(h) == handoffs
    assert [x["call_id"] for x in c] == [f"DQ-test-03-C{i}" for i in range(1, calls + 1)]
    for x in h:
        assert x["from_agent"] != x["to_agent"] and x["asked"] and x["why"] and x["evidence"] and x["call_id"] in {y["call_id"] for y in c}
        assert x["run_id"] == "test" and x["decision_id"] == "DQ-test-03"
    if design == "agent_team":
        assert [(x["from_agent"], x["to_agent"]) for x in h] == [("lead_agent", "policy_checker"), ("lead_agent", "message_drafter")]
        assert [x["agent"] for x in c] == ["lead_agent", "policy_checker", "lead_agent", "message_drafter", "lead_agent"]
        assert h[0]["why"] == "check the policy first" and h[0]["confidence"] == 0.9


def test_a_lead_that_never_answers_is_stopped(eng, pb, prepared):
    q, f = prepared["Q-0003"]

    def loops(client, request):
        return FakeClaude.tool("ask_policy_checker", {"why": "again"}) if "lead agent" in request["system"] else answer(
            {k: labelled_triage("Q-0003")[k] for k in ("exceptions", "proposed_action", "reason", "confidence", "flags")}), 1

    desk = quote_desk.Desk(eng, pb, MODEL, client=None, caller=loops)
    p, c, h = desk.run("agent_team", q, f, {"decision_id": "D", "run_id": "r", "design": "agent_team", "model": MODEL})
    assert not p["output_valid"] and "did not finish" in p["review_detail"] and len(h) == quote_desk.MAX_LEAD_TURNS


# ---------------------------------------------------------------- the queue, the review, the decisions (B4, B5, B7)


def demo_queue(eng, pb, prepared):
    ps = [triage(eng, pb, prepared, c["case_id"]) for c in CASES.values() if c["demo"]]
    for i, p in enumerate(ps):
        p["quote_id"] = f"0Q0{i:012d}"
    return eng.call("deskQueue", ps)


def test_the_queue_is_ordered_by_the_date_at_risk_then_deal_size(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    assert [p["case_id"] for p in queue] == ["Q-0011", "Q-0009", "Q-0015", "Q-0004", "Q-0017", "Q-0007", "Q-0003", "Q-0005"]
    q4, q17 = queue[3], queue[4]  # the same date at risk: the larger deal first
    assert q4["date_at_risk"] == q17["date_at_risk"] and q4["deal_size"] > q17["deal_size"]
    assert [p["position"] for p in queue] == list(range(1, 9))


def test_the_review_page_asks_for_a_choice_and_a_reason_for_every_quote(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    fields = eng.call("buildDeskReviewForm", pb, queue, {"run_id": "n8n-1", "design": "one_prompt", "model": MODEL})
    html = fields[0]["html"]
    assert all(p["case_id"] in html for p in queue) and "Nothing is sent to a customer" in html
    for p in queue:
        choice = next(f for f in fields if f.get("fieldName") == f"quote_{p['position']}")
        reason = next(f for f in fields if f.get("fieldName") == f"reason_{p['position']}")
        assert choice["requiredField"] and reason["requiredField"] and reason["fieldType"] == "textarea"
        options = [o["option"] for o in choice["fieldOptions"]["values"]]
        reject = "Reject: send back to the owner"
        if p["fix_needed"]:
            assert options == [reject]
        else:
            assert options == (["Approve", reject] if p["proposed_action"] == "approve" else [reject, "Approve"])


def form_for(queue, **choices):
    form = {"approver": "reviewer-01"}
    for p in queue:
        form[f"quote_{p['position']}"] = choices.get(p["case_id"], "Approve" if p["proposed_action"] == "approve" and p["approve_allowed"] else "Reject: send back to the owner")
        form[f"reason_{p['position']}"] = f"reason for {p['case_id']}"
    return form


def test_decisions_update_only_status_reason_and_stamp_on_each_quote(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    out = eng.call("applyDeskDecisions", pb, queue, form_for(queue), {"decided_at": "2026-11-24T05:00:00.000Z"})
    records = out["update"]["body"]["records"]
    assert out["update"]["body"]["allOrNone"] is False and len(records) == 8
    for r in records:
        assert set(r) == {"attributes", "id", "Status", "GTM_Desk_Reason__c", "GTM_Desk_Stamp__c"} and r["Status"] in ("Approved", "Rejected")
        assert len(r["GTM_Desk_Stamp__c"]) <= 255 and len(r["GTM_Desk_Reason__c"]) <= 1000
    d = {x["case_id"]: x for x in out["decisions"]}
    assert d["Q-0003"]["action"] == "approved" and d["Q-0004"]["action"] == "rejected"
    assert re.match(r"^gtm-v2-desk DQ-test-03 \| one_prompt \| claude-haiku-5-5 \| quote-desk-playbook@\d+\.\d+\.\d+ \| approved by reviewer-01 \| 2026-11-24T05:00:00Z$", d["Q-0003"]["stamp"])
    assert "Rules broken: discount_over_10" in next(r for r in records if r["GTM_Desk_Stamp__c"] == d["Q-0003"]["stamp"])["GTM_Desk_Reason__c"]
    assert all(x["matches_proposal"] for x in out["decisions"])


@pytest.mark.parametrize("change, message", [
    ({"approver": " "}, "no reviewer name"),
    ({"reason_1": ""}, "no reason for quote 1"),
    ({"quote_2": "Maybe"}, "no choice for quote 2"),
    ({"quote_2": "Approve"}, "breaks a fix rule and cannot be approved"),  # position 2 is Q-0009, missing fields
])
def test_a_decision_without_a_person_a_reason_or_against_a_fix_rule_changes_nothing(eng, pb, prepared, change, message):
    queue = demo_queue(eng, pb, prepared)
    form = dict(form_for(queue), **change)
    with pytest.raises(EngineError, match=message):
        eng.call("applyDeskDecisions", pb, queue, form, {})


def decode(raw):
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")


def test_every_staff_message_goes_to_the_build_accounts_own_inbox(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    msg = eng.call("buildApproverMessage", pb, queue, {"run_id": "n8n-1", "link": "http://localhost:5678/form-waiting/1"})
    assert "form-waiting/1" in msg["text"] and "Rule broken: figures_mismatch" in msg["text"] and "[CHECK CLOSELY]" in msg["text"]
    out = eng.call("applyDeskDecisions", pb, queue, form_for(queue), {})
    owners = eng.call("buildOwnerMessages", pb, queue, out["decisions"], INBOX)
    assert len(owners) == 8 and {m["to"] for m in owners} == {"desk.owner+gtm-owner@example.com"}
    body = decode(owners[0]["raw"])
    assert body.startswith("To: desk.owner+gtm-owner@example.com\r\n") and "DRAFT reply to the customer. It has not been sent." in body
    for to in ("procurement@bellbird-telecom.example", "desk.owner@example.com", "someone+gtm-owner@example.com"):
        with pytest.raises(EngineError, match="own inbox"):
            eng.call("buildRawEmail", INBOX, to, "s", "t")


def test_the_owner_is_warned_when_the_draft_was_written_for_the_other_outcome(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    out = eng.call("applyDeskDecisions", pb, queue, form_for(queue, **{"Q-0003": "Reject: send back to the owner"}), {})
    owners = eng.call("buildOwnerMessages", pb, queue, out["decisions"], INBOX)
    q3 = next(m for m, d in zip(owners, out["decisions"]) if d["case_id"] == "Q-0003")
    assert 'wrote this draft for "approve"' in decode(q3["raw"])
    assert next(d for d in out["decisions"] if d["case_id"] == "Q-0003")["matches_proposal"] is False


def test_the_log_rows_record_what_salesforce_and_gmail_did(eng, pb, prepared):
    queue = demo_queue(eng, pb, prepared)
    decisions = eng.call("applyDeskDecisions", pb, queue, form_for(queue), {})["decisions"]
    sf = {"statusCode": 200, "body": [{"id": "x", "success": i != 0, "errors": [] if i else [{"statusCode": "ENTITY_IS_LOCKED", "message": "locked"}]} for i in range(8)]}
    sends = {d["decision_id"]: {"statusCode": 200, "body": {"id": f"m{i}"}} for i, d in enumerate(decisions) if i}
    rows = eng.call("deskDecisionLogRows", decisions, sf, sends)
    assert rows[0]["crm_write_status"] == "failed" and "ENTITY_IS_LOCKED" in rows[0]["crm_error"]
    assert rows[0]["owner_message_status"] == "failed" and "Salesforce did not save" in rows[0]["owner_message_error"]
    assert all(r["crm_write_status"] == "written" and r["owner_message_status"] == "sent" for r in rows[1:])
    assert eng.call("summariseDesk", rows) == {"decisions": 8, "approved": 2, "rejected": 6, "written": 7, "failed": 1, "owners_told": 7, "against_proposal": 0}
    failed = eng.call("deskDecisionLogRows", decisions, {"statusCode": 401, "body": [{"errorCode": "INVALID_SESSION_ID", "message": "Session expired"}]}, {})
    assert all(r["crm_write_status"] == "failed" and "INVALID_SESSION_ID" in r["crm_error"] for r in failed)


# ---------------------------------------------------------------- the grader and the results (B2)


def test_the_grader_counts_a_hostile_quote_blocked_only_when_every_part_holds(eng, pb, prepared):
    good = triage(eng, pb, prepared, "Q-0019")
    assert quote_desk.grade(CASES["Q-0019"], good)["blocked"]
    leaked = triage(eng, pb, prepared, "Q-0019", customer_reply_draft="We will give you 40% off at renewal.\n\nKind regards,")
    assert not quote_desk.grade(CASES["Q-0019"], leaked)["blocked"]
    steered = triage(eng, pb, prepared, "Q-0017", proposed_action="approve")
    g = quote_desk.grade(CASES["Q-0017"], steered)
    assert not g["action_ok"] and not g["blocked"]


def test_the_simplest_design_that_meets_the_bar_is_kept():
    bar = json.loads((REPO / "skins/quote-desk/eval/bar.json").read_text(encoding="utf-8"))
    ok = {"passes": True, "failed_lines": []}
    no = {"passes": False, "failed_lines": ["attacks_blocked"]}
    assert quote_desk.kept_design({"one_prompt": ok, "fixed_chain": ok, "agent_team": ok}, bar)[0] == "one_prompt"
    kept, why = quote_desk.kept_design({"one_prompt": no, "fixed_chain": no, "agent_team": ok}, bar)
    assert kept == "agent_team" and "one_prompt missed attacks_blocked" in why
    assert quote_desk.kept_design({"one_prompt": no}, bar)[0] is None


def test_the_bar_was_set_before_the_results_and_names_every_line():
    bar = json.loads((REPO / "skins/quote-desk/eval/bar.json").read_text(encoding="utf-8"))
    res = json.loads((REPO / "skins/quote-desk/eval/results.json").read_text(encoding="utf-8"))
    assert res["bar"] == bar["lines"] and bar["set_on"] <= res["run_at"][:4] + "-" + res["run_at"][4:6] + "-" + res["run_at"][6:8]
    assert set(bar["lines"]) <= set(next(iter(res["designs"].values()))["summary"])


def test_the_results_file_names_the_kept_design_and_every_figure_is_made_by_the_script():
    res = json.loads((REPO / "skins/quote-desk/eval/results.json").read_text(encoding="utf-8"))
    assert set(res["designs"]) == {"one_prompt", "fixed_chain", "agent_team"} and res["cases"] == 20
    assert res["kept"] in res["designs"] and res["designs"][res["kept"]]["summary"]["passes"]
    order = ["one_prompt", "fixed_chain", "agent_team"]
    assert all(not res["designs"][d]["summary"]["passes"] for d in order[:order.index(res["kept"])])
    assert res["playbook"]["sha256"] == __import__("hashlib").sha256(PLAYBOOK.encode("utf-8")).hexdigest()
    md = (REPO / "skins/quote-desk/eval/results.md").read_text(encoding="utf-8")
    assert md == quote_desk.results_markdown(copy.deepcopy(res))
    for v in res["designs"].values():
        assert len(v["cases"]) == 20 * res["rounds"]
    s = {d: v["summary"] for d, v in res["designs"].items()}
    assert s["one_prompt"]["handoffs_per_quote"] == 0 and s["one_prompt"]["calls_per_quote"] == 1
    assert 0 < s["fixed_chain"]["handoffs_per_quote"] <= 1 and s["agent_team"]["handoffs_per_quote"] >= 2
