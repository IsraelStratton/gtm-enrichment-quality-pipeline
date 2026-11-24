# Cost sheet: what each AI decision costs

KB-137 A5. Made by `scripts/cost_sheet.py` on 2026-11-24T04:37:26Z from the run log (schema gtm_v2) through the pipeline login gtm_v2_pipeline, and from the two price files. **No figure on this page is typed by hand:** a test remakes it from [`cost-sheet.json`](cost-sheet.json) and the price files, and fails if they differ. The run log works out each call's cost from the prices below (`gtm_v2.model_prices`, loaded from `pricing/claude_prices.json`).

## Prices used

Claude API list prices, USD per million tokens.

| Model | Input | Output | Long prompts | Read on | Source |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | 0.10 | 0.50 | over 100,000 tokens in: 0.50 / 2.50 | 2026-11-23 | https://platform.claude.com/docs/en/about-claude/pricing |
| `claude-sonnet-5-5` | 2.00 | 10.00 | no separate price | 2026-11-23 | https://platform.claude.com/docs/en/about-claude/pricing |

## Routing: cost per decision, by model

One decision is one enquiry routed: one Claude call. Live runs are the n8n workflows of chapters 2 and 4; the Python runs are the evals and proofs (`scripts/route_leads.py`, `scripts/route_eval.py`).

| Model | Runs | Decisions | Tokens per decision, in / out | Cost per decision (US$) | Total (US$) |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | n8n, live runs | 39 | 3365 / 114 | 0.00039343 | 0.015344 |
| `claude-haiku-5-5` | Python, evals and proofs | 280 | 3366 / 115 | 0.00039392 | 0.110297 |
| `claude-sonnet-5-5` | Python, evals and proofs | 120 | 3363 / 100 | 0.00773008 | 0.927610 |

## Routing: cost per decision, by model and route

The route is the one the AI proposed. All runs, live and eval.

| Model | Route | Decisions | Cost per decision (US$) | Total (US$) |
|---|---|---|---|---|
| `claude-haiku-5-5` | `customer_support` | 17 | 0.00039032 | 0.006636 |
| `claude-haiku-5-5` | `disqualify` | 44 | 0.00040630 | 0.017877 |
| `claude-haiku-5-5` | `enterprise_anz` | 66 | 0.00039891 | 0.026328 |
| `claude-haiku-5-5` | `enterprise_global` | 22 | 0.00039335 | 0.008654 |
| `claude-haiku-5-5` | `mid_market` | 77 | 0.00039230 | 0.030207 |
| `claude-haiku-5-5` | `nurture` | 33 | 0.00038322 | 0.012646 |
| `claude-haiku-5-5` | `partnerships` | 24 | 0.00038800 | 0.009312 |
| `claude-haiku-5-5` | `smb` | 36 | 0.00038836 | 0.013981 |
| `claude-sonnet-5-5` | `customer_support` | 6 | 0.00768567 | 0.046114 |
| `claude-sonnet-5-5` | `disqualify` | 15 | 0.00768467 | 0.115270 |
| `claude-sonnet-5-5` | `enterprise_anz` | 30 | 0.00784547 | 0.235364 |
| `claude-sonnet-5-5` | `enterprise_global` | 9 | 0.00777022 | 0.069932 |
| `claude-sonnet-5-5` | `mid_market` | 21 | 0.00774419 | 0.162628 |
| `claude-sonnet-5-5` | `nurture` | 15 | 0.00767027 | 0.115054 |
| `claude-sonnet-5-5` | `partnerships` | 9 | 0.00767622 | 0.069086 |
| `claude-sonnet-5-5` | `smb` | 15 | 0.00761080 | 0.114162 |

## Routing, live runs: cost per record written

Every proposal costs a call, including the ones a person rejects, so the cost per record written is above the cost per decision.

| Model | Proposals | Written to a CRM | Rejected | AI cost per record written (US$) | CRMs |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | 39 | 30 | 9 | 0.00051146 | hubspot, salesforce |

## Quote desk: cost per quote, by design and model

One triage is one quote, whatever number of calls the design makes (chapter 5).

| Design | Model | Runs | Quotes | Claude calls per quote | Cost per quote (US$) | Total (US$) |
|---|---|---|---|---|---|---|
| `agent_team` | `claude-haiku-5-5` | Python, evals and proofs | 180 | 5.0 | 0.00350592 | 0.631066 |
| `fixed_chain` | `claude-haiku-5-5` | Python, evals and proofs | 180 | 2.0 | 0.00140315 | 0.252566 |
| `one_prompt` | `claude-haiku-5-5` | n8n, live runs | 8 | 1.0 | 0.00070004 | 0.005600 |
| `one_prompt` | `claude-haiku-5-5` | Python, evals and proofs | 180 | 1.0 | 0.00077420 | 0.139356 |

**All AI spend in the run log:** US$2.0818: routing US$1.0533 over 439 decisions, the quote desk US$1.0286 over 548 triages.

## Comparison lines

- **Model choice.** On routing, `claude-sonnet-5-5` costs 20 times as much as `claude-haiku-5-5` per decision (US$0.00773008 against US$0.00039386, every run of each in the run log). The chapter 6 eval found both meet the bar, so the live workflow keeps the cheaper one ([`results.md`](../../skins/lead-routing/eval/results.md)).
- **A vendor's list price, not like for like.** One Agentforce action at Salesforce's list price (20 Flex Credits at US$0.005 each, US$0.10; read on 2026-11-24) costs about 254 times one live routing decision on `claude-haiku-5-5` (US$0.00039343, the n8n runs in the run log). **Not like for like:** an Agentforce action is billed per action whatever its size, a routing decision by the tokens it uses; the work differs; and this build's Agentforce explainer runs free in a developer org with no payment method. Sources: https://www.salesforce.com/agentforce/pricing/; https://www.salesforce.com/en-us/wp-content/uploads/sites/4/assets/pdf/agentforce/Flex-Credits-Rate-Card-11.3.2026.pdf.
