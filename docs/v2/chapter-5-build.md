# Chapter 5 build guide: the quote exceptions desk

What has to be set up, by whom and in what order, for the quote desk workflow to read quotes from the Salesforce developer org, triage the ones that break a rule, ask a person to approve or reject each one, and then update the quote and tell its owner. Every value below comes from [`salesforce/quote-desk-setup.json`](../../salesforce/quote-desk-setup.json); `scripts/salesforce_quote_desk_check.py` signs in as the desk does afterwards and checks the org against that file.

Who does what follows Israel's ruling of 23/11/2026 and his brief for this chapter (24/11/2026): the planning chat (COURSES 2ND) does every click in Salesforce Setup and n8n, including switching Quotes on; Israel signs in, passes any verification or consent screen, pastes every secret himself, and does anything that could spend money; the Code chat does the command line, the seed data and the n8n API. No clips or videos in this chapter (Israel's ruling of 24/11/2026).

**Cost rule.** Nothing here should cost anything: Quotes, a second Salesforce licence user and an External Client App are all part of the free Developer Edition. If any screen shows a price, a trial, a card field, a licence purchase or an upgrade, stop and tell Israel.

| Part | What | Who | State |
|---|---|---|---|
| 0 | Read the org first: licences, sharing defaults, quote statuses | COURSES 2ND | Done 24/11/2026; read again by the Code chat: Salesforce licences 2 of 4 used before part E, Salesforce Integration 1 of 1; Opportunity default access Public Read/Write; Quote Status holds Needs Review, Approved and Rejected |
| A | Switch Quotes on | COURSES 2ND | Done 24/11/2026 (Quotes list on four Opportunity layouts) |
| B | Seven custom fields on Quote | COURSES 2ND made field 1; the Code chat made 2 to 7 through the CLI | Done 24/11/2026, read back: all seven as specified; field-level security on System Administrator and the permission set only; all on the Quote Layout, six in a new "GTM v2 quote desk" section |
| C | Profile "GTM v2 API only" | COURSES 2ND cloned it; the Code chat set the two permissions through the CLI | Done 24/11/2026, read back: API Enabled and API Only User on; Salesforce licence |
| D | Permission set "GTM v2 quote desk" | Code chat, through the CLI | Done 24/11/2026, read back: no licence, no system permission; Quote read and edit; Opportunity, Account, Product read; edit on Status and the two desk fields only; no contact, email, phone or fax |
| E | The API-only desk user | Code chat, through the CLI (`scripts/make_desk_user.py`; Israel's own address copied inside the org from his admin user) | Done 24/11/2026, read back: GTM Quote Desk, active, never signed in, profile GTM v2 API only, permission set assigned; username in `.env` and the private list only. Salesforce licences 3 of 4 used |
| F | Sharing for the seeded opportunities (only if part 0 says so) | COURSES 2ND | Not needed: Opportunity default access is Public Read/Write |
| G | External Client App "GTM v2 quote desk (n8n)" | COURSES 2ND; Israel passes the verification code and copies the key and secret | To do |
| H | Two lines in `.env` | Israel pastes | To do |
| I | n8n credential "Salesforce quote desk (client credentials)" | COURSES 2ND makes it; Israel pastes the key and secret | Made by COURSES 2ND; waiting for the key and secret from part G |
| J | Sign the Salesforce CLI in as the admin, for parts B to E and the seed | Israel (a sign-in) | Done 24/11/2026 (alias gtm-v2-admin). It stays signed in until part L |
| K | Seed the made-up quotes, then check the org | Code chat | Done 24/11/2026: seed (5 products, the standard price book switched on, 8 quotes with 12 lines, in Needs Review); org check **27 of 27**, signed in as the desk. On the way, two changes on Israel's yes: Price Books Read (Salesforce hid quote lines without it), and the Apex guard (with price books readable, Salesforce let the desk change quote lines) |
| L | Sign the CLI out | Israel | To do |
| M | Import and publish the workflow | Code chat | To do |
| N | One reviewed run | COURSES 2ND opens the pages; Israel makes the choices, or says yes to the Code chat making them | To do |
| O | Check the run against the log, Salesforce and the inbox | Code chat | To do |

Parts 0 to I can run while the Code chat builds the desk.

**Change of method, 24/11/2026 (13:38), on COURSES 2ND's word:** clicking parts B to E in classic Setup was too slow and fragile, so the Code chat did them through the Salesforce CLI, signed in as the admin (part J moved up). Parts B to D are metadata in [`salesforce/quote-desk/`](../../salesforce/quote-desk/), written from `quote-desk-setup.json` by `scripts/build_quote_desk_metadata.py` and deployed with `sf project deploy start` (11 components, after a dry run); part E is `scripts/make_desk_user.py`. The CLI makes every call itself, so the admin's token never reaches the scripts. The click steps below stay as the record of what the metadata does. Sign in to the developer org first (Enpass: "Salesforce Dev gtm-pipeline"). That is Israel's.

## 0. Read the org first (COURSES 2ND; change nothing)

Report each value to the Code chat. Change nothing in this part.

1. Setup, quick find **Company Information**. In **User Licenses**, the Total and Used figures for **Salesforce** and for **Salesforce Integration**. The desk user needs one free **Salesforce** licence (Israel's own user takes one; a Developer Edition org usually has two). If none is free, stop: do not take Israel's licence or buy one.
2. Setup, quick find **Sharing Settings**. Under Organization-Wide Defaults, the **Default Internal Access** for **Opportunity** and for **Quote** (Quote may be missing until part A; read it again after A).
3. Setup, quick find **Profiles**. Is there a profile named **Minimum Access - Salesforce**? (Part C copies it.)
4. After part A only: Object Manager, **Quote**, Fields & Relationships, **Status**. List its values. The desk uses **Needs Review**, **Approved** and **Rejected**; all three are Salesforce's own values.

## A. Switch Quotes on (COURSES 2ND)

Setup, quick find **Quote Settings**. Tick **Enable Quotes**, then **Save**. On the next screen, keep the Opportunity page layouts ticked so the Quotes list appears on opportunities, and **Save**. Leave every other quote setting as it is (no quote templates, no quote PDF, no sync).

## B. Seven custom fields on Quote (COURSES 2ND)

Setup, Object Manager, **Quote**, Fields & Relationships, **New**. For each field: choose the data type, type the label, then **overwrite the Field Name** with the one in the table (Salesforce suggests one with the label's capital letters; the workflow uses these exact names). On the field-level security step, untick the **Visible** header so no profile gets the field, then tick **System Administrator** only: the desk user gets its access from the permission set in D. On the page-layout step, keep **Quote Layout** ticked.

| # | Data type | Field Label | Field Name | Settings |
|---|---|---|---|---|
| 1 | Text | GTM case id | `GTM_Case_Id` | Length 20. Tick **Unique**, with **Treat "ABC" and "abc" as duplicate values (case insensitive)**. Tick **External ID** |
| 2 | Number | GTM payment terms (days) | `GTM_Payment_Terms_Days` | Length 3, Decimal Places 0 |
| 3 | Number | GTM term (months) | `GTM_Term_Months` | Length 3, Decimal Places 0 |
| 4 | Text Area (Long) | GTM special terms | `GTM_Special_Terms` | Length 2000, 4 visible lines |
| 5 | Text Area (Long) | GTM rep note | `GTM_Rep_Note` | Length 2000, 4 visible lines |
| 6 | Text Area (Long) | GTM desk reason | `GTM_Desk_Reason` | Length 1000, 3 visible lines |
| 7 | Text | GTM desk stamp | `GTM_Desk_Stamp` | Length 255 |

Salesforce adds `__c`, so the API names are `GTM_Case_Id__c` and so on. Descriptions (optional, for the record) are in `quote-desk-setup.json`.

## C. Profile "GTM v2 API only" (COURSES 2ND)

Setup, quick find **Profiles**, open **Minimum Access - Salesforce**, **Clone**. Profile Name: `GTM v2 API only`. **Save**. On the new profile, **Edit**, then under **Administrative Permissions** (or **System Permissions**, depending on the page):

- tick **API Enabled**;
- tick **API Only User** (the user can call the API but cannot sign in to Salesforce's screens).

Change nothing else. **Save**. If the profile list has no **Minimum Access - Salesforce**, stop and tell the Code chat: do not clone Standard User or System Administrator.

## D. Permission set "GTM v2 quote desk" (COURSES 2ND)

Setup, Users, **Permission Sets**, **New**.

| Field | Value |
|---|---|
| Label | GTM v2 quote desk |
| API Name | `GTM_v2_Quote_Desk` |
| Description | Lets the GTM v2 quote desk read quotes and change only their status and the two desk fields. No create, no delete. |
| License | **--None--** |

Save. Then **Object Settings**:

| Object | Object permissions | Field permissions |
|---|---|---|
| **Quotes** | **Read**, **Edit**. Leave Create, Delete, View All, Modify All unticked | **Read and Edit**: Status, GTM desk reason, GTM desk stamp. **Read only**: GTM case id, GTM payment terms (days), GTM term (months), GTM special terms, GTM rep note, Expiration Date, Bill To, Opportunity Name, Account Name, Subtotal, Total Price. **Leave unticked**: Contact Name, Email, Phone, Fax, and every other field |
| **Quote Line Items** (if listed on its own) | Whatever the page allows, read only | **Read** on every field |
| **Opportunities** | **Read** only | **Read**: Amount, Close Date. Nothing else ticked |
| **Accounts** | **Read** only | Nothing ticked (Account Name needs no tick) |
| **Products** | **Read** only | Nothing extra |
| **Price Books** | **Read** only | Nothing (added 24/11/2026 with Israel's yes: without it Salesforce hides quote lines from the desk) |
| **Custom permission** GTM v2 quote desk: no quote line changes (`GTM_Quote_Desk_No_Line_Changes`) | Enabled | Added 24/11/2026 with Israel's yes. The Apex trigger `GtmQuoteDeskLineGuard` refuses any quote line create, edit or delete by its holders: Salesforce lets anyone who can edit a quote and see its price book change its lines |

Some fields have no tick box (Salesforce always lets them be read, or works them out itself); note which ones. Nothing else in the permission set: no system permissions, no other objects, no apps or tabs.

## E. The desk user (COURSES 2ND; Israel types his email)

Setup, Users, **Users**, **New User**.

| Field | Value |
|---|---|
| First Name | GTM |
| Last Name | Quote Desk |
| Alias | gtmdesk |
| Email | Israel's own address (he types it). Nothing is sent with the box below unticked |
| Username | `gtm-v2-quote-desk-` plus four random lowercase letters or digits, then `@example.com` |
| User License | **Salesforce** |
| Profile | **GTM v2 API only** |
| Role | none |
| Generate new password and notify user immediately | **Untick** |

Save. Then, on the new user's page, **Permission Set Assignments**, Edit Assignments: add **GTM v2 quote desk**. Save. Report the username to Israel only (it goes in `.env` and the private list, nowhere else).

## F. Sharing for the seeded opportunities (COURSES 2ND; only if part 0 says so)

Skip this part if part 0 found **Opportunity** Default Internal Access is **Public Read/Write**. If it is **Private** or **Public Read Only**, the desk user cannot reach the opportunities the seed makes (they belong to Israel), so share just those:

1. Setup, quick find **Public Groups**, **New**. Label `GTM v2 quote desk`; Group Name `GTM_v2_Quote_Desk`; untick **Grant Access Using Hierarchies**; add the member **User: GTM Quote Desk**. Save.
2. Setup, **Sharing Settings**, **Opportunity Sharing Rules**, **New**. Label `GTM v2 quote desk`; Rule Name `GTM_v2_Quote_Desk`; type **Based on criteria**; criteria: **Opportunity Name** **starts with** `GTM v2 quote desk:`; share with **Public Groups: GTM v2 quote desk**; Opportunity Access **Read/Write**. Save.

The rule reaches only the opportunities whose name starts with that text, which only the seed makes. The permission set still gives Opportunity **Read** only, so the desk can never change an opportunity itself. If Quote's own Default Internal Access (part 0, step 2) is anything other than **Controlled by Parent**, tell the Code chat before going on.

## G. External Client App (COURSES 2ND; Israel's hands for the key and secret)

The same steps as chapter 4's part D, with these values. Setup, quick find **External Client App Manager**, **New External Client App**.

| Section | Field | Value |
|---|---|---|
| Basic Information | External Client App Name | GTM v2 quote desk (n8n) |
| | API Name | leave what Salesforce suggests |
| | Contact Email | Israel's own address (he types it) |
| | Distribution State | **Local** |
| | Description | n8n on Israel's Mac reads quotes that need review and records the approver's decision. Client credentials; runs as the GTM Quote Desk user. |
| API (Enable OAuth Settings) | Enable OAuth | **Tick** |
| | Callback URL | `http://localhost:5678/rest/oauth2-credential/callback` (required; never used) |
| | OAuth Scopes | **Manage user data via APIs (api)** only |
| | Flow Enablement | Tick **Enable Client Credentials Flow** and accept the warning |

**Create.** Then the **Policies** tab, **Edit**:

| Section | Field | Value |
|---|---|---|
| OAuth Policies, Plugin Policies | Permitted Users | **Admin approved users are pre-authorized** |
| App Policies | Select Permission Sets | add **GTM v2 quote desk** |
| OAuth Flows and External Client App Enhancements | Enable Client Credentials Flow | **Tick** |
| | Run As (Username) | the GTM Quote Desk user from E |

Save. **Israel's hands from here:** the **Settings** tab, **OAuth Settings**, **Consumer Key and Secret**; enter the code Salesforce emails him; keep the page open for H and I. Neither value goes in any note, chat or file other than `.env` and the n8n credential.

## H. Two lines in `.env` (Israel)

In the repo folder, `open -e .env`. The Code chat has added two empty lines at the end. Paste:

| Line | Value |
|---|---|
| `SALESFORCE_DESK_CLIENT_ID=` | the Consumer Key of "GTM v2 quote desk (n8n)" |
| `SALESFORCE_DESK_CLIENT_SECRET=` | its Consumer Secret |

`SALESFORCE_DOMAIN` is already there from chapter 4: the same org. Save and close.

## I. n8n credential (COURSES 2ND makes it; Israel pastes the key and secret)

n8n at http://localhost:5678, signed in as the owner. **Credentials**, **Create credential**, type **OAuth2 API** (the general one, as in chapter 4).

| Field | Value |
|---|---|
| Credential name | `Salesforce quote desk (client credentials)` (exactly: the import finds it by name) |
| Grant Type | **Client Credentials** |
| Access Token URL | `https://<the My Domain host>/services/oauth2/token` (the same host as chapter 4's credential) |
| Client ID | Israel pastes the Consumer Key |
| Client Secret | Israel pastes the Consumer Secret |
| Scope | leave empty |
| Authentication | **Body** |

Save. The staff messages use the Google login n8n already has ("Google least reach gtm-pipeline", chapter 3: send mail only, to the account's own inbox). No new Google login and no consent screen.

## J. Sign the Salesforce CLI in, for the seed only (Israel)

The desk user can read and decide quotes but cannot create them, on purpose. The made-up products, opportunities and quotes are written once by the admin, through the CLI, as in INIT-164. In Terminal, in the repo folder:

```bash
sf org login web --alias gtm-v2-admin
```

Sign in to the developer org in the browser window that opens and allow the CLI. Tell the Code chat when it says "Successfully authorized".

## K. Seed the quotes, then check the org (Code chat)

```bash
python scripts/seed_quotes.py --admin
python scripts/salesforce_quote_desk_check.py
```

The seed signs in as the admin through the CLI (it reads the CLI's token and never prints it). It makes five products in the standard price book, one opportunity per demo case named `GTM v2 quote desk: Q-00NN`, and one quote per demo case with its line items, upserted on `GTM_Case_Id__c`, all in status **Needs Review**. Made-up companies already in the org (chapter 4), no contacts, no people.

The check signs in exactly as n8n will and checks: scope `api` only; runs as GTM Quote Desk, API only; all seven fields as specified; it can read every demo quote with its lines, opportunity and account; it can edit a quote's status and the two desk fields (proved by writing a quote's own values back to it); it cannot create or delete a quote; it cannot edit an opportunity, account, product, price book or price book entry; it can read quote lines, and the Apex guard refuses it any change to one (proved by an edit to a line's own quantity); it cannot read a quote's contact, email, phone or fax; it cannot touch Leads, Contacts, Cases, Users or any other custom field.

## L. Sign the CLI out (Israel)

```bash
sf org logout --target-org gtm-v2-admin --no-prompt
```

No admin token stays on the Mac. To reset the demo quotes later, the Code chat uses the desk's own login (`python scripts/seed_quotes.py --reset`): it can set a quote back to **Needs Review** and clear the desk fields, and nothing more.

## M. Import and publish the workflow (Code chat)

```bash
python scripts/n8n_publish_routing.py --target quote_desk
python scripts/n8n_publish_routing.py --target quote_desk --check
```

The first builds the workflow from the committed file plus the org's host from `.env`, finds the credentials by name, creates and publishes "GTM v2 chapter 5: quote exceptions desk", and checks the form answers at http://localhost:5678/form/gtm-v2-quote-desk. The second reads the live copy back and compares it with the file.

## N. One reviewed run (COURSES 2ND opens the pages; Israel reviews)

1. Open http://localhost:5678/form/gtm-v2-quote-desk in Chrome (the Claude app's built-in browser pane blocks n8n's form submit).
2. Press **Read the queue**. The desk reads every quote in **Needs Review**, checks the rules, and the AI triages each one. Wait about a minute.
3. An approver message arrives in Israel's inbox (to his own address with `+gtm-approver`): each exception, the rule broken, the evidence and the proposed action, with a link to the review page. The browser that started the run shows the same page.
4. On the review page, type a reviewer label (not a personal name), and for every quote choose **Approve** or **Reject: send back to the owner**, with a reason (required for a reject). Quotes that must be fixed first (missing fields, figures that do not match, an expired quote) offer only Reject. Suggested choices for the test run, from the labels in `skins/quote-desk/cases.json`: approve Q-0003 and Q-0005; reject the other six.
5. Submit. Approved quotes become **Approved** in Salesforce and rejected ones **Rejected**, each with the reason and a stamp. The owner of each quote gets a message (to `+gtm-owner`) with the decision, the reason and a draft reply to the customer, marked as a draft. Nothing is sent to a customer at any step.

## O. Check the run (Code chat)

```bash
python scripts/check_desk_run.py --latest --salesforce
python scripts/check_desk_run.py --stamp "<a GTM desk stamp copied from a quote in Salesforce>"
```

It passes when every quote triaged has a person's decision with a reason; every decision carries a stamp matching its log row; no quote that had to be fixed was approved; every decision reached Salesforce; Gmail accepted a message for the owner of every saved quote (its id is in the log; the address is the build account's own, fixed in code and tested); and, with `--salesforce`, each quote carries the logged status, reason and stamp.

## Switching it off

Nothing is scheduled. To stop the desk at once: deactivate the workflow in n8n; or untick **Enable Client Credentials Flow** on the app's Policies tab; or deactivate the GTM Quote Desk user. The seeded quotes can stay: they are made up and sit in a free org.
