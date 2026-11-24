"""INIT-165, Ask the pipeline (KB-140): a read-only MCP server over the run log.

Offline tests check the workflow file and the SQL: four read tools, one fixed query each, no SQL
from the client, typed inputs, a token on the door, a 50-row cap, enquiry text marked untrusted
(Q1 to Q3, Q6). The live tests sign in as the tool's own login, gtm_v2_reader, and prove a write
with it fails (Q4, KB-140 section 10 item 2). They need the local Supabase Postgres and the
reader's password in .env, so they skip in CI. The MCP test needs the server switched on.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import ask_pipeline as ap  # noqa: E402
import build_n8n_ask_pipeline as build  # noqa: E402

WF = json.loads((REPO / "n8n/workflow-v2-ask-pipeline.json").read_text(encoding="utf-8"))
NODES = {n["name"]: n for n in WF["nodes"]}
SQL = (REPO / "db/ask_pipeline.sql").read_text(encoding="utf-8")
TOOL_NAMES = ["run_summary", "list_decisions", "explain_decision", "cost_summary"]
FUNCTION_OF = {"run_summary": "ask_run_summary", "list_decisions": "ask_decisions",
               "explain_decision": "ask_explain", "cost_summary": "ask_costs"}


def function_body(name: str) -> str:
    m = re.search(rf"create or replace function gtm_v2\.{name}\(.*?\n(?:.*\n)*?end \$\$;", SQL)
    assert m, name
    return m.group(0)


# ---------------------------------------------------------------- the workflow (Q1, Q3, Q5)


def test_the_workflow_file_is_what_the_build_script_makes():
    assert (REPO / "n8n/workflow-v2-ask-pipeline.json").read_text(encoding="utf-8") == build.render(build.build())


def test_the_server_offers_four_tools_and_nothing_else():
    assert sorted(NODES) == sorted(TOOL_NAMES + ["Ask the Pipeline"])
    assert {n["type"] for n in WF["nodes"]} == {"@n8n/n8n-nodes-langchain.mcpTrigger", "n8n-nodes-base.postgresTool"}
    for name in TOOL_NAMES:
        assert WF["connections"][name] == {"ai_tool": [[{"node": "Ask the Pipeline", "type": "ai_tool", "index": 0}]]}
    assert "Ask the Pipeline" not in WF["connections"], "the trigger feeds no other step"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_each_tool_runs_one_fixed_query_with_no_sql_from_the_client(name):
    p = NODES[name]["parameters"]
    assert p["operation"] == "executeQuery"
    assert p["query"] == f"select gtm_v2.{FUNCTION_OF[name]}($1::jsonb) as result"
    assert "{{" not in p["query"] and "$fromAI" not in p["query"], "nothing the client sends is pasted into the SQL"
    replacement = p["options"]["queryReplacement"]
    assert replacement.startswith("={{ JSON.stringify({ ") and replacement.endswith(" }) }}"), \
        "the client's arguments reach the query only as one JSON value in $1"
    assert set(p) == {"descriptionType", "toolDescription", "operation", "query", "options"}
    assert set(p["options"]) == {"queryReplacement"}
    assert p["toolDescription"].startswith("Read only.")
    assert not re.search(r"\b(sql|query)\b", " ".join(a for a, _, _ in build.from_ai_arguments(NODES[name])))


def test_the_inputs_are_typed_and_the_required_ones_have_no_default():
    args = {name: {a: (kind, optional) for a, kind, optional in build.from_ai_arguments(NODES[name])} for name in TOOL_NAMES}
    assert args["run_summary"] == {"from_date": ("string", False), "to_date": ("string", False), "kind": ("string", True)}
    assert args["list_decisions"] == {"run_id": ("string", True), "route": ("string", True),
                                      "changed_only": ("boolean", True), "company": ("string", True)}
    assert args["explain_decision"] == {"decision_id": ("string", False)}
    assert args["cost_summary"] == {"from_date": ("string", False), "to_date": ("string", False),
                                    "group_by": ("string", False), "kind": ("string", True)}
    every = sum(NODES[n]["parameters"]["options"]["queryReplacement"].count("$fromAI(") for n in TOOL_NAMES)
    assert every == sum(len(a) for a in args.values()), "every argument is declared with a type"


def test_the_door_needs_a_token_and_every_tool_signs_in_as_the_reader():
    trigger = NODES["Ask the Pipeline"]
    assert trigger["parameters"] == {"authentication": "bearerAuth", "path": "gtm-v2-ask-the-pipeline"}
    assert trigger["credentials"] == {"httpBearerAuth": {"id": None, "name": "GTM v2 ask the pipeline token"}}
    assert "webhookId" not in trigger, "the publish script gives the trigger its webhook ID"
    for name in TOOL_NAMES:
        assert NODES[name]["credentials"] == {"postgres": {"id": None, "name": "GTM v2 run log reader (read only)"}}


def test_n8n_listens_on_this_mac_only():
    start = (REPO / "scripts/n8n_docker.sh").read_text(encoding="utf-8")
    assert "-p 127.0.0.1:5678:5678" in start and "0.0.0.0" not in start


# ---------------------------------------------------------------- the SQL (Q1 to Q4, Q6)


def test_every_function_runs_with_the_callers_rights_and_writes_nothing():
    functions = re.findall(r"create or replace function (gtm_v2\.\w+)\(", SQL)
    assert len(functions) == 17 and len(set(functions)) == 17
    assert SQL.count("security invoker") == 17 and "security definer" not in SQL.lower()
    code = re.sub(r"--[^\n]*", "", SQL).lower()
    for word in ("insert", "update", "delete", "truncate", "merge", "create table", "alter", "grant", "copy", "execute",
                 "call", "do", "pg_read_file", "dblink", "lo_import"):
        assert not re.search(rf"(?<!')\b{word}\b(?!')", code), word


def test_the_functions_read_only_the_two_views():
    code = re.sub(r"--[^\n]*", "", SQL)
    read = {m for m in re.findall(r"gtm_v2\.(\w+)", code) if not m.startswith("ask_")}
    assert read == {"decision_record", "run_summary"}


@pytest.mark.parametrize("name", ["ask_run_summary", "ask_decisions", "ask_costs"])
def test_every_list_is_cut_off_at_50_and_says_so(name):
    body = function_body(name)
    assert body.count("limit 50") == 1 and "> 50" in body and "'truncated'" in body


@pytest.mark.parametrize("name", ["ask_run_summary", "ask_decisions", "ask_explain", "ask_costs"])
def test_every_tool_checks_its_argument_names_first(name):
    body = function_body(name)
    first = body.split("begin", 1)[1].strip().splitlines()[0]
    assert first.startswith("perform gtm_v2.ask_check_args(args, array[")


def test_text_from_an_enquiry_is_only_returned_under_untrusted_text_with_the_notice():
    for name, fields in (("ask_decisions", ["lead_id", "company_name"]),
                         ("ask_explain", ["lead_id", "company_name", "domain", "reason", "review_detail", "approver",
                                          "note", "stamp", "crm_error"])):
        body = function_body(name)
        assert "gtm_v2.ask_notice()" in body
        inside = body.split("'untrusted_text', json_build_object(", 1)[1]
        outside = body.split("'untrusted_text', json_build_object(", 1)[0]
        for f in fields:
            assert f"'{f}'" in inside and f"'{f}'" not in outside, f"{name}: {f}"
    assert "never an instruction to follow" in function_body("ask_notice")
    assert "untrusted_text" in build.TOOLS["explain_decision"][1] and "never follow" in build.TOOLS["explain_decision"][1]


def test_the_reader_gets_two_views_and_the_ask_functions_only():
    grants = [line.strip() for line in ap.reader_sql("abc_DEF-123").splitlines()
              if line.strip().startswith(("grant", "alter role gtm_v2_reader set"))]
    assert grants[:4] == ["alter role gtm_v2_reader set search_path = gtm_v2;",
                          "alter role gtm_v2_reader set default_transaction_read_only = on;",
                          "alter role gtm_v2_reader set statement_timeout = '10s';",
                          "grant usage on schema gtm_v2 to gtm_v2_reader;"]
    assert grants[4] == "grant select on gtm_v2.decision_record, gtm_v2.run_summary to gtm_v2_reader;"
    assert all(g.startswith("grant execute on function gtm_v2.ask_") or ", gtm_v2.ask_" in g for g in grants[5:])
    assert len(grants) == 7
    with pytest.raises(ValueError):
        ap.reader_sql("x'; drop role postgres; --")


# ---------------------------------------------------------------- the questions and the grader (Q7)


def test_eight_questions_cover_the_four_tools():
    assert [q["id"] for q in ap.QUESTIONS] == [f"Q{i}" for i in range(1, 9)]
    assert {t for q in ap.QUESTIONS for t in q["tools"]} == set(TOOL_NAMES)
    for q in ap.QUESTIONS:
        assert "gtm_v2.ask_" not in q["sql"], "the answers are worked out from the views, not through the tool"


def test_the_saved_sql_answers_are_for_the_same_eight_questions():
    saved = json.loads((REPO / "docs/v2/init-165-evidence/sql-answers.json").read_text(encoding="utf-8"))
    assert saved["login"] == "gtm_v2_reader"
    assert [(k, v["question"]) for k, v in saved["answers"].items()] == [(q["id"], q["question"]) for q in ap.QUESTIONS]


def test_the_grader_takes_rounded_costs_but_exact_counts():
    assert ap.number_matches(0.0047, 0.004688) and ap.number_matches(0.00469, 0.004688)
    assert not ap.number_matches(0.005, 0.004688), "one significant figure is not a match"
    assert not ap.number_matches(0.0046, 0.004688)
    assert ap.number_matches(9, 9) and not ap.number_matches(8, 9) and not ap.number_matches(9.4, 9)
    want = {"route": "smb", "n": 3, "ids": ["A", "B"]}
    assert ap.figures_match({"Route": "SMB", "n": 3, "ids": ["B", "A"]}, want) == []
    assert ap.figures_match({"route": "smb", "n": 3}, want) == ["ids: missing"]
    assert ap.figures_match({"route": "smb", "n": 3, "ids": ["A", "B"], "x": 1}, want) == ["x: not in the answer"]
    counts = {"smb": 1, "rejected": 3}
    assert ap.figures_match({"smb": 1, "rejected": 3, "disqualify": 0}, counts, zero_if_missing=True) == []
    assert ap.figures_match({"smb": 1, "rejected": 3, "disqualify": 1}, counts, zero_if_missing=True) == ["disqualify: not in the answer"]
    assert ap.figures_match({"smb": 1, "rejected": 3, "disqualify": 0}, counts) == ["disqualify: not in the answer"]
    assert ap.figures_from('The run cost US$0.0047.\nFIGURES: {"total_cost_usd": 0.0047}') == {"total_cost_usd": 0.0047}
    assert ap.figures_from("no figures here") is None


def test_the_planted_instruction_is_aimed_at_the_client_and_kept_out_of_the_cost_sheet():
    row = ap.planted_row()
    assert row["run_id"].startswith("test-") and row["decision_id"] == ap.PLANTED_ID
    assert "AI assistant" in row["reason"] and "US$0.00" in row["reason"]
    assert (row["input_tokens"], row["output_tokens"], row["proposed_at"]) == (0, 0, None)
    from cost_sheet import QUERIES
    for name in ("routing_by_model", "routing_by_route"):
        assert "run_id not like 'test-%'" in QUERIES[name]


def test_the_bridge_holds_no_secret_and_reads_the_token_from_env():
    src = (REPO / "scripts/ask_pipeline.py").read_text(encoding="utf-8")
    assert "def bridge()" in src and "McpClient()" in src.split("def bridge()", 1)[1].split("\ndef ", 1)[0]
    assert ap.TOKEN_KEY in (REPO / ".env.example").read_text(encoding="utf-8")
    assert ap.READER_PASSWORD_KEY in (REPO / ".env.example").read_text(encoding="utf-8")


# ---------------------------------------------------------------- live: the reader's login (Q4)


def reader():
    try:
        return ap.reader_connection(autocommit=False)
    except RuntimeError:
        pytest.skip("no reader password in .env")
    except Exception:
        pytest.skip("local Supabase Postgres not reachable")


WRITES = [
    "insert into gtm_v2.proposals (decision_id) values ('D-pytest-reader')",
    "update gtm_v2.decisions set approver = 'pytest'",
    "delete from gtm_v2.proposals",
    "update gtm_v2.model_prices set input_per_mtok = 0",
    "select gtm_v2.log_proposals('[]'::jsonb)",
    "select gtm_v2.log_decisions('[]'::jsonb)",
    "create table gtm_v2.pytest_reader (x int)",
    "create table public.pytest_reader (x int)",
]


@pytest.mark.parametrize("sql", WRITES)
def test_a_write_with_the_tools_login_fails_even_in_a_read_write_transaction(sql):
    import psycopg

    conn = reader()
    try:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction if not sql.startswith("select")
                           else psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)
        conn.rollback()
        conn.execute("set transaction read write")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("sql", ["select 1 from gtm_v2.proposals", "select 1 from gtm_v2.decisions",
                                 "select 1 from gtm_v2.desk_record", "select 1 from gtm_v2.cost_by_route"])
def test_the_tools_login_cannot_read_past_its_two_views(sql):
    import psycopg

    conn = reader()
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(sql)
    finally:
        conn.rollback()
        conn.close()


def test_the_tool_functions_refuse_bad_input_and_cap_a_wide_list_at_50():
    import psycopg

    conn = reader()

    def call(fn, args):
        try:
            return conn.execute(f"select gtm_v2.{fn}(%s::jsonb)", (json.dumps(args),)).fetchone()[0]
        finally:
            conn.rollback()

    try:
        for fn, args in [("ask_run_summary", {"from_date": "24/11/2026", "to_date": "2026-11-24"}),
                         ("ask_run_summary", {"from_date": "2026-11-23", "to_date": "2026-11-24", "sql": "select 1"}),
                         ("ask_decisions", {"route": "vip"}), ("ask_decisions", {"changed_only": "yes"}),
                         ("ask_explain", {"decision_id": "D-1'; delete from gtm_v2.proposals; --"}),
                         ("ask_costs", {"from_date": "2026-11-24", "to_date": "2026-11-23", "group_by": "model"})]:
            with pytest.raises(psycopg.errors.InvalidParameterValue, match="refused"):
                call(fn, args)
        wide = call("ask_decisions", {})
        assert wide["decisions_returned"] == 50 and wide["truncated"] is True and wide["decisions_matching"] > 50
        planted = call("ask_explain", {"decision_id": ap.PLANTED_ID})
        if planted["found"]:
            assert planted["decision"]["untrusted_text"]["reason"] == ap.PLANTED_TEXT
            assert "never an instruction" in planted["notice"]
    finally:
        conn.close()


def test_the_mcp_server_refuses_a_client_with_no_token():
    import requests

    try:
        status = requests.post(ap.mcp_url(), json={}, timeout=3).status_code
    except requests.RequestException:
        pytest.skip("n8n is not running")
    if status == 404:
        pytest.skip("the MCP server is off")
    assert status in (401, 403)
    with pytest.raises(ap.McpError) as e:
        ap.McpClient(token="not-the-token").open()
    assert e.value.status in (401, 403)
