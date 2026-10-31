# Local run (macOS)

How to run the HubSpot smoke test on a Mac. It runs locally because it needs network access to HubSpot and the real service key.

## 1. Clone

```bash
git clone https://github.com/IsraelStratton/gtm-enrichment-quality-pipeline.git
cd gtm-enrichment-quality-pipeline
```

## 2. Create a virtual environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

`python3.13 --version` should print 3.13.x. If `python3.13` isn't found, install it with `brew install python@3.13`. Run `source .venv/bin/activate` again in every new terminal.

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

Optional offline check (no credentials, no network calls):

```bash
pytest -q
```

Expected: `30 passed`.

## 4. Configure `.env`

```bash
cp .env.example .env
open -e .env
```

Set these two values and leave the others at their defaults:

```
HUBSPOT_SERVICE_KEY=<the gtm-pipeline service key from Enpass>
HUBSPOT_PORTAL_ID=443844940
```

No quotes and no spaces around `=`. `.env` is git-ignored. Check that it's ignored before committing anything:

```bash
git check-ignore .env
```

It should print `.env`.

## 5. Run the smoke test

Read scope only (no writes):

```bash
python scripts/hubspot_smoke_test.py --search-only
```

Full test: search by domain, create or update, read back:

```bash
python scripts/hubspot_smoke_test.py
```

The test only touches one synthetic company, **GTM Pipeline Smoke Test Co** on the domain `gtm-pipeline-smoke-test.example`. To delete it afterwards, run the full test again with `--archive`:

```bash
python scripts/hubspot_smoke_test.py --archive
```

## 6. What success looks like

**`--search-only`.** The output ends with a `PASS read scope` line. Before the first full run it shows 0 matches; after that, 1 match and its record ID:

```
Searching HubSpot companies for domain gtm-pipeline-smoke-test.example ...
PASS read scope: 0 match(es)
```

**Full test, first run.** Creates the company, waits for HubSpot search to index it, then updates it (the record ID will differ):

```
Searching HubSpot companies for domain gtm-pipeline-smoke-test.example ...
CREATE company id 12345678901
Waiting for the new company to appear in search (HubSpot indexes writes asynchronously) ...
Searchable after ~4s
UPDATE company id 12345678901
PASS search by domain -> create/update -> read back
View: https://app-ap1.hubspot.com/contacts/443844940/record/0-2/12345678901
```

The `Searchable after ~Ns` line is the search-index lag in this portal. Note it down, because it decides how far apart pipeline runs need to be (see `docs/rules.md`).

**Later runs.** The company already exists, so the run goes straight to the update path:

```
Searching HubSpot companies for domain gtm-pipeline-smoke-test.example ...
UPDATE company id 12345678901
PASS search by domain -> create/update -> read back
View: https://app-ap1.hubspot.com/contacts/443844940/record/0-2/12345678901
```

Open the `View:` link: the company's description shows the timestamp of the run. `echo $?` right after a run prints the exit code: `0` pass, `1` HubSpot or network failure, `2` configuration error.

## 7. Reading errors

Failures print one `FAIL` line to the terminal and exit with code `1`. The key itself is never printed.

### 401: `FAIL Service key rejected (401) ...`

HubSpot didn't accept the key. Check, in order:

1. `HUBSPOT_SERVICE_KEY` in `.env` is the **gtm-pipeline** key, copied in full with no quotes or line break.
2. The key hasn't been rotated or revoked. In HubSpot, open the service key under Settings → Integrations. If it was rotated, copy the current value from there into `.env` (and Enpass).
3. The key belongs to portal 443844940, not another account.

### 403: `FAIL Missing scope (403) ...`

The key is valid but lacks a permission. The `--search-only` result tells you which one:

| `--search-only` | Full test | Missing scope |
|---|---|---|
| 403 | 403 | `crm.objects.companies.read` (and probably write too) |
| PASS | 403 | `crm.objects.companies.write` |

Add the missing scope to the gtm-pipeline service key in HubSpot, then re-run. No change to `.env` is needed unless HubSpot issues a new key value.

### Other failures

| Output | Meaning | What to do |
|---|---|---|
| `HUBSPOT_SERVICE_KEY is not set` (exit 2) | `.env` missing or the key line is empty | Redo step 4 from the repo root |
| `FAIL network error: ConnectionError` | Can't reach api.hubapi.com | Check internet/VPN, then re-run |
| `FAIL HubSpot returned HTTP 429 ...` | Rate-limited after 3 retries | Wait a minute and re-run |
| `FAIL company not searchable after 30s` | The record was created but search hasn't indexed it yet | Wait a minute and re-run; the second run takes the update path |
| `FAIL 2 companies share domain ...` | Duplicate test companies exist | Delete the extras in HubSpot, then re-run |
