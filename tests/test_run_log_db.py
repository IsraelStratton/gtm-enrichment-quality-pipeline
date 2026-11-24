"""The run log (db/run_log.sql): what the pipeline login may do, and the rules the tables enforce.

The live tests need the local Supabase Postgres and GTM_V2_DB_PASSWORD in .env, so they skip in
CI. Each runs inside a transaction that is rolled back, so the add-only log gets no test rows.
"""
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import setup_run_log as srl  # noqa: E402

SQL = (REPO / "db/run_log.sql").read_text(encoding="utf-8")
DESK_SQL = (REPO / "db/quote_desk.sql").read_text(encoding="utf-8")


def test_the_pipeline_login_gets_four_functions_and_six_views_only():
    grants = [line.strip() for line in srl.role_sql("abc_DEF-123").splitlines() if line.strip().startswith("grant")]
    assert grants == [
        "grant usage on schema gtm_v2 to gtm_v2_pipeline;",
        "grant execute on function gtm_v2.log_proposals(jsonb), gtm_v2.log_decisions(jsonb) to gtm_v2_pipeline;",
        "grant select on gtm_v2.decision_record, gtm_v2.run_summary, gtm_v2.cost_by_route to gtm_v2_pipeline;",
        # Chapter 5, the quote desk (db/quote_desk.sql).
        "grant execute on function gtm_v2.log_desk_triage(jsonb, jsonb, jsonb), gtm_v2.log_desk_decisions(jsonb) to gtm_v2_pipeline;",
        "grant select on gtm_v2.desk_record, gtm_v2.desk_run_summary, gtm_v2.handoff_record to gtm_v2_pipeline;",
    ]
    for text in (SQL, DESK_SQL):
        lowered = text.lower()
        assert "revoke all on all tables in schema gtm_v2 from public" in lowered
        assert "grant update" not in lowered and "grant delete" not in lowered and "grant insert" not in lowered
    assert "security definer" in DESK_SQL and "check (approve_allowed = not fix_needed)" in DESK_SQL


def test_password_must_be_safe_inside_sql():
    with pytest.raises(ValueError):
        srl.role_sql("bad'; drop table x; --")


def test_prices_come_from_the_one_price_file():
    prices = json.loads((REPO / "pricing/claude_prices.json").read_text(encoding="utf-8"))
    sql = srl.prices_sql(prices)
    for model, p in prices["models"].items():
        assert f"'{model}', {p['input']!r}, {p['output']!r}" in sql
        assert p["read_on"] and p["source"].startswith("https://")


def live_connection():
    from dotenv import dotenv_values

    password = (dotenv_values(REPO / ".env").get(srl.PASSWORD_KEY) if (REPO / ".env").exists() else None) or ""
    if not password:
        pytest.skip("no run-log password in .env")
    try:
        import psycopg

        s = srl.db_settings()
        return psycopg.connect(host=s["host"], port=s["port"], dbname=s["dbname"], user=s["user"],
                               password=password, connect_timeout=3)
    except Exception:
        pytest.skip("local Supabase Postgres not reachable")


def proposal(decision_id="D-pytest-01", **over):
    p = {"decision_id": decision_id, "run_id": "pytest", "source": "python", "row_number": 1, "lead_id": "L-0001",
         "company_name": "Northwind Freight", "domain": "northwind-freight.example", "model": "claude-haiku-5-5",
         "model_served": "claude-haiku-5-5", "playbook_name": "lead-routing-playbook", "playbook_version": "1.0.0",
         "playbook_sha256": "0" * 64, "engine_version": "1.0.0", "output_valid": True, "intent": "demo_request",
         "route": "enterprise_anz", "priority": "high", "reason": "Test.", "confidence": 0.9, "flags": ["unclear"],
         "needs_review": True, "review_reasons": ["model_flags"], "review_detail": "", "stop_reason": "end_turn",
         "input_tokens": 3400, "output_tokens": 100, "latency_ms": 1500, "api_request_id": "req_x",
         "proposed_at": "2026-11-23T05:00:00Z"}
    p.update(over)
    return p


