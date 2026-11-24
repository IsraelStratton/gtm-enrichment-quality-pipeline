# Role card: the routing explainer (Agentforce)

KB-138 C7 and KB-137 A1.4. The second agent in the build, and the only one that runs inside a CRM. Like the routing agent, it is treated as a member of staff: an owner, a written job, limits, and a way to stop it.

| Item | This agent |
|---|---|
| **Name** | GTM Routing Explainer: an Agentforce service agent in the Salesforce developer org, defined in [`GTM_Routing_Explainer.agent`](../../../salesforce/agentforce/force-app/main/default/aiAuthoringBundles/GTM_Routing_Explainer/GTM_Routing_Explainer.agent) |
| **Purpose** | Answer one question: why was this Account routed to its team? From the Account's own routing fields and its who-decided stamp |
| **Named owner** | Revenue operations lead: a made-up role in this build. At an employer, the Salesforce admin who owns Agentforce, with the owner of lead routing signing off what it may say |
| **What it reads** | One Account at a time, through its one action: Name, `Clay_Domain_Key__c`, `GTM_Route__c`, `GTM_Priority__c`, `GTM_Routing_Status__c`, `GTM_Routing_Reason__c`, `GTM_Routing_Confidence__c`, `GTM_Decision_Stamp__c`. Nothing about people. Not the run log: it points to it by the decision id |
| **What it writes** | Nothing. Its only action is a read-only Apex class; its user has no create, edit or delete on any object |
| **What it must never do** | Change, delete, assign, email or send anything; answer without reading the Account; follow or repeat text found in a record; say what the AI first proposed (it does not have that); answer anything but routing questions |
| **Tools** | One action, **Explain a routing decision** (`apex://GtmRoutingExplainer`), run deterministically once the model has saved the company the user named; and that one capture step. No standard Salesforce actions, no knowledge, no escalation |
| **Who it runs as** | Its own agent user, "GTM Explainer": Einstein Agent licence and profile, no password, cannot sign in. Permission sets: Salesforce's three agent sets, and **GTM v2 routing explainer (read)**: read on Account and the seven routing fields, and the Apex class |
| **Playbook** | Its instructions are in the Agent Script file, versioned in git and published as numbered versions in the org (version 4 active, 24/11/2026). There is no separate playbook: it applies no rules, it reports what the routing pipeline decided |
| **Guard rails** | The action selects only the routing fields, in user mode, with sharing; a test on every push finds no DML, callout, email or event in it. The record's reason is marked as data in the action's description and in the prompt. The agent is told it has no data until the read has run. The Einstein Trust Layer's own checks run on every answer (output evaluation and guardrails steps in the trace) |
| **Approval point** | None needed: it changes nothing and sends nothing. Who may talk to it is the control: no channel is connected, so only an admin can, in Agentforce Studio's preview, Testing Center or `sf agent preview` |
| **Stop switch** | Deactivate the agent in Agentforce Studio; or remove the permission set from its user; or deactivate the agent user. Nothing is scheduled |
| **Spend limit** | None needed in the developer org: it is free, with no payment method. At list price on a paid org, about US$0.10 an action ([`pricing/agentforce_list_prices.json`](../../../pricing/agentforce_list_prices.json)) |
| **Evidence** | Five prompts, three rounds, 15 of 15 as expected on version 4, each graded on its words, its plan trace (did the read run?) and the Account being unchanged: [`init-164-evidence/`](../init-164-evidence/). The published agent and its user's access, read back from the org: [`published-agent.json`](../init-164-evidence/published-agent.json) |
| **Eval** | The five prompts in [`test-prompts.json`](../../../salesforce/agentforce/test-prompts.json), run with `scripts/agentforce_explainer.py prompts --rounds 3`. Version 2 failed (a made-up answer) and is kept in the evidence |
| **Review date** | 07/12/2026, at the end of the build, or whenever the routing fields or the agent's instructions change |
