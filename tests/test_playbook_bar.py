"""KB-137 A3.4: a push that takes a playbook's eval below its bar fails.

CI runs this on every push, on the pushed commit. scripts/prepush_check.py runs the same checks on HEAD
before a push leaves the Mac. The routing gate's own cases are in test_route_eval.py.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import playbook_bar  # noqa: E402
import prepush_check  # noqa: E402


def test_every_live_playbook_is_the_one_its_saved_eval_tested_and_meets_the_bar():
    assert playbook_bar.check_all(playbook_bar.tree_reader()) == []


def test_python_hashes_the_playbooks_as_the_engines_do():
    for rel, results in ((playbook_bar.REL["playbook"], playbook_bar.REL["results_json"]),
                         (playbook_bar.DESK["playbook"], playbook_bar.DESK["results_json"])):
        out = json.loads((REPO / results).read_text(encoding="utf-8"))
        assert playbook_bar.sha256((REPO / rel).read_text(encoding="utf-8")) == out["playbook"]["sha256"]


def test_a_quote_desk_playbook_edit_with_no_eval_fails_the_gate():
    tree = playbook_bar.tree_reader()
    edited = tree(playbook_bar.DESK["playbook"]) + "\nOne more line.\n"
    findings = playbook_bar.check_quote_desk(lambda rel: edited if rel == playbook_bar.DESK["playbook"] else tree(rel))
    assert len(findings) == 1 and "is not the one the saved eval tested" in findings[0]


def test_a_quote_desk_workflow_on_a_design_the_eval_did_not_keep_fails_the_gate():
    tree = playbook_bar.tree_reader()
    builder = tree(playbook_bar.DESK["builder"]).replace('DESIGN = "one_prompt"', 'DESIGN = "agent_team"')
    findings = playbook_bar.check_quote_desk(lambda rel: builder if rel == playbook_bar.DESK["builder"] else tree(rel))
    assert any("the workflow runs agent_team, but the saved eval kept one_prompt" in f for f in findings)


def test_the_pre_push_check_runs_the_playbook_bar():
    source = (REPO / "scripts" / "prepush_check.py").read_text(encoding="utf-8")
    assert 'check_all(git_reader("HEAD", REPO))' in source and prepush_check.__doc__.count("playbook_bar.py") == 1
