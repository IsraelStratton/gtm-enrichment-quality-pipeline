# Chapter 3 notes: the slice in n8n, Make and Zapier

The same job in three tools: an approved lead arrives, the owner is told by email, and one row is added to a tracking sheet. The tools are compared on steps, plan limits and the workarounds each one needed, not on build minutes (Israel, 23/11/2026, 13:05). Claude does every step it can; Israel does sign-ins, consent screens, secrets and the yes before a push (Israel's ruling, 23/11/2026, 12:39).

## Done when

KB-135 gives chapter 3 no list of its own, so it is drawn from its section 0b row ("hands-on in all three, and when to use which; Zapier shown four ways"), its section 6, item 3, and KB-137 section 9, "Showing Zapier". Checked 24/11/2026, 12:20.

| # | Item | State | Proved by |
|---|---|---|---|
| 1 | The slice works in n8n, Make and Zapier, with a key on every entry point | Done 23/11/2026 | Setup log: rows, emails, and wrong-key calls refused or filtered |
| 2 | Zapier way 1: Free, two Zaps joined through a Table | Done 23/11/2026 | 3 runs of each Zap, 3 records, 3 emails |
| 3 | Zapier way 2: Pro trial, Zapier's AI and a person's approval in one Zap | Done. Built and tested 23/11/2026. L-0003 approved by Israel himself and a decline tested, 24/11/2026 | Setup log, 24/11/2026 rows: the approved note in the owner email; the declined run Filtered, with no row and no email |
| 4 | Zapier way 3: Zapier MCP, Claude runs one Zapier action | Done 24/11/2026 | One Create Record call; record 8 marked `claude-mcp`; Zap 2's email 10 seconds later; one entry in the server's history |
| 5 | Zapier way 4: admin settings on paper | Done 23/11/2026 | [zapier-admin-on-paper.md](zapier-admin-on-paper.md) |
| 6 | Notes: comparison, limits met, cost per lead, when to use which, how each one works | Done 24/11/2026 | This page |
| 7 | Every connection on the control sheet with its reach | Done 24/11/2026 | [control-sheet.md](control-sheet.md): the Zapier MCP row |
| 8 | Left switched off | Done 24/11/2026, 12:17 | All three Zaps off; the MCP client disconnected and removed from Claude Code |

**Moved to the wrap (Israel's ruling, 24/11/2026, 12:14; KB-135 v3.13):** the Zapier Pro clip. No clip or video is recorded until the larger initiatives are finished. The trial ends 07/12/2026, and the approval step exists only on Pro, so after that date the Zapier approval can be shown from its run history, not pressed live.

**Still open, outside this chapter's list:** the day-8 Google login test, on or after 01/12/2026 (below).

## Comparison

| | n8n | Make | Zapier Free | Zapier Pro trial |
|---|---|---|---|---|
| Plan | Community Edition, local | Free | Free | 14-day trial |
| Entry point | Webhook | Custom webhook | Zapier Form (no webhooks on Free) | Webhook |
| Design | One workflow | One scenario | Two Zaps joined through a Zapier Table; Email by Zapier; no outside login | One Zap with AI and approval steps |
| Steps in the slice | 6 nodes | 5 modules | 2 Zaps of 2 steps each, plus a Form and a Table | 7 steps in one Zap |
| Logins | 1: the general Google login, 3 permissions | 1: an HTTP OAuth 2.0 connection on a second client in the same Google app, same 3 permissions | None outside Zapier | None outside Zapier. The lead's made-up text goes to Zapier's AI provider |
| Where the row goes | Shared Google Sheet | Shared Google Sheet | Zapier Table | Shared Google Sheet |
| Plan limits met | None | None in the slice. Free allows 1,000 credits a month and 2 active scenarios | No webhooks; one action per Zap; Email by Zapier sends 5 emails a day; step tests email only the account's own address | Email by Zapier still sends 5 emails a day; approval requests go only to the account owner |
| Webhook guard | `X-Slice-Key` header (Header Auth); wrong or missing key gets 403 | Built-in API key (`x-make-apikey`); wrong or missing key gets 401 | No webhook. Entry is a Zapier Form, filled in by the approver | A Filter on the `X-Slice-Key` header. Zapier answers 200 to every call; a wrong key ends as "Filtered", with 0 tasks and no email |
| Workarounds | The built-in Gmail and Sheets logins ask for full mailbox access and every spreadsheet, so the slice uses HTTP requests to the Google APIs and one Code node | Make's Google Sheets module needs full Drive access, so the slice uses the HTTP module with its own OAuth connection. Base64url is made with `base64()` and three `replace()` calls. Mappings must be pasted, not typed | A Form stands in for the webhook; a Table joins the two Zaps; the email is shorter, because the Table does not carry the enquiry and reason | Only the raw hook shows headers, so a Code step reads the body. The Code input had to be named `rawBody`. The row goes to the Zapier Table, so Zapier needs no Google login |
| Units per lead | 1 execution: 6 steps, 3 Google API calls. No plan limit | 5 module runs; 5 credits | 1 task: the email step. Zapier did not charge for the Table step | 4 tasks |
| Time from send to arrival | 0.03 to 0.5 s (local) | 1.1 to 1.2 s (Make's EU cloud) | About 4 s from form submission to the email in the inbox | Set by the approver: the email follows within seconds of approval |
| How it was made | Workflow file written by the Code chat, imported by the planning chat | Built in Make's editor by the planning chat from the guide | Built in Zapier's editor by the planning chat from the guide | Built in Zapier's editor by the planning chat from the guide |

## Setup log

| When | What | Result |
|---|---|---|
| 23/11/2026, 12:54 | Google app made; n8n Google login connected | Connected. App still in Testing: Google will not publish it without a home page and a privacy policy link |
| 23/11/2026, 12:58 | Tracker sheet made by the run-once n8n workflow | Private sheet, tab `rows`, 13 headings. Checked through the Drive connector |
| 23/11/2026, by 13:14 | n8n slice workflow imported and published | Live workflow matches the file node for node, with the same wiring |
| 23/11/2026, 13:14 to 13:15 | n8n test: three leads at the live address | Pass. 3 runs, every step green; 3 rows with `written_by` = `n8n`; 3 emails to the `+gtm-slice` address. Each lead reached n8n 53 to 480 ms after it was sent; each run took 1.9 to 3.8 s |
| 23/11/2026, 13:30 | Google app published to production, unverified; n8n login reconnected | Consent screen: the three permissions asked for, plus Google's own `openid` sign-in line |
| 23/11/2026, 13:34 | Proof run with the new login | Pass: every step green, row 5 in the tracker, email arrived |
| 23/11/2026, 14:22 | Make scenario built and switched on, with a second Google client `make` and the webhook key | Five modules; connection limited to the three Google API hosts |
| 23/11/2026, 14:23 to 14:24 | Make test: three leads with the key, then no key and a wrong key | Pass. 3 rows with `written_by` = `make` and 3 emails to the `+gtm-slice` address. Both bad calls got 401 and wrote nothing. Make's client reached the sheet n8n's client made, so `drive.file` covers the whole Google app |
| 23/11/2026, 15:09 | Zapier Free: Table, Form, Zap 1 and Zap 2 built; form submitted three times | Pass. 3 successful runs of each Zap; 3 Table records with `written_by` = `zapier` (plus one from Zap 1's step test); 3 emails from Email by Zapier to the `+gtm-slice` address, each with the right run ID. 3 of 100 tasks used. Both Zaps switched off afterwards. Changes from the guide: `route`, `priority` and `decision` are short text, and Zapier's Copilot could not map the fields, so they were mapped by hand |
| 23/11/2026, 15:54 to 16:00 | Zapier Pro test: L-0001 and L-0002 with the key, then one wrong-key call | Pass. Both runs successful after approval; 2 owner emails, each carrying its approved AI note and the right run ID, to the `+gtm-slice` address. Wrong key: "Filtered", 0 tasks, no email. 4 tasks a lead. **The two approvals were pressed by the planning chat on Israel's word, after it read each note**, so this test proves the mechanism, not a person's review. On 24/11/2026 Israel pressed Approve himself (row below). Only one approval email arrived for the two requests: an open point, not a fault. The Table rows rest on the planning chat's report: on 24/11/2026 the record count (7 after L-0003, 8 after the MCP call) agreed with every run. All three Zaps are off |
| 23/11/2026, 15:35 | Zapier Pro trial started; Pro Zap drafted with steps 1 and 2 | No card asked. Trial ends 07/12/2026; 3 of 2,000 tasks used. One sample lead fired with the key at 15:36: HTTP 200, nothing run, since the Zap is a draft |
| 23/11/2026, 15:34 | Commits re-stamped with the GitHub no-reply address and pushed | Seven commits; `scripts/prepush_check.py` now checks author and committer email, agent lines and private values before every push |
| 23/11/2026, 15:30 | Zapier way 4: admin settings on paper | [zapier-admin-on-paper.md](zapier-admin-on-paper.md), from the Admin Essentials course (KB-124). Knowledge, not practice |
| 23/11/2026, 15:15 | Make blueprint exported and cleaned into [the repo](../../slice/make/slice-scenario.blueprint.json) | Tracker ID, webhook number and connection number replaced by placeholders; a test holds it to the design |
| 23/11/2026, 13:51 | n8n webhook switched to require the `X-Slice-Key` header, through the n8n API | No key: 403, no run. Wrong key: 403, no run. Right key: 200, run passed. One extra keyed test call added a sixth made-up row |
| 24/11/2026, 11:30 to 11:38 | Zapier Pro: L-0003, approved by Israel himself | Pass. Fired at 11:30:16 with the key (HTTP 200). The run waited at the approval step; Zapier's review notice arrived at 11:30:35; Israel read the AI note and pressed Approve. The owner email arrived at 11:36:17 at the `+gtm-slice` address, carrying the approved note and run ID `slice-zapier-20261124T003016Z-L-0003`. Table record with `written_by` = `zapier-pro` (7 records in all). 4 tasks. Pro Zap off. **This is the first approval in the build made by Israel's own hand.** No clip was recorded: clips wait for the wrap (Israel's ruling, 12:14) |
| 24/11/2026, 11:25 to 11:59 | Zapier MCP set up (way 3) | Added to Claude Code for this folder only (`claude mcp add --transport http`). Sign-in is OAuth, so the address holds no secret. Israel signed in. **The server started in agentic mode:** Claude Code saw 17 tools that can find, switch on and run any Zapier action, and the sign-in alone had switched on 9 apps already connected to the Zapier account, about 125 actions (Gmail 22, OneDrive 21, Trello 51 among them). The Code chat called none of them. COURSES 2ND switched the server to managed mode, removed all 9 apps, and added one action, Zapier Tables Create Record, with the Table and `written_by` = `claude-mcp` fixed. After "Reload servers" in `/mcp`, Claude Code saw 4 tools: that action and three helpers that read only (the field list, dropdown values, the settings link) |
| 24/11/2026, 11:59 | Zapier MCP: one schema read | Reached Zapier, but Claude Code (2.1.318) rejected the reply: "Structured content does not match the tool's output schema". Not retried. COURSES 2ND read the 13 field IDs from the Table instead: `f1` to `f13`, in the guide's order. The call is not in the server's history and used no task |
| 24/11/2026, 12:04 | Zapier MCP: one Create Record call (way 3) | Pass. Record 8 in the Table, `written_by` = `claude-mcp`, run ID `slice-claude-mcp-20261124T010408Z-L-0001`, every field in its place. Zap 2, switched on for this test only, emailed the owner at 12:04:18, 10 seconds after the call. The server's history: one Create Record, Success. Tasks: 0 for the call (Zapier's reply said `billingTasksUsed: 0`; the billing page still showed it at 12:20), 1 for Zap 2. Zapier's docs say 2 a call. Then Zap 2 off, Claude Code's client disconnected on mcp.zapier.com (pressed by COURSES 2ND on Israel's standing word), the server removed from Claude Code. The server stays, in managed mode, with its one action and its log |
| 24/11/2026, 12:10 to 12:17 | Zapier Pro: decline stops the run | Pass. L-0003 fired again at 12:10:41 for a clip (run `slice-zapier-20261124T011041Z-L-0003`). At 12:14 Israel ruled that clips wait for the wrap, so the waiting run was declined, pressed by COURSES 2ND on his word. Zap history: Filtered, 2 tasks. No Table row (still 8 records) and no owner email (checked in the inbox). Pro Zap off; all three Zaps off. Tasks used in the trial: 18 of 2,000 (billing page, 12:20) |

## Limits met

| Tool | Limit | Effect on the slice | Source |
|---|---|---|---|
| Zapier Free | Webhooks by Zapier is a paid-plan app | The Free version starts from a Zapier Form, not the shared webhook | Zapier pricing and help pages, read 23/11/2026 |
| Zapier Free | A trigger and one action per Zap; 100 tasks a month | Two Zaps joined through a Zapier Table | Zapier Free plan help page |
| Zapier Free | Email by Zapier sends 5 emails a day; while testing it delivers only to the account's own address | Fine for the slice; not for volume | Zapier help, "Send emails in Zap workflows" |
| Make Free | 1,000 credits a month; 2 active scenarios; 1 data store | The slice is one scenario | Make pricing page, read 23/11/2026 |
| n8n | The built-in Gmail and Sheets logins ask for far more than the slice needs | General Google login with three narrow permissions, and HTTP Request nodes | n8n 2.10.3 source; [control sheet](control-sheet.md) |
| Google | An app in "Testing" gets logins that expire after 7 days. Publishing needs a home page and a privacy policy link | Links point at the public repo and [PRIVACY.md](../../PRIVACY.md). Day-8 test below | Google OAuth 2.0 docs; Google Cloud, 23/11/2026 |
| Zapier MCP | A new server starts in agentic mode, and sign-in switches on actions for every app already connected to the account | Switched to managed mode and cut to one action before the first call | Zapier MCP docs ("how tools work", "switch modes"), read 24/11/2026; seen on the server |
| Zapier MCP | Managed mode is a setting, not a lock: anyone signed in to the Zapier account can switch it back or add actions | Client disconnected after the one call; recorded on the control sheet | Zapier MCP docs, "switch modes" |
| Zapier MCP and Claude Code 2.1.318 | Claude Code rejected the field-list helper's reply because its shape did not match the tool's declared output | Field IDs read from the Table instead. The action call itself worked | This session's Claude Code MCP log |
| Zapier MCP | A client sees a changed tool list only after it reloads the server | `/mcp`, "Reload servers" | Zapier MCP docs, "switch modes"; seen 24/11/2026 |

## Cost per lead

From the test runs on 23/11/2026.

| Tool | Units used by one lead | Free allowance | Leads a month on the free plan | Money |
|---|---|---|---|---|
| n8n (local) | 1 execution | No limit | No limit | US$0 |
| Make Free | 5 credits (5 operations) | 1,000 credits a month | 200 | US$0 |
| Zapier Free | 1 task | 100 tasks a month, and 5 emails a day from Email by Zapier | 100, at most 5 a day | US$0 |
| Zapier Pro trial | 4 tasks for an approved lead; 2 for a declined one | 2,000 tasks during the trial, and still 5 emails a day | 500, at most 5 a day | US$0 for 14 days; the plan is paid after that |
| Zapier MCP (way 3) | 0 tasks for the Create Record call on 24/11/2026 (Zapier's docs say 2), plus 1 for Zap 2's email | The account's task allowance | Not a lead flow: one call, to show the route | US$0 |

From 24/11/2026 (the Zapier rows): 11 tasks used at the start of the day, 18 at the end. L-0003 approved: 4. Zap 2 after the MCP call: 1. L-0003 declined: 2. The MCP call: 0.

## When to use which

Drawn from this build, not from vendor claims.

| Use | When | What this build showed |
|---|---|---|
| **n8n** | You need control: exact permissions, code steps, data kept on your own machine, and workflows kept in git and tested | The only tool where the workflow is a file in the repo, checked by tests on every push. Fastest here, because it runs locally. Its ready-made Google steps ask for too much, so the narrow version needs HTTP requests and a Code node |
| **Make** | A business team wants visual building in the cloud, with room to grow on a free plan | 200 leads a month on Free, against Zapier Free's 100. A key check is built into the webhook. HTTP OAuth keeps the Google reach as narrow as n8n's. Costs: mappings have to be pasted, its Google modules ask for full Drive, and the export holds IDs that must be removed |
| **Zapier Free** | A small app-to-app job that a non-engineer builds and keeps running | No webhooks and one action per Zap, so the job is split into two Zaps joined by a Table. Its Form, Table and email stay inside Zapier, so no outside login is needed. Email by Zapier caps it at 5 emails a day |
| **Zapier Pro** | The same people need AI and a person's approval inside the flow | Zapier's AI step and approval step are built in, and work without writing code. Approve lets the run go on; decline ends it with no row and no email (tested 24/11/2026). Costs: 4 tasks a lead, and only the account owner can approve on Pro. A wrong key is filtered inside the Zap, not refused at the door |
| **Zapier MCP** | An AI client such as Claude needs to act in an app it has no direct connection to | One Create Record call reached the Table, and Zap 2 carried it on to email, with no mail login on Claude's side. The default is far too wide: sign-in alone switched on about 125 actions across 9 connected apps, Gmail among them. Managed mode with one fixed action is the safe set-up. The call cost 0 tasks here. One helper's reply was rejected by Claude Code, so check the client and the server together |

**Say it in one line.** "n8n when you need control and tests, Make when a team wants visual building with room to grow, Zapier when the job is short and the builder is not an engineer."

## How it works

### n8n

1. An approved lead arrives at the webhook as JSON. The sample leads are made up and company-level only.
2. One step keeps the 13 tracking columns and stamps the time it arrived.
3. The row is written to the shared Google Sheet first, so there is always a record, even if the email fails.
4. Then the workflow asks Google which account is signed in, and emails that account's own inbox. The address is never stored in the workflow, and nothing in a lead can send the email somewhere else.
5. The Gmail API sends a short plain-text email naming the company, the route, the priority and the reason.

**Why it is built this way.** n8n's ready-made Gmail and Sheets steps need a login that can read and delete all mail and every spreadsheet. This one can only send mail, see its own address, and touch the one sheet it created.

**Say it in one line.** "When a lead is approved, n8n logs it in a shared sheet and emails the owner, using a Google login that can't read anyone's mail."

### Zapier (Free)

1. A person approves a lead by filling in a Zapier Form. Free has no webhooks, so the form is the way in.
2. Zap 1 adds a record to a Zapier Table. That is its only action, because Free allows one per Zap.
3. Zap 2 starts when the new record appears, and emails the owner through Zapier's own mail service.

**Why it is built this way.** The Table joins two one-action Zaps into one flow. Nothing leaves Zapier, so no outside login is needed.

**Say it in one line.** "On Zapier's free plan I split the job into two Zaps joined by a table, and it needs no access to anyone's mail or files."

### Zapier (Pro trial)

1. The same approved lead and key arrive at a Zapier webhook. A Filter lets the run go on only if the key matches.
2. A Code step reads the lead, and Zapier's AI writes a two-line note for the owner. The prompt treats the customer's words as data, never as instructions.
3. The run then waits for a person. They read the note, can change it, and approve. Declining stops the run.
4. Only then is the row added to the Zapier Table and the owner emailed, with the approved note.

**Why it is built this way.** An AI's words reach staff only after a person has read them. The row goes to Zapier's own Table, so Zapier needs no access to Google.

**Say it in one line.** "On Zapier's paid plan the same job runs in one Zap, and a person approves what the AI wrote before anyone sees it."

### Zapier MCP (way 3)

1. Claude Code connects to Zapier's MCP server. Israel signs in on Zapier's own consent screen, so no key sits in the repo or in `.env`.
2. The server is in managed mode with one action: Zapier Tables, Create Record. Zapier fixes the table and sets `written_by` to `claude-mcp`; Claude fills in the other 11 fields.
3. Claude writes one record for a lead a person has already approved. It records the decision; it does not make it.
4. Zap 2 sees the new record and emails the owner, just as it does for the Free slice.

**Why it is built this way.** Zapier becomes Claude's route into an app it has no direct connection to, here email, without Claude holding a mail login. Out of the box, the server let Claude switch on any app the Zapier account was connected to, Gmail included. So before the first call it was cut down to one action on one table, and every record it writes is marked as Claude's.

**Say it in one line.** "Claude can use Zapier as its hands, but I gave it one action on one table, and every record it writes is marked as Claude's."

### Make

1. The same approved lead arrives at a Make webhook. Make checks the key before the scenario starts, and refuses a call without it.
2. An HTTP module adds the row to the same shared sheet. It uses its own Google login, made in the same Google app, so it reaches the sheet n8n made and nothing else.
3. A second HTTP module asks Google which account is signed in.
4. A Tools module writes the email, addressed to that account's own inbox.
5. A third HTTP module sends it through the Gmail API.

**Why it is built this way.** Make's ready-made Google Sheets module needs access to every file in Drive. The HTTP module lets the scenario keep the same three narrow permissions as n8n.

**Say it in one line.** "Make does the same job in five steps in the cloud, with the same narrow Google login and a key on its webhook."

## Day-8 test of the Google login

The Google app goes to production but stays unverified. Google's pages do not say whether such logins escape the 7-day limit, so it is tested.

- Reconnected under "In production" on: 23/11/2026, 13:30
- Test on or after: 01/12/2026
- Test: fire the n8n slice with no reconnect. Pass if the row and the email both arrive.
- Result: (pending)
- If it fails: reconnect weekly, and keep the check below.

## Demo checklist

- [ ] Google login still valid: fire `python scripts/fire_slice.py --target n8n --lead L-0001` and see the row and the email arrive. Reconnect the n8n Google credential if not.
- [ ] Claude API key not expired (expires 23/12/2026).
- [ ] The Make scenario and the Zaps are switched on only for the demo, then off again.
- [ ] The tracker holds made-up rows only.

## Clips for the wrap

No clip or video is recorded until the larger initiatives are finished (Israel's ruling, 24/11/2026, 12:14; KB-135 v3.13). Listed here so the wrap picks them up.

| Clip | What it shows | How | Dated limit |
|---|---|---|---|
| Zapier Pro: Israel approves an AI note | One L-0003 run waiting at the approval step; Israel reads the note and presses Approve; the run turns Successful; the new `zapier-pro` row in the Table | Part 1 of [slice/zapier/BUILD.md](../../slice/zapier/BUILD.md), "The clip": Pro Zap on, Zap 2 off, fire L-0003, record the Chrome page only. 1 Email by Zapier email | The trial ends 07/12/2026. After that, the approval can be shown from the run history only |

## Video checklist (privacy)

- [ ] No Gmail inbox header, account chip or To and From lines on screen. Show the email body only.
- [ ] Never open a credential, a connection dialog or the Google Cloud client page.
- [ ] Never open the n8n execution data of the "Get owner inbox" or "Build owner email" nodes: they hold the address.
- [ ] In Google Sheets, crop out the account avatar and the Share dialog.
- [ ] The tracker and the emails hold made-up company data only.
- [ ] Email by Zapier adds a footer with a "stop these emails" link and the Zap's number. Crop it.
- [ ] In Zapier, never open the Pro Zap's trigger step (it shows the key header) or its email step (it shows the owner address). On mcp.zapier.com, never open the Connect tab.
