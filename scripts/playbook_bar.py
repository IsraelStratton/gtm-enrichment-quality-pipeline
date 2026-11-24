#!/usr/bin/env python3
"""The playbook bar (KB-137 A3.4): a push fails when a live playbook has no saved eval that meets its bar.

For each playbook the workflows read at run time:

  routing (chapters 2 and 4)  skins/lead-routing/lead-routing-playbook/SKILL.md
    - the saved eval (skins/lead-routing/eval/results.json) tested this exact file (same SHA-256),
      against these labels (enquiries.csv) and this bar (bar.json);
    - it holds every enquiry for at least the bar's rounds, for the model the workflow runs;
    - re-graded here from its stored answers, that model meets every line of the bar and is the one kept;
    - results.md is exactly what the eval script makes from results.json.
  quote desk (chapter 5)  skins/quote-desk/quote-desk-playbook/SKILL.md
    - the saved eval (skins/quote-desk/eval/results.json) tested this exact file;
    - the design the workflow runs is the one the eval kept, over every case and the bar's rounds,
      and its summary meets every line of the bar.

So a playbook edit cannot be pushed until it has been tested and met the bar: test a candidate from its
own file (route_eval.py eval --playbook ... --results ...), and swap it in with route_eval.py promote,
which runs these same checks first. The checks read files through a reader, so scripts/prepush_check.py
checks the commit being pushed (git show HEAD:path) and pytest checks the working tree, which in CI is
the pushed commit. This stops a mistake, not a person set on faking a results file: git shows every edit.

  python scripts/playbook_bar.py            # the working tree
  python scripts/playbook_bar.py --ref HEAD # a commit

Exit codes: 0 every playbook meets its bar, 1 a finding, 2 could not run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_eval import REL, live_model, read_labels, regrade, results_markdown  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DESK = {"playbook": "skins/quote-desk/quote-desk-playbook/SKILL.md", "results_json": "skins/quote-desk/eval/results.json",
        "bar": "skins/quote-desk/eval/bar.json", "cases": "skins/quote-desk/cases.json", "builder": "scripts/build_n8n_quote_desk.py"}
Reader = Callable[[str], "str | None"]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(read: Reader, rel: str, findings: list[str]):
    text = read(rel)
    if text is None:
        findings.append(f"{rel} is missing")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        findings.append(f"{rel} is not valid JSON")
        return None


def check_routing(read: Reader) -> list[str]:
    f: list[str] = []
    playbook, labels_text, bar_text, builder = (read(REL[k]) for k in ("playbook", "labels", "bar", "builder"))
    for rel, text in ((REL["playbook"], playbook), (REL["labels"], labels_text), (REL["bar"], bar_text), (REL["builder"], builder)):
        if text is None:
            f.append(f"{rel} is missing")
    out = _json(read, REL["results_json"], f)
    if f:
        return [f"routing: {x}" for x in f]
    bar = json.loads(bar_text)
    live = live_model(builder)
    if out["playbook"]["sha256"] != sha256(playbook):
        f.append(f"the live playbook ({sha256(playbook)[:12]}) is not the one the saved eval tested ({out['playbook']['sha256'][:12]}): "
                 "test the change as a candidate (route_eval.py eval --playbook <file> --results <name>) and promote it only if it meets the bar")
    if out.get("labels_sha256") != sha256(labels_text):
        f.append("enquiries.csv has changed since the saved eval: run the eval again")
    if out.get("bar_sha256") != sha256(bar_text):
        f.append("bar.json has changed since the saved eval: run the eval again")
    if live not in out["models"]:
        f.append(f"the saved eval did not test {live}, the model the workflow runs")
    else:
        rows = out["models"][live]["rows"]
        ids = [r["lead_id"] for r in read_labels(labels_text)]
        if out["rounds"] < bar["rounds"] or any(sorted(r["lead_id"] for r in rows if r["round"] == n) != sorted(ids)
                                                for n in range(1, out["rounds"] + 1)):
            f.append(f"the saved eval for {live} does not hold every enquiry for {bar['rounds']} rounds")
        fresh = regrade(out, bar)
        s = fresh["models"][live]["summary"]
        if not s["passes"]:
            f.append(f"{live} is below the bar on the saved eval: {', '.join(s['failed_lines'])}")
        elif fresh["kept"] != live:
            f.append(f"the eval keeps {fresh['kept']}, but the workflow runs {live}")
        if read(REL["results_md"]) != results_markdown(fresh):
            f.append("results.md is not what route_eval.py makes from results.json: re-save the eval, do not edit the page")
    return [f"routing: {x}" for x in f]


def check_quote_desk(read: Reader) -> list[str]:
    f: list[str] = []
    playbook, builder = read(DESK["playbook"]), read(DESK["builder"])
    for rel, text in ((DESK["playbook"], playbook), (DESK["builder"], builder)):
        if text is None:
            f.append(f"{rel} is missing")
    out, bar, cases = (_json(read, DESK[k], f) for k in ("results_json", "bar", "cases"))
    if f:
        return [f"quote desk: {x}" for x in f]
    m = re.search(r'^DESIGN = "([^"]+)"', builder, re.M)
    design = m.group(1) if m else None
    if out["playbook"]["sha256"] != sha256(playbook):
        f.append(f"the live playbook ({sha256(playbook)[:12]}) is not the one the saved eval tested ({out['playbook']['sha256'][:12]}): "
                 "test the change as a candidate (quote_desk.py eval --playbook <file> --results <name>)")
    if out.get("kept") != design or design not in out["designs"]:
        f.append(f"the workflow runs {design}, but the saved eval kept {out.get('kept')}")
    else:
        d = out["designs"][design]
        s = d["summary"]
        below = [k for k, line in bar["lines"].items() if s.get(k, -1) < line["min"]]
        if below:
            f.append(f"{design} is below the bar on the saved eval: {', '.join(below)}")
        if out["rounds"] < bar["rounds"] or len(d["cases"]) != len(cases["cases"]) * out["rounds"]:
            f.append(f"the saved eval for {design} does not hold every case for {bar['rounds']} rounds")
    return [f"quote desk: {x}" for x in f]


def check_all(read: Reader) -> list[str]:
    return check_routing(read) + check_quote_desk(read)


def tree_reader(root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        path = root / rel
        return path.read_text(encoding="utf-8") if path.exists() else None
    return read


def git_reader(ref: str, root: Path = REPO) -> Reader:
    def read(rel: str) -> str | None:
        out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=root, capture_output=True, check=False)
        return out.stdout.decode("utf-8") if out.returncode == 0 else None
    return read


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", help="check a commit (for example HEAD) instead of the working tree")
    args = ap.parse_args(argv)
    try:
        findings = check_all(git_reader(args.ref) if args.ref else tree_reader())
    except (KeyError, TypeError, ValueError) as e:
        print(f"CANNOT RUN a results file is not in the shape the eval writes: {type(e).__name__}: {e}")
        return 2
    for x in findings:
        print(f"FAIL {x}")
    if not findings:
        print("PASS every live playbook is the one its saved eval tested, and that eval meets the bar")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
