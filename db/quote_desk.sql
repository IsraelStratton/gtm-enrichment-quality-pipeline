-- GTM pipeline v2, chapter 5: the quote desk's run log.
--
-- Beside the routing log in the same schema (db/run_log.sql), with the same rule: the pipeline's
-- login (gtm_v2_pipeline) gets no table rights. It adds rows only through the two functions
-- below and reads only the views. Applied by scripts/setup_run_log.py after run_log.sql (it uses
-- gtm_v2.model_prices and gtm_v2.join_list from that file). Safe to run again.
--
--   desk_proposals  one row per quote triaged: the rules found by code and by the AI, the proposal, the messages
--   desk_calls      one row per Claude call, with its tokens and time (cost is worked out in the views)
--   handoffs        one row per hand-off between agents (KB-137 B3): from, to, asked, why, evidence, confidence
--   desk_decisions  one row per person's decision: approve or reject, the reason, what Salesforce and the owner got

create table if not exists gtm_v2.desk_proposals (
  decision_id            text primary key,
  run_id                 text not null,
  source                 text not null check (source in ('n8n', 'python')),
  design                 text not null check (design in ('one_prompt', 'fixed_chain', 'agent_team')),
  case_id                text,
  quote_id               text,
  quote_name             text,
  account_name           text,
  model                  text not null,
  playbook_name          text not null,
  playbook_version       text not null,
  playbook_sha256        text not null check (playbook_sha256 ~ '^[0-9a-f]{64}$'),
  engine_version         text not null,
  output_valid           boolean not null,
  code_rules             text not null default '',
  ai_rules               text not null default '',
  rules                  text not null default '',
  exceptions             jsonb not null default '[]'::jsonb,
  approvers              text not null default '',
  fix_needed             boolean not null,
  approve_allowed        boolean not null,
  proposed_action        text check (proposed_action in ('approve', 'reject')),
  reason                 text,
  approver_message       text,
  customer_reply_draft   text,
  draft_problems         text not null default '',
  confidence             numeric(4, 3) check (confidence between 0 and 1),
  flags                  text not null default '',
  needs_review           boolean not null,
  review_reasons         text not null default '',
  review_detail          text not null default '',
  effective_discount_pct numeric(7, 2),
  deal_size              numeric(14, 2),
  date_at_risk           date,
  queue_position         integer,
  calls                  integer not null default 0 check (calls >= 0),
  handoffs               integer not null default 0 check (handoffs >= 0),
  input_tokens           integer not null default 0 check (input_tokens >= 0),
  output_tokens          integer not null default 0 check (output_tokens >= 0),
  latency_ms             integer check (latency_ms >= 0),
  proposed_at            timestamptz,
  logged_at              timestamptz not null default now(),
  check (output_valid = (proposed_action is not null)),
  -- A quote that breaks a fix rule can never be approved.
  check (approve_allowed = not fix_needed)
);
create index if not exists desk_proposals_run_idx on gtm_v2.desk_proposals (run_id);

create table if not exists gtm_v2.desk_calls (
  call_id         text primary key,
  decision_id     text not null references gtm_v2.desk_proposals (decision_id),
  run_id          text not null,
  design          text not null,
  agent           text not null check (agent in ('triage_agent', 'policy_checker', 'message_drafter', 'lead_agent')),
  turn            integer not null check (turn >= 1),
  model           text not null,
  model_served    text,
  input_tokens    integer not null default 0 check (input_tokens >= 0),
  output_tokens   integer not null default 0 check (output_tokens >= 0),
  latency_ms      integer check (latency_ms >= 0),
  stop_reason     text,
  ok              boolean not null,
  error           text,
  api_request_id  text,
  called_at       timestamptz,
  logged_at       timestamptz not null default now()
);
create index if not exists desk_calls_run_idx on gtm_v2.desk_calls (run_id);

