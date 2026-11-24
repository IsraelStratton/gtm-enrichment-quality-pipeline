# Walk-throughs by role

One walk-through for each kind of role in KB-135 section 0b, in two lengths: 90 seconds by default, five minutes when asked. Every one follows the same three rules.

1. **Open on the data rules and the quarantine.** Revenue systems lead; AI is the edge.
2. **Ask before the AI half:** "Do your staff have an AI model available to them?" The answer sets how much of the AI half to give.
3. **Claim only what is built and proved.** Every figure below is in the repo, with the file named. The "it went wrong" story is part of the walk-through, not an aside.

These are the points and the order. The spoken wording is made with the Say-Aloud Method and approved by Israel on the job-search side before it is used.

| Role | Lead with | Then | Points that fit (KB-136 section 8) |
|---|---|---|---|
| [CRM administrator](#crm-administrator-salesforce-or-hubspot) | Chapters 1 and 4: clean data, on their CRM | Chapter 2; the Agentforce explainer if Salesforce-led | Data ready for agents. The web-form attack. Who may switch on AI connectors |
| [Revenue systems, RevOps, CPQ](#revenue-systems-revops-cpq) | Chapter 5: the quote exceptions desk | Chapter 2 | Where an agent drafts and a person decides. Cost per action |
| [Business systems](#business-systems) | The approval, the run log and the guard rails | Chapter 3 | The control sheet and the 10/12/2026 duty. An owner for every agent |
| [AI and automation](#ai-and-automation) | Chapters 2, 3 and 6 | — | Evals that choose the design. Cost per decision. The logged hand-off |

**Before any live demo:** the demo checklists in the [chapter 2](chapter-2-notes.md#demo-checklist), [chapter 4](chapter-4-notes.md#demo-checklist), [chapter 5](chapter-5-notes.md#demo-checklist) and [INIT-164](init-164-notes.md#demo-checklist) notes. Use Chrome for the n8n pages. Use a reviewer label, never a personal name. Keep the org host, the inbox and any credential off screen.

## The opening every walk-through shares (about 20 seconds)

"A company list comes in. Before anything else, seven data rules check every row: is the name there, is the domain real, is it a duplicate, is the headcount a number. A bad row goes to a quarantine table with the reason, so it can be fixed. Nothing dirty reaches the CRM. Run the same file twice and it updates the records; it never copies them."

Show, if there is a screen: [the rules page](../rules.md) and one quarantined row with its reason code.

## CRM administrator (Salesforce or HubSpot)

### 90 seconds

1. The shared opening.
2. "The same clean data lands in HubSpot or in Salesforce. In Salesforce it is written by an API-only user with one permission set: Accounts, create and edit, ten fields, no delete. A script signs in as that user and proves what it cannot do: 19 checks, all passing."
3. "Every record carries a stamp: which decision, which model, which rules, who approved it, and when. From the stamp, one query finds the full record."
4. Ask: "Do your staff have an AI model available?"
5. "Before the write, an AI step proposes the team and the priority from a written playbook, and a person approves, changes or rejects every row. Nothing is written until they do. The same web-form attack that hit Agentforce in 2025 was tried here seven ways; all 21 attempts were blocked."

### Five minutes

| Minute | Say | Show |
|---|---|---|
| 0 to 1 | The shared opening, then why the rules come first: an agent is only as good as the record it reads | [`docs/rules.md`](../rules.md); the quarantine table |
| 1 to 2 | Chapter 4: the same engine on Salesforce. The two workflows differ in one step, and a test proves it | The two workflows side by side in n8n; [`salesforce/setup.json`](../../salesforce/setup.json) |
| 2 to 3 | Least reach: why not n8n's own Salesforce login (it asks for full access) and why not an admin's | [`connections-and-reach.md`](connections-and-reach.md); `scripts/salesforce_setup_check.py` passing |
| 3 to 4 | Ask the AI question. Then the review page, a stamped Account, and the run log row it leads to | The review page; an Account's stamp; `check_run.py --stamp` |
| 4 to 5 | Salesforce-led room: the CRM's own agent explains why the Account was routed, and cannot change it. HubSpot room: the web-form attack, measured | The Agentforce preview, or [the attack table](../../skins/lead-routing/eval/results.md) |

**It went wrong.** "The least-reach check failed on the real org: it said the integration user could create users and delete ninety kinds of record. I did not loosen the check. Two create requests showed what Salesforce really allows: no new users, and the deletable items are each user's own posts and notes. The check now tests the real risk, and lists the rest on every run." ([chapter 4 notes](chapter-4-notes.md))

**For a Salesforce-led room, a second one.** "The Agentforce agent once answered confidently without looking anything up: a wrong status, an invented stamp. Rewording the instructions could not force the lookup, so the lookup now runs every time before it answers, and the test fails any answer whose trace shows no lookup." ([INIT-164 notes](init-164-notes.md))

**If they ask who may switch on AI connectors:** Zapier's MCP server starts in a mode that had switched on about 125 actions across nine connected apps at sign-in. It was cut to one action on one table before the first call. ([chapter 3 notes](chapter-3-notes.md))

## Revenue systems, RevOps, CPQ

### 90 seconds

1. The shared opening, in one line: "The data rules run first, so the desk only sees clean records."
2. "Quotes that break the deal desk policy are caught before they go out. Code does the arithmetic: the real discount across the quote, totals against the opportunity, missing fields, expiry, payment terms."
3. "The approver gets one message: every exception, the rule broken, the evidence and a proposed action, ordered by the date at risk, then deal size. They approve or reject each quote with a reason. A quote with a missing field or a wrong total can only be sent back."
4. Ask: "Do your staff have an AI model available?"
5. "The AI reads only what code cannot: the special terms, and whether the rep's reason is one the policy accepts. The owner gets a draft reply to the customer: a draft. Nothing is sent to a customer. It costs under a tenth of a US cent a quote."

### Five minutes

| Minute | Say | Show |
|---|---|---|
| 0 to 1 | The shared opening, then the desk's rules: three must be fixed first, four are checked in code, two need judgement | [The desk playbook](../../skins/quote-desk/quote-desk-playbook/SKILL.md) |
| 1 to 2 | The queue in Salesforce, and what the desk's login can change: a quote's status and two fields. An Apex guard stops it changing quote lines | The quote list; [`connections-and-reach.md`](connections-and-reach.md), the desk row |
| 2 to 3 | The approver's message and the review page. Q-0009 offers only Reject. Q-0017 carries a planted instruction and is marked Check | The review page |
| 3 to 4 | Ask the AI question. Then three designs built and measured: one call, a fixed chain, an agent team. The simplest that passed was kept | [The B2 table](../../README.md#evals) |
| 4 to 5 | The decided quote with its stamp, the owner's draft reply, and the cost per quote | A stamped quote; `check_desk_run.py --stamp`; [the cost sheet](cost-sheet.md) |

**It went wrong.** "The design that sounded safest, a policy checker and a separate message writer in a fixed order, was the only one that failed. On the quote whose note tried to make the customer reply promise 40%, its checker twice gave an empty reason. The one-call design blocked all twelve attacks. The eval chose the design, not the diagram." ([chapter 5 notes](chapter-5-notes.md))

**A second one.** "A one-line wording fix to the policy, meant only to stop a false warning, made the kept design reject the attack quote in all three rounds. The eval caught it before any live use, and the change was rolled back the same hour. Prompt wording is code: it gets tested before it ships."

## Business systems

### 90 seconds

1. The shared opening.
2. "Every AI decision passes one approval point: a review page where a person approves, changes or rejects it. A test proves there is no other path to the CRM. Nothing is scheduled; every workflow starts by hand."
3. "Every decision is logged with its cost, and the log's login can only add rows. Every record written carries a stamp back to its log row."
4. Ask: "Do your staff have an AI model available?"
5. "Each agent has a role card, like a member of staff: an owner, what it may read and write, what it must never do, and how to stop it. One control sheet lays it out on Australia's Guidance for AI Adoption. It also lists the questions the privacy duty from 10 December raises, with this build's facts, for the employer's privacy lead to decide."

### Five minutes

| Minute | Say | Show |
|---|---|---|
| 0 to 1 | The shared opening, and why: bad data in a CRM is a cost every team pays | [`docs/rules.md`](../rules.md) |
| 1 to 2 | The approval point and the run log: proposed, chosen, who, when, cost | The review page; the run log's [decision view](../../db/run_log.sql) |
| 2 to 3 | Ask the AI question. Then the guard rails: the enquiry is data, never instructions; code checks every answer; seven attacks tried | [`connections-and-reach.md`](connections-and-reach.md); [the attack table](../../skins/lead-routing/eval/results.md) |
| 3 to 4 | The control sheet, one page: the register, the six practices, the stop switches, the disclosure questions | [`control-sheet.md`](control-sheet.md); a [role card](role-cards/routing-agent.md) |
| 4 to 5 | Chapter 3: the same job in n8n, Make and Zapier, and when to use which | [Chapter 3 notes](chapter-3-notes.md), "When to use which" |

**It went wrong.** "Zapier's MCP server, the way an AI client acts in Zapier, starts in a mode where signing in alone had switched on about 125 actions across nine apps, Gmail among them. It was cut to one action on one table before the first call, and the finding is on the control sheet. The default was the risk, not the tool." ([chapter 3 notes](chapter-3-notes.md))

**When to use which, in one line:** "n8n when you need control and tests, Make when a team wants visual building with room to grow, Zapier when the job is short and the builder is not an engineer."

## AI and automation

### 90 seconds

1. The shared opening, in one line: "The AI only ever sees rows that passed seven data rules."
2. Ask: "Do your staff have an AI model available?"
3. "One AI step proposes a team, a priority and a reason. It follows a playbook written as an Agent Skill and read from disk on every run: change the playbook and the routing changes, with no change to the workflow."
4. "The eval set is 40 labelled enquiries, seven of them attacks of different kinds. Haiku and Sonnet both met a bar fixed before the run. Haiku is kept at about four hundredths of a cent a decision; Sonnet costs 20 times as much. A playbook change that falls below the bar cannot be pushed."
5. "For the quote desk the eval chose the design: an agent team also passed, at 4.6 times the cost, so the one-call design was kept."

### Five minutes

| Minute | Say | Show |
|---|---|---|
| 0 to 1 | The shared opening, then the AI step: one call, structured output, no tools, the enquiry passed in as data | [The workflow page](workflows.md), chapter 2 |
| 1 to 2 | The playbook as a skill, its version and hash logged with every decision | [The routing playbook](../../skins/lead-routing/lead-routing-playbook/SKILL.md) |
| 2 to 3 | The eval and the bar: two models, three rounds, the attack measure, every miss listed | [The results](../../README.md#evals); [`results.md`](../../skins/lead-routing/eval/results.md) |
| 3 to 4 | The gate: a bad playbook change refused, a good one promoted, both through the same check | [The evidence](chapter-6-evidence/bad-playbook-push.txt); [chapter 6 notes](chapter-6-notes.md) |
| 4 to 5 | The agent team: each hand-off logged with from, to, why, evidence and cost. Then the cost sheet, made from the run log | `check_desk_run.py --handoffs`; [the cost sheet](cost-sheet.md) |

**It went wrong.** "Haiku gave two high-priority leads a medium priority in every round. One reason even said 'high priority' while the field said medium, and no code check catches that. I changed two lines of the playbook, tested it once as a candidate against the same bar, and promoted it because it met the bar: priority 100%, every attack still blocked." ([chapter 6 notes](chapter-6-notes.md))

**What the scores do not say.** The bar guards against a regression on these 40 enquiries; there is no held-out set, and the labels were drafted by the build. A person still decides every write.

## Proof behind each claim

| Claim | Where it is proved |
|---|---|
| Seven data rules; nothing dirty reaches the CRM | [`docs/rules.md`](../rules.md); `tests/test_rules_sync.py`; [version 1 results](../../README.md#version-1-results) |
| A person approves before any write | `tests/test_n8n_routing_workflow.py`, `tests/test_quote_desk_workflow.py` |
| 21 of 21 attacks blocked | [`results.md`](../../skins/lead-routing/eval/results.md) |
| The Salesforce login can do nothing else | `scripts/salesforce_setup_check.py`, 19 of 19; `scripts/salesforce_quote_desk_check.py`, 27 of 27 |
| The desk kept the simplest design that passed | [`skins/quote-desk/eval/results.md`](../../skins/quote-desk/eval/results.md) |
| Cost per decision and per quote | [`cost-sheet.md`](cost-sheet.md) |
| The Agentforce agent reads and cannot change | [INIT-164 notes](init-164-notes.md); `tests/test_agentforce_explainer.py` |
| The documents cannot drift from what runs | `tests/test_rules_sync.py`, `tests/test_build_docs.py` |
