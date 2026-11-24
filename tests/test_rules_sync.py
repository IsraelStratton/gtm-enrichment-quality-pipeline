"""KB-137 A4.1: a test on every push fails when the rules page and the workflow disagree, in either direction.

Done when: removing a rule from either side fails the push. CI runs this file on every push;
scripts/prepush_check.py runs the same check on the commit being pushed, so the push never leaves the Mac.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import playbook_bar  # noqa: E402
import prepush_check  # noqa: E402
import rules_sync  # noqa: E402

TREE = playbook_bar.tree_reader()
PAGE = TREE(rules_sync.RULES_PAGE)
V1 = rules_sync.WORKFLOWS[0]


def with_page(text):
    return lambda rel: text if rel == rules_sync.RULES_PAGE else TREE(rel)


def with_rules_code(change, rels=tuple(rules_sync.WORKFLOWS)):
    """Every workflow file in `rels` with its DQ Checks code changed by `change`."""
    def read(rel):
        text = TREE(rel)
        if rel not in rels:
            return text
        wf = json.loads(text)
        node = next(n for n in wf["nodes"] if n["name"] == "DQ Checks")
        node["parameters"]["jsCode"] = change(node["parameters"]["jsCode"])
        return json.dumps(wf)
    return read


def page_row(rule_id):
    return next(line for line in PAGE.splitlines() if line.startswith(f"| {rule_id} |"))


def test_the_rules_page_and_every_workflow_with_the_data_rules_agree():
    assert rules_sync.check_all(TREE) == []


def test_the_check_reads_all_seven_rules_and_every_workflow_that_runs_them():
    page = rules_sync.parse_rules_page(PAGE)
    assert sorted(page["rules"]) == [f"DQ-0{i}" for i in range(1, 8)]
    assert {k: v["type"] for k, v in page["rules"].items()}["DQ-04"] == "Route"
    with_dq = [rel for rel in ("n8n/workflow.json", "n8n/workflow-v2.json", "n8n/workflow-v2-salesforce.json", "n8n/workflow-v2-quote-desk.json")
               if any(n["name"] == "DQ Checks" for n in json.loads(TREE(rel))["nodes"])]
    assert with_dq == rules_sync.WORKFLOWS


# ---- one direction: the page changes, the workflow does not


def test_a_rule_removed_from_the_page_fails():
    found = rules_sync.check_all(with_page(PAGE.replace(page_row("DQ-05") + "\n", "")))
    assert any("checks DQ-05, which is not on the rules page" in f for f in found)
    assert len({f.split(":")[0] for f in found}) == 3, "every workflow with the rules is named"


def test_a_rule_added_only_to_the_page_fails():
    extra = "| DQ-08 | `hq_country` is present | Flag | Load, record the flag | `COUNTRY_MISSING` |"
    found = rules_sync.check_all(with_page(PAGE.replace(page_row("DQ-07"), page_row("DQ-07") + "\n" + extra)))
    assert any("DQ-08 is on the rules page but the workflow does not check it" in f for f in found)


def test_a_code_renamed_on_the_page_fails():
    found = rules_sync.check_all(with_page(PAGE.replace("`INVALID_DOMAIN` |", "`BAD_DOMAIN` |", 1)))
    assert any("the page gives DQ-02 the code BAD_DOMAIN" in f for f in found)
    assert any("records INVALID_DOMAIN under DQ-02, which the page does not give it" in f for f in found)


def test_a_block_rule_turned_into_a_flag_on_the_page_fails():
    row = page_row("DQ-05")
    found = rules_sync.check_all(with_page(PAGE.replace(row, row.replace("| Block |", "| Flag |"))))
    assert any("HEADCOUNT_NOT_NUMERIC is a Flag code on the page, but the workflow records it as a Block" in f for f in found)


def test_a_quarantine_column_removed_from_the_page_fails():
    found = rules_sync.check_all(with_page(PAGE.replace("| `reason_detail` |", "| reason detail (removed) |")))
    assert any("writes the quarantine column reason_detail, which is not on the rules page" in f for f in found)


# ---- the other direction: the workflow changes, the page does not


def drop_rule(code, rule_id):
    """Take one rule's part out of the DQ Checks code: its comment and everything to the next rule."""
    start = code.index(f"  // {rule_id}:")
    end = code.index("  // ", start + 5)
    return code[:start] + code[end:]


def test_a_rule_removed_from_the_workflow_fails():
    found = rules_sync.check_all(with_rules_code(lambda c: drop_rule(c, "DQ-05")))
    assert sum("DQ-05 is on the rules page but the workflow does not check it" in f for f in found) == 3


def test_a_rule_removed_from_one_workflow_only_names_that_workflow():
    found = rules_sync.check_all(with_rules_code(lambda c: drop_rule(c, "DQ-01"), rels=("n8n/workflow-v2-salesforce.json",)))
    assert found and all(f.startswith("n8n/workflow-v2-salesforce.json: ") for f in found)


def test_a_code_the_workflow_records_but_the_page_does_not_have_fails():
    found = rules_sync.check_all(with_rules_code(lambda c: c.replace("flags.push('INDUSTRY_UNMAPPED')", "flags.push('INDUSTRY_UNKNOWN')")))
    assert any("records INDUSTRY_UNKNOWN under DQ-06 / DQ-07" in f for f in found)


def test_a_block_quietly_turned_into_a_flag_in_the_workflow_fails():
    found = rules_sync.check_all(with_rules_code(lambda c: c.replace("reasonCodes.push('DUPLICATE_IN_BATCH')", "flags.push('DUPLICATE_IN_BATCH')")))
    assert any("DUPLICATE_IN_BATCH is a Block code on the page, but the workflow records it as a Flag" in f for f in found)


def test_a_rule_comment_removed_from_the_workflow_fails():
    """The code still runs, but nobody can see which rule it is: its codes land under the rule before it."""
    found = rules_sync.check_all(with_rules_code(lambda c: c.replace("  // DQ-05: employee_count numeric when present\n", "")))
    assert any("DQ-05 is on the rules page but the workflow does not check it" in f for f in found)
    assert any("records HEADCOUNT_NOT_NUMERIC under DQ-02" in f for f in found)


def test_an_upsert_that_no_longer_uses_the_domain_key_fails():
    def read(rel):
        text = TREE(rel)
        return text.replace("idProperty: 'clay_domain_key'", "idProperty: 'domain'") if rel == V1 else text
    assert any("DQ-04 says the write is an upsert keyed on clay_domain_key" in f for f in rules_sync.check_all(read))


def test_the_pre_push_check_runs_the_rules_check_on_the_commit():
    source = (REPO / "scripts" / "prepush_check.py").read_text(encoding="utf-8")
    assert "rules_sync" in source and 'git_reader("HEAD", REPO)' in source
    assert "rules_sync.py" in prepush_check.__doc__


@pytest.mark.parametrize("rel", rules_sync.WORKFLOWS[1:])
def test_the_routing_workflows_still_copy_version_1s_rules_node_unchanged(rel):
    """Why one rules page covers three files: chapters 2 and 4 copy version 1's node byte for byte."""
    def dq(r):
        return next(n for n in json.loads(TREE(r))["nodes"] if n["name"] == "DQ Checks")["parameters"]
    assert dq(rel) == dq(V1)
