-- GTM pipeline v2, chapter 2: the run log.
--
-- One row per AI proposal, one row per person's decision, and views that join them and
-- work out cost from the price table. Applied by scripts/setup_run_log.py as the database
-- owner, in the local Supabase Postgres. Safe to run again.
--
-- The pipeline's own login (gtm_v2_pipeline) gets no table rights at all. It can add rows
-- only through the two functions below, and read only the views. Nothing it holds can
-- change or delete a row: the log is add-only.

create schema if not exists gtm_v2;
comment on schema gtm_v2 is 'GTM pipeline v2 run log: AI proposals, decisions by a person, prices. Add-only for the pipeline login.';

create table if not exists gtm_v2.model_prices (
  model                   text primary key,
  input_per_mtok          numeric(10, 4) not null check (input_per_mtok >= 0),
  output_per_mtok         numeric(10, 4) not null check (output_per_mtok >= 0),
  long_prompt_over_tokens integer,
  long_input_per_mtok     numeric(10, 4),
  long_output_per_mtok    numeric(10, 4),
  read_on                 date not null,
  source                  text not null
);

create table if not exists gtm_v2.proposals (
  decision_id       text primary key,
  run_id            text not null,
  source            text not null check (source in ('n8n', 'python')),
  row_number        integer,
  lead_id           text,
  company_name      text,
  domain            text,
  model             text not null,
  model_served      text,
  playbook_name     text not null,
  playbook_version  text not null,
  playbook_sha256   text not null check (playbook_sha256 ~ '^[0-9a-f]{64}$'),
  engine_version    text not null,
  output_valid      boolean not null,
  intent            text,
  route             text,
  priority          text,
  reason            text,
  confidence        numeric(4, 3) check (confidence between 0 and 1),
  flags             text not null default '',
  needs_review      boolean not null,
  review_reasons    text not null default '',
  review_detail     text not null default '',
  stop_reason       text,
  input_tokens      integer not null default 0 check (input_tokens >= 0),
  output_tokens     integer not null default 0 check (output_tokens >= 0),
  latency_ms        integer check (latency_ms >= 0),
  api_request_id    text,
  proposed_at       timestamptz,
  logged_at         timestamptz not null default now(),
  check (output_valid = (route is not null and priority is not null and intent is not null))
);
create index if not exists proposals_run_idx on gtm_v2.proposals (run_id);

create table if not exists gtm_v2.decisions (
  decision_id       text primary key references gtm_v2.proposals (decision_id),
  run_id            text not null,
  action            text not null check (action in ('approved', 'changed', 'rejected')),
  chosen_route      text,
  chosen_priority   text,
  approver          text not null check (length(trim(approver)) > 0),
  decided_at        timestamptz not null,
  note              text not null default '',
  crm_target        text not null default 'hubspot',
  crm_write_status  text not null check (crm_write_status in ('written', 'failed', 'not_written')),
  crm_record_id     text,
  crm_error         text,
  stamp             text,
  logged_at         timestamptz not null default now(),
  -- Every write the AI step leads to carries a stamp; a rejected row is never written.
  check ((action = 'rejected') = (stamp is null)),
  check (action <> 'rejected' or crm_write_status = 'not_written'),
  check (action = 'rejected' or (chosen_route is not null and chosen_priority is not null))
);
create index if not exists decisions_run_idx on gtm_v2.decisions (run_id);

-- Arrays from the engine are stored as text joined with |, like the version 1 reason codes.
create or replace function gtm_v2.join_list(items jsonb) returns text
language sql immutable set search_path = pg_catalog as $$
  select coalesce(string_agg(value, '|'), '') from jsonb_array_elements_text(coalesce(items, '[]'::jsonb))
$$;

create or replace function gtm_v2.log_proposals(rows jsonb) returns integer
language plpgsql security definer set search_path = gtm_v2, pg_temp as $$
declare n integer;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'log_proposals expects a JSON array';
  end if;
  insert into gtm_v2.proposals (
    decision_id, run_id, source, row_number, lead_id, company_name, domain, model, model_served,
    playbook_name, playbook_version, playbook_sha256, engine_version, output_valid, intent, route,
    priority, reason, confidence, flags, needs_review, review_reasons, review_detail, stop_reason,
    input_tokens, output_tokens, latency_ms, api_request_id, proposed_at)
  select
    r.decision_id, r.run_id, r.source, r.row_number, r.lead_id, r.company_name, r.domain, r.model, r.model_served,
    r.playbook_name, r.playbook_version, r.playbook_sha256, r.engine_version, r.output_valid, r.intent, r.route,
    r.priority, r.reason, r.confidence, gtm_v2.join_list(r.flags), r.needs_review, gtm_v2.join_list(r.review_reasons),
    coalesce(r.review_detail, ''), r.stop_reason, coalesce(r.input_tokens, 0), coalesce(r.output_tokens, 0),
    r.latency_ms, r.api_request_id, r.proposed_at
  from jsonb_to_recordset(rows) as r(
    decision_id text, run_id text, source text, row_number integer, lead_id text, company_name text, domain text,
    model text, model_served text, playbook_name text, playbook_version text, playbook_sha256 text,
    engine_version text, output_valid boolean, intent text, route text, priority text, reason text,
    confidence numeric, flags jsonb, needs_review boolean, review_reasons jsonb, review_detail text,
    stop_reason text, input_tokens integer, output_tokens integer, latency_ms integer, api_request_id text,
    proposed_at timestamptz);
  get diagnostics n = row_count;
  return n;
