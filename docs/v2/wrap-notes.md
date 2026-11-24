# Wrap notes: the README, documents kept in step, the control sheet, clean exports, walk-throughs

KB-135 section 0b (the wrap) and KB-137 section 6 (the control sheet, A1.5 to A1.7, and documents in step, A4). Built 24/11/2026 on the `v2` branch. Not in this session, on Israel's ruling: clips, videos and the merge to `main`.

## Done when

KB-135 section 6 item 4, KB-137 section 10 items 2, 3, 5 and 7, KB-138 section 11 item 4, and the session's brief.

| # | Done when | State |
|---|---|---|
| 1 | The README shows version 2, with the diagram, the cost table and the results, and keeps a "version 1 results" section | Done: [`README.md`](../../README.md). The version 1 figures the hub quotes are kept word for word |
| 2 | B2's results table is in the README, naming the kept design and why (KB-137 B2) | Done: the README's evals, made from [`skins/quote-desk/eval/results.json`](../../skins/quote-desk/eval/results.json) |
| 3 | The attack count and block rate are in the README (KB-137 A2.3) | Done: "7 attack rows of 7 kinds, 3 rounds each: 21 of 21 blocked, a block rate of 100%", made from the live results file |
| 4 | A README section for the Agentforce routing explainer (KB-138 section 11 item 4) | Done. The clip waits, with every other clip, for Israel's ruling |
| 5 | The diagram and the step list are made from the workflow file by a script, and a test checks the README matches a fresh run (A4.2) | Done: [`scripts/build_docs.py`](../../scripts/build_docs.py), [`workflows.md`](workflows.md), `tests/test_build_docs.py` |
| 6 | A test on every push fails when the rules page and the workflow disagree, either way; removing a rule from either side fails the push (A4.1) | Done: [`scripts/rules_sync.py`](../../scripts/rules_sync.py) in the pre-push check, and `tests/test_rules_sync.py` in CI, with both directions shown |
| 7 | The control sheet fits one page, every line points to a file, a test or a log row, and it states no legal conclusion (A1.5, A1.6) | Done: [`control-sheet.md`](control-sheet.md), held to it by `tests/test_control_sheet.py`. **Israel's read-through is still to do** (KB-137 section 6) |
| 8 | One table matches process, playbook, agent or tool, approval point, owner and eval (A1.7) | Done: the AI register on the control sheet |
| 9 | Clean exports of the n8n workflows, the Make blueprint and the Zapier builds | Done for n8n and Make, and for Zapier as an as-built record. **Zapier's own export file is not in yet**: it needs COURSES 2ND (below) |
| 10 | Walk-throughs by role, 90 seconds and five minutes each, opening on the data rules | Done: [`walk-throughs.md`](walk-throughs.md). Spoken wording goes through the Say-Aloud Method on the job-search side |

## What was built

| Item | Where |
|---|---|
| The README for version 2, its six generated parts between markers | [`README.md`](../../README.md) |
| The docs generator: diagrams and step lists from every workflow export, the README's generated parts | [`scripts/build_docs.py`](../../scripts/build_docs.py), [`workflows.md`](workflows.md) |
| The rules-page check | [`scripts/rules_sync.py`](../../scripts/rules_sync.py) |
| The clean-export check, and cleaners for raw n8n and Zapier files | [`scripts/clean_exports.py`](../../scripts/clean_exports.py) |
| The quarantine table ID, which all three n8n files with the data rules held, now a placeholder found by name when published | [`n8n/workflow.json`](../../n8n/workflow.json); [`scripts/n8n_publish_routing.py`](../../scripts/n8n_publish_routing.py) |
| The run-once tracker workflow, exported clean from n8n for the first time | [`slice/n8n/create-tracker-workflow.json`](../../slice/n8n/create-tracker-workflow.json) |
| The Zapier builds as clean data: the Table, the Form, the three Zaps step by step, the MCP server | [`slice/zapier/zap-builds.json`](../../slice/zapier/zap-builds.json) |
| The one-page control sheet; the connection register moved to its own page | [`control-sheet.md`](control-sheet.md), [`connections-and-reach.md`](connections-and-reach.md) |
| The walk-throughs | [`walk-throughs.md`](walk-throughs.md) |
| The pre-push check now also runs the rules check, the export check and the docs check on the commit | [`scripts/prepush_check.py`](../../scripts/prepush_check.py) |
| Every variable name the scripts read, with no values | [`.env.example`](../../.env.example) |
| Tests: the docs, the rules page, the exports, the control sheet, the data table lookup | `tests/test_build_docs.py`, `tests/test_rules_sync.py`, `tests/test_clean_exports.py`, `tests/test_control_sheet.py`, `tests/test_n8n_publish_routing.py` |

