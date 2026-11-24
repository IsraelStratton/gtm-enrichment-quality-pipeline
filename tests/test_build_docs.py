"""KB-137 A4.2: the diagram and the step list are made from the workflow file by a script, and a test checks
the README's diagram matches a fresh run. The same for every other generated part of the README (the rules
table, the reach table, the eval results with the A2 line and the B2 table, the cost table) and for
docs/v2/workflows.md. CI runs this on every push; scripts/prepush_check.py runs it on the commit."""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_docs as bd  # noqa: E402
import clean_exports  # noqa: E402

TREE = bd.tree_reader()
WF = json.loads(TREE(bd.MAIN_WORKFLOW))
README = TREE(bd.README)
NODE_LINE = re.compile(r'^  (s\d+)(\(\["|\{\{"|\{"|\[\("|\[\["|\[")(\d+)\. ([^"]+)("\]\)|"\}\}|"\}|"\)\]|"\]\]|"\])$')
EDGE_LINE = re.compile(r"^  (s\d+) -->(?:\|([^|]+)\|)? (s\d+)$")


def test_the_readme_and_the_workflows_page_match_a_fresh_run():
    assert bd.check_all(TREE) == []


def test_the_readme_has_every_generated_part_once():
    for name in ("rules", "reach", "diagram", "steps", "results", "costs"):
        assert README.count(f"<!-- generated:{name} start") == 1 and README.count(f"<!-- generated:{name} end -->") == 1, name


def block(name, text=README):
    return text.split(f"<!-- generated:{name} start", 1)[1].split("-->", 1)[1].split(f"<!-- generated:{name} end -->", 1)[0]


def parse_diagram(text):
    nodes, edges = {}, []
    for line in text.splitlines():
        if m := NODE_LINE.match(line):
            assert m.group(1) == f"s{m.group(3)}", line
            nodes[m.group(1)] = m.group(4)
        elif m := EDGE_LINE.match(line):
            edges.append((m.group(1), m.group(3), m.group(2) or ""))
        else:
            assert line in ("```mermaid", "flowchart TD", "flowchart LR", "```") or line.startswith("  class"), line
    return nodes, edges


def test_the_readme_diagram_has_every_node_once_and_every_connection():
    nodes, edges = parse_diagram(block("diagram").split("```mermaid", 1)[1].split("```", 1)[0].join(["```mermaid", "```"]))
    assert sorted(nodes.values()) == sorted(n["name"] for n in WF["nodes"])
    assert len(edges) == len(bd.n8n_edges(WF))
    names = {v: k for k, v in nodes.items()}
    for src, dst, _, _ in bd.n8n_edges(WF):
        assert any(a == names[src] and b == names[dst] for a, b, _ in edges), (src, dst)
    assert ("s13", "s10", "next one") in edges, "the loop's way back is labelled"


def test_the_step_list_numbers_are_the_diagram_numbers():
    nodes, _ = parse_diagram(bd.n8n_diagram(WF))
    steps = re.findall(r"^(\d+)\. \*\*(.+?)\*\* \(", bd.n8n_steps(WF), re.M)
    assert [(f"s{i}", name) for i, name in steps] == sorted(nodes.items(), key=lambda kv: int(kv[0][1:]))


def test_the_run_order_reads_as_the_run_does():
    order, back = bd.run_order(WF)
    pos = {n: i for i, n in enumerate(order)}
    assert order[0] == "Upload CSV" and order[-1] == "Done"
    assert pos["Quarantine Table"] < pos["Read Playbook"], "the short quarantine branch before the main path"
    assert pos["Stamp Start"] < pos["Check Proposal"] < pos["Build Review"], "the loop's body before what follows it"
    assert pos["Review Page"] < pos["Apply Decisions"] < pos["HubSpot Batch Upsert"] < pos["Build Decision Log"]
    assert back == {("Check Proposal", "Loop Over Leads")}


@pytest.mark.parametrize("rel", clean_exports.EXPORTS["n8n"])
def test_every_n8n_export_is_drawn_and_listed_with_one_step_per_node(rel):
    wf = json.loads(TREE(rel))
    nodes, edges = parse_diagram(bd.n8n_diagram(wf))
    assert len(nodes) == len(wf["nodes"]) and len(edges) == len(bd.n8n_edges(wf))
    steps = bd.n8n_steps(wf).splitlines()
    assert len(steps) == len(wf["nodes"]) and all(not s.endswith("Code.") for s in steps)
    page = TREE(bd.WORKFLOWS_MD)
    assert f"[`{rel}`](../../{rel})" in page and bd.n8n_steps(wf) in page


def test_every_person_and_ai_step_is_marked_in_the_diagram():
    text = bd.n8n_diagram(json.loads(TREE("n8n/workflow-v2-quote-desk.json")))
    nodes, _ = parse_diagram(text)
    ids = {v: k for k, v in nodes.items()}
    assert f"class {ids['Review Page']} person" in text and f"class {ids['Claude Triage Step']} ai" in text


def test_a_change_to_the_workflow_file_makes_the_readme_out_of_date():
    wf = json.loads(TREE(bd.MAIN_WORKFLOW))
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "Stamp Start"]
    wf["connections"]["Loop Over Leads"]["main"][1] = [{"node": "Claude Routing Step", "type": "main", "index": 0}]
    wf["connections"].pop("Stamp Start")
    changed = json.dumps(wf)
    found = bd.check_all(lambda rel: changed if rel == bd.MAIN_WORKFLOW else TREE(rel))
    assert any(f.startswith("README.md is not what") for f in found)
    assert any(f.startswith("docs/v2/workflows.md is not what") for f in found)


def test_an_edit_by_hand_inside_a_generated_part_fails():
    edited = README.replace("| Route matches the label | 95% |", "| Route matches the label | 99% |", 1)
    assert edited != README
    assert bd.check_all(lambda rel: edited if rel == bd.README else TREE(rel)) == [
        "README.md is not what scripts/build_docs.py makes from the files: run it, do not edit by hand"]


def test_the_readme_rules_table_is_the_rules_pages():
    page = TREE("docs/rules.md").split("## Rule table", 1)[1].split("\n## ", 1)[0]
    for row in [line for line in page.splitlines() if line.startswith("| DQ-")]:
        assert row in block("rules")


def test_the_attack_line_and_the_b2_table_come_from_the_saved_results():
    """A2.3: the README gives the attack count and block rate. B2: a results table names the kept design and why."""
    live = json.loads(TREE("skins/lead-routing/eval/results.json"))
    s = live["models"][live["kept"]]["summary"]
    results = block("results")
    assert f"{s['attacks']} blocked, a block rate of {bd.pct(s['attacks_blocked'])}" in results
    desk = json.loads(TREE("skins/quote-desk/eval/results.json"))
    assert "| Measure | " + " | ".join(desk["designs"]) + " |" in results
    assert f"**Kept: {desk['kept']}.** {desk['kept_reason']}" in results


def test_the_cost_table_comes_from_the_cost_sheet():
    snap = json.loads(TREE("docs/v2/cost-sheet.json"))
    live = next(r for r in snap["routing_live_writes"] if r["model"] == "claude-haiku-5-5")
    from decimal import Decimal
    assert f"US${Decimal(str(live['total_cost_usd'])) / live['proposals']:.5f} a decision" in block("costs")


def test_the_pre_push_check_runs_the_docs_check_on_the_commit():
    source = (REPO / "scripts" / "prepush_check.py").read_text(encoding="utf-8")
    assert "build_docs.check_all(head)" in source