create table if not exists gtm_v2.handoffs (
  handoff_id   text primary key,
  decision_id  text not null references gtm_v2.desk_proposals (decision_id),
  run_id       text not null,
  design       text not null check (design in ('fixed_chain', 'agent_team')),
  from_agent   text not null,
  to_agent     text not null,
  asked        text not null,
  why          text not null,
  evidence     text not null,
  confidence   numeric(4, 3) check (confidence between 0 and 1),
  call_id      text references gtm_v2.desk_calls (call_id),
  logged_at    timestamptz not null default now(),
  check (from_agent <> to_agent)
);
create index if not exists handoffs_run_idx on gtm_v2.handoffs (run_id);

create table if not exists gtm_v2.desk_decisions (
  decision_id           text primary key references gtm_v2.desk_proposals (decision_id),
  run_id                text not null,
  case_id               text,
  quote_id              text not null,
  position              integer not null,
  action                text not null check (action in ('approved', 'rejected')),
  reason                text not null check (length(trim(reason)) > 0),
  approver              text not null check (length(trim(approver)) > 0),
  decided_at            timestamptz not null,
  matches_proposal      boolean,
  sf_status             text not null check (sf_status in ('Approved', 'Rejected')),
  stamp                 text not null check (stamp like 'gtm-v2-desk %'),
  crm_write_status      text not null check (crm_write_status in ('written', 'failed')),
  crm_error             text,
  owner_message_status  text not null check (owner_message_status in ('sent', 'failed')),
  owner_message_id      text,
  owner_message_error   text,
  logged_at             timestamptz not null default now(),
  check ((action = 'approved') = (sf_status = 'Approved'))
);
create index if not exists desk_decisions_run_idx on gtm_v2.desk_decisions (run_id);

-- The triage of a run: proposals, then their calls, then their hand-offs, in one go.
create or replace function gtm_v2.log_desk_triage(proposals jsonb, calls jsonb, handoffs jsonb) returns integer
language plpgsql security definer set search_path = gtm_v2, pg_temp as $$
declare n integer;
begin
  if jsonb_typeof(proposals) <> 'array' or jsonb_typeof(calls) <> 'array' or jsonb_typeof(handoffs) <> 'array' then
    raise exception 'log_desk_triage expects three JSON arrays';
  end if;
  insert into gtm_v2.desk_proposals (
    decision_id, run_id, source, design, case_id, quote_id, quote_name, account_name, model, playbook_name,
    playbook_version, playbook_sha256, engine_version, output_valid, code_rules, ai_rules, rules, exceptions,
    approvers, fix_needed, approve_allowed, proposed_action, reason, approver_message, customer_reply_draft,
    draft_problems, confidence, flags, needs_review, review_reasons, review_detail, effective_discount_pct,
    deal_size, date_at_risk, queue_position, calls, handoffs, input_tokens, output_tokens, latency_ms, proposed_at)
  select
    r.decision_id, r.run_id, r.source, r.design, r.case_id, r.quote_id, r.quote_name, r.account_name, r.model, r.playbook_name,
    r.playbook_version, r.playbook_sha256, r.engine_version, r.output_valid, gtm_v2.join_list(r.code_rules),
    gtm_v2.join_list(r.ai_rules), gtm_v2.join_list(r.rules), coalesce(r.exceptions, '[]'::jsonb),
    gtm_v2.join_list(r.approvers), r.fix_needed, r.approve_allowed, r.proposed_action, r.reason, r.approver_message,
    r.customer_reply_draft, gtm_v2.join_list(r.draft_problems), r.confidence, gtm_v2.join_list(r.flags), r.needs_review,
    gtm_v2.join_list(r.review_reasons), coalesce(r.review_detail, ''), r.effective_discount_pct, r.deal_size,
    r.date_at_risk, r."position", coalesce(r.calls, 0), coalesce(r.handoffs, 0), coalesce(r.input_tokens, 0),
    coalesce(r.output_tokens, 0), r.latency_ms, r.proposed_at
  from jsonb_to_recordset(proposals) as r(
    decision_id text, run_id text, source text, design text, case_id text, quote_id text, quote_name text,
    account_name text, model text, playbook_name text, playbook_version text, playbook_sha256 text,
    engine_version text, output_valid boolean, code_rules jsonb, ai_rules jsonb, rules jsonb, exceptions jsonb,
    approvers jsonb, fix_needed boolean, approve_allowed boolean, proposed_action text, reason text,
    approver_message text, customer_reply_draft text, draft_problems jsonb, confidence numeric, flags jsonb,
    needs_review boolean, review_reasons jsonb, review_detail text, effective_discount_pct numeric,
    deal_size numeric, date_at_risk date, "position" integer, calls integer, handoffs integer,
    input_tokens integer, output_tokens integer, latency_ms integer, proposed_at timestamptz);
  get diagnostics n = row_count;
  insert into gtm_v2.desk_calls (
    call_id, decision_id, run_id, design, agent, turn, model, model_served, input_tokens, output_tokens,
    latency_ms, stop_reason, ok, error, api_request_id, called_at)
  select c.call_id, c.decision_id, c.run_id, c.design, c.agent, c.turn, c.model, c.model_served,
         coalesce(c.input_tokens, 0), coalesce(c.output_tokens, 0), c.latency_ms, c.stop_reason, c.ok, c.error,
         c.api_request_id, c.called_at
  from jsonb_to_recordset(calls) as c(
    call_id text, decision_id text, run_id text, design text, agent text, turn integer, model text,
    model_served text, input_tokens integer, output_tokens integer, latency_ms integer, stop_reason text,
    ok boolean, error text, api_request_id text, called_at timestamptz);
  insert into gtm_v2.handoffs (handoff_id, decision_id, run_id, design, from_agent, to_agent, asked, why, evidence, confidence, call_id)
  select h.handoff_id, h.decision_id, h.run_id, h.design, h.from_agent, h.to_agent, h.asked, h.why, h.evidence,
         h.confidence, h.call_id
  from jsonb_to_recordset(handoffs) as h(
    handoff_id text, decision_id text, run_id text, design text, from_agent text, to_agent text, asked text,
    why text, evidence text, confidence numeric, call_id text);
  return n;