def decision(decision_id="D-pytest-01", **over):
    d = {"decision_id": decision_id, "run_id": "pytest", "action": "changed", "chosen_route": "mid_market",
         "chosen_priority": "medium", "approver": "reviewer-01", "decided_at": "2026-11-23T05:02:00Z", "note": "",
         "crm_target": "hubspot", "crm_write_status": "written", "crm_record_id": "123",
         "stamp": "gtm-v2 D-pytest-01 | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | changed by reviewer-01 | 2026-11-23T05:02:00Z"}
    d.update(over)
    return d


def test_a_logged_decision_reads_back_with_both_values_and_its_cost():
    conn = live_connection()
    try:
        with conn.transaction(force_rollback=True):
            assert conn.execute("select gtm_v2.log_proposals(%s::jsonb)", (json.dumps([proposal()]),)).fetchone()[0] == 1
            assert conn.execute("select gtm_v2.log_decisions(%s::jsonb)", (json.dumps([decision()]),)).fetchone()[0] == 1
            cur = conn.execute("select * from gtm_v2.decision_record where decision_id = 'D-pytest-01'")
            r = dict(zip([c.name for c in cur.description], cur.fetchone()))
            assert (r["proposed_route"], r["chosen_route"], r["changed"]) == ("enterprise_anz", "mid_market", True)
            assert float(r["cost_usd"]) == pytest.approx((3400 * 0.10 + 100 * 0.50) / 1e6)
            assert (r["flags"], r["review_reasons"], r["seconds_to_decision"]) == ("unclear", "model_flags", 120)
    finally:
        conn.close()


@pytest.mark.parametrize("bad", [
    decision(stamp=None),                                                   # a write with no stamp
    decision(action="rejected", chosen_route=None, chosen_priority=None),   # a rejected row with a stamp
    decision(action="rejected", stamp=None, crm_write_status="written"),    # a rejected row that was written
    decision(approver=" "),                                                 # no reviewer
    decision(decision_id="D-nobody-99"),                                    # a decision with no proposal
])
def test_the_tables_refuse_a_decision_that_breaks_the_rules(bad):
    import psycopg

    conn = live_connection()
    try:
        with pytest.raises(psycopg.errors.IntegrityError):
            with conn.transaction(force_rollback=True):
                conn.execute("select gtm_v2.log_proposals(%s::jsonb)", (json.dumps([proposal()]),))
                conn.execute("select gtm_v2.log_decisions(%s::jsonb)", (json.dumps([bad]),))
    finally:
        conn.close()


def test_a_proposal_cannot_be_logged_twice():
    import psycopg

    conn = live_connection()
    try:
        with pytest.raises(psycopg.errors.UniqueViolation):
            with conn.transaction(force_rollback=True):
                conn.execute("select gtm_v2.log_proposals(%s::jsonb)", (json.dumps([proposal(), proposal()]),))
    finally:
        conn.close()


# ---------------------------------------------------------------- chapter 5, the quote desk


def desk_proposal(decision_id="DQ-pytest-01", **over):
    p = {"decision_id": decision_id, "run_id": "pytest-desk", "source": "python", "design": "agent_team", "case_id": "Q-0003",
         "quote_id": "Q-0003", "quote_name": "Kestrel Logistics: three-year platform", "account_name": "Kestrel Logistics",
         "model": "claude-haiku-5-5", "playbook_name": "quote-desk-playbook", "playbook_version": "1.0.0", "playbook_sha256": "0" * 64,
         "engine_version": "1.0.0", "output_valid": True, "code_rules": ["discount_over_10"], "ai_rules": [], "rules": ["discount_over_10"],
         "exceptions": [{"rule": "discount_over_10", "evidence": "13.85%"}], "approvers": ["sales_manager"], "fix_needed": False,
         "approve_allowed": True, "proposed_action": "approve", "reason": "Multi-year.", "approver_message": "A.", "customer_reply_draft": "B.",
         "draft_problems": [], "confidence": 0.9, "flags": [], "needs_review": False, "review_reasons": [], "review_detail": "",
         "effective_discount_pct": 13.85, "deal_size": 168000, "date_at_risk": "2027-01-08", "position": 1, "calls": 2, "handoffs": 1,
         "input_tokens": 9000, "output_tokens": 600, "latency_ms": 9000, "proposed_at": "2026-11-24T05:00:00Z"}
    p.update(over)
    return p


