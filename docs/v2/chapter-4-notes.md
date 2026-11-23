# Chapter 4 notes: the same engine, on Salesforce

KB-135 section 0b, chapter 4: "Runs on your CRM": a second target in a developer org. KB-137 section 6 adds nothing to this chapter. Built 23/11/2026; the org set up, checked and run end to end 24/11/2026 (run `n8n-8791`).

## What chapter 4 adds

The chapter 2 workflow, unchanged up to the write, now has a twin that writes to Salesforce. The same data rules, the same playbook, the same AI step and guard rails, the same review page and the same run log; at the end, approved and changed rows become Salesforce Accounts instead of HubSpot companies, each with the same who-decided stamp.

```mermaid
flowchart LR
  A[CSV upload] --> B{Data rules<br/>version 1}
  B -- fails --> Q[(Quarantine)]
  B -- passes --> C[Playbook, AI step, guard rails<br/>the chapter 2 engine]
  C --> L1[(Log the proposals)]
  L1 --> R[Review page<br/>a person approves, changes or rejects]
  R --> H[(HubSpot upsert<br/>chapter 2 workflow)]
  R --> S[(Salesforce Account upsert<br/>chapter 4 workflow)]
  H --> L2[(Log the decisions<br/>crm_target names the CRM)]
  S --> L2
```

Drawn by hand for these notes. One run writes to one CRM: the workflow you start decides which.

## Done when (KB-135 gives no list for this chapter; these follow its section 6, item 1, and KB-137 A1, for the second target)

| # | Done when | State |
|---|---|---|
| 1 | The same engine writes to Salesforce, with nothing before the write changed, and a test shows the two workflows differ only in the write step | Done: `test_the_salesforce_workflow_differs_from_hubspot_only_in_the_write_step` |
| 2 | The org is set up from one file and checked against it, signed in as the workflow is, including what the login cannot do | Done 24/11/2026: [`salesforce/setup.json`](../../salesforce/setup.json), [`scripts/salesforce_setup_check.py`](../../scripts/salesforce_setup_check.py), 19 of 19 |
| 3 | A sample file runs end to end on Salesforce: rules, AI step, approval, Salesforce, log | Done 24/11/2026: run `n8n-8791`, 9 Accounts written, 3 rejected, 0 failed |
| 4 | Every Salesforce write carries the stamp (A1.1), one query from a stamp finds its record (A1.2), a changed row keeps both values (A1.3), rejected rows are never written | Done 24/11/2026: `check_run.py --latest --salesforce` 8 of 8; a stamp read from an Account found its record in one query |
| 5 | The login has least reach, and that is recorded on the control sheet | Done 24/11/2026: proved by the setup check, signed in as the workflow; [`control-sheet.md`](control-sheet.md) |
| 6 | Tests on every push; these notes with the walk-through | Done |

## What was built

| Item | Where |
|---|---|
| The engine knows two CRM targets. The decisions, stamps and review are the same for both; only the record shape, the batch limit and how the reply is read differ. Engine version 1.1.0 | [`engine/routing.js`](../../engine/routing.js): `CRM_TARGETS`, `salesforceRecord`, `applyDecisions(..., {target})`, `decisionLogRows` |
| The Salesforce workflow, 24 nodes, made by the same script from the same parts. Its only new node is "Salesforce Upsert": an sObject Collections upsert of Accounts on the external ID `Clay_Domain_Key__c`, up to 200 a call, each saved or refused on its own | [`n8n/workflow-v2-salesforce.json`](../../n8n/workflow-v2-salesforce.json), [`scripts/build_n8n_routing.py`](../../scripts/build_n8n_routing.py) |
| What the org needs, in one file: seven Account fields, the permission set, the integration user, the External Client App, the n8n credential | [`salesforce/setup.json`](../../salesforce/setup.json) |
| The org check: scope, who it runs as, fields, field access, and reach (no data object deletable; no Leads, Contacts, Opportunities, Cases, Quotes or custom objects; no new Users) | [`scripts/salesforce_setup_check.py`](../../scripts/salesforce_setup_check.py), [`scripts/salesforce_client.py`](../../scripts/salesforce_client.py) |
| `check_run.py --salesforce`: the chapter 2 run checks, read back from Salesforce | [`scripts/check_run.py`](../../scripts/check_run.py) |
| Import and drift check through the n8n API: credentials matched by name, the live copy compared with the file | [`scripts/n8n_publish_routing.py`](../../scripts/n8n_publish_routing.py) |
| The run log refuses an unknown CRM target, and each run shows which CRM it wrote to | [`db/run_log.sql`](../../db/run_log.sql): `decisions_crm_target_check`, `run_summary.crm_targets` |
| Setup steps, by who does them | [`chapter-4-build.md`](chapter-4-build.md) |
| Control sheet and role card | [`control-sheet.md`](control-sheet.md), [`role-cards/routing-agent.md`](role-cards/routing-agent.md) |

