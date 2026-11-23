# Build the slice in Zapier

Zapier is shown four ways (KB-137, section 9, "Showing Zapier"). This guide covers way 1, the Free version. Ways 2 to 4 are listed at the end and get their own steps when reached.

Who does what (Israel's ruling, 23/11/2026, 12:39): COURSES 2ND clicks in Zapier. The Code chat writes the steps and checks the emails. Israel does sign-ins and the yes before the Pro trial.

## Way 1: Free plan, two Zaps joined through a Zapier Table

Zapier Free has no webhooks and allows one action per Zap. So the slice is two Zaps with a Zapier Table between them.

```text
Zapier Form "Approve a lead" -> Zap 1 -> Zapier Table "GTM v2 tracker (Zapier)" -> Zap 2 -> Email by Zapier to the owner
```

- **The entry point is a person approving.** The approver fills in a Zapier Form. That stands in for the shared webhook, which Free cannot have.
- **No outside login.** The Form, the Table and Email by Zapier are all inside Zapier, so this version reaches nothing in Google.
- **Cost.** Each lead uses 1 task: Zapier did not charge for the Table step. Free allows 100 tasks a month, and Email by Zapier sends at most 5 emails a day.
- **State, 23/11/2026, 15:15.** Built by COURSES 2ND and tested: 3 leads, 3 runs of each Zap, 3 records, 3 emails, 3 tasks. Both Zaps are now off. The form is public on zapier.app (see the [control sheet](../../docs/v2/control-sheet.md)).

### 1. The Table: `GTM v2 tracker (Zapier)`

Zapier, **Tables**, **Create**. Add these 13 text fields, in this order:

`written_by`, `run_id`, `lead_id`, `company_name`, `domain`, `route`, `priority`, `owner_team`, `decision`, `approved_by`, `approved_at`, `sent_at`, `received_at`

### 2. The Form: `Approve a lead`

Zapier, **Forms** (Interfaces), **Create**, a form named `Approve a lead`. **Do not** connect it straight to the Table: Zap 1 does that, so the two Zaps are joined only through the Table.

| Field | Type | Values |
|---|---|---|
| `lead_id` | Short text | |
| `company_name` | Short text | |
| `domain` | Short text | |
| `industry` | Short text | |
| `enquiry` | Long text | |
| `route` | Short text | `enterprise_anz` or `mid_market` |
| `priority` | Short text | `high`, `medium` or `low` |
| `owner_team` | Short text | |
| `reason` | Long text | |
| `decision` | Short text | `approved` or `changed` |
| `approved_by` | Short text | |

### 3. Zap 1: `GTM v2 slice 1 of 2: approved lead to tracker`

- Trigger: **Zapier Forms**, **Form Submission Created**, form `Approve a lead`.
- Action: **Zapier Tables**, **Create Record**, table `GTM v2 tracker (Zapier)`.

| Table field | Value |
|---|---|
| `written_by` | `zapier` |
| `run_id` | `slice-zapier-` then the trigger's submission ID, then `-` and `lead_id` |
| `lead_id` to `approved_by` | The matching form fields |
| `approved_at` | The submission's created time |
| `sent_at` | The submission's created time |
| `received_at` | `{{zap_meta_utc_iso}}` |

Test the trigger with one submission, test the action, then **Publish**. Zapier's Copilot could not map these fields on 23/11/2026, so map them by hand. The step test writes one real record.

### 4. Zap 2: `GTM v2 slice 2 of 2: tracker row to owner email`

- Trigger: **Zapier Tables**, **New Record**, table `GTM v2 tracker (Zapier)`.
- Action: **Email by Zapier**, **Send Outbound Email**.
  - To: the owner inbox, written as the `+gtm-slice` address. This is the one place the address is typed. Keep it off screen in the video, and out of any export.
  - Subject: `Approved lead for {owner_team}: {company_name} ({priority})`, mapped from the record.
  - Body, mapped from the record:

```text
{company_name} ({domain}) is approved for {owner_team}.

Route: {route}
Priority: {priority}
Decision: {decision} by {approved_by} at {approved_at}

Run: {run_id}
Sent by the Zapier slice (Free plan). Made-up demo data.
```

The Table has no `industry`, `enquiry` or `reason` field, so Zap 2's email is shorter than the n8n and Make ones. That is one cost of joining the Zaps through a Table on Free.

Skip Zap 2's step test: on Free it emails only the account's own address, and it counts towards the 5 emails a day. **Publish**.

### 5. Test (COURSES 2ND, then the Code chat)

1. Submit the form three times, with the values of `L-0001`, `L-0002` and `L-0003` from [approved_leads.json](../approved_leads.json).
2. Pass when Zap 1 and Zap 2 each show three successful runs, and the Table holds three records with `written_by` = `zapier`. The Code chat then checks for three emails from Email by Zapier.
3. Note the tasks used. Expect 3.

Then switch both Zaps off, unless the Pro trial follows straight away (KB-135, section 5).

## Ways 2 to 4

| Way | What | Gate |
|---|---|---|
| 2 | Pro trial: one Zap. Webhook with the shared payload, Zapier's AI step, an approval step, then the row and the email | Israel's yes before the trial starts. Check first whether it asks for a card: if it does, stop |
| 3 | Zapier MCP: Claude runs one Zapier action, adding a record to the tracker Table, which sets off Zap 2 | Israel signs in to connect Zapier MCP. One MCP call uses 2 tasks |
| 4 | Zapier admin settings on paper: sign-on, allowed apps, roles, audit | None. Written by the Code chat for the governance brief (KB-141, brief 3) |
