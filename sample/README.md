# Sample data

`companies_sample.csv` is **synthetic**. Every company is made up, and every domain uses the reserved `.example` TLD (RFC 2606), so nothing here can match a real business. The file has the same columns as the Clay CSV export the pipeline reads, and its bad rows are planted on purpose, one or more for each rule in [`docs/rules.md`](../docs/rules.md).

## Expected outcome (25 rows)

- **12 load cleanly**
- **3 load with a flag** (2 × `INDUSTRY_MISSING`, 1 × `INDUSTRY_UNMAPPED`)
- **10 go to quarantine**

| Row | Company | What's wrong | Expected result |
|---|---|---|---|
| 2 | Brightwater Analytics | Domain given as `https://www.Brightwater-Analytics.example/about` | Pass, normalises to `brightwater-analytics.example` |
| 3 | Copperleaf Energy | Headcount `1,250` | Pass, read as `1250` |
| 5 | Ironbark Robotics | Industry blank | Flag `INDUSTRY_MISSING`, still loads |
| 6 | *(blank)* | Name missing | Quarantine `MISSING_REQUIRED` |
| 7 | Saltbush Logistics | Domain missing | Quarantine `MISSING_REQUIRED` |
| 8 | Kestrel Payments | Domain `not a domain` | Quarantine `INVALID_DOMAIN` |
| 9 | Wattle Labs | Domain contains `_` | Quarantine `INVALID_DOMAIN` |
| 10 | Blue Gum Systems | Domain starts with `-` | Quarantine `INVALID_DOMAIN` |
| 11 | Northwind Freight Pty | `WWW.northwind-freight.example` is the same domain as row 1 | Quarantine `DUPLICATE_IN_BATCH` |
| 12 | Coral Coast Retail | Headcount `about 200` | Quarantine `HEADCOUNT_NOT_NUMERIC` |
| 13 | Silver Gull Insurance | Headcount `51-200` (a range) | Quarantine `HEADCOUNT_NOT_NUMERIC` |
| 17 | Paperbark Design | Industry blank | Flag `INDUSTRY_MISSING`, still loads |
| 22 | Jacaranda Travel | Industry `Leisure Travel & Tourism` (missing comma vs picklist `Leisure, Travel & Tourism`) | Flag `INDUSTRY_UNMAPPED`, still loads |
| 23 | Bilby Biotech | Headcount `12.5` | Quarantine `HEADCOUNT_NOT_NUMERIC` |
| 24 | Spinifex Solar | Headcount blank | Pass (DQ-05 only checks headcount when it's present) |
| 25 | Platypus Water | Domain has a space **and** headcount `many` | Quarantine `INVALID_DOMAIN\|HEADCOUNT_NOT_NUMERIC` |

Row numbers count data rows from 1 and skip the header. On a second run against the same HubSpot portal, all 15 loadable rows should take the DQ-04 update path, not create.