def desk_calls(decision_id="DQ-pytest-01"):
    return [{"call_id": f"{decision_id}-C{i}", "decision_id": decision_id, "run_id": "pytest-desk", "design": "agent_team", "agent": a,
             "turn": i, "model": "claude-haiku-5-5", "input_tokens": 4500, "output_tokens": 300, "latency_ms": 4500, "ok": True}
            for i, a in ((1, "lead_agent"), (2, "policy_checker"))]


def desk_handoff(decision_id="DQ-pytest-01"):
    return [{"handoff_id": f"{decision_id}-H1", "decision_id": decision_id, "run_id": "pytest-desk", "design": "agent_team",
             "from_agent": "lead_agent", "to_agent": "policy_checker", "asked": "ask_policy_checker", "why": "check first",
             "evidence": "discount_over_10: 13.85%", "confidence": 0.9, "call_id": f"{decision_id}-C2"}]


def desk_decision(decision_id="DQ-pytest-01", **over):
    d = {"decision_id": decision_id, "run_id": "pytest-desk", "case_id": "Q-0003", "quote_id": "Q-0003", "position": 1, "action": "approved",
         "reason": "Three-year term.", "approver": "reviewer-01", "decided_at": "2026-11-24T05:02:00Z", "matches_proposal": True,
         "sf_status": "Approved", "crm_write_status": "written", "owner_message_status": "sent", "owner_message_id": "m1",
         "stamp": "gtm-v2-desk DQ-pytest-01 | agent_team | claude-haiku-5-5 | quote-desk-playbook@1.0.0 | approved by reviewer-01 | 2026-11-24T05:02:00Z"}
    d.update(over)
    return d


def test_a_desk_triage_reads_back_with_its_hand_off_and_the_cost_of_every_call():
    conn = live_connection()
    try:
        with conn.transaction(force_rollback=True):
            n = conn.execute("select gtm_v2.log_desk_triage(%s::jsonb, %s::jsonb, %s::jsonb)",
                             (json.dumps([desk_proposal()]), json.dumps(desk_calls()), json.dumps(desk_handoff()))).fetchone()[0]
            assert n == 1
            assert conn.execute("select gtm_v2.log_desk_decisions(%s::jsonb)", (json.dumps([desk_decision()]),)).fetchone()[0] == 1
            cur = conn.execute("select * from gtm_v2.desk_record where decision_id = 'DQ-pytest-01'")
            r = dict(zip([c.name for c in cur.description], cur.fetchone()))
            assert float(r["cost_usd"]) == pytest.approx(2 * (4500 * 0.10 + 300 * 0.50) / 1e6)
            assert (r["rules"], r["action"], r["queue_position"], r["seconds_to_decision"]) == ("discount_over_10", "approved", 1, 120)
            cur = conn.execute("select from_agent, to_agent, input_tokens, cost_usd from gtm_v2.handoff_record where run_id = 'pytest-desk'")
            h = cur.fetchone()
            assert h[:3] == ("lead_agent", "policy_checker", 4500) and float(h[3]) == pytest.approx((4500 * 0.10 + 300 * 0.50) / 1e6)
    finally:
        conn.close()


@pytest.mark.parametrize("prop, dec", [
    (desk_proposal(fix_needed=True, approve_allowed=True), None),                                         # a fix quote marked approvable
    (desk_proposal(fix_needed=True, approve_allowed=False), desk_decision()),                             # an approved fix quote
    (desk_proposal(), desk_decision(reason=" ")),                                                         # no reason
    (desk_proposal(), desk_decision(sf_status="Rejected")),                                               # approved, but the quote says rejected
    (desk_proposal(), desk_decision(stamp="no stamp")),                                                   # not a desk stamp
])
def test_the_desk_log_refuses_what_breaks_its_rules(prop, dec):
    import psycopg

    conn = live_connection()
    try:
        with pytest.raises((psycopg.errors.IntegrityError, psycopg.errors.RaiseException)):
            with conn.transaction(force_rollback=True):
                conn.execute("select gtm_v2.log_desk_triage(%s::jsonb, '[]'::jsonb, '[]'::jsonb)", (json.dumps([prop]),))
                if dec:
                    conn.execute("select gtm_v2.log_desk_decisions(%s::jsonb)", (json.dumps([dec]),))
    finally:
        conn.close()