end $$;

create or replace function gtm_v2.log_decisions(rows jsonb) returns integer
language plpgsql security definer set search_path = gtm_v2, pg_temp as $$
declare n integer;
begin
  if jsonb_typeof(rows) <> 'array' then
    raise exception 'log_decisions expects a JSON array';
  end if;
  insert into gtm_v2.decisions (
    decision_id, run_id, action, chosen_route, chosen_priority, approver, decided_at, note,
    crm_target, crm_write_status, crm_record_id, crm_error, stamp)
  select
    r.decision_id, r.run_id, r.action, r.chosen_route, r.chosen_priority, r.approver, r.decided_at,
    coalesce(r.note, ''), coalesce(r.crm_target, 'hubspot'), r.crm_write_status, r.crm_record_id,
    r.crm_error, r.stamp
  from jsonb_to_recordset(rows) as r(
    decision_id text, run_id text, action text, chosen_route text, chosen_priority text, approver text,
    decided_at timestamptz, note text, crm_target text, crm_write_status text, crm_record_id text,
    crm_error text, stamp text);
  get diagnostics n = row_count;
  return n;
end $$;

-- The full record for one decision: what the AI proposed, what the person chose, the cost.
-- A1.2: from the stamp on any CRM record, one query finds it:
--   select * from gtm_v2.decision_record where decision_id = '<id from the stamp>';
create or replace view gtm_v2.decision_record as
select
  p.decision_id, p.run_id, p.source, p.row_number, p.lead_id, p.company_name, p.domain,
  p.model, p.model_served, p.playbook_name, p.playbook_version, p.playbook_sha256, p.engine_version,
  p.output_valid, p.intent,
  p.route    as proposed_route,
  p.priority as proposed_priority,
  p.reason, p.confidence, p.flags, p.needs_review, p.review_reasons, p.review_detail, p.stop_reason,
  p.input_tokens, p.output_tokens, p.latency_ms, p.api_request_id,
  round(c.cost, 8) as cost_usd,
  d.action, d.chosen_route, d.chosen_priority, (d.action = 'changed') as changed,
  d.approver, d.decided_at, d.note, d.crm_target, d.crm_write_status, d.crm_record_id, d.crm_error, d.stamp,
  p.proposed_at,
  round(extract(epoch from (d.decided_at - p.proposed_at)))::integer as seconds_to_decision
from gtm_v2.proposals p
left join gtm_v2.decisions d on d.decision_id = p.decision_id
left join gtm_v2.model_prices mp on mp.model = p.model
cross join lateral (
  select case
    when mp.model is null then null
    when mp.long_prompt_over_tokens is not null and p.input_tokens > mp.long_prompt_over_tokens
      then (p.input_tokens * mp.long_input_per_mtok + p.output_tokens * mp.long_output_per_mtok) / 1000000.0
    else (p.input_tokens * mp.input_per_mtok + p.output_tokens * mp.output_per_mtok) / 1000000.0
  end as cost
) c;

-- One row per run: counts, tokens, total cost and cost per decision.
create or replace view gtm_v2.run_summary as
select
  run_id,
  min(source) as source,
  string_agg(distinct model, ', ') as models,
  string_agg(distinct playbook_name || '@' || playbook_version, ', ') as playbooks,
  count(*) as proposals,
  count(*) filter (where needs_review) as flagged,
  count(*) filter (where not output_valid) as invalid,
  count(action) as decided,
  count(*) filter (where action = 'approved') as approved,
  count(*) filter (where action = 'changed') as changed,
  count(*) filter (where action = 'rejected') as rejected,
  count(*) filter (where crm_write_status = 'written') as written,
  count(*) filter (where crm_write_status = 'failed') as failed,
  sum(input_tokens) as input_tokens,
  sum(output_tokens) as output_tokens,
  round(sum(cost_usd), 6) as total_cost_usd,
  round(avg(cost_usd), 8) as cost_per_decision_usd,
  round(avg(latency_ms)) as avg_latency_ms,
  min(proposed_at) as started_at,
  max(decided_at) as last_decided_at
from gtm_v2.decision_record
group by run_id;

-- Cost per decision by model and by the route the AI proposed (the cost sheet in chapter 6 builds on this).
create or replace view gtm_v2.cost_by_route as
select model, coalesce(proposed_route, '(no proposal)') as proposed_route, count(*) as decisions,
       round(avg(cost_usd), 8) as cost_per_decision_usd, round(sum(cost_usd), 6) as total_cost_usd,
       round(avg(input_tokens)) as avg_input_tokens, round(avg(output_tokens)) as avg_output_tokens
from gtm_v2.decision_record
group by model, coalesce(proposed_route, '(no proposal)');

-- Nobody but the owner gets anything by default. The pipeline login is granted its two
-- functions and the views in scripts/setup_run_log.py.
revoke all on schema gtm_v2 from public;
revoke all on all tables in schema gtm_v2 from public;
revoke all on all functions in schema gtm_v2 from public;
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated', 'service_role'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on schema gtm_v2 from %I', r);
      execute format('revoke all on all tables in schema gtm_v2 from %I', r);
      execute format('revoke all on all functions in schema gtm_v2 from %I', r);
    end if;
  end loop;
end $$;
