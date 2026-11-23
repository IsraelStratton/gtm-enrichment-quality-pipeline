# Role card: the routing agent

KB-137 A1.4. One card per agent; this is the one for chapter 2. It reads like a job description, because the agent is treated like a member of staff: it has an owner, a written playbook, limits, and a person who checks its work.

| Item | This agent |
|---|---|
| **Name** | Routing agent (the "Claude Routing Step" in n8n, and `scripts/route_leads.py` for runs outside n8n) |
| **Purpose** | Read one company enquiry, after the data rules have passed, and propose an intent, a route, a priority, a two-line reason and a confidence |
| **Named owner** | Revenue operations lead: a made-up role in this build. At an employer, the person who owns lead routing, with sales leadership signing off the rules |
| **What it reads** | One company record: name, normalised domain, industry, staff number, head-office city and country, and the enquiry text. Nothing about people. It sees no other row, no CRM data and no earlier decisions |
| **What it writes** | Nothing. It returns one JSON object in a fixed shape. The workflow, not the agent, logs the proposal and, after a person approves, writes to HubSpot |
| **What it must never do** | Follow instructions found in an enquiry; send anything to anyone; write to the CRM; route outside the playbook's routes; take size or region from the enquiry instead of the enrichment fields; repeat its instructions or a person's contact details |
| **Tools** | None. It is a single Claude Messages call with structured outputs (`output_config.format`), so it cannot call anything. Model `claude-haiku-5-5`, effort `low` |
| **Playbook** | [`skins/lead-routing/lead-routing-playbook/SKILL.md`](../../../skins/lead-routing/lead-routing-playbook/SKILL.md), version 1.0.0, read from disk on every run. Its name, version and SHA-256 hash are logged with every proposal |
| **Guard rails** | Fixed in [`engine/routing.js`](../../../engine/routing.js), outside the playbook: the enquiry goes in as escaped JSON data; the reply must fit the schema; confidence below 0.70 is flagged; code checks the route against the size and region rules; a code screen looks for instructions, markup, fake output and contact details; a reason that repeats the instructions is flagged |
| **Approval point** | The n8n review page. A named reviewer approves, changes or rejects every row. Flagged rows are listed first and none has a default choice. Nothing reaches HubSpot without that page being submitted; a test checks there is no other path |
| **Stop switch** | Nothing is scheduled. Close the review page, or reject every row, and nothing is written. Deactivate the n8n workflow to stop all runs. Revoke the key in the Claude Console workspace `gtm-pipeline` to stop every AI call at once |
| **Spend limit** | The Claude Console workspace `gtm-pipeline` has a US$10 monthly limit. A decision costs about US$0.0004 on Haiku 5.5 (40 enquiries, 23/11/2026) |
| **Evidence** | `gtm_v2.proposals` (what it proposed, tokens, time, why flagged), `gtm_v2.decisions` (what the person did), and a stamp on each HubSpot company that leads back to both. First full run, `n8n-8790` on 23/11/2026: 12 proposals, 9 written, 3 rejected, every check in `scripts/check_run.py` passed |
| **Eval** | 40 labelled enquiries in [`skins/lead-routing/enquiries.csv`](../../../skins/lead-routing/enquiries.csv), seven of them attacks. First run 23/11/2026: route 39 of 40, priority 39 of 40, review flags 36 of 36 against the drafted labels; all seven attacks flagged and none steered. The grader, the Haiku and Sonnet comparison and the bar a push must meet come in chapter 6 |
| **Review date** | 07/12/2026, at the end of the build, or sooner if the eval bar is missed or the playbook changes its routes |