end $$;

create or replace function gtm_v2.log_desk_decisions(rows jsonb) returns integer
language plpgsql security definer set search_path = gtm_v2, pg_temp as $$
declare n integer;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'log_desk_decisions expects a JSON array';
  end if;
  -- The third lock on "fix first" (after the review page and the engine): refuse the whole batch.
  if exists (
    select 1 from jsonb_to_recordset(rows) as r(decision_id text, action text)
    join gtm_v2.desk_proposals p on p.decision_id = r.decision_id
    where r.action = 'approved' and not p.approve_allowed
  ) then
    raise exception 'log_desk_decisions: a quote that breaks a fix rule cannot be approved';
  end if;
  insert into gtm_v2.desk_decisions (
    decision_id, run_id, case_id, quote_id, position, action, reason, approver, decided_at, matches_proposal,
    sf_status, stamp, crm_write_status, crm_error, owner_message_status, owner_message_id, owner_message_error)
  select r.decision_id, r.run_id, r.case_id, r.quote_id, r."position", r.action, r.reason, r.approver, r.decided_at,
         r.matches_proposal, r.sf_status, r.stamp, r.crm_write_status, r.crm_error, r.owner_message_status,
         r.owner_message_id, r.owner_message_error
  from jsonb_to_recordset(rows) as r(
    decision_id text, run_id text, case_id text, quote_id text, "position" integer, action text, reason text,
    approver text, decided_at timestamptz, matches_proposal boolean, sf_status text, stamp text,
    crm_write_status text, crm_error text, owner_message_status text, owner_message_id text, owner_message_error text);
  get diagnostics n = row_count;
  return n;
end $$;

-- Cost per call, from the price table. The long-prompt price applies per request.
create or replace view gtm_v2.desk_call_cost as
select c.*,
  round(case
    when mp.model is null then null
    when mp.long_prompt_over_tokens is not null and c.input_tokens > mp.long_prompt_over_tokens
      then (c.input_tokens * mp.long_input_per_mtok + c.output_tokens * mp.long_output_per_mtok) / 1000000.0
    else (c.input_tokens * mp.input_per_mtok + c.output_tokens * mp.output_per_mtok) / 1000000.0
  end, 8) as cost_usd
