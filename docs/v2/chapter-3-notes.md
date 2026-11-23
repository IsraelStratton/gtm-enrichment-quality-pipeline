# Chapter 3 notes: the slice in n8n, Make and Zapier

The same job in three tools: an approved lead arrives, the owner is told by email, and one row is added to a tracking sheet. The tools are compared on steps, plan limits and the workarounds each one needed, not on build minutes (Israel, 23/11/2026, 13:05). Claude does every step it can; Israel does sign-ins, consent screens, secrets and the yes before a push (Israel's ruling, 23/11/2026, 12:39).

## Comparison

| | n8n | Make | Zapier Free | Zapier Pro trial |
|---|---|---|---|---|
| Plan | Community Edition, local | Free | Free | 14-day trial |
| Entry point | Webhook | Custom webhook | Zapier Form (no webhooks on Free) | Webhook |
| Steps in the slice | 6 nodes | | | |
| Logins | 1: the general Google login, 3 permissions | | | |
| Where the row goes | Shared Google Sheet | Shared Google Sheet | Zapier Table | Shared Google Sheet |
| Plan limits met | None | | | |
| Webhook guard | `X-Slice-Key` header (Header Auth); wrong or missing key gets 403 | | | |
| Workarounds | The built-in Gmail and Sheets logins ask for full mailbox access and every spreadsheet, so the slice uses HTTP requests to the Google APIs and one Code node | | | |
| Units per lead | 1 execution: 6 steps, 3 Google API calls. No plan limit | | | |
| How it was made | Workflow file written by the Code chat, imported by the planning chat | | | |

## Setup log

| When | What | Result |
|---|---|---|
| 23/11/2026, 12:54 | Google app made; n8n Google login connected | Connected. App still in Testing: Google will not publish it without a home page and a privacy policy link |
| 23/11/2026, 12:58 | Tracker sheet made by the run-once n8n workflow | Private sheet, tab `rows`, 13 headings. Checked through the Drive connector |
| 23/11/2026, by 13:14 | n8n slice workflow imported and published | Live workflow matches the file node for node, with the same wiring |
| 23/11/2026, 13:14 to 13:15 | n8n test: three leads at the live address | Pass. 3 runs, every step green; 3 rows with `written_by` = `n8n`; 3 emails to the `+gtm-slice` address. Each lead reached n8n 53 to 480 ms after it was sent; each run took 1.9 to 3.8 s |
| 23/11/2026, 13:30 | Google app published to production, unverified; n8n login reconnected | Consent screen: the three permissions asked for, plus Google's own `openid` sign-in line |
| 23/11/2026, 13:34 | Proof run with the new login | Pass: every step green, row 5 in the tracker, email arrived |
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

To be filled from real runs.

| Tool | Units used by one lead | Free allowance | Leads a month on the free plan | Money |
|---|---|---|---|---|
| n8n (local) | 1 execution | No limit | No limit | US$0 |
| Make Free | | 1,000 credits a month | | US$0 |
| Zapier Free | | 100 tasks a month | | US$0 |

## When to use which

Written at the end of the chapter, from the comparison and the limits above.

## How it works

### n8n

1. An approved lead arrives at the webhook as JSON. The sample leads are made up and company-level only.
2. One step keeps the 13 tracking columns and stamps the time it arrived.
3. The row is written to the shared Google Sheet first, so there is always a record, even if the email fails.
4. Then the workflow asks Google which account is signed in, and emails that account's own inbox. The address is never stored in the workflow, and nothing in a lead can send the email somewhere else.
5. The Gmail API sends a short plain-text email naming the company, the route, the priority and the reason.

**Why it is built this way.** n8n's ready-made Gmail and Sheets steps need a login that can read and delete all mail and every spreadsheet. This one can only send mail, see its own address, and touch the one sheet it created.

**Say it in one line.** "When a lead is approved, n8n logs it in a shared sheet and emails the owner, using a Google login that can't read anyone's mail."

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
