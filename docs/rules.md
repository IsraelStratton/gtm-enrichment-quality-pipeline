# Data-quality rules

Every enriched Clay row passes through these checks in n8n before anything is written to HubSpot. A row that fails a **block** rule goes to the quarantine data table with a reason code. **Flag** rules record a warning but still let the row load. **Route** rules decide between creating and updating the record.

## Rule table

| ID | Check | Type | Outcome | Reason code |
|---|---|---|---|---|
| DQ-01 | `company_name` and `domain` are both present (not blank after trimming) | Block | Quarantine | `MISSING_REQUIRED` |
| DQ-02 | `domain` is a valid hostname after normalisation | Block | Quarantine | `INVALID_DOMAIN` |
| DQ-03 | The normalised `domain` has not already appeared earlier in the same batch | Block | Quarantine the later copies; keep the first | `DUPLICATE_IN_BATCH` |
| DQ-04 | A HubSpot company with this domain already exists | Route | Update the existing record (PATCH), don't create a new one | — (logged as `action=update`) |
| DQ-05 | If `employee_count` is present, it is a whole number ≥ 0 | Block | Quarantine | `HEADCOUNT_NOT_NUMERIC` |
| DQ-06 | `industry` is present | Flag | Load without industry, record the flag in the run log | `INDUSTRY_MISSING` |

## Evaluation order

1. **DQ-01**, then **DQ-02**. Domain checks only run when a domain is present.
2. **DQ-05** and **DQ-06** on every row.
3. **DQ-03**, only on rows that passed DQ-02. Two different invalid strings are not counted as duplicates of each other.
4. **DQ-04**, only on rows that passed every block rule. This is the only rule that calls HubSpot (a search by domain).

A row can fail more than one block rule. All of its codes are recorded, separated by `|` (for example `INVALID_DOMAIN|HEADCOUNT_NOT_NUMERIC`), so one pass shows everything wrong with the row.

## Normalisation (applied before DQ-02 and DQ-03)

Domains are compared after normalisation, so `https://www.Example.com/about` and `example.com` count as the same company.

1. Trim whitespace and lowercase.
2. Strip any scheme (`http://`, `https://`).
3. Strip any path, query string, fragment or port.
4. Strip a leading `www.` and a trailing `.`.

**Valid after normalisation (DQ-02):** at most 253 characters, at least two labels separated by dots, each label 1–63 characters of `a-z`, `0-9` or `-` and not starting or ending with `-`, and an alphabetic last label (the TLD) of 2–63 characters.

`employee_count` (DQ-05) accepts thousands separators (`1,250` → `1250`). Ranges (`51-200`), words (`about 200`), decimals and negative numbers fail. Map Clay's numeric employee-count field, not its size-band field.

## Quarantine data table (n8n)

| Column | Content |
|---|---|
| `run_id` | n8n execution ID |
| `row_number` | 1-based position in the source batch |
| `company_name` | As received (may be blank) |
| `domain` | As received (not normalised) |
| `reason_codes` | Every block rule that failed, `\|`-separated |
| `reason_detail` | Short readable explanation, e.g. `domain "bad_domain.example" contains "_"` |
| `quarantined_at` | ISO-8601 timestamp |

## Field mapping (Clay → HubSpot company)

| Clay column | HubSpot property | Notes |
|---|---|---|
| `company_name` | `name` | |
| `domain` | `domain` | Written in normalised form |
| `industry` | `industry` | ⚠️ HubSpot's `industry` is a fixed picklist (e.g. `COMPUTER_SOFTWARE`). Clay's free-text values are rejected with HTTP 400. See *Proposed for week 2* below. |
| `employee_count` | `numberofemployees` | Integer |
| `hq_city` | `city` | |
| `hq_country` | `country` | |

## Known edge case: HubSpot search lag

HubSpot's search index updates a few seconds after a write. A company created moments ago may not show up in a DQ-04 search yet. Within one batch, DQ-03 already stops the same domain from being written twice. Across runs, leave at least 30 seconds between runs. `scripts/hubspot_smoke_test.py` measures the lag in your portal. A sturdier fix is proposed below.

## Proposed for week 2 (pending confirmation)

Nothing in this section is built yet. Both items need sign-off before the n8n build starts.

### P-1 — Industry mapping + DQ-07

- A mapping table from Clay industry text to HubSpot `industry` picklist values, for example `Computer Software` → `COMPUTER_SOFTWARE`, `Hospital & Health Care` → `HOSPITAL_HEALTH_CARE`, `Financial Services` → `FINANCIAL_SERVICES`. Keys are matched trimmed and lowercased.
- The HubSpot side of the table is filled from the live picklist (`GET /crm/v3/properties/companies/industry`), not typed by hand. That call may need a schema-read scope the service key doesn't have yet; check this in the local session.
- New rule:

| ID | Check | Type | Outcome | Reason code |
|---|---|---|---|---|
| DQ-07 | `industry` is present and appears in the mapping table | Flag | Load without industry, record the flag in the run log | `INDUSTRY_UNMAPPED` |

  DQ-06 covers a blank industry and DQ-07 covers an industry that's present but unmapped, so a row never gets both flags.

### P-2 — `clay_domain_key` + batch upsert (replaces search-then-create)

- A custom company property `clay_domain_key`: single-line text, **unique values**, holding the normalised domain.
- Writes go through `POST /crm/v3/objects/companies/batch/upsert` with `idProperty: "clay_domain_key"` (up to 100 rows per call). HubSpot decides create vs update on its side, so search lag no longer matters and DQ-04 stops needing a search call.
- **Fallback:** if the property can't be created, keep search-then-create and space runs at least 30 seconds apart (see *Known edge case* above).
- **Open points for the local session:**
  - Creating the property needs a schema-write scope (`crm.schemas.companies.write`) on top of the service key's current companies read/write.
  - Companies that exist without the key (for example the smoke-test record, or anything created by hand) would be duplicated. Backfill the key on those first.
  - Confirm how the upsert response marks each row as created or updated, so the run log can still report `action=create` / `action=update`.