## Proved

### On the real org, 24/11/2026

COURSES 2ND did the Setup clicks (parts A to D and F of [`chapter-4-build.md`](chapter-4-build.md)); Israel passed the verification code and pasted the key and secret into `.env` and the n8n credential. Then the Code chat:

- **The org check, 19 of 19** (`python scripts/salesforce_setup_check.py`), signed in exactly as n8n does: scope `api` only; runs as GTM Integration, active, read from Salesforce's identity URL; cannot see profiles or permission sets at all; API v64.0 offered (v68.0 is the newest); all seven fields as specified, with the picklist labels still the codes (optional); can create and edit the twelve fields the engine writes; Accounts read, create and edit, no delete; no right on Leads, Contacts, Opportunities, Cases, Quotes or the rest of the core list, or on any custom object; cannot create Users; can delete no data object; can edit no other custom field on Account. The first run of the check failed three rules: see "Limits met".
- **Published through the n8n API**: "GTM v2 chapter 4: route leads with approval (Salesforce)", 24 nodes, credentials found by name, the org's host filled in from `.env`; the form at `/form/gtm-v2-route-leads-salesforce` answers 200; the drift check reads the live copy back: in step. Chapter 2's live workflow: still in step.
- **One reviewed run, `n8n-8791`**, on `skins/lead-routing/sample_run.csv`: the data rules stopped 2 rows; the AI step proposed for 12 (4 flagged); on the review page, under the label "Claude for Israel (on his yes)" (Israel delegated the choices for this test run), 3 rejected (L-0031 spam, L-0034 and L-0036 attacks), 2 changed, 7 approved; **9 Accounts written to Salesforce, 0 failed**; AI cost US$0.004688 (US$0.00039 a decision). Nothing was written before the review page was submitted.
- **The same choices as `n8n-8790`, with one difference the review caught.** For L-0025 Marri Robotics (staff number unknown; the enquiry says only "a demo for our sales team") the AI proposed `enterprise_anz · medium` this time, where chapter 2's run proposed `smb · medium`. The build guide says to approve it only if its route looks right; an enterprise route with no size evidence does not, so it was changed to `smb · medium`, the value chapter 2 ended with. Both CRMs therefore hold the same nine routes, and the two runs differ only in L-0025's action (approved there, changed here). The model's variance on a row with a missing fact is exactly what the review page is for.
- **`python scripts/check_run.py --latest --salesforce`: 8 of 8.** Every proposal has a person's decision; 9 of 9 writes carry a stamp matching the log; the 3 rejected rows carry none and were not written; both changed rows keep the AI's and the person's values; every write went to Salesforce; all 9 Accounts, read back from Salesforce, carry the logged stamp, route, priority and status; no rejected row carries the run's stamp.
- **A stamp finds its record in one query (A1.2).** The stamp read from the Bluegum Retail Group Account, `gtm-v2 D-n8n8791-04 | claude-haiku-5-5 | lead-routing-playbook@1.0.0 | changed by Claude for Israel (on his yes) | 2026-11-23T23:01:21Z` (UTC), gave the full decision record with `--stamp`: the AI's proposal and reason, the person's change, tokens, cost, engine 1.1.0 and `crm_target salesforce`.
- **The run log keeps the CRMs apart**: `run_summary` shows `hubspot` for `n8n-8790` and `salesforce` for `n8n-8791`.
- **Chapter 2 on HubSpot, live again after the engine change.** The engine change was copied into chapter 2's live workflow on 23/11/2026 but not run live. Run `n8n-8792` on 24/11/2026: the same sample file and the same review choices; the AI again proposed `enterprise_anz` for L-0025 with no staff number, and the review changed it to `smb · medium`. 9 companies written to HubSpot (approved 7, changed 2), 3 rejected, 0 failed, US$0.004790; `check_run.py --latest --hubspot` 8 of 8. Both CRMs are now proved live on engine 1.1.0.

