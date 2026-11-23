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


def test_the_pipeline_login_gets_two_functions_and_three_views_only():
    grants = [line.strip() for line in srl.role_sql("abc_DEF-123").splitlines() if line.strip().startswith("grant")]
    assert grants == [
        "grant usage on schema gtm_v2 to gtm_v2_pipeline;",
        "grant execute on function gtm_v2.log_proposals(jsonb), gtm_v2.log_decisions(jsonb) to gtm_v2_pipeline;",
        "grant select on gtm_v2.decision_record, gtm_v2.run_summary, gtm_v2.cost_by_route to gtm_v2_pipeline;",
    ]
    lowered = SQL.lower()
    assert "revoke all on all tables in schema gtm_v2 from public" in lowered
    assert "grant update" not in lowered and "grant delete" not in lowered and "grant insert" not in lowered


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
