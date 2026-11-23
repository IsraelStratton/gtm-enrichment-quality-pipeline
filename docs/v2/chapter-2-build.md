# Chapter 2 build guide: AI routing with a person's approval

What has to be set up, by whom, and in what order, for the n8n workflow [`n8n/workflow-v2.json`](../../n8n/workflow-v2.json) to run end to end: the data rules, the AI step, the review page, the HubSpot write and the run log.

Who does what follows Israel's ruling of 23/11/2026: the Code chat does the command line; the planning chat (COURSES 2ND) does the clicks in Chrome; Israel pastes every secret himself.

| Part | What | Who | State |
|---|---|---|---|
| A | n8n container re-created with the playbook folder mounted read-only, and published on this Mac only | Code chat | Done 23/11/2026 |
| B | Run log in the local Supabase Postgres, with an add-only login | Code chat | Done 23/11/2026 |
| C | Six company properties in HubSpot | COURSES 2ND | Done 23/11/2026 |
| D | Two n8n credentials | COURSES 2ND, Israel pasted the secrets | Done 23/11/2026 |
| E | Import and publish the workflow | COURSES 2ND | Done 23/11/2026; Form Path fixed afterwards (see E) |
| F | One test run of the demo file, approved on the review page | COURSES 2ND; the choices were entered by Claude in Chrome on Israel's yes | Done 23/11/2026, run `n8n-8790` |
| G | Check the run against the log and HubSpot | Code chat | Done 23/11/2026: every check passed |

## A. The playbook folder inside n8n (done)

`scripts/n8n_docker.sh` re-creates the `n8n` container exactly as before (same image, port and two data folders) plus one read-only folder: the repo's `skins/`, at `/home/node/gtm-skins`. n8n's file access is limited to that folder and its default `~/.n8n-files`. Proved on 23/11/2026: n8n 2.10.3 healthy, the playbook readable inside the container with the same SHA-256 as the repo file, a write refused ("Read-only file system"), all nine workflows and every credential still there, and the chapter 3 slice workflow active again.

From now on, start n8n with `scripts/n8n_docker.sh`. An older `docker run` command without the third `-v` line starts n8n without the playbook, and the routing step then stops at "Read Playbook".

After the test run passed, on Israel's yes, the same script publishes n8n on this Mac only (`-p 127.0.0.1:5678:5678`). Before, n8n answered on the Mac's network address (HTTP 200); after, that address is refused and `localhost` works as before. The script checks this every time it starts n8n. It also stops n8n with 30 seconds' grace, so n8n no longer logs "Last session crashed" on the next start.

## B. The run log (done)

`python scripts/setup_run_log.py` made schema `gtm_v2` (tables `proposals`, `decisions`, `model_prices`; views `decision_record`, `run_summary`, `cost_by_route`) and the login `gtm_v2_pipeline`. That login can only call two add-only functions and read the three views: it cannot read the tables, change or delete a row, change a price, or read any other schema (all nine checks passed). Its password is in `.env` as `GTM_V2_DB_PASSWORD`.

## C. HubSpot: six company properties (COURSES 2ND)

HubSpot, Stratton GTM Sandbox: Settings, Data management, Properties, Company properties.

1. Create a property group: **GTM v2 routing**.
2. Create these six properties on the Company object, in that group. Type the label exactly as written: HubSpot then makes the internal name shown, which is what the workflow writes to. Check each internal name before saving.

| Label | Internal name | Field type | Options: label, then internal value |
|---|---|---|---|
| GTM route | `gtm_route` | Dropdown select | Enterprise sales ANZ, `enterprise_anz` · Enterprise sales global, `enterprise_global` · Mid-market sales, `mid_market` · SMB sales, `smb` · Partnerships, `partnerships` · Customer support, `customer_support` · Marketing nurture, `nurture` · Not a fit, `disqualify` |
| GTM priority | `gtm_priority` | Dropdown select | High, `high` · Medium, `medium` · Low, `low` |
| GTM routing reason | `gtm_routing_reason` | Multi-line text | |
| GTM routing confidence | `gtm_routing_confidence` | Number (unformatted, decimals allowed) | |
| GTM routing status | `gtm_routing_status` | Dropdown select | Approved, `approved` · Changed, `changed` |
| GTM decision stamp | `gtm_decision_stamp` | Single-line text | |

For the three dropdowns, HubSpot makes an internal value from each option label (for example `enterprise_sales_anz`). Overwrite it with the internal value in the table: the workflow sends `enterprise_anz`, and HubSpot refuses a value that is not an option.

After this the portal has seven custom properties: these six and `clay_domain_key`.

## D. n8n: two credentials (COURSES 2ND, Israel pastes the secrets)

n8n at http://localhost:5678, signed in as the owner. Credentials, Create credential. The names must match exactly: the workflow finds its credentials by name.

**1. Claude key gtm-pipeline-v2**, type **Header Auth**

| Field | Value |
|---|---|
| Name | `x-api-key` |
| Value | Israel pastes the key from Enpass, "Claude key gtm-pipeline-v2" (workspace `gtm-pipeline`, US$10 monthly limit) |

