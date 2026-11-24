# Build the slice in Make

Who does what (Israel's ruling, 23/11/2026, 12:39): COURSES 2ND clicks in Google Cloud and Make. Israel pastes the secrets and keys. The Code chat writes the steps, fires the test leads and checks the runs, rows and emails.

The Make slice reaches Google with the same three permissions as n8n (send mail, only this app's files, the account's own address). It uses Make's HTTP module with its own Google login, not Make's Google Sheets and Gmail modules. Make's Google Sheets module needs full Drive access (Israel's choice, 23/11/2026; [connections and reach](../../docs/v2/connections-and-reach.md)).

| Part | What | Who |
|---|---|---|
| K | One webhook key each for n8n and Make | Israel, then the Code chat |
| G | A second Google client, for Make | COURSES 2ND, then Israel pastes |
| M | The Make scenario, five modules | COURSES 2ND |
| T | Test: three leads with the key, one without | Code chat |

**State, 23/11/2026, 14:24.** Built by COURSES 2ND as scenario "GTM v2 slice: approved lead (Make)", active. Test passed: 3 runs, 3 rows with `written_by` = `make`, 3 emails to the `+gtm-slice` address. No key and a wrong key both got HTTP 401 and wrote nothing. The steps below are as built, with the five differences COURSES 2ND found folded in.

**Pasting mappings.** Typing `{{function(...)}}` into a Make field does not turn it into a mapping. Paste each mapping below as a whole instead.

## Part K. Webhook keys (Israel, about 5 minutes)

Each command makes a random key, writes it to `.env`, and copies it to the clipboard. It never shows the key on screen.

**n8n key.** Run:

```bash
cd ~/gtm-enrichment-quality-pipeline && grep -q '^SLICE_KEY_N8N=.' .env && echo "SLICE_KEY_N8N is already set" || { k=$(openssl rand -hex 24); printf 'SLICE_KEY_N8N=%s\n' "$k" >> .env; printf %s "$k" | pbcopy; unset k; echo "n8n key saved to .env and copied"; }
```

Then in n8n, create a credential of type **Header Auth**:

- Name it `Slice webhook key (n8n)`.
- Header name: `X-Slice-Key`.
- Value: paste the key.

Save, then clear the clipboard:

```bash
pbcopy < /dev/null
```

Tell the Code chat. It switches the n8n webhook to require the key (`scripts/render_n8n_slice.py --update`), then proves that a call without the key is refused.

**Make key.** Run this when Part M step 2 asks for it:

```bash
cd ~/gtm-enrichment-quality-pipeline && grep -q '^SLICE_KEY_MAKE=.' .env && echo "SLICE_KEY_MAKE is already set" || { k=$(openssl rand -hex 24); printf 'SLICE_KEY_MAKE=%s\n' "$k" >> .env; printf %s "$k" | pbcopy; unset k; echo "Make key saved to .env and copied"; }
```

## Part G. A Google client for Make (COURSES 2ND, then Israel)

Same Google project, `gtm-pipeline-v2`, so Make reaches the same tracker the n8n app made.

1. Google Cloud, **Google Auth Platform**, **Clients**, **Create client**.
   - Application type **Web application**. Name `make`.
   - Authorized redirect URI: `https://www.integromat.com/oauth/cb/oauth2`
   - If Google asks for an authorized domain, add `integromat.com` on the Branding page.
2. **Create**. Google shows the client ID and secret once. Israel copies them straight into the Make connection in Part M step 3, and keeps them nowhere else.

## Part M. The Make scenario (COURSES 2ND, about 20 minutes)

Make, **Scenarios**, **Create a new scenario**, named `GTM v2 slice: approved lead (Make)`. Add the modules in this order, so their numbers match the mappings below: 1 webhook, 2 add row, 3 get inbox, 4 compose, 5 send. The modules keep Make's default names (Webhook, HTTP, HTTP, Tools, HTTP); the names below say what each one does.

```text
1 Approved lead in -> 2 Add tracking row -> 3 Get owner inbox -> 4 Compose owner email -> 5 Send owner email
```

Make runs modules in a line, so the row is written before the email.

### 1. Webhooks, Custom webhook: `Approved lead in`

1. **Add** a webhook named `gtm-v2-approved-lead`.
2. **Advanced settings**, **API Key authentication**, **Add**. Israel runs the Make key command in Part K, then pastes the key here.
3. Leave IP restrictions empty. Set **Get request headers** to No.
4. No data structure is needed: Make learns the fields from the first call. The sample below shows what arrives:

