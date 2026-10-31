# GTM enrichment quality pipeline

A single go-to-market data workflow: **Clay** enriches a list of companies, **n8n** runs data-quality checks on every row, and only rows that pass reach **HubSpot**, as a create or update matched on domain. Rows that fail go to a quarantine table with a reason code, so you can see and fix bad data before it reaches the CRM.

> **Status:** week 1 of 3. Scaffold, rules and HubSpot smoke test are done; the n8n workflow arrives in week 2. Everything here is company-level and synthetic. The repo contains no personal contact data.

## Architecture

```mermaid
flowchart LR
    A[Clay table<br/>name + domain] --> B[Clay enrichment<br/>industry · headcount · HQ]
    B -->|CSV export| C[n8n: read file]
    C --> D{DQ checks<br/>DQ-01 · 02 · 03 · 05 · 06}
    D -->|fail| Q[(n8n data table<br/>quarantine + reason code)]
    D -->|pass| E{DQ-04<br/>search HubSpot by domain}
    E -->|not found| F[Create company]
    E -->|found| G[Update company]
    F --> H[(HubSpot)]
    G --> H
```

**Pull model.** n8n pulls the data; Clay never pushes. Clay's webhook sources and HTTP API column are Growth-plan features, and the Public API's table-read endpoint is Enterprise-only, so on the free plan rows leave Clay as a CSV export. No tunnel or public endpoint is needed: n8n runs locally in Docker.

## Data-quality rules

| ID | Check | Outcome | Reason code |
|---|---|---|---|
| DQ-01 | Name and domain present | Quarantine | `MISSING_REQUIRED` |
| DQ-02 | Domain format valid (after normalisation) | Quarantine | `INVALID_DOMAIN` |
| DQ-03 | Duplicate domain within the batch | Quarantine later copies | `DUPLICATE_IN_BATCH` |
| DQ-04 | Company already in HubSpot | Update, not create | — |
| DQ-05 | Headcount numeric when present | Quarantine | `HEADCOUNT_NOT_NUMERIC` |
| DQ-06 | Industry missing | Flag, still load | `INDUSTRY_MISSING` |

[`docs/rules.md`](docs/rules.md) has the full spec: evaluation order, domain normalisation, quarantine schema and the Clay → HubSpot field mapping.

## Repo layout

```
docs/rules.md                 DQ rule spec (source of truth for the n8n checks)
sample/companies_sample.csv   25 synthetic companies with seeded bad rows
sample/README.md              Expected result for every seeded row
scripts/hubspot_smoke_test.py Service-key test: search by domain → create/update → read back
tests/                        pytest, with all HubSpot calls mocked
n8n/                          Workflow export, credentials stripped (week 2)
```

## Run steps

### Prerequisites

- Python 3.13, plus n8n running locally in Docker (`curl -s localhost:5678/healthz` returns `{"status":"ok"}`)
- A HubSpot account with a **service key** that has `crm.objects.companies.read` and `crm.objects.companies.write`. Use a service key, not a private app, because private apps are retired on new accounts.
- A Clay account. The free plan is enough, since data leaves Clay as a CSV export.

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in HUBSPOT_SERVICE_KEY
pytest -q              # offline, no credentials needed
```

### HubSpot smoke test

```bash
python scripts/hubspot_smoke_test.py --search-only   # read scope only
python scripts/hubspot_smoke_test.py                 # search → create → wait for index → update → read back
python scripts/hubspot_smoke_test.py --archive       # same, then delete the test company
```

The test writes only to the synthetic domain `gtm-pipeline-smoke-test.example`. On the first run it creates the company, waits for HubSpot search to index it and reports the lag, then updates it. Later runs go straight to the update path.

### Pipeline run

Week 2: export the enriched Clay table to CSV → import `n8n/workflow.json` → set the HubSpot credential in n8n → run.

## Demo

Week 3: a 2–3 minute walkthrough.

## Security

- Secrets live only in `.env` (git-ignored). `.env.example` lists the variable names with no values.
- The n8n workflow is exported with credentials stripped. The HubSpot credential is re-created in n8n by whoever runs it.
- Sample data is fictional and uses the reserved `.example` TLD. Live runs use public company-level data only, never personal contacts.