### Before the org existed, 23/11/2026

- **Tests: 234 pass** (176 at the end of chapter 2). New: the two workflows differ only in the write step; the Salesforce write is a PATCH upsert on the external ID, after the review page, with no other path to it; the demo file through every Code node of the Salesforce workflow gives the same decisions and stamps as HubSpot, now as Accounts; one refused record fails only its own row; a refused request fails every write with Salesforce's reason; records use only the fields in `setup.json`; the picklists hold exactly the playbook's codes and owner-team labels; the longest possible stamp fits the 255-character field; the org check fails on a missing field, a wrong type, an unrestricted picklist, a lost external ID, delete rights, any core object, or any other editable custom field; the client never returns the token or shows the secret; the drift check passes n8n's normalised copy and catches a hand edit. On 24/11/2026: **247**, with the check's new identity, User and delete rules, and the publish script's webhook ID.
- **The run log**: `setup_run_log.py` applied the new check and column; 9 of 9 login checks still pass.
- **Chapter 2 kept in step.** The engine change touches the five Code nodes chapter 2 runs, so its live copy was updated through the n8n API. First, the drift check read the live copy against the committed chapter 2 file: in step. Then no run was waiting or running; the update kept the trigger's webhook ID; the workflow was published; the form at `/form/gtm-v2-route-leads` answers 200; and the drift check against the new file: in step. HubSpot's write is unchanged: its tests pass as before.
- **n8n's own code, read in the container**: the built-in "Salesforce OAuth2 API" login has a hidden, fixed scope of `full refresh_token`; the general "OAuth2 API" login offers the client-credentials grant, fetches the token at first use and fetches a new one on a 401, even with "never error" set on the node.

## Choices made, and why

| Choice | Why |
|---|---|
| Accounts, not Leads | The data is company-level, as in version 1 (HubSpot companies). A Salesforce Lead needs a person's last name; making one up would break the "no personal data" rule |
| Upsert on an external ID, `Clay_Domain_Key__c` | The same key as HubSpot's `clay_domain_key`. A second run updates the Account instead of making a copy, so the run is safe to repeat. Salesforce's own uniqueness rule backs the data rule that removes duplicates by domain |
| A second workflow from the same script, not a switch inside one | Chapter 2's proven workflow keeps working if the Salesforce org is closed or switched off, and the claim "only the write differs" is a test, not a sentence |
| sObject Collections with `allOrNone: false` | One call for the batch, as with HubSpot, but each record is saved or refused on its own, so one bad row is logged as failed and the rest are written |
| Client-credentials flow, run as an API-only integration user | No person's login; no consent screen; no refresh token. The user's reach is one permission set: Accounts, read, create and edit, ten fields, no delete. Developer Edition gives one free Salesforce Integration licence for it |
| n8n's general OAuth2 login, not its Salesforce one | n8n's Salesforce login asks for `full refresh_token`, fixed in its code. With client credentials, the app decides the scope: `api` only |
| An External Client App, not a Connected App | Salesforce's current way to make an OAuth app, and the app can admit only holders of the permission set |
| The org's host stays private | It names the org. The committed workflow holds a placeholder; the publish script fills it in from `.env` when it imports |
| Industry is not written to Salesforce | Salesforce's standard Industry list is not HubSpot's, and version 1's mapping is HubSpot's. Writing raw values into an open picklist would make the data dirty, which version 1 exists to stop. A mapping is a later change |
| A missing confidence is sent as null | Salesforce keeps a field that is left out, so an old confidence would stay on the Account when the AI gave no usable proposal this time. HubSpot's write is left as chapter 2 proved it |
| The import goes through the n8n API | No clicks, credentials found by name, the trigger's webhook ID kept, and a drift check that reads the live copy back. The UI import's form-path problem from chapter 2 does not arise |

## Limits met

