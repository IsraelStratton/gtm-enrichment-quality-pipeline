# Chapter 3 notes: the slice in n8n, Make and Zapier

The same job in three tools: an approved lead arrives, the owner is told by email, and one row is added to a tracking sheet. The tools are compared on steps, plan limits and the workarounds each one needed, not on build minutes (Israel, 23/11/2026, 13:05). Claude does every step it can; Israel does sign-ins, consent screens, secrets and the yes before a push (Israel's ruling, 23/11/2026, 12:39).

## Comparison

| | n8n | Make | Zapier Free | Zapier Pro trial |
|---|---|---|---|---|
| Plan | Community Edition, local | Free | Free | 14-day trial |
| Entry point | Webhook | Custom webhook | Zapier Form (no webhooks on Free) | Webhook |
| Design | One workflow | One scenario | Two Zaps joined through a Zapier Table; Email by Zapier; no outside login | One Zap with AI and approval steps |
| Steps in the slice | 6 nodes | 5 modules | 2 Zaps of 2 steps each, plus a Form and a Table | |
| Logins | 1: the general Google login, 3 permissions | 1: an HTTP OAuth 2.0 connection on a second client in the same Google app, same 3 permissions | None outside Zapier | |
| Where the row goes | Shared Google Sheet | Shared Google Sheet | Zapier Table | Shared Google Sheet |
| Plan limits met | None | None in the slice. Free allows 1,000 credits a month and 2 active scenarios | No webhooks; one action per Zap; Email by Zapier sends 5 emails a day; step tests email only the account's own address | |
| Webhook guard | `X-Slice-Key` header (Header Auth); wrong or missing key gets 403 | Built-in API key (`x-make-apikey`); wrong or missing key gets 401 | No webhook. Entry is a Zapier Form, filled in by the approver | |
| Workarounds | The built-in Gmail and Sheets logins ask for full mailbox access and every spreadsheet, so the slice uses HTTP requests to the Google APIs and one Code node | Make's Google Sheets module needs full Drive access, so the slice uses the HTTP module with its own OAuth connection. Base64url is made with `base64()` and three `replace()` calls. Mappings must be pasted, not typed | A Form stands in for the webhook; a Table joins the two Zaps; the email is shorter, because the Table does not carry the enquiry and reason | |
| Units per lead | 1 execution: 6 steps, 3 Google API calls. No plan limit | 5 module runs; 5 credits | 1 task: the email step. Zapier did not charge for the Table step | |
| Time from send to arrival | 0.03 to 0.5 s (local) | 1.1 to 1.2 s (Make's EU cloud) | About 4 s from form submission to the email in the inbox | |
| How it was made | Workflow file written by the Code chat, imported by the planning chat | Built in Make's editor by the planning chat from the guide | Built in Zapier's editor by the planning chat from the guide | |

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
| 23/11/2026, 15:30 | Zapier way 4: admin settings on paper | [zapier-admin-on-paper.md](zapier-admin-on-paper.md), from the Admin Essentials course (KB-124). Knowledge, not practice |
| 23/11/2026, 15:15 | Make blueprint exported and cleaned into [the repo](../../slice/make/slice-scenario.blueprint.json) | Tracker ID, webhook number and connection number replaced by placeholders; a test holds it to the design |
| 23/11/2026, 13:51 | n8n webhook switched to require the `X-Slice-Key` header, through the n8n API | No key: 403, no run. Wrong key: 403, no run. Right key: 200, run passed. One extra keyed test call added a sixth made-up row |

## Limits met

| Tool | Limit | Effect on the slice | Source |
|---|---|---|---|
| Zapier Free | Webhooks by Zapier is a paid-plan app | The Free version starts from a Zapier Form, not the shared webhook | Zapier pricing and help pages, read 23/11/2026 |
| Zapier Free | A trigger and one action per Zap; 100 tasks a month | Two Zaps joined through a Zapier Table | Zapier Free plan help page |
| Zapier Free | Email by Zapier sends 5 emails a day; while testing it delivers only to the account's own address | Fine for the slice; not for volume | Zapier help, "Send emails in Zap workflows" |
| Make Free | 1,000 credits a month; 2 active scenarios; 1 data store | The slice is one scenario | Make pricing page, read 23/11/2026 |
| n8n | The built-in Gmail and Sheets logins ask for far more than the slice needs | General Google login with three narrow permissions, and HTTP Request nodes | n8n 2.10.3 source; [control sheet](control-sheet.md) |
| Google | An app in "Testing" gets logins that expire after 7 days. Publishing needs a home page and a privacy policy link | Links point at the public repo and [PRIVACY.md](../../PRIVACY.md). Day-8 test below | Google OAuth 2.0 docs; Google Cloud, 23/11/2026 |

## Cost per lead

From the test runs on 23/11/2026.

| Tool | Units used by one lead | Free allowance | Leads a month on the free plan | Money |
|---|---|---|---|---|
| n8n (local) | 1 execution | No limit | No limit | US$0 |
| Make Free | 5 credits (5 operations) | 1,000 credits a month | 200 | US$0 |
| Zapier Free | 1 task | 100 tasks a month, and 5 emails a day from Email by Zapier | 100, at most 5 a day | US$0 |

## When to use which

Drawn from this build, not from vendor claims. The Zapier Pro line waits for its test.

| Use | When | What this build showed |
|---|---|---|
| **n8n** | You need control: exact permissions, code steps, data kept on your own machine, and workflows kept in git and tested | The only tool where the workflow is a file in the repo, checked by tests on every push. Fastest here, because it runs locally. Its ready-made Google steps ask for too much, so the narrow version needs HTTP requests and a Code node |
| **Make** | A business team wants visual building in the cloud, with room to grow on a free plan | 200 leads a month on Free, against Zapier Free's 100. A key check is built into the webhook. HTTP OAuth keeps the Google reach as narrow as n8n's. Costs: mappings have to be pasted, its Google modules ask for full Drive, and the export holds IDs that must be removed |
| **Zapier Free** | A small app-to-app job that a non-engineer builds and keeps running | No webhooks and one action per Zap, so the job is split into two Zaps joined by a Table. Its Form, Table and email stay inside Zapier, so no outside login is needed. Email by Zapier caps it at 5 emails a day |
| **Zapier Pro** | The same people need AI and a person's approval inside the flow | Pending: way 2 test |

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

## Video checklist (privacy)

- [ ] No Gmail inbox header, account chip or To and From lines on screen. Show the email body only.
- [ ] Never open a credential, a connection dialog or the Google Cloud client page.
- [ ] Never open the n8n execution data of the "Get owner inbox" or "Build owner email" nodes: they hold the address.
- [ ] In Google Sheets, crop out the account avatar and the Share dialog.
- [ ] The tracker and the emails hold made-up company data only.
- [ ] Email by Zapier adds a footer with a "stop these emails" link and the Zap's number. Crop it.
