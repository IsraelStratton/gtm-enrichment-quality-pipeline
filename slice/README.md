# The slice: one approved lead, built in n8n, Make and Zapier

Chapter 3 of version 2. The same small job is built in three tools, so they can be compared on steps, plan limits and the workarounds each one needed.

**The job.** An approved lead arrives. The tool tells the owner by email and adds one row to a tracking sheet.

## Input

One approved lead as JSON. The samples are in [approved_leads.json](approved_leads.json). They are made up and company-level only, with `.example` domains and no people.

`scripts/fire_slice.py` sends a sample to a tool and adds three fields: `run_id`, `target` and `sent_at`.

```bash
python scripts/fire_slice.py --target n8n --test --lead L-0001
```

| Field | Example |
|---|---|
| `event` | `lead.approved` |
| `run_id` | `slice-n8n-20261123T012203Z-L-0001` |
| `target` | `n8n`, `make` or `zapier` |
| `sent_at` | `2026-11-23T01:22:03.456Z` (UTC) |
| `lead_id`, `company_name`, `domain`, `industry`, `employee_count`, `hq_country` | The company |
| `enquiry`, `intent`, `priority`, `route`, `owner_team`, `reason` | What it asked for and where it goes |
| `decision`, `approved_by`, `approved_at` | `approved` or `changed`, a reviewer label, and when |

The payload never names a recipient. Each tool decides where the owner email goes, so a payload cannot redirect it.

## Outputs

1. **The owner is told.** One plain-text email: the company, the route, the priority, the reason and the run id.
2. **One tracking row.** Thirteen columns, in this order:

`written_by`, `run_id`, `lead_id`, `company_name`, `domain`, `route`, `priority`, `owner_team`, `decision`, `approved_by`, `approved_at`, `sent_at`, `received_at`

`written_by` is the tool's name. `received_at` is the tool's own clock when the lead arrived, in UTC, so `received_at - sent_at` is the time to reach each tool.

## Where each tool writes

| Tool | Plan | Entry point | Tracking row | Owner email |
|---|---|---|---|---|
| n8n | Community Edition, local | Webhook | The shared Google Sheet | Gmail API, send-only |
| Make | Free | Custom webhook | The shared Google Sheet | Gmail |
| Zapier, way 1 | Free | Zapier Form (Free has no webhooks) | A Zapier Table, which also joins the two Zaps | Zap 2 |
| Zapier, way 2 | Pro trial | Webhook, with a Filter on the key | The Zapier Table (so Zapier needs no Google login) | In the same Zap, after Zapier's AI and approval steps |
| Zapier, way 3 | Zapier MCP | Claude, through one Zapier action (Tables: Create Record) | The Zapier Table, marked `claude-mcp` | Zap 2, when it is on |

Build steps: [n8n](n8n/BUILD.md), [Make](make/BUILD.md), [Zapier](zapier/BUILD.md) (ways 1 to 3; way 4 is [on paper](../docs/v2/zapier-admin-on-paper.md)). Notes on time, limits and cost: [docs/v2/chapter-3-notes.md](../docs/v2/chapter-3-notes.md). What each connection can reach: [docs/v2/control-sheet.md](../docs/v2/control-sheet.md).
