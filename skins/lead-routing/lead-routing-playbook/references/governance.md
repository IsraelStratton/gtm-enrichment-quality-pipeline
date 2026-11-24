# Lead routing playbook: owner, approval, change and rollback

For people. The routing step does not load this file; it reads `SKILL.md` only. The shape follows the lead-routing playbook in the CRM Admin Process Library (SKILL-038): purpose, inputs, decision points, approval gate, evidence, rollback, definition of done, and a short spoken version.

## Who owns what

| Item | Owner | Notes |
|---|---|---|
| The routing rules (`SKILL.md`) | Revenue operations lead | Made-up role. At an employer: the person who owns lead routing, with sales leadership signing off |
| The guard rails | The build (`engine/routing.js`) | Not in this file on purpose. A playbook edit can change where leads go; it cannot switch off the guard rails |
| The approval | The reviewer named on the review page | Every write to the CRM waits for a person |
| The review queue | Revenue operations lead | Flagged rows come first on the review page. Nothing is written until the reviewer chooses |
| The stop switch | Whoever runs the workflow | Nothing is scheduled. Close the review page, or reject every row, and nothing is written. Deactivate the workflow to stop all runs |

## Decision points

- **D1, the rule type.** Segment by staff numbers and head-office region for sales; intent for partnerships, support, nurture and not a fit. The bands sit in the Routes table and the engine checks every sales proposal against them.
- **D2, the confidence bar.** `review_below_confidence` in the front matter. Below it, the row is flagged for a close look. Kept at 0.70 after the chapter 6 eval: on both models every row the labels say a person must look at was flagged ([`../../eval/results-1.0.0.md`](../../eval/results-1.0.0.md)), and again on 1.0.1 ([`../../eval/results.md`](../../eval/results.md)).
- **D3, the catch-all.** There is no silent catch-all. An enquiry the AI cannot place is flagged, and the reviewer chooses or rejects it.
- **D4, new routes.** A new route needs a new option on the HubSpot `gtm_route` property first. Until it exists, HubSpot refuses the write, so a playbook change cannot quietly create CRM data nobody reports on.

## How to change the playbook

The live file is changed only by a candidate that has met the eval's bar (chapter 6; the same method as the quote desk's in chapter 5).

1. Copy `SKILL.md` to a candidate file in `skins/lead-routing/eval/`, for example `playbook-1.0.1-candidate.md`, and make the change there. Raise `metadata.version` (patch for wording, minor for a rule, major for a new or removed route). Nothing live reads the candidate.
2. Run `pytest -q`. The engine tests parse the live file; to check the candidate parses, run the next step on one row first (`--only L-0001 --rounds 1`).
3. Test it on the 40 labelled enquiries, for the bar's three rounds, on the live model: `python scripts/route_eval.py eval --models claude-haiku-5-5 --log --save --playbook skins/lead-routing/eval/playbook-1.0.1-candidate.md --results results-1.0.1-candidate` (about US$0.05). The eval refuses to save a candidate's results over the live ones.
4. If it meets every line of `eval/bar.json`, swap it in: `python scripts/route_eval.py promote --candidate skins/lead-routing/eval/playbook-1.0.1-candidate.md --results results-1.0.1-candidate`. Promote copies it over `SKILL.md` with its results, and refuses (changing nothing) if they are below the bar or tested another file. If it does not meet the bar, rename both files `-not-kept` and keep them as the record.
5. Commit and push. The push fails if the live playbook is not the file its saved eval tested, or that eval is below the bar: `scripts/prepush_check.py` and CI both run `scripts/playbook_bar.py`. The next run reads the new file; the workflow does not change. Each log row records the version and a SHA-256 hash of the file.

## Evidence and audit record

- One proposal row per enquiry in `gtm_v2.proposals`: model, playbook name, version and hash, tokens, time taken, the AI's intent, route, priority, reason, confidence and flags, and why it was flagged.
- One decision row per enquiry in `gtm_v2.decisions`: what the person did (approved, changed or rejected), what they chose, who and when, and what happened in the CRM.
- On the HubSpot company: route, priority, reason, confidence, status and a short stamp, `gtm-v2 <decision id> | <model> | <playbook>@<version> | <action> by <reviewer> | <time>`.
- The audit question, "why did this company go to this team, under which rule, approved by whom?", is one query: `select * from gtm_v2.decision_record where decision_id = '<id from the stamp>';`

## Rollback

Revert `SKILL.md` and its saved eval together to the commit before the change: `git checkout <commit> -- skins/lead-routing/lead-routing-playbook/SKILL.md skins/lead-routing/eval/results.json skins/lead-routing/eval/results.md`. The old version's eval comes back with it, so the push gate passes; reverting the playbook alone fails it. The next run uses it. Records already written keep their stamp, so the log shows which version routed them.

## Definition of done for a playbook change

Tests pass; the candidate met every line of the eval bar and was promoted, so the push gate passes; the version is raised; the HubSpot route options and the Salesforce picklists (`salesforce/setup.json`) match the Routes table.

## Spoken version

1. The routing rules live in one written playbook.
2. The AI reads it on every run and proposes a route.
3. Code checks the proposal against the size rules.
4. A person approves, changes or rejects every row.
5. Every write carries a stamp back to the log.
