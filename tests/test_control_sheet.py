"""KB-137 A1.5 to A1.7: the control sheet is one page; every line on it points to a file, a test or a log row;
it states no legal conclusion and names who would decide at an employer; one table matches process, playbook,
agent or tool, approval point, owner and eval."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "docs/v2/control-sheet.md"
TEXT = SHEET.read_text(encoding="utf-8")
LINES = TEXT.splitlines()
SQL = "\n".join(p.read_text(encoding="utf-8") for p in (REPO / "db").glob("*.sql"))

LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
TEST_REF = re.compile(r"`(tests/[\w/]+\.py)::(\w+)`")
FILE_REF = re.compile(r"`((?:scripts|tests|docs|db|skins|salesforce|n8n|slice)/[\w./-]+\.\w+)`")
LOG_REF = re.compile(r"`(gtm_v2\.\w+)`")
PRACTICES = ["Decide who is accountable", "Understand impacts and plan accordingly", "Measure and manage risks",
             "Share essential information", "Test and monitor", "Maintain human control"]
LEGAL_CONCLUSIONS = re.compile(
    r"\b(complies|compliant|in compliance|is lawful|is unlawful|is exempt|does not apply|doesn't apply|is not covered|"
    r"is covered by|meets the (duty|law|requirement)|satisfies the (duty|law)|not required to|no disclosure is (needed|required))\b", re.I)


def evidence_lines():
    """Every table body row and every list item: the lines the sheet's rule covers."""
    out = []
    for i, line in enumerate(LINES):
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line) and i + 1 < len(LINES) and re.match(r"^\|[-| ]+\|$", LINES[i + 1]):
            continue  # a header row
        if (line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line)) or re.match(r"^(\d+\.|-) ", line):
            out.append(line)
    return out


def pointers(line):
    found = []
    for target in LINK.findall(line):
        if not target.startswith("http"):
            found.append(("file", target.split("#", 1)[0]))
    found += [("test", f"{f}::{name}") for f, name in TEST_REF.findall(line)]
    found += [("file", f"../../{f}") for f in FILE_REF.findall(line) if "::" not in f]
    found += [("log", name) for name in LOG_REF.findall(line)]
    return found


def resolves(kind, ref):
    if kind == "file":
        return (SHEET.parent / ref).resolve().exists()
    if kind == "test":
        f, name = ref.split("::")
        path = REPO / f
        return path.is_file() and re.search(rf"^def {name}\(", path.read_text(encoding="utf-8"), re.M) is not None
    return re.search(rf"create or replace (view|function|table) {re.escape(ref)}\b", SQL) is not None


def test_every_line_points_to_a_file_a_test_or_a_log_row():
    lines = evidence_lines()
    assert len(lines) >= 15
    bare = [line[:80] for line in lines if not pointers(line)]
    assert bare == [], "lines with no evidence:\n" + "\n".join(bare)


def test_every_pointer_on_the_sheet_resolves():
    broken = [f"{kind} {ref}" for line in LINES for kind, ref in pointers(line) if not resolves(kind, ref)]
    assert broken == []


def test_it_fits_one_page():
    """50 lines and 850 visible words. The word cap was 800 at the wrap; INIT-165 added a register line and a stop
    switch line (25/11/2026), and the cap went to 850 rather than cutting wording Israel had read through."""
    visible = re.sub(r"\]\([^)]+\)", "]", TEXT)
    visible = re.sub(r"`[^`]+`", "x", visible)
    assert len(LINES) <= 50 and len(re.findall(r"[A-Za-z0-9$%][\w$%.,'/-]*", visible)) <= 850


def test_it_is_laid_out_on_the_six_practices_in_order():
    found = re.findall(r"^\d+\. \*\*(.+?)\.\*\*", TEXT, re.M)
    assert found == PRACTICES
    assert "Guidance for AI Adoption" in TEXT.split("\n## ", 1)[0]


def test_it_holds_the_register_the_approval_points_the_stop_switches_and_the_disclosure_questions():
    headings = re.findall(r"^## (.+)$", TEXT, re.M)
    assert headings == ["The AI register (A1.7)", "The six practices", "Approval points and stop switches",
                        "The 10/12/2026 disclosure questions"]
    assert "| Process | Playbook | Agent or tool | Approval point | Owner | Eval |" in TEXT
    assert "| Workflow | Where a person decides | Proof | Stop switch |" in TEXT


def test_every_agent_with_a_role_card_is_on_the_register():
    register = TEXT.split("## The AI register", 1)[1].split("\n## ", 1)[0]
    for card in (REPO / "docs/v2/role-cards").glob("*.md"):
        assert f"](role-cards/{card.name})" in register, card.name


def test_it_states_no_legal_conclusion_and_names_who_would_decide():
    assert not LEGAL_CONCLUSIONS.search(TEXT), LEGAL_CONCLUSIONS.search(TEXT)
    assert "states no legal conclusion" in TEXT and TEXT.count("privacy lead") >= 2
    assert "All three tests must be met" in TEXT


def test_the_disclosure_duty_is_in_the_oaics_own_terms():
    """Israel's read-through, 24/11/2026: quote the OAIC, do not paraphrase it."""
    duty = TEXT.split("## The 10/12/2026 disclosure questions", 1)[1]
    assert '"make, or do a thing that is substantially and directly related to making, a decision"' in duty
    assert '"could reasonably be expected to significantly affect the rights or interests of an individual"' in duty
    assert "substantially help" not in duty and "significantly affect a person" not in duty


def test_the_checks_catch_a_line_with_no_evidence_and_a_broken_pointer():
    assert pointers("| A row | with | only words |") == []
    assert pointers("| A row | with [a source](https://example.org) |") == []
    assert not resolves("test", "tests/test_control_sheet.py::test_that_does_not_exist")
    assert not resolves("log", "gtm_v2.no_such_view") and resolves("log", "gtm_v2.decision_record")
    assert not resolves("file", "no-such-file.md")
