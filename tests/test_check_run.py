"""scripts/check_run.py: the log checks behind A1.1 (a stamp on every write) and A1.3 (both values kept)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import check_run as cr  # noqa: E402


def record(n, action, **over):
    r = {"decision_id": f"D-n8n7-{n:02d}", "lead_id": f"L-00{n:02d}", "model": "claude-haiku-5-5",
         "playbook_name": "lead-routing-playbook", "playbook_version": "1.0.0", "approver": "reviewer-01",
         "proposed_route": "enterprise_anz", "proposed_priority": "high", "action": action,
         "chosen_route": None, "chosen_priority": None, "stamp": None, "crm_write_status": "not_written", "crm_error": None}
    if action in ("approved", "changed"):
        r.update(chosen_route="enterprise_anz" if action == "approved" else "mid_market",
                 chosen_priority="high" if action == "approved" else "medium", crm_write_status="written",
                 stamp=f"gtm-v2 D-n8n7-{n:02d} | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | {action} by reviewer-01 | 2026-11-24T01:00:00Z")
    r.update(over)
    return r


def test_a_clean_run_passes_every_check():
    results = cr.check_log([record(1, "approved"), record(2, "changed"), record(3, "rejected")])
    assert all(ok for ok, _ in results), results
    assert any("AI enterprise_anz high, person mid_market medium" in text for _, text in results)


def test_a_write_whose_stamp_names_another_decision_fails():
    bad = record(1, "approved", stamp="gtm-v2 D-n8n7-09 | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | approved by reviewer-01 | 2026-11-24T01:00:00Z")
    assert not all(ok for ok, _ in cr.check_log([bad]))


def test_an_undecided_proposal_fails_the_run():
    results = cr.check_log([record(1, None)])
    assert results[0][0] is False and "waiting: D-n8n7-01" in results[0][1]


def test_a_failed_write_is_reported_with_its_error():
    results = cr.check_log([record(1, "approved", crm_write_status="failed", crm_error="HTTP 400: INVALID_OPTION")])
    assert any(not ok and "INVALID_OPTION" in text for ok, text in results)


def test_stamp_pattern_matches_what_the_engine_writes():
    m = cr.STAMP.match("gtm-v2 D-n8n123-04 | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | changed by Israel S | 2026-11-24T01:02:03Z")
    assert m and (m["decision"], m["action"], m["approver"]) == ("D-n8n123-04", "changed", "Israel S")
