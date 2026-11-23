# Zapier admin settings, on paper (way 4)

How this slice would be governed in a company's Zapier account. Written for the governance brief (KB-141, brief 3).

**What this is and is not.** The personal account is on the Free plan, which has none of these settings. This page applies what the Admin Essentials course teaches (KB-124) to the slice. It is course knowledge applied on paper, not experience administering Zapier Enterprise.

## The settings, applied to this slice

| Setting | What it decides | Setting for this slice | Why |
|---|---|---|---|
| Single sign-on and provisioning | One way in, through the company's identity provider. Leavers lose access when they are removed there | Required for every user; provisioning on | Access ends the day someone leaves, with no Zapier step to forget |
| Roles | Who can administer, build or only use | Two admins, an owner and a backup. Builders as members. Approvers only use the form | No single point of failure; approvers cannot change the Zaps |
| Audit trail | A record of who changed what, and when | On before the first user; reviewed monthly by the owner | A change to a Zap that emails staff can be traced |
| Allowed apps | Which apps can be used at all | Free version: Zapier Forms, Zapier Tables, Email by Zapier. Pro version adds Webhooks by Zapier, AI by Zapier and the approval step. Everything else blocked | The slice needs six apps; nothing else should be one click away |
| Managed apps | Only admins may connect the app, whatever the connection type | Any app that reaches company data, such as Google Sheets, Gmail or the CRM | Builders cannot connect a personal or over-wide login |
| Allowed domains | Which email domains may complete a sign-in connection | The company's domain only | Stops a personal Google account being connected by mistake |
| Action restrictions | Which triggers and actions are available inside an allowed app, per workspace | Email by Zapier: send only. Zapier Tables: create record only. No delete actions | Same least-reach rule as the Google logins in n8n and Make |
| Shared connections | Connections owned by a service account, not a person | The tracker and the mail sender use service-account connections | The slice keeps working when a builder moves on |
| Usage alerts | A warning before tasks run out | Alert at 80% of the monthly tasks | A runaway Zap is caught before the plan stops every Zap |
| Approvals and one request path | New or changed Zaps that touch company data need sign-off | Any change to the slice goes through the request path, with the owner approving | Matches the rule that a person approves before a CRM write |
| Workspaces | Separate spaces with their own apps and rules | One workspace for revenue-operations automations | GTM Zaps and their connections stay apart from other teams' |
| MCP under the same controls | Zapier MCP calls are held to the same allowed apps and actions | Expose only "Zapier Tables: Create Record" on the tracker | Claude can start the slice and do nothing else (way 3) |
| Own model provider, guardrail steps | Which AI model the AI steps use, and checks on their output | The company's approved provider; a guardrail step before any AI output is emailed | AI output is checked before it reaches staff |

## Three phases

From the Admin Essentials course, in our words:

1. **Before the first user.** Audit trail, connection rules, one way in, roles, allowed apps.
2. **As use grows.** Shared service-account connections, usage alerts, approvals, one request path.
3. **At scale.** Workspaces, action restrictions, MCP under the same controls, own model provider, guardrail steps.

## Controls that are easy to confuse

| Control | What it decides |
|---|---|
| Allowed domains | Which email domains may complete a sign-in connection. Covers apps that connect by sign-in only |
| Managed apps | Only admins may connect the app. Covers every connection type, including API keys |
| Allowed apps | Which apps can be used at all |
| Action restrictions | Which triggers and actions are available inside an allowed app, per workspace |
| Domain capture | Who joins the company account when they sign up |

## What the Free account does instead

- Both Zaps are switched off outside tests and demos.
- The Free version reaches nothing outside Zapier, so there is no outside login to govern.
- The approver's form is public on zapier.app. That is an open point on the [control sheet](control-sheet.md).
