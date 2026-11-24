"""KB-137 A5: the cost sheet is made by script from the run log; no figure on it is typed by hand."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import cost_sheet  # noqa: E402

PRICES, AGENTFORCE = cost_sheet.load_prices()

FIXTURE = {
    "made_at": "2026-11-24T00:00:00Z", "read_from": "a test fixture",
    "routing_by_model": [
        {"model": "claude-haiku-5-5", "source": "n8n", "decisions": 10, "input_tokens": 33600, "output_tokens": 1200, "total_cost_usd": "0.00396000"},
        {"model": "claude-haiku-5-5", "source": "python", "decisions": 30, "input_tokens": 100800, "output_tokens": 3600, "total_cost_usd": "0.01188000"},
        {"model": "claude-sonnet-5-5", "source": "python", "decisions": 40, "input_tokens": 134400, "output_tokens": 4000, "total_cost_usd": "0.31680000"},
    ],
    "routing_by_route": [
        {"model": "claude-haiku-5-5", "route": "smb", "decisions": 4, "total_cost_usd": "0.00160000"},
        {"model": "claude-sonnet-5-5", "route": "smb", "decisions": 2, "total_cost_usd": "0.01544000"},
    ],
    "routing_live_writes": [{"model": "claude-haiku-5-5", "proposals": 10, "written": 8, "rejected": 2, "total_cost_usd": "0.00396000",
                             "crm_targets": "hubspot"}],
    "desk_by_design": [{"design": "one_prompt", "model": "claude-haiku-5-5", "source": "n8n", "quotes": 4, "calls": 4, "total_cost_usd": "0.00280000"}],
}


def test_the_committed_sheet_is_exactly_what_the_script_makes_from_its_json():
    snap = json.loads(cost_sheet.SHEET_JSON.read_text(encoding="utf-8"))
    assert cost_sheet.SHEET_MD.read_text(encoding="utf-8") == cost_sheet.render(snap, PRICES, AGENTFORCE)


def test_the_sheet_covers_both_models_live_and_eval_runs_and_the_quote_desk():
    snap = json.loads(cost_sheet.SHEET_JSON.read_text(encoding="utf-8"))
    models = {r["model"] for r in snap["routing_by_model"]}
    assert {"claude-haiku-5-5", "claude-sonnet-5-5"} <= models
    assert {r["source"] for r in snap["routing_by_model"]} == {"n8n", "python"}
    assert len({r["route"] for r in snap["routing_by_route"]}) >= 8
    assert {"one_prompt", "fixed_chain", "agent_team"} <= {r["design"] for r in snap["desk_by_design"]}


def test_cost_per_decision_is_worked_out_from_the_totals_by_model_and_route():
    page = cost_sheet.render(FIXTURE, PRICES, AGENTFORCE)
    assert "| `claude-haiku-5-5` | n8n, live runs | 10 | 3360 / 120 | 0.00039600 | 0.003960 |" in page
    assert "| `claude-sonnet-5-5` | `smb` | 2 | 0.00772000 | 0.015440 |" in page
    assert "| `claude-haiku-5-5` | 10 | 8 | 2 | 0.00049500 | hubspot |" in page  # cost per record written
    assert "| `one_prompt` | `claude-haiku-5-5` | n8n, live runs | 4 | 1.0 | 0.00070000 | 0.002800 |" in page
    assert "costs 20 times as much as `claude-haiku-5-5` per decision (US$0.00792000 against US$0.00039600" in page


def test_every_price_shows_the_date_it_was_read_and_its_source():
    """A5.2."""
    page = cost_sheet.render(FIXTURE, PRICES, AGENTFORCE)
    for model, p in PRICES["models"].items():
        row = next(line for line in page.splitlines() if line.startswith(f"| `{model}` | {p['input']:.2f} |"))
        assert p["read_on"] in row and p["source"] in row
    assert f"read on {AGENTFORCE['read_on']}" in page and all(s in page for s in AGENTFORCE["sources"])


def test_the_vendor_line_is_computed_and_marked_not_like_for_like():
    """A5.3: US$0.10 an action against US$0.000396 a decision is about 253 times."""
    page = cost_sheet.render(FIXTURE, PRICES, AGENTFORCE)
    line = next(x for x in page.splitlines() if "Agentforce action" in x)
    assert "costs about 253 times one live routing decision" in line
    assert "Not like for like" in line


def test_no_price_is_typed_into_the_script():
    source = (REPO / "scripts" / "cost_sheet.py").read_text(encoding="utf-8")
    assert not re.search(r"\b0\.(10|50|005)\b|\b2\.00\b|\b10\.00\b", source)
