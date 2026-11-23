# Control sheet (draft)

Draft started in chapter 3. The full one-page sheet, laid out on the six practices of Australia's Guidance for AI Adoption, is finished in the wrap (KB-137, A1.5). This draft holds the part that exists now: every connection the build uses and what it can reach.

Rule: ask for the narrowest permissions that work. When a tool's built-in login asks for more, record what it would reach and why it was not used.

## Connections and their reach

| Connection | Used by | Permissions asked | Can read | Can change | Can send | Can delete | Guard | Login expiry | Secret lives in |
|---|---|---|---|---|---|---|---|---|---|
| Google, general login "Google least reach gtm-pipeline" | n8n slice | `gmail.send` (sensitive), `drive.file` (non-sensitive), `userinfo.email` (non-sensitive) | The account's own email address; only files this app created (the tracker). No mail | The tracker | Email as the account | Files this app created | The recipient is the connected account's own inbox, read at run time. It never comes from the payload | Decided: own app, In production, unverified, with a day-8 check. On 23/11/2026 at 12:54 it was still in "Testing", so that login lapses 7 days after sign-in | n8n credential only. Client ID and secret are never in the repo, exports or video |
| Make Google connection(s) | Make slice | To be read at connection, before approval | | | | | | | Make connection |
| Zapier Google connection | Zapier way 2 | To be read at connection, before approval | | | | | | | Zapier connection |
| Zapier MCP | Claude, way 3 | To be set when connected | | | | | | | Zapier |
| Claude API key | Chapter 2 onwards | Workspace `gtm-pipeline`, US$10 monthly limit | | | | | | Expires 23/12/2026 | `.env` (ignored by git) |
| HubSpot service key | Version 1 upsert | `crm.objects.companies.read`, `crm.objects.companies.write` | Companies | Companies | Nothing | Nothing | Upsert on `clay_domain_key` only | None set | `.env` and the n8n credential |

## Logins considered and not used

| Login | Permissions it asks for | What it could reach | Why not used |
|---|---|---|---|
| n8n built-in Gmail login (n8n 2.10.3) | `https://mail.google.com/`, `gmail.modify`, `gmail.compose`, `gmail.labels`, two add-on scopes. Fixed in n8n's code; cannot be narrowed | Read, send and permanently delete all mail in the account | The slice only needs to send one email |
| n8n built-in Google Sheets login (n8n 2.10.3) | `spreadsheets`, `drive.file`, `drive.metadata`. Fixed in n8n's code | See, edit, create and delete every spreadsheet, and see details of every Drive file | The slice only needs one sheet that it created |

Sources: n8n's credential files for version 2.10.3 on GitHub; Google's Gmail and Sheets scope pages, read 23/11/2026.
