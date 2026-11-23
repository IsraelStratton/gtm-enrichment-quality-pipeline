# Chapter 4 build guide: the same engine, writing to Salesforce

What has to be set up, by whom and in what order, for [`n8n/workflow-v2-salesforce.json`](../../n8n/workflow-v2-salesforce.json) to write approved routing decisions to Accounts in the Salesforce developer org. Every value below comes from [`salesforce/setup.json`](../../salesforce/setup.json); `scripts/salesforce_setup_check.py` reads the org afterwards and checks it against that file.

Who does what follows Israel's ruling of 23/11/2026: the Code chat does the command line and the n8n API; the planning chat (COURSES 2ND) does the clicks in Salesforce Setup and n8n; Israel signs in, passes any verification screen and pastes every secret himself.

| Part | What | Who | State |
|---|---|---|---|
| A | Seven custom fields on Account | COURSES 2ND | To do |
| B | Permission set "GTM v2 routing writer" | COURSES 2ND | To do |
| C | The API-only integration user | COURSES 2ND (Israel types his own email address) | To do |
| D | External Client App "GTM v2 routing (n8n)", client-credentials flow | COURSES 2ND; Israel passes the verification code and copies the key and secret | To do |
| E | Three lines in `.env` | Israel pastes | To do |
| F | n8n credential "Salesforce gtm-pipeline (client credentials)" | COURSES 2ND makes it; Israel pastes the key and secret | To do |
| G | Check the org, then import and publish the workflow | Code chat | To do |
| H | One test run of the demo file, reviewed | COURSES 2ND opens the pages; Israel makes the choices, or says yes to Claude in Chrome making them | To do |
| I | Check the run against the log and Salesforce | Code chat | To do |

Sign in to the developer org first (Enpass: "Salesforce Dev gtm-pipeline"). That is Israel's.

## A. Seven custom fields on Account (COURSES 2ND)

Setup, Object Manager, **Account**, Fields & Relationships, **New**. For each field: choose the data type, type the label, then **overwrite the Field Name** with the one in the table (Salesforce suggests one from the label with different capital letters; the workflow writes these exact names). On the field-level security step, untick the **Visible** header so no profile gets the field, then tick **System Administrator** only: the integration user gets its access from the permission set in B. On the page-layout step, keep **Account Layout** ticked.

| # | Data type | Field Label | Field Name | Settings |
|---|---|---|---|---|
| 1 | Text | Clay domain key | `Clay_Domain_Key` | Length 255. Tick **Unique**, with **Treat "ABC" and "abc" as duplicate values (case insensitive)**. Tick **External ID** |
| 2 | Picklist | GTM route | `GTM_Route` | "Enter values, with each value separated by a new line", one per line: `enterprise_anz`, `enterprise_global`, `mid_market`, `smb`, `partnerships`, `customer_support`, `nurture`, `disqualify`. Tick **Restrict picklist to the values defined in the value set** |
| 3 | Picklist | GTM priority | `GTM_Priority` | Values: `high`, `medium`, `low`. Restricted, as above |
| 4 | Text Area (Long) | GTM routing reason | `GTM_Routing_Reason` | Length 1000, 3 visible lines |
| 5 | Number | GTM routing confidence | `GTM_Routing_Confidence` | Length 1, Decimal Places 3 |
| 6 | Picklist | GTM routing status | `GTM_Routing_Status` | Values: `approved`, `changed`. Restricted |
| 7 | Text | GTM decision stamp | `GTM_Decision_Stamp` | Length 255 |

Salesforce adds `__c` to each name, so the API names are `Clay_Domain_Key__c`, `GTM_Route__c` and so on.

**Optional, for nicer screens only:** in each picklist's Values list, Edit a value and change its **Label** (never its API Name). Route labels: Enterprise sales ANZ, Enterprise sales global, Mid-market sales, SMB sales, Partnerships, Customer support, Marketing nurture, Not a fit. Priorities: High, Medium, Low. Status: Approved, Changed. The check notes labels left as codes; it does not fail on them.

## B. Permission set "GTM v2 routing writer" (COURSES 2ND)