**2. GTM v2 run log (Postgres)**, type **Postgres**

| Field | Value |
|---|---|
| Host | `host.docker.internal` |
| Database | `postgres` |
| User | `gtm_v2_pipeline` |
| Password | Israel pastes `GTM_V2_DB_PASSWORD` from `.env` in the repo folder (open it with `open -e .env`) |
| Port | `54322` |
| SSL | Disable |

Save each. The Postgres one shows "Connection tested successfully" when the password is right.

The HubSpot credential already exists from version 1 ("HubSpot Service Key"). Nothing to do.

## E. Import and publish the workflow (COURSES 2ND)

1. Workflows, Create workflow, then the three-dot menu, **Import from File**. Choose `n8n/workflow-v2.json` in the repo folder (`/Users/israelstratton/gtm-enrichment-quality-pipeline/n8n/workflow-v2.json`).
2. Check the three credential nodes show their credential, not a warning: **Claude Routing Step** (Claude key gtm-pipeline-v2), **HubSpot Batch Upsert** (HubSpot Service Key), and the three Postgres nodes **Log Proposals**, **Log Decisions**, **Read Run Summary** (GTM v2 run log). n8n matches them by name on save; if one shows a warning, pick the credential of that name from its list.
3. Save, then **Publish**. The form is then at http://localhost:5678/form/gtm-v2-route-leads.
4. Open the **Upload CSV** node, Options, and check **Form Path** reads `gtm-v2-route-leads`. If it shows a long ID instead, type `gtm-v2-route-leads`, save and publish again.
5. Leave every other workflow, and every Zap, as it is.

The workflow has 24 nodes. Its name is "GTM v2 chapter 2: route leads with approval".

**Why step 4.** On the first import (23/11/2026) the form came up at `/form/<a new ID>`, not at `/form/gtm-v2-route-leads`. n8n's editor (2.10.3) gives any imported trigger that already carries a webhook ID a new one, and copies that ID over its Form Path. A trigger with no webhook ID gets an ID too, but keeps its path. The file now ships the trigger with no webhook ID, so the path should survive the next import; that has been read from n8n's editor code, not yet tried by a second import, so step 4 stays. The live workflow was fixed the same day by setting its Form Path through the n8n API and publishing again: the named address now answers 200, and the old one 404.

## F. One test run (COURSES 2ND opens the pages; Israel reviews)

1. Open http://localhost:5678/form/gtm-v2-route-leads.
2. Upload `skins/lead-routing/sample_run.csv` (14 made-up companies) and press **Run the rules and the AI step**.
3. Wait about 30 seconds. The data rules stop two rows; the AI proposes a route for the other 12, one at a time.
4. The review page lists the 12 proposals, flagged rows first (marked **Check**). Israel types a reviewer label (for example `reviewer-01`) and chooses for every row. For the test, so all three actions are proved:
   - **Reject** the two attack rows (L-0034 Numbat Data, L-0036 Wombat Water) and the spam row (L-0031 Brolga Web Services);
   - **Change** one row, for example L-0007 Bluegum Retail Group to `mid_market · high`;
   - **Approve** the rest, including L-0025 Marri Robotics only if the route looks right to him (its staff number is unknown).
5. Submit. The last page shows how many rows were written, approved, changed and rejected, and the AI cost read back from the run log.

Nothing is written to HubSpot before step 5. Nothing is sent to anyone at any step.

**As run on 23/11/2026 (`n8n-8790`).** 12 proposals, 4 flagged, 2 rows quarantined. On Israel's yes, Claude in Chrome entered the choices under the reviewer label "Claude for Israel (on his yes)": rejected L-0031, L-0034 and L-0036; changed L-0007 to `mid_market · high`; approved the other 8, including L-0025 as `smb · medium`. Done page: 9 written (8 approved, 1 changed), 3 rejected, no write failed, AI cost US$0.004683. As in chapter 3, this proves the steps work; it is not a separate person's review. For the recorded demo, Israel makes the choices himself.

## G. Check the run (Code chat)

```bash
python scripts/check_run.py --latest --hubspot
```

It passes when every proposal has a decision, every write carries a stamp that matches its log row (A1.1), each changed row keeps both values (A1.3), each written HubSpot company carries the logged stamp, route, priority and status, and no rejected row carries this run's stamp. Then one stamp is looked up in one query (A1.2):

```bash
python scripts/check_run.py --stamp "<paste a gtm_decision_stamp from a HubSpot company>"
```

**Result for `n8n-8790`.** All seven checks passed: 12 of 12 proposals decided; 9 of 9 writes carry a stamp matching the log; 3 rejected rows carry none and were not written; the changed row keeps both values (L-0007: AI `mid_market · medium`, person `mid_market · high`); 9 of 9 writes reached HubSpot; 9 of 9 companies in HubSpot carry the logged stamp, route, priority and status; no rejected row carries the run's stamp. The stamp read from Bluegum Retail Group in HubSpot found its full record in one query, with the playbook hash n8n logged equal to the repo file's.