```json
{
  "event": "lead.approved",
  "run_id": "slice-make-20261123T023653Z-L-0001",
  "target": "make",
  "sent_at": "2026-11-23T02:36:53.079Z",
  "lead_id": "L-0001",
  "company_name": "Northwind Freight",
  "domain": "northwind-freight.example",
  "industry": "Transportation/Trucking/Railroad",
  "employee_count": 420,
  "hq_country": "Australia",
  "enquiry": "Wants a demo of lead routing for their new regional sales team before 1 February.",
  "intent": "demo_request",
  "priority": "high",
  "route": "enterprise_anz",
  "owner_team": "Enterprise sales ANZ",
  "reason": "Large freight firm asking for a dated demo. Size and region fit the enterprise ANZ team.",
  "decision": "approved",
  "approved_by": "reviewer-01",
  "approved_at": "2026-11-23T01:05:00Z"
}
```

5. **Save**. Copy the webhook address and give it to Israel for the Code chat. It goes in `.env` as `SLICE_URL_MAKE`, never in the repo.

### 2. HTTP, Make a request: `Add tracking row`

1. Authentication type **OAuth 2.0**. **Create a connection**, named `Google least reach (Make)`:

   | Field | Value |
   |---|---|
   | Flow type | Authorization Code |
   | Authorize URI | `https://accounts.google.com/o/oauth2/v2/auth` |
   | Token URI | `https://oauth2.googleapis.com/token` |
   | Scope | Three items: `https://www.googleapis.com/auth/gmail.send`, `https://www.googleapis.com/auth/drive.file`, `https://www.googleapis.com/auth/userinfo.email` |
   | Scope separator | SPACE |
   | Client ID, Client Secret | Israel pastes them from Part G |
   | Authorize parameters | `access_type` = `offline`, `prompt` = `consent` |
   | Token placement | In the header, token name `Bearer` |

2. **Save**. On Google's consent screen, check for the three permissions plus Google's `openid` sign-in line, and nothing else. Then allow.
3. URL, with the tracker ID in place of `SPREADSHEET_ID`:

```text
https://sheets.googleapis.com/v4/spreadsheets/SPREADSHEET_ID/values/rows!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS
```

4. Method `POST`. Body content type `application/json`. Body:

```text
{"values":[["make","{{1.run_id}}","{{1.lead_id}}","{{1.company_name}}","{{1.domain}}","{{1.route}}","{{1.priority}}","{{1.owner_team}}","{{1.decision}}","{{1.approved_by}}","{{1.approved_at}}","{{1.sent_at}}","{{now}}"]]}
```

5. Parse response **Yes**.

### 3. HTTP, Make a request: `Get owner inbox`

Same OAuth 2.0 connection. Method `GET`. URL `https://www.googleapis.com/oauth2/v3/userinfo`. Parse response **Yes**.

### 4. Tools, Compose a string: `Compose owner email`

Paste this text, keeping the line breaks and the blank lines:

```text
To: {{replace(3.data.email; "@"; "+gtm-slice@")}}
Subject: Approved lead for {{1.owner_team}}: {{1.company_name}} ({{1.priority}})
MIME-Version: 1.0
Content-Type: text/plain; charset="UTF-8"
Content-Transfer-Encoding: 8bit

{{1.company_name}} ({{1.domain}}) is approved for {{1.owner_team}}.

Route: {{1.route}}
Priority: {{1.priority}}
Industry: {{1.industry}}
Enquiry: {{1.enquiry}}
Reason: {{1.reason}}
Decision: {{1.decision}} by {{1.approved_by}} at {{1.approved_at}}

Run: {{1.run_id}}
Sent by the Make slice. Made-up demo data.
```

The recipient comes from Google at run time, as in n8n. Nothing in a lead can change it. The module's output is `4.value`.

On save, Make warns "Tools: you're not using the data generated by this module". Module 5 does use it, so the warning can be ignored. The first email arrived with its full body.

### 5. HTTP, Make a request: `Send owner email`

Same OAuth 2.0 connection. Method `POST`. URL `https://gmail.googleapis.com/gmail/v1/users/me/messages/send`. Body content type `application/json`. Body:

```text
{"raw":"{{replace(replace(replace(base64(4.value); "+"; "-"); "/"; "_"); "="; emptystring)}}"}
```

The Gmail API wants base64url, so `+` and `/` are swapped and the padding is dropped.

### Then

- **Save**. Scheduling stays **Immediately**: the webhook runs only when called. Switch the scenario **on**. Free allows two active scenarios.
- Tell Israel "Make is on", with the webhook address. The Code chat runs Part T.

## Part T. Test (Code chat)

```bash
cd ~/gtm-enrichment-quality-pipeline && .venv/bin/python scripts/fire_slice.py --target make --lead L-0001
```

Pass when:

- Leads 1 to 3 each give one green run in Make, a tracker row with `written_by` = `make`, and an email to the `+gtm-slice` address.
- A call with `--no-key` is refused, and writes no row.

Then COURSES 2ND exports the blueprint (scenario menu, **Export Blueprint**). The Code chat removes the IDs and addresses, and saves it to this folder.

## If the tracker cannot be reached

The `drive.file` permission covers files made by this Google app. The Make client sits in the same project as the n8n client, so it should reach the tracker. If the add-row step returns 403 or 404 instead, stop. The Code chat then sets out the options before anything is widened.