Setup, Users, **Permission Sets**, **New**.

| Field | Value |
|---|---|
| Label | GTM v2 routing writer |
| API Name | `GTM_v2_Routing_Writer` |
| Description | Lets the GTM v2 routing integration create and edit Accounts and the routing fields. No delete. |
| License | **Salesforce API Integration** |

Save. Then **Object Settings**, **Accounts**, **Edit**:

- Object permissions: tick **Read**, **Create**, **Edit**. Leave **Delete**, **View All Records**, **Modify All Records** and **View All Fields** unticked.
- Field permissions: tick **Read Access** and **Edit Access** for these ten only: Clay domain key, GTM route, GTM priority, GTM routing reason, GTM routing confidence, GTM routing status, GTM decision stamp, Website, Billing Address, Employees. Leave every other field unticked. (Account Name has no field setting; Create and Edit cover it.)

Save. Nothing else in the permission set: no system permissions, no other objects, no apps or tabs. The integration user's profile already allows API access.

## C. The integration user (COURSES 2ND; Israel types his email)

Setup, Users, **Users**, **New User**.

| Field | Value |
|---|---|
| First Name | GTM |
| Last Name | Integration |
| Alias | gtmint |
| Email | Israel's own address (he types it). Nothing is sent with the box below unticked |
| Username | `gtm-v2-integration-` plus four random letters or digits, then `@example.com` (it must be unique across all Salesforce orgs; it is never used to sign in) |
| User License | **Salesforce Integration** |
| Profile | **Minimum Access - API Only Integrations** |
| Generate new password and notify user immediately | **Untick** |

Save. Then, on the new user's page:

1. **Permission Set License Assignments**, Edit Assignments: tick **Salesforce API Integration**. Save.
2. **Permission Set Assignments**, Edit Assignments: add **GTM v2 routing writer**. Save.

A Developer Edition org has one Salesforce Integration licence. If the User License list does not offer it, stop and tell the Code chat: do not use Israel's own user or a standard licence instead.

## D. External Client App (COURSES 2ND; Israel's hands for the key and secret)

Setup, quick find **External Client App Manager**, **New External Client App**.

| Section | Field | Value |
|---|---|---|
| Basic Information | External Client App Name | GTM v2 routing (n8n) |
| | API Name | leave what Salesforce suggests |
| | Contact Email | Israel's own address (he types it) |
| | Distribution State | **Local** |
| | Description | n8n on Israel's Mac writes approved routing decisions to Accounts. Client credentials; runs as the GTM Integration user. |
| API (Enable OAuth Settings) | Enable OAuth | **Tick** |
| | Callback URL | `http://localhost:5678/rest/oauth2-credential/callback` (Salesforce requires one; this flow never uses it) |
| | OAuth Scopes | **Manage user data via APIs (api)** only. No `full`, no `refresh_token, offline_access` (that one breaks the client-credentials flow) |
| | Flow Enablement | Tick **Enable Client Credentials Flow** and accept the warning |
| | Security | Leave the defaults |

**Create.** Then the **Policies** tab, **Edit**:

| Section | Field | Value |
|---|---|---|
| OAuth Policies, Plugin Policies | Permitted Users | **Admin approved users are pre-authorized** |
| App Policies | Select Permission Sets | add **GTM v2 routing writer** |
| OAuth Flows and External Client App Enhancements | Enable Client Credentials Flow | **Tick** |
| | Run As (Username) | the GTM Integration user from C |
| Everything else | | Leave the defaults |

Save. If the Run As field is under a differently named section in this release, use it there and note where it was.

**Israel's hands from here.** The **Settings** tab, **OAuth Settings**, **Consumer Key and Secret**. Salesforce emails Israel a verification code. Enter it; the Consumer Key and Consumer Secret are shown. Keep the page open for E and F. Neither value goes in any note, chat or file other than `.env` and the n8n credential.

**My Domain host:** Setup, quick find **My Domain**, "Current My Domain URL". The host is the part after `https://`, ending in `.my.salesforce.com`. It is not secret, but it is private: it stays out of the repo, the video and every note that leaves the Mac.

## E. Three lines in `.env` (Israel)

