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
- **D2, the confidence bar.** `review_below_confidence` in the front matter. Below it, the row is flagged for a close look. The bar is set again after the first eval in chapter 6.
- **D3, the catch-all.** There is no silent catch-all. An enquiry the AI cannot place is flagged, and the reviewer chooses or rejects it.
- **D4, new routes.** A new route needs a new option on the HubSpot `gtm_route` property first. Until it exists, HubSpot refuses the write, so a playbook change cannot quietly create CRM data nobody reports on.

## How to change the playbook

1. Edit `SKILL.md` on a branch. Raise `metadata.version` (patch for wording, minor for a rule, major for a new or removed route).
2. Run `pytest -q`. The engine tests parse the file and fail on a broken table, a missing guard flag or an unknown band.
3. Run the routing step on the 40 enquiries (`python scripts/route_leads.py --file skins/lead-routing/enquiries.csv`) and compare with the last run. From chapter 6 the eval does this, and a push that drops below the bar fails.
4. Merge. The next run reads the new file; the workflow does not change. Each log row records the version and a SHA-256 hash of the file, so a change without a version bump still shows.

## Evidence and audit record

- One proposal row per enquiry in `gtm_v2.proposals`: model, playbook name, version and hash, tokens, time taken, the AI's intent, route, priority, reason, confidence and flags, and why it was flagged.
- One decision row per enquiry in `gtm_v2.decisions`: what the person did (approved, changed or rejected), what they chose, who and when, and what happened in the CRM.
- On the HubSpot company: route, priority, reason, confidence, status and a short stamp, `gtm-v2 <decision id> | <model> | <playbook>@<version> | <action> by <reviewer> | <time>`.
- The audit question, "why did this company go to this team, under which rule, approved by whom?", is one query: `select * from gtm_v2.decision_record where decision_id = '<id from the stamp>';`

## Rollback

Revert `SKILL.md` to the previous version in git. The next run uses it. Records already written keep their stamp, so the log shows which version routed them.

## Definition of done for a playbook change

Tests pass; the 40-enquiry run is no worse than the last one (from chapter 6, the eval bar); the version is raised; the HubSpot route options match the Routes table.

## Spoken version

1. The routing rules live in one written playbook.
2. The AI reads it on every run and proposes a route.
3. Code checks the proposal against the size rules.
4. A person approves, changes or rejects every row.
5. Every write carries a stamp back to the log.
