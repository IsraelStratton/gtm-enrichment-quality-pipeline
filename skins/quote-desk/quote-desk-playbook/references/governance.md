# Quote desk playbook: owner, approval, change and rollback

For people. The desk does not load this file; it reads `SKILL.md` only. The shape follows the quote-approval patterns in the CRM Admin Process Library (the CPQ approval-matrix and catalogue playbooks): purpose, inputs, decision points, approval gate, evidence, rollback, definition of done, and a short spoken version.

## Who owns what

| Item | Owner | Notes |
|---|---|---|
| The policy (`SKILL.md`): rules, limits, approvers, accepted reasons | Deal desk lead | Made-up role. At an employer: the deal desk or revenue operations, with finance signing off the discount bands and legal signing off the legal terms |
| The rule check | The build (`engine/quotes.js`) | The figures are worked out in code, not by the AI: the effective discount, the totals, the dates, the missing fields. The playbook sets the limits; it cannot switch the check off |
| The guard rails | The build (`engine/quotes.js`) | A quote with a `fix` rule cannot be approved, whatever the AI or the page says; the rep note and special terms are data; the customer draft is checked for codes, limits and figures that are not on the quote |
| The approval | The reviewer named on the review page | Every decision waits for a person, with a reason |
| The queue | Deal desk lead | Ordered by the date at risk, then deal size |
| The stop switch | Whoever runs the workflow | Nothing is scheduled. Close the review page and nothing changes. Deactivate the workflow, or the desk's Salesforce app, to stop it |

## Decision points

- **D1, what code checks and what the AI checks.** Anything that can be worked out from the figures is code (the `code` rows in the Rules table). The AI reads only what code cannot: the special terms, and whether the rep note gives a reason this playbook accepts.
- **D2, the discount bands.** The `Limit` column. Each discount rule's name carries its limit (`discount_over_20` has limit 20); the engine refuses a playbook where they differ, so a band cannot be moved without renaming the rule everyone reports on.
- **D3, fix before approve.** A `fix` rule sends the quote back. The review page offers only Reject for it, and the engine refuses an approval sent any other way.
- **D4, the confidence bar.** `review_below_confidence` in the front matter. Below it the quote is marked for a close look; it is still decided by a person either way.
- **D5, the queue order.** The date at risk (the earlier of the quote's expiry and the deal's close), then deal size: so a small quote about to lapse is not starved by a large one that can wait (KB-136 section 6.5).

## How to change the playbook

1. Edit `SKILL.md` on a branch. Raise `metadata.version` (patch for wording, minor for a rule or limit, major for a new or removed rule).
2. Run `pytest -q`. The engine tests parse the file and fail on a broken table, a code rule the engine does not know, a limit that does not match its rule name, or a missing flag.
3. Run the eval on the 20 cases (`python scripts/quote_desk.py eval --design <kept design>`) and compare with the last results in `skins/quote-desk/eval/`.
4. Merge. The next run reads the new file; the workflow does not change. Each log row records the version and a SHA-256 hash of the file.

## Evidence and audit record

- One triage row per quote in `gtm_v2.desk_proposals`: design, model, playbook name, version and hash, the rules found by code and by the AI with evidence, the proposed action and reason, the two messages, confidence, flags, why it was flagged, the date at risk and deal size.
- One row per Claude call in `gtm_v2.desk_calls` (tokens, time), and one row per hand-off between agents in `gtm_v2.handoffs`: from, to, what was asked, why, the evidence returned, confidence, and the call's tokens and cost.
- One decision row per quote in `gtm_v2.desk_decisions`: approved or rejected, the reason, who and when, what happened in Salesforce, and that the owner was told.
- On the quote: status, the desk reason and a short stamp, `gtm-v2-desk <decision id> | <design> | <model> | <playbook>@<version> | <action> by <reviewer> | <time>`.
- The audit question, "why was this quote approved, under which rule, by whom?", is one query: `select * from gtm_v2.desk_record where decision_id = '<id from the stamp>';`

## Rollback

Revert `SKILL.md` to the previous version in git. The next run uses it. Quotes already decided keep their stamp, so the log shows which version triaged them.

## Definition of done for a playbook change

Tests pass; the eval on the 20 cases still meets its bar; the version is raised.

## Spoken version

1. The deal desk policy lives in one written playbook.
2. Code works out the figures and the rules they break.
3. The AI reads the special terms and the rep's reason, and proposes approve or reject.
4. A person decides every quote, with a reason.
5. The quote carries a stamp back to the log, and the owner gets the reason and a draft reply.

## Change log

| Version | Date | Change | Why |
|---|---|---|---|
| 1.0.0 | 24/11/2026 | First version | Chapter 5 |
| 1.0.1 | 24/11/2026 | **Not kept: failed the bar, rolled back to 1.0.0 the same hour.** The reject-draft rule described what to say instead of giving the words ("it promises no price, discount, term or date"), and both messages were to be in the agent's own words | Tried on Israel's yes to stop a false mark: the 1.0.0 rule gave exact words, the agents copied them, and the guard that flags eight words in a row from the instructions marked Q-0011 in run `n8n-8794` and 19 of 180 eval triages. The marks fell from 34 to 12, but the kept design then rejected Q-0019 in 3 of 3 rounds: it read the attacker's request to promise 40% as a breach of the quote. The eval caught it before any live run. Text and results: `eval/playbook-1.0.1-not-kept.md`, `eval/results-1.0.1-not-kept.md` |