In the repo folder, `open -e .env`. The Code chat has added the three empty lines at the end. Paste:

| Line | Value |
|---|---|
| `SALESFORCE_DOMAIN=` | the My Domain host only, for example `something.develop.my.salesforce.com` |
| `SALESFORCE_CLIENT_ID=` | the Consumer Key |
| `SALESFORCE_CLIENT_SECRET=` | the Consumer Secret |

Save and close. The Code chat's checks sign in with these, as n8n does, and print neither.

## F. n8n credential (COURSES 2ND makes it; Israel pastes the key and secret)

n8n at http://localhost:5678, signed in as the owner. **Credentials**, **Create credential**, type **OAuth2 API** (the general one, not "Salesforce OAuth2 API": n8n's own Salesforce login asks for the `full` scope and cannot be narrowed).

| Field | Value |
|---|---|
| Credential name | `Salesforce gtm-pipeline (client credentials)` (exactly: the import finds it by name) |
| Grant Type | **Client Credentials** |
| Access Token URL | `https://<the My Domain host>/services/oauth2/token` |
| Client ID | Israel pastes the Consumer Key |
| Client Secret | Israel pastes the Consumer Secret |
| Scope | leave empty |
| Authentication | **Body** |

Save. There is no "Connect" button for this grant: n8n asks Salesforce for a token at the first run and renews it by itself. Leave every other credential, workflow and Zap as it is.

## G. Check the org, then import and publish (Code chat)

```bash
python scripts/salesforce_setup_check.py
```

It signs in as n8n will and checks: scope `api` only; running as the API-only integration user; API v64.0 offered; all seven fields as specified; the user can create and edit the ten fields the engine writes; it can read, create and edit Accounts but not delete them; it cannot touch Leads, Contacts, Opportunities, Cases, Quotes, Users or the rest of the core list; it can delete nothing; it can edit no other custom field.

```bash
python scripts/n8n_publish_routing.py --target salesforce
python scripts/n8n_publish_routing.py --target salesforce --check
```

The first builds the workflow from the committed file plus the host from `.env`, finds the four credentials in n8n by name, creates and publishes "GTM v2 chapter 4: route leads with approval (Salesforce)", and checks the form answers at http://localhost:5678/form/gtm-v2-route-leads-salesforce. The second reads the live copy back and compares it with the file.

## H. One test run (COURSES 2ND opens the pages; Israel reviews)

The same run as chapter 2, so the two CRMs can be compared row for row.

1. Open http://localhost:5678/form/gtm-v2-route-leads-salesforce.
2. Upload `skins/lead-routing/sample_run.csv` and press **Run the rules and the AI step**.
3. Wait about 30 seconds. The data rules stop two rows; the AI proposes a route for the other 12.
4. On the review page, type a reviewer label (not a personal name) and choose for every row:
   - **Reject** L-0031 Brolga Web Services (spam), L-0034 Numbat Data and L-0036 Wombat Water (attacks);
   - **Change** L-0007 Bluegum Retail Group to `mid_market · high`;
   - **Approve** the rest, including L-0025 Marri Robotics only if its route looks right (its staff number is unknown).
5. Submit. The last page says how many Accounts were written, approved, changed and rejected, and the AI cost.

Nothing is written to Salesforce before step 5. Nothing is sent to anyone at any step.

## I. Check the run (Code chat)

```bash
python scripts/check_run.py --latest --salesforce
python scripts/check_run.py --stamp "<a GTM decision stamp copied from an Account in Salesforce>"
```

It passes when every proposal has a decision, every write carries a stamp matching its log row, the changed row keeps both values, every write went to Salesforce, every written Account carries the logged stamp, route, priority and status, and no rejected row carries the run's stamp.

## Switching it off

Nothing is scheduled. To stop every Salesforce write at once: deactivate the workflow in n8n, or in Salesforce untick **Enable Client Credentials Flow** on the app's Policies tab, or deactivate the GTM Integration user. A Developer Edition org may be closed after a time without a sign-in (KB-137 section 9 says 45 days), so Israel signs in now and then; the repo, the log and the video keep the record either way.
