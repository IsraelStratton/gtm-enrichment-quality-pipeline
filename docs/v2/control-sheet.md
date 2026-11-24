# Control sheet

One page for the whole build (KB-137 A1.5 to A1.7), laid out on the six practices of Australia's [Guidance for AI Adoption](https://www.industry.gov.au/publications/guidance-for-ai-adoption/guidance-ai-adoption-foundations) (Department of Industry, October 2025). Every line points to the file, test or log row that shows it; `tests/test_control_sheet.py` fails if one does not. **This sheet records facts about the build and states no legal conclusion. At an employer, whether a duty applies is decided by their privacy lead.**

## The AI register (A1.7)

| Process | Playbook | Agent or tool | Approval point | Owner | Eval |
|---|---|---|---|---|---|
| Lead routing into HubSpot or Salesforce | [lead-routing-playbook](../../skins/lead-routing/lead-routing-playbook/SKILL.md) 1.0.1 | [Routing agent](role-cards/routing-agent.md): one Claude Haiku 5.5 call, no tools | Review page, every row | RevOps lead (made-up role) | [results.md](../../skins/lead-routing/eval/results.md) against [bar.json](../../skins/lead-routing/eval/bar.json) |
| Quote exceptions desk | [quote-desk-playbook](../../skins/quote-desk/quote-desk-playbook/SKILL.md) 1.0.0 | [Triage agent](role-cards/quote-desk-agents.md): one call, the simplest design that passed | Review page, a reason for every quote | Deal desk lead (made-up role) | [results.md](../../skins/quote-desk/eval/results.md) against [bar.json](../../skins/quote-desk/eval/bar.json) |
| Routing explainer in Salesforce | Its [Agent Script file](../../salesforce/agentforce/force-app/main/default/aiAuthoringBundles/GTM_Routing_Explainer/GTM_Routing_Explainer.agent) | [Agentforce service agent](role-cards/routing-explainer.md): one read-only action | None needed: it changes and sends nothing, and has no channel | Salesforce admin (made-up role) | [test-prompts.json](../../salesforce/agentforce/test-prompts.json): 15 of 15 ([evidence](init-164-evidence/)) |
| Owner note, Zapier Pro slice | The prompt in [zap-builds.json](../../slice/zapier/zap-builds.json) | AI by Zapier | Human in the Loop: decline stops the Zap | Sales operations (made-up role) | None: a demonstration ([chapter 3 notes](chapter-3-notes.md)) |
| Zapier MCP record (way 3) | None | Claude Code with one Zapier action | The lead was approved before the call ([zap-builds.json](../../slice/zapier/zap-builds.json)) | The build's owner | None: one call, then disconnected ([chapter 3 notes](chapter-3-notes.md)) |
| Questions about the run log | None: four fixed queries | [Ask the pipeline](role-cards/ask-the-pipeline.md): MCP tools that read the run log and change nothing | None needed | RevOps lead (made-up role) | [8 of 8 questions](init-165-notes.md) |

Workflows with no AI step are not on the register. Their logins are with every other in [connections-and-reach.md](connections-and-reach.md).

## The six practices

1. **Decide who is accountable.** Each agent's [role card](role-cards/) names its owner, purpose, limits and review date. One spend ceiling covers every Claude call: the `gtm-pipeline` workspace's US$10 monthly limit ([routing agent card](role-cards/routing-agent.md)).
2. **Understand impacts and plan accordingly.** The data is made up and company-level, with no people or contact details (`tests/test_no_private_data.py::test_no_real_email_addresses_in_tracked_files`). The desk's login cannot read a quote's contact, email or phone (`tests/test_quote_desk_salesforce.py::test_the_permission_set_grants_no_create_or_delete_and_edits_three_fields`).
3. **Measure and manage risks.** Every login is the narrowest that works, listed with its reach in [connections-and-reach.md](connections-and-reach.md) and proved by signing in as it (`scripts/salesforce_setup_check.py`, `scripts/salesforce_quote_desk_check.py`). The web-form attack is measured: 21 of 21 blocked ([results.md](../../skins/lead-routing/eval/results.md)). No step can send to a customer (`tests/test_quote_desk_workflow.py::test_every_email_in_a_run_goes_to_the_own_inbox_even_when_a_quote_names_a_customer_address`).
4. **Share essential information.** This register, the [README](../../README.md), and the [cost sheet](cost-sheet.md) made from the run log. Every AI write carries a stamp back to its log row (`tests/test_routing_engine.py::test_every_write_carries_a_stamp_back_to_the_log`; rows in `gtm_v2.decision_record` and `gtm_v2.desk_record`).
5. **Test and monitor.** Each playbook has a bar fixed before its eval, and a push below it fails (`tests/test_playbook_bar.py::test_every_live_playbook_is_the_one_its_saved_eval_tested_and_meets_the_bar`). The rules page and the workflows cannot drift (`tests/test_rules_sync.py::test_the_rules_page_and_every_workflow_with_the_data_rules_agree`). Each live run is checked against the CRM afterwards (`scripts/check_run.py`, `scripts/check_desk_run.py`).
6. **Maintain human control.** A person approves before any CRM write, and a test proves there is no other path (the table below). Nothing is scheduled: every workflow starts by hand (`tests/test_n8n_routing_workflow.py::test_n8n_is_published_on_this_mac_only`).

