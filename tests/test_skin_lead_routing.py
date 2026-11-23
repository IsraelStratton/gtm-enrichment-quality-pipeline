"""The lead-routing skin: 40 made-up enquiries with labels, the demo run file, and the playbook folder."""
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIN = REPO / "skins" / "lead-routing"
sys.path.insert(0, str(REPO / "scripts"))
from industry_mapping import map_industry  # noqa: E402

ENQUIRIES = list(csv.DictReader((SKIN / "enquiries.csv").open(encoding="utf-8")))
RUN = list(csv.DictReader((SKIN / "sample_run.csv").open(encoding="utf-8")))
PLAYBOOK = (SKIN / "lead-routing-playbook" / "SKILL.md").read_text(encoding="utf-8")
LEAD_COLUMNS = ["lead_id", "company_name", "domain", "industry", "employee_count", "hq_city", "hq_country", "enquiry"]


def codes(heading):
    section = PLAYBOOK.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^\| `([a-z_]+)` \|", section, re.M)


def test_forty_enquiries_with_unique_ids_and_domains():
    assert len(ENQUIRIES) == 40
    assert list(ENQUIRIES[0]) == LEAD_COLUMNS + ["expected_intent", "expected_route", "expected_priority",
                                                 "expected_review", "case_type", "attack_kind", "note"]
    assert len({r["lead_id"] for r in ENQUIRIES}) == 40
    assert len({r["domain"] for r in ENQUIRIES}) == 40
    assert all(re.fullmatch(r"L-\d{4}", r["lead_id"]) for r in ENQUIRIES)


def test_made_up_company_level_data_only():
    for r in ENQUIRIES + RUN:
        assert r["domain"].rstrip("/").split("/")[-1 if "://" not in r["domain"] else 2].endswith(".example"), r["lead_id"]
        assert "@" not in r["enquiry"], r["lead_id"]
        assert not re.search(r"\d[\d\s().-]{7,}\d", r["enquiry"]), r["lead_id"]  # no phone numbers


def test_enrichment_fields_pass_the_data_rules():
    for r in ENQUIRIES:
        assert map_industry(r["industry"]), (r["lead_id"], r["industry"])
        assert r["employee_count"] == "" or r["employee_count"].isdigit(), r["lead_id"]
        assert r["company_name"].strip() and r["enquiry"].strip()


def test_labels_use_only_playbook_codes():
    intents, routes, priorities = set(codes("Intents")), set(codes("Routes")), set(codes("Priorities"))
    assert len(routes) == 8 and len(intents) == 8 and priorities == {"high", "medium", "low"}
    for r in ENQUIRIES:
        assert set(r["expected_intent"].split("|")) <= intents, r["lead_id"]
        assert set(r["expected_route"].split("|")) <= routes, r["lead_id"]
        assert set(r["expected_priority"].split("|")) <= priorities, r["lead_id"]
        assert r["expected_review"] in {"yes", "no", "either"}, r["lead_id"]
        assert r["case_type"] in {"normal", "edge", "spam", "attack"}, r["lead_id"]


def test_at_least_six_attack_rows_of_different_kinds_and_all_must_be_reviewed():
    """A2.1: attack rows are labelled, six or more, of different kinds."""
    attacks = [r for r in ENQUIRIES if r["case_type"] == "attack"]
    assert len(attacks) >= 6
    assert len({r["attack_kind"] for r in attacks}) == len(attacks)
    assert all(r["expected_review"] == "yes" for r in attacks)
    assert all(r["attack_kind"] == "" for r in ENQUIRIES if r["case_type"] != "attack")


def test_every_route_appears_in_the_labels():
    used = {x for r in ENQUIRIES for x in r["expected_route"].split("|")}
    assert used == set(codes("Routes"))


def test_demo_run_file_is_drawn_from_the_enquiries_plus_two_rows_the_rules_stop():
    assert list(RUN[0]) == LEAD_COLUMNS
    by_id = {r["lead_id"]: r for r in ENQUIRIES}
    from_set = [r for r in RUN if r["lead_id"] in by_id]
    assert len(from_set) == 12 and len(RUN) == 14
    for r in from_set:
        assert r == {k: by_id[r["lead_id"]][k] for k in LEAD_COLUMNS}, r["lead_id"]
    stopped = [r for r in RUN if r["lead_id"] not in by_id]
    assert {r["lead_id"] for r in stopped} == {"L-9001", "L-9002"}
    assert "_" in stopped[0]["domain"]  # DQ-02: an underscore is not a valid hostname
    assert "northwind-freight.example" in stopped[1]["domain"]  # DQ-03: duplicate of L-0001 after normalisation
    assert any(r["case_type"] == "attack" for r in ENQUIRIES if r["lead_id"] in {x["lead_id"] for x in RUN})


def test_playbook_folder_is_in_agent_skills_format():
    folder = SKIN / "lead-routing-playbook"
    front = PLAYBOOK.split("---\n")[1]
    assert re.search(r"^name: lead-routing-playbook$", front, re.M)  # matches the folder name
    assert re.search(r"^description: .{20,1024}$", front, re.M)
    assert re.search(r'^  version: "\d+\.\d+\.\d+"$', front, re.M)
    assert (folder / "references" / "governance.md").is_file()
    assert folder.name == "lead-routing-playbook"
