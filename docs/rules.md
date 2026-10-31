# Data-quality rules

Every enriched Clay row passes through these checks in n8n before anything is written to HubSpot. A row that fails a **block** rule goes to the quarantine data table with a reason code. **Flag** rules record a warning but still let the row load. **Route** rules decide between creating and updating the record.

## Rule table

| ID | Check | Type | Outcome | Reason code |
|---|---|---|---|---|
| DQ-01 | `company_name` and `domain` are both present (not blank after trimming) | Block | Quarantine | `MISSING_REQUIRED` |
| DQ-02 | `domain` is a valid hostname after normalisation | Block | Quarantine | `INVALID_DOMAIN` |
| DQ-03 | The normalised `domain` has not already appeared earlier in the same batch | Block | Quarantine the later copies; keep the first | `DUPLICATE_IN_BATCH` |
| DQ-04 | *(Replaced by `clay_domain_key` batch upsert — HubSpot decides create vs update)* | Route | Batch upsert keyed on `clay_domain_key`; response marks each row `new: true` (created) or `new: false` (updated) | — |
| DQ-05 | If `employee_count` is present, it is a whole number ≥ 0 | Block | Quarantine | `HEADCOUNT_NOT_NUMERIC` |
| DQ-06 | `industry` is present | Flag | Load without industry, record the flag in the run log | `INDUSTRY_MISSING` |
| DQ-07 | `industry` is present but does **not** appear in the mapping table | Flag | Load without industry, record the flag in the run log | `INDUSTRY_UNMAPPED` |

DQ-06 covers a blank industry; DQ-07 covers an industry that is present but not in the mapping table. A row never gets both flags.

## Evaluation order

1. **DQ-01**, then **DQ-02**. Domain checks only run when a domain is present.
2. **DQ-05**, **DQ-06** and **DQ-07** on every row.
3. **DQ-03**, only on rows that passed DQ-02. Two different invalid strings are not counted as duplicates of each other.
4. **DQ-04** is replaced by batch upsert keyed on `clay_domain_key`. Rows that pass all block rules are sent to HubSpot via `POST /crm/v3/objects/companies/batch/upsert` with `idProperty: "clay_domain_key"`. No search call is needed.

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
| `industry` | `industry` | Mapped via `scripts/industry_mapping.py` (Clay label → HubSpot enum). Unmapped values are flagged (DQ-07) and loaded without industry. |
| `employee_count` | `numberofemployees` | Integer |
| `hq_city` | `city` | |
| `hq_country` | `country` | |

## Confirmed in week 2 (2026-10-31)

### P-1 — Industry mapping + DQ-07 ✓

- Mapping table lives in `scripts/industry_mapping.py` (148 entries, sourced from the live HubSpot picklist on 2026-10-31).
- DQ-07 (`INDUSTRY_UNMAPPED`) added to the rule table above. DQ-06 and DQ-07 are mutually exclusive.

### P-2 — `clay_domain_key` + batch upsert ✓

- Custom property `clay_domain_key` created: single-line text, unique values, holding the normalised domain.
- Writes go through `POST /crm/v3/objects/companies/batch/upsert` with `idProperty: "clay_domain_key"` (up to 100 rows per call).
- The upsert response marks each row `"new": true` (created) or `"new": false` (updated).
- Existing companies (including smoke-test record 301412818400) were backfilled with their normalised domain as `clay_domain_key`.