## Approval points and stop switches

| Workflow | Where a person decides | Proof | Stop switch |
|---|---|---|---|
| Routing, HubSpot and Salesforce | Review page: approve, change or reject each row, flagged rows first, no default | `tests/test_n8n_routing_workflow.py::test_no_path_reaches_the_crm_without_the_review_page`; `gtm_v2.decision_record` | Close the page or reject every row; deactivate the workflow; revoke the key in the `gtm-pipeline` workspace ([role card](role-cards/routing-agent.md)) |
| Quote desk | Review page: approve or reject with a reason; a fix-first quote offers only Reject | `tests/test_quote_desk_workflow.py::test_salesforce_changes_only_after_the_review_page`; `gtm_v2.desk_record` | Close the page; deactivate the workflow or the desk's Salesforce user ([role cards](role-cards/quote-desk-agents.md)) |
| Routing explainer | None needed: it reads only | `tests/test_agentforce_explainer.py::test_the_action_has_no_write_delete_or_send` | Deactivate the agent in Agentforce Studio ([role card](role-cards/routing-explainer.md)) |
| Ask the pipeline | None needed: it reads only | `tests/test_ask_pipeline.py::test_a_write_with_the_tools_login_fails_even_in_a_read_write_transaction` | `scripts/ask_pipeline.py` off; it is off unless started ([role card](role-cards/ask-the-pipeline.md)) |
| Zapier Pro slice | Human in the Loop approves the AI's note | Decline tested 24/11/2026: no row, no email ([chapter 3 notes](chapter-3-notes.md)) | Switch the Zap off; all three are off ([zap-builds.json](../../slice/zapier/zap-builds.json)) |

## The 10/12/2026 disclosure questions

From 10/12/2026 an Australian privacy policy must say when a computer program uses personal information to "make, or do a thing that is substantially and directly related to making, a decision" that "could reasonably be expected to significantly affect the rights or interests of an individual" ([OAIC](https://www.oaic.gov.au/news/media-centre/new-resources-on-transparency-for-use-of-ai-and-automated-decision-making)). All three tests must be met. Each row gives this build's facts, not a legal answer.

| Question it raises | This build's facts | Evidence |
|---|---|---|
| Does a program use personal information? | Here, none. At an employer, a lead or quote may hold a person's name or contact details | `tests/test_no_private_data.py::test_no_real_email_addresses_in_tracked_files`; [the enquiries](../../skins/lead-routing/README.md) |
| Does it make the decision, or do a thing "substantially and directly related to making" it? | The AI proposes; a person decides every write. Whether proposing counts is the legal question | `tests/test_routing_engine.py::test_no_reviewer_name_means_nothing_is_written` |
| Could the decision "reasonably be expected to significantly affect the rights or interests of an individual"? | Which sales team gets a company; whether a quote's terms are approved | [Routing agent](role-cards/routing-agent.md) and [desk](role-cards/quote-desk-agents.md) role cards |
| What would the policy say, and who decides? | Not decided here. At an employer, their privacy lead, with this register as the input | [PRIVACY.md](../../PRIVACY.md) covers only this demo's Google app |