- **n8n drops parameters that equal a node's default** when it saves a workflow (for example a batch size of 1, or a Code node's default mode). A strict comparison of the live copy with the file therefore always failed. The drift check now treats a key the file sets and n8n does not hold as that default, and still requires every value n8n holds, and every Code node's JavaScript, to match.
- **Salesforce reports errors as a list** (`[{errorCode, message}]`), unlike Claude and HubSpot. The engine read it as "HTTP 401" with no reason until the harness test was written.
- **Salesforce suggests field names with the label's capital letters** (`GTM_route`). The steps say to overwrite them, and the setup check compares exact names.
- **The org check's first run failed three of its own rules, not the org.** (1) It read the user's profile and licence through `User.Profile`; the API-only integration user cannot see the Profile object at all, so the read failed. The check now reads who it runs as from Salesforce's identity URL, and counts "cannot see profiles or permission sets" as evidence (an administrator can see both); the profile and licence names are confirmed in Setup. (2) Salesforce's describe marks `User` as createable and editable for every user. Two create requests that could not succeed settled it: the first stopped on missing required fields, including `ProfileId`; the second, with every field filled in, was refused because this login cannot see `ProfileId`. So it cannot create users, and the check now tests exactly that; editing its own user record is something every Salesforce user can do. (3) "Can delete nothing in the org" is not possible in Salesforce: describe marks about ninety platform objects deletable for every user, for their own items (posts, files, notes, list views, sessions, sharing rows on records they own), and no permission set controls them. The check now fails on any data object (Account, User, the core list, any custom object) and lists the rest on every run.
- **n8n registers no webhook for a trigger without a webhook ID.** The first publish answered 404 at the form, and n8n's log said the webhook was not registered. The file ships the trigger without an ID on purpose (chapter 2: the editor's import copies a new ID over the Form Path), so the publish script now keeps the live trigger's ID or gives a new trigger a fresh one. A test covers both.
- **The app's built-in browser pane blocked the review page's submit** (`ERR_BLOCKED_BY_CLIENT`), so nothing was sent. The same 12 choices, checked against each row's own options, were posted to the review page's own address from the command line, as the page's script does. n8n's closing page also finishes the run with a POST that a real browser sends by itself; it was sent the same way. For the recorded demo, Israel uses his own browser.

## How it works (walk-through)

**In 90 seconds**, for a Salesforce-led room. Open on the data, as always.

1. The same company list, the same seven data rules, the same quarantine. Nothing dirty reaches the CRM, whichever CRM it is.
2. The same AI step proposes a team, a priority and a reason from a written playbook, and the same guard rails check it.
3. A person approves, changes or rejects every row. Only then does anything reach Salesforce.
4. Approved rows become Accounts, matched on the company's domain as an external ID, so running the file twice updates the Accounts instead of copying them.
5. Salesforce is reached by an API-only integration user with one permission set: Accounts, create and edit, ten fields, no delete. A script signs in as that user and proves what it cannot do.
6. Every Account carries the stamp: decision, model, playbook version, who decided, when. One query from the stamp finds the full record and the cost.

**In five minutes:** show the two workflows side by side in n8n; they differ in one node. Open `salesforce/setup.json`, then the Account in Salesforce with its stamp, then `check_run.py --stamp`. Then the control sheet row: why not n8n's own Salesforce login (`full` scope), and why not an admin's login.

**The "it went wrong" story for this chapter:** the first drift check said every node of chapter 2's live workflow had changed, though nothing had. n8n leaves out any setting that equals its default when it saves, so a byte-for-byte comparison could never pass. The check now knows that one rule and nothing more: every value n8n holds must still match the file, and the code must match in full.

**A second one, for a Salesforce room:** the least-reach check failed on the real org: it said the integration user could create Users and delete ninety kinds of record. Instead of loosening the check, two create requests that could not succeed showed what Salesforce really allows: the user cannot create users, because it cannot see `ProfileId`, and the "deletable" objects are each user's own posts, files and notes, which every Salesforce user has. The check now tests the real risk (no data object deletable, no new users) and lists the rest on every run.

## Demo checklist

- n8n started with `scripts/n8n_docker.sh`; both routing workflows published.
- `python scripts/salesforce_setup_check.py` passes on the day.
- The Salesforce form at http://localhost:5678/form/gtm-v2-route-leads-salesforce; `skins/lead-routing/sample_run.csv` ready.
- A reviewer label, not a personal name, on the review page in a recording. The org's host is not shown on screen.
- After the run: `python scripts/check_run.py --latest --salesforce`, then one stamp looked up with `--stamp`.
- Use your own browser for the form and the review page: the app's built-in browser pane blocks the page's submit.
- Have a row the model may route differently (L-0025, staff number unknown) ready to show the review catching it.
