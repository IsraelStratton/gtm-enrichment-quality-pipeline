# Control sheet (draft)

Draft started in chapter 3. The full one-page sheet, laid out on the six practices of Australia's Guidance for AI Adoption, is finished in the wrap (KB-137, A1.5). This draft holds the part that exists now: every connection the build uses and what it can reach.

Rule: ask for the narrowest permissions that work. When a tool's built-in login asks for more, record what it would reach and why it was not used.

## Connections and their reach

| Connection | Used by | Permissions asked | Can read | Can change | Can send | Can delete | Guard | Login expiry | Secret lives in |
|---|---|---|---|---|---|---|---|---|---|
| Google, general login "Google least reach gtm-pipeline" | n8n slice | Asked: `gmail.send` (sensitive), `drive.file` (non-sensitive), `userinfo.email` (non-sensitive). Google adds `openid` (non-sensitive) itself, shown as "Associate you with your personal info on Google" | The account's own email address; only files this app created (the tracker). No mail | The tracker | Email as the account | Files this app created | The recipient is the connected account's own inbox, read at run time. It never comes from the payload | Own app, In production, unverified: published and reconnected 23/11/2026, 13:30. Day-8 test on or after 01/12/2026 | n8n credential only. Client ID and secret are never in the repo, exports or video |
| Make HTTP OAuth 2.0 connection "Google least reach (Make)" | Make slice | Same three as n8n, on a second client (`make`) in the same Google app. Google adds `openid`. The connection is limited to the Sheets, Gmail and `www.googleapis.com` hosts | The account's own address; only files this app created. No mail | The tracker | Email as the account | Files this app created | Recipient read from Google at run time | Production app | Make connection only |
| Zapier Free slice (way 1) | Zapier Form, Table and Email by Zapier | None outside Zapier | Nothing outside Zapier | The Zapier Table | Email from Zapier's own mail service | Nothing outside Zapier | The owner address is typed once, in Zap 2. It is kept out of the video and any export | Not applicable | Zapier account |
| Zapier Google connection | Zapier way 2 | To be read at connection, before approval | | | | | | | Zapier connection |
| Zapier Pro slice (way 2) | AI by Zapier, Human in the Loop, Zapier Tables, Email by Zapier | None outside Zapier. The lead's made-up text goes to Zapier's AI provider | Nothing outside Zapier | The Zapier Table | Email from Zapier's own mail service, after Israel approves the AI note | Nothing outside Zapier | A person approves the AI's note before any email; decline stops the Zap | Trial ends about 07/12/2026 | Zapier account |
| Zapier MCP | Claude, way 3 | To be set when connected | | | | | | | Zapier |
| Claude API key | Chapter 2 onwards | Workspace `gtm-pipeline`, US$10 monthly limit | | | | | | Expires 23/12/2026 | `.env` (ignored by git) |
| HubSpot service key | Version 1 upsert | `crm.objects.companies.read`, `crm.objects.companies.write` | Companies | Companies | Nothing | Nothing | Upsert on `clay_domain_key` only | None set | `.env` and the n8n credential |

## Entry points

| Entry point | Who can call it | Guard today | Open point |
|---|---|---|---|
| n8n webhook `POST /webhook/gtm-v2-approved-lead` | Anything that can reach port 5678. Docker publishes it on every network interface, so other devices on the same network can reach it | Requires the `X-Slice-Key` header (n8n Header Auth credential "Slice webhook key (n8n)"; the key lives in that credential and `.env`). Live 23/11/2026, 13:51 | Proved: no key and a wrong key both get HTTP 403 and start no run; the right key gets 200 |
| Zapier Form "Approve a lead" (Free slice) | Anyone with its zapier.app link: the form is public | None on Free. Both Zaps are switched off outside tests and demos, so a submission starts nothing | Check whether Zapier Forms can require a sign-in on Free. Worst case while the Zaps are on: a made-up record and an email to the owner's own inbox. One submission was made before the Zaps were live: no run, no record |
| Zapier Pro webhook (Catch Raw Hook, way 2) | Anyone holding its address | A Filter step lets the run continue only when `X-Slice-Key` matches. Zapier still answers 200, so a wrong key is stopped inside the Zap, not refused at the door | To be proved in the way 2 test |
| Make webhook `gtm-v2-approved-lead` | Anyone holding its address | Make's built-in API key check (`x-make-apikey`); the key lives in Make's keychain and `.env` | Proved 23/11/2026: no key and a wrong key both get 401 and write nothing |

## Logins considered and not used

| Login | Permissions it asks for | What it could reach | Why not used |
|---|---|---|---|
| Make Google Sheets module | `spreadsheets` and full `drive` (Make's custom-client instructions) | See, edit and delete every spreadsheet and every Drive file | The slice only needs the one sheet. Make's Gmail module page could not be read on 23/11/2026, so its reach is unconfirmed |
| n8n built-in Gmail login (n8n 2.10.3) | `https://mail.google.com/`, `gmail.modify`, `gmail.compose`, `gmail.labels`, two add-on scopes. Fixed in n8n's code; cannot be narrowed | Read, send and permanently delete all mail in the account | The slice only needs to send one email |
| n8n built-in Google Sheets login (n8n 2.10.3) | `spreadsheets`, `drive.file`, `drive.metadata`. Fixed in n8n's code | See, edit, create and delete every spreadsheet, and see details of every Drive file | The slice only needs one sheet that it created |

Sources: n8n's credential files for version 2.10.3 on GitHub; Google's Gmail and Sheets scope pages, read 23/11/2026.