from gtm_v2.desk_calls c
left join gtm_v2.model_prices mp on mp.model = c.model;

-- B3: every hand-off with the tokens and cost of the call it led to, joined to the run by run_id.
create or replace view gtm_v2.handoff_record as
select h.handoff_id, h.run_id, h.decision_id, h.design, h.from_agent, h.to_agent, h.asked, h.why, h.evidence,
       h.confidence, h.call_id, cc.model, cc.input_tokens, cc.output_tokens, cc.latency_ms, cc.cost_usd,
       p.case_id, p.quote_name, h.logged_at
from gtm_v2.handoffs h
join gtm_v2.desk_proposals p on p.decision_id = h.decision_id
left join gtm_v2.desk_call_cost cc on cc.call_id = h.call_id;

-- The full record for one quote decision. From the stamp on a quote, one query finds it:
--   select * from gtm_v2.desk_record where decision_id = '<id from the stamp>';
create or replace view gtm_v2.desk_record as
select p.decision_id, p.run_id, p.source, p.design, p.case_id, p.quote_id, p.quote_name, p.account_name, p.model,
       p.playbook_name, p.playbook_version, p.playbook_sha256, p.engine_version, p.output_valid,
       p.code_rules, p.ai_rules, p.rules, p.exceptions, p.approvers, p.fix_needed, p.approve_allowed,
       p.proposed_action, p.reason, p.approver_message, p.customer_reply_draft, p.draft_problems, p.confidence,
       p.flags, p.needs_review, p.review_reasons, p.review_detail, p.effective_discount_pct, p.deal_size,
       p.date_at_risk, p.queue_position, p.calls, p.handoffs, p.input_tokens, p.output_tokens, p.latency_ms,
       c.cost_usd, p.proposed_at,
       d.action, d.reason as decision_reason, d.approver, d.decided_at, d.matches_proposal, d.sf_status, d.stamp,
       d.crm_write_status, d.crm_error, d.owner_message_status, d.owner_message_id, d.owner_message_error,
       round(extract(epoch from (d.decided_at - p.proposed_at)))::integer as seconds_to_decision
from gtm_v2.desk_proposals p
left join gtm_v2.desk_decisions d on d.decision_id = p.decision_id
left join lateral (
  select round(sum(cost_usd), 8) as cost_usd from gtm_v2.desk_call_cost cc where cc.decision_id = p.decision_id
) c on true;

-- One row per run: counts, calls, hand-offs, cost per quote.
create or replace view gtm_v2.desk_run_summary as
select run_id,
       min(source) as source,
       string_agg(distinct design, ', ') as designs,
       string_agg(distinct model, ', ') as models,
       string_agg(distinct playbook_name || '@' || playbook_version, ', ') as playbooks,
       count(*) as quotes,
       count(*) filter (where needs_review) as flagged,
       count(*) filter (where not output_valid) as invalid,
       count(*) filter (where fix_needed) as fix_first,
       count(action) as decided,
       count(*) filter (where action = 'approved') as approved,
       count(*) filter (where action = 'rejected') as rejected,
       count(*) filter (where crm_write_status = 'written') as written,
       count(*) filter (where crm_write_status = 'failed') as failed,
       count(*) filter (where owner_message_status = 'sent') as owners_told,
       count(*) filter (where matches_proposal = false) as against_proposal,
       sum(calls) as calls,
       sum(handoffs) as handoffs,
       sum(input_tokens) as input_tokens,
       sum(output_tokens) as output_tokens,
       round(sum(cost_usd), 6) as total_cost_usd,
       round(avg(cost_usd), 8) as cost_per_quote_usd,
       round(avg(latency_ms)) as avg_latency_ms,
       min(proposed_at) as started_at,
       max(decided_at) as last_decided_at
from gtm_v2.desk_record
group by run_id;

revoke all on all tables in schema gtm_v2 from public;
revoke all on all functions in schema gtm_v2 from public;
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on all tables in schema gtm_v2 from %I', r);
      execute format('revoke all on all functions in schema gtm_v2 from %I', r);
    end if;
  end loop;
end $$;