## Proved

- **The rules check, both ways.** On today's files it passes for all three workflows that run the rules. Taking DQ-05 out of the rules page fails it; taking DQ-05 out of the workflow fails it; so do a renamed code, a Block turned into a Flag on either side, a removed rule comment, a dropped quarantine column, and an upsert that no longer uses the domain key. Each case is a test.
- **The docs check.** The README's generated parts and the workflows page match a fresh run. Removing one node from the chapter 2 workflow file makes both out of date, and an edit by hand inside a generated part fails.
- **The exports.** All eight are clean against every pattern, and on this Mac against every value in `.env` and the private list. Each kind of leak, planted in a copy, is caught.
- **The live workflows are still in step** after the data table placeholder: `n8n_publish_routing.py --check` for the HubSpot, Salesforce and quote desk workflows, each "In step", with the table found by name. No live workflow was changed.
- **Every relative link and anchor** in the repo's pages resolves, after the control sheet's register moved.

## Found on the way

- **A tool ID was in three public files.** n8n's quarantine data table ID sat in version 1's workflow and both routing workflows that copy its rules node, and it has been on `main` since version 1. The files now hold a placeholder, and the ID is on the private list so the pre-push check refuses it. It stays in the git history: removing it would mean rewriting history, which is Israel's call. On its own the ID reaches nothing: n8n listens on this Mac only.
- **The control sheet's draft was a connection register, not one page.** It became [`connections-and-reach.md`](connections-and-reach.md), and the one-page sheet points to it for practice 3. Notes and guides that meant the connection rows now link there.

## Changed from spec

| Spec | What was built | Why |
|---|---|---|
| KB-135 step 7: "README, diagram" | Six parts of the README are generated, not only the diagram: the rules table, the reach table, the step list, the evals and the costs | So no figure in the README can drift from the file it came from, the same rule as the cost sheet (A5.1) |
| KB-137 A4.2: "the diagram and the step list are made from the workflow file" | From every export, not only the routing workflow: n8n, Make and the Zapier record | One page shows every build, and a test covers each |
| "Clean exports of the Zapier builds" | An as-built record in clean JSON, plus a cleaner ready for Zapier's own export | Zapier emails its export to the account owner, which is a click in Israel's Zapier settings: a COURSES 2ND step |
| KB-137 A1.5: one control sheet | The one-page sheet, with the connection register as its detail page | The register alone was several pages long; one page cannot also hold every connection's reach |

## How it works (walk-through)

1. **The README is partly written by a script.** Six parts sit between markers. `scripts/build_docs.py` reads the rules page, the workflow files, the eval results and the cost sheet, and writes those parts. Everything else is written by hand.
2. **The diagrams come from the workflow files.** For each n8n workflow the script reads its steps and connections, puts the steps in the order a run reaches them, and draws them. The step list uses the same numbers, with words taken from each step's own code comment or settings. A person's approval step gets a thick border; the AI step a dashed one.
3. **The rules page and the workflow are checked against each other.** The script reads the rule table on the rules page and the rule comments in the workflow's code. Every rule must be on both, with the same reason codes and the same type. Take a rule out of either one and the push is refused.
4. **The exports are checked for anything private.** Every workflow file is scanned for addresses, keys, hosts, usernames and IDs, and on the Mac for every private value too. Credentials and tables are named in the files and found by name when a workflow is imported.
5. **The control sheet is held to its own rule.** A test reads every line, follows every link, test name and log view on it, and fails if one does not exist, if the page grows past one page, or if it ever states a legal conclusion.
6. **All of it runs twice:** in the pre-push check on the Mac, on the commit being pushed, and in CI on every push.

**Say it in one line.** "The documents are checked against what runs on every push, so they cannot quietly go out of date."

**The "it went wrong" story for the wrap.** "Writing the export check, the first run found a tool ID in three public workflow files: the quarantine table's ID from version 1, copied into both routing workflows. It reaches nothing on its own, but it should not have been there. The files now name the table and the publish script finds it by name, and the check refuses the ID on every push."

## Still to do, outside this session

- **Israel:** the read-through of the control sheet (KB-137 section 6), and the merge to `main` when ready.
- **COURSES 2ND:** Zapier's own export file; the Notion records (below in the session summary).
- **After the merge:** the Google app's privacy link moves to `main` before the `v2` branch is deleted.
- **Clips and the video**, on Israel's ruling: the Zapier Pro approval (the trial ends 07/12/2026), the Agentforce explainer, and the version 2 demo.
- **The day-8 Google login test**, on or after 01/12/2026 ([chapter 3 notes](chapter-3-notes.md#day-8-test-of-the-google-login)).
