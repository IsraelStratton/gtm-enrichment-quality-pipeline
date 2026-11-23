# Build the slice in n8n

Who does what (Israel's ruling, 23/11/2026, 12:39): Claude does every step it can. The Code chat writes the files, runs the scripts and checks the results. The planning chat (COURSES 2ND) does the clicks in Chrome. Israel does only sign-ins, consent screens, secrets and the yes before a push.

| Part | What | State |
|---|---|---|
| A | Google app `n8n local gtm-pipeline` in project `gtm-pipeline-v2` | Made 23/11/2026. Published to production (unverified) at 13:30, after Part F |
| B | n8n credential `Google least reach gtm-pipeline` | Connected 23/11/2026, 12:54; reconnected under production at 13:30 |
| C | Tracker sheet, made by the run-once workflow | Made 23/11/2026, 12:58. **Do not run that workflow again: each run makes another sheet** |
| D | Slice workflow, imported from [slice-workflow.json](slice-workflow.json) | Imported and published 23/11/2026; matches the file node for node |
| E | Test: three leads, three rows, three emails | Passed 23/11/2026, 13:15 |
| F | Publish the Google app, then reconnect | Done 23/11/2026, 13:30. Proof run at 13:34 passed |

The slice uses n8n's general **Google OAuth2 API** login with three narrow permissions, and HTTP Request nodes. It does not use n8n's Gmail or Google Sheets nodes, because their logins ask for full mailbox access and every spreadsheet ([control sheet](../../docs/v2/control-sheet.md)).

## Part A. Your own Google app (one-off, about 15 minutes)

1. Open [console.cloud.google.com](https://console.cloud.google.com), signed in to the Google account that will own the tracker and receive the owner emails.
2. Project picker in the top bar, then **New project**. Name: `gtm-pipeline-v2`. No billing. **Create**, then select it.
3. Menu, **APIs & Services**, **Library**. Find **Gmail API** and **Enable**. Go back, find **Google Sheets API** and **Enable**. Nothing else.
4. Menu, **Google Auth Platform** (also reached from APIs & Services, OAuth consent screen). **Get started**.
   - App name: `n8n local gtm-pipeline`. User support email: yours.
   - Audience: **External**.
   - Contact information: yours. Agree, then **Create**.
5. **Audience**, then under Publishing status, **Publish app**. Found on 23/11/2026: the button stays disabled until the Branding page has a home page link and a privacy policy link. That is Part F.
6. Leave this tab open. The client is made in Part B, because it needs n8n's redirect address.

## Part B. The n8n login (one-off, about 5 minutes)

1. Open n8n at `http://localhost:5678` and sign in with the owner account.
2. Create a credential. Search **Google OAuth2 API** and pick that one: the general one, not "Gmail OAuth2 API" or "Google Sheets OAuth2 API".
3. Copy the **OAuth Redirect URL** it shows. Expect `http://localhost:5678/rest/oauth2-credential/callback`.
4. In the Google tab: **Google Auth Platform**, **Clients**, **Create client**.
   - Application type: **Web application**. Name: `n8n local`.
   - Authorized redirect URIs, **Add URI**: paste the address from step 3. **Create**.
5. Google shows the **Client ID** and **Client secret** once. Copy each straight into the n8n credential. Keep them nowhere else. If the secret is lost later, add a new secret on the client page.
6. In **Scope**, paste exactly this one line:

   ```text
   https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email
   ```

7. If the credential shows **Allowed HTTP Request Domains**, choose specific domains and enter `sheets.googleapis.com,gmail.googleapis.com,www.googleapis.com`.
8. Rename the credential to `Google least reach gtm-pipeline`.
9. **Sign in with Google**. Pick the account. On "Google hasn't verified this app", choose **Advanced**, then **Go to n8n local gtm-pipeline**.
10. **Stop and check the consent screen.** It must list these three, plus Google's own sign-in line, and nothing else:
    - Send email on your behalf.
    - See, edit, create and delete only the specific Google Drive files you use with this app.
    - See your primary Google Account email address.
    - Associate you with your personal info on Google. Google adds this `openid` line itself, because the app asks for the email address.

    If it lists anything else, stop and tell Claude. If it matches, tick all three and **Continue**.
11. n8n shows "Account connected". **Save**. Tell Claude the date you connected: it starts the day-8 test.

## Part C. Make the tracker sheet from n8n (about 5 minutes)

The `drive.file` permission only reaches files this app created, so n8n makes the sheet itself.

1. New workflow, named `GTM v2 slice: create tracker (run once)`.
2. Trigger: **Trigger manually**.
3. Add an **HTTP Request** node, named `Create tracker sheet`.
   - Method `POST`. URL `https://sheets.googleapis.com/v4/spreadsheets`
   - Authentication **Predefined Credential Type**. Credential type **Google OAuth2 API**. Credential `Google least reach gtm-pipeline`.
   - Send Body on. Body Content Type **JSON**. Specify Body **Using JSON**. Paste:

```json
{
  "properties": { "title": "GTM v2 approved leads tracker" },
  "sheets": [
    {
      "properties": { "title": "rows", "gridProperties": { "frozenRowCount": 1 } },
      "data": [
        {
          "startRow": 0,
          "startColumn": 0,
          "rowData": [
            {
              "values": [
                { "userEnteredValue": { "stringValue": "written_by" } },
                { "userEnteredValue": { "stringValue": "run_id" } },
                { "userEnteredValue": { "stringValue": "lead_id" } },
                { "userEnteredValue": { "stringValue": "company_name" } },
                { "userEnteredValue": { "stringValue": "domain" } },
                { "userEnteredValue": { "stringValue": "route" } },
                { "userEnteredValue": { "stringValue": "priority" } },
                { "userEnteredValue": { "stringValue": "owner_team" } },
                { "userEnteredValue": { "stringValue": "decision" } },
                { "userEnteredValue": { "stringValue": "approved_by" } },
                { "userEnteredValue": { "stringValue": "approved_at" } },
                { "userEnteredValue": { "stringValue": "sent_at" } },
                { "userEnteredValue": { "stringValue": "received_at" } }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

4. If **Google OAuth2 API** is missing from the credential types, stop and tell Claude.
5. **Execute workflow**. The output holds `spreadsheetId` and `spreadsheetUrl`. Open the URL: one tab called `rows` with 13 headings. Copy the `spreadsheetId` for Part D.
6. **Save**. Do not publish it. It is run once, by hand.

## Part D. Load the slice workflow (COURSES 2ND, about 5 minutes)

The workflow is [slice-workflow.json](slice-workflow.json). It holds two placeholders, so the public file carries no tracker ID and no credential ID. The Code chat fills them into a local copy that git ignores:

```bash
cd ~/gtm-enrichment-quality-pipeline && .venv/bin/python scripts/render_n8n_slice.py
```

1. In n8n, start a new workflow. In its menu choose **Import from File** and pick `~/gtm-enrichment-quality-pipeline/slice/n8n/slice-workflow.local.json`.
2. Check the three HTTP Request nodes. Each must show the credential `Google least reach gtm-pipeline`, with no warning.
3. **Save**, then **Publish**. The webhook only runs when it is called, so nothing is scheduled.
4. Tell Israel "published". He tells the Code chat.

### What each node does

```text
Approved lead in -> Shape tracking row -> Add tracking row                                    (runs first)
                                       -> Get owner inbox -> Build owner email -> Send owner email
```

| Node | Type | What it does |
|---|---|---|
| Approved lead in | Webhook, `POST /webhook/gtm-v2-approved-lead` | Receives one approved lead as JSON and answers at once |
| Shape tracking row | Edit Fields, JSON mode | Keeps the 13 tracking columns and stamps `received_at` in UTC |
| Add tracking row | HTTP Request, Sheets API `values:append` | Adds the row to the tracker. It sits higher on the canvas, so it runs before the email branch |
| Get owner inbox | HTTP Request, Google `userinfo` | Asks Google which account is signed in |
| Build owner email | Code ([build_owner_email.js](build_owner_email.js)) | Writes a plain-text email to that account's `+gtm-slice` address. The recipient never comes from the payload |
| Send owner email | HTTP Request, Gmail API `messages.send` | Sends it. The login can send mail but cannot read any |

## Part E. Test it (Code chat)

The Code chat fires the three sample leads at the live address and checks the run, the rows and the emails:

```bash
cd ~/gtm-enrichment-quality-pipeline && .venv/bin/python scripts/fire_slice.py --target n8n --lead L-0001
```

Pass when all three runs succeed in n8n, the tracker has three rows with `written_by` = `n8n`, and three emails arrive with subjects starting "Approved lead for".

## Part F. Publish the Google app (COURSES 2ND, then Israel)

Google will not publish an app without a home page link and a privacy policy link. Both point at the public repository, so [PRIVACY.md](../../PRIVACY.md) must be on GitHub first. That push waits for Israel's yes.

1. Google Cloud, project `gtm-pipeline-v2`, **Google Auth Platform**, **Branding**.
   - Application home page: `https://github.com/IsraelStratton/gtm-enrichment-quality-pipeline`
   - Application privacy policy link: `https://github.com/IsraelStratton/gtm-enrichment-quality-pipeline/blob/v2/PRIVACY.md`
   - Authorized domains: `github.com`, if Google asks for it. If Google refuses it, stop and tell the Code chat.
   - **Save**.
2. **Audience**, **Publish app**, confirm. Submit nothing for verification.
3. Israel: in n8n, open `Google least reach gtm-pipeline`, **Sign in with Google** again, and check that the consent screen lists exactly the three permissions in Part B. **Save**. This gives a login made under "In production".
4. Tell the Code chat the date of the reconnect. The day-8 test falls 8 days later.
