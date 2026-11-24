// Run the Code nodes of the quote desk workflow (n8n/workflow-v2-quote-desk.json) outside n8n, in
// workflow order, with the n8n helpers they use ($, $input, $json, $execution) stubbed. The HTTP,
// Postgres and form nodes are replaced by the answers the test passes in. Used by
// tests/test_quote_desk_workflow.py.
//
// stdin: {workflow, playbook, records, answers: {case_id: http result}, execution_id, inbox,
//         choices: {case_id: [choice, reason]} (default: follow the AI, reason "harness"),
//         sf_update: "ok" | "fail" | "partial", gmail: "ok" | "fail"}
// stdout: the output of every stage, as JSON, plus the emails Gmail was asked to send.
'use strict';
const fs = require('fs');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const wf = JSON.parse(fs.readFileSync(input.workflow, 'utf8'));
const nodes = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const out = {};
const execution = { id: input.execution_id, resumeFormUrl: `http://localhost:5678/form-waiting/${input.execution_id}` };

function run(name, items) {
  const node = nodes[name];
  if (!node || node.type !== 'n8n-nodes-base.code') throw new Error(`${name} is not a Code node`);
  const each = node.parameters.mode === 'runOnceForEachItem';
  const $ = (ref) => {
    const got = out[ref];
    if (!got) throw new Error(`${name}: $('${ref}') has not run`);
    return { all: () => got, first: () => got[0], get item() { return got[0]; } };
  };
  const fn = new Function('$', '$input', '$json', '$execution', node.parameters.jsCode);
  const $input = { all: () => items, first: () => items[0] };
  if (each) {
    return items.map((it) => {
      out.__current = it;
      const r = fn($, Object.assign({ item: it }, $input), it.json, execution);
      return Array.isArray(r) ? r[0] : r;
    });
  }
  return fn($, $input, undefined, execution);
}

out['Playbook Text'] = [{ json: { data: input.playbook } }];
out['Read Quotes'] = [{ json: { totalSize: input.records.length, done: true, records: input.records } }];
out['Build Requests'] = run('Build Requests', out['Playbook Text']);
if (out['Build Requests'][0].json.empty) {
  process.stdout.write(JSON.stringify({ empty: true, stages: out }));
  process.exit(0);
}

const checked = [];
for (const req of out['Build Requests']) {
  out['Stamp Start'] = run('Stamp Start', [req]);
  const http = input.answers[req.json.quote.case_id];
  if (!http) throw new Error(`no fake answer for ${req.json.quote.case_id}`);
  out['Claude Triage Step'] = [{ json: http }];
  checked.push(...run('Check Triage', out['Claude Triage Step']));
}
out['Build Queue'] = run('Build Queue', checked);
out['Get Inbox'] = [{ json: { email: input.inbox } }];
out['Build Approver Message'] = run('Build Approver Message', out['Build Queue']);
const emails = [{ node: 'Send Approver Email', raw: out['Build Approver Message'][0].json.raw }];
out['Send Approver Email'] = [{ json: { statusCode: 200, headers: {}, body: { id: 'msg-approver' } } }];

// The reviewer: the test's choices, or follow the AI with the reason "harness".
const q = out['Build Queue'][0].json;
const form = { approver: 'reviewer-01' };
for (const p of q.queue) {
  const field = q.form_fields.find((f) => f.fieldName === `quote_${p.position}`);
  const options = field.fieldOptions.values.map((v) => v.option);
  const pick = (input.choices || {})[p.case_id];
  form[`quote_${p.position}`] = pick ? pick[0] : options[0];
  form[`reason_${p.position}`] = pick ? pick[1] : 'harness';
}
out['Review Page'] = [{ json: form }];
out['Apply Decisions'] = run('Apply Decisions', out['Review Page']);

const records = out['Apply Decisions'][0].json.update.body.records;
let sfBody;
if (input.sf_update === 'fail') sfBody = { statusCode: 401, headers: {}, body: [{ errorCode: 'INVALID_SESSION_ID', message: 'Session expired or invalid' }] };
else {
  sfBody = { statusCode: 200, headers: {}, body: records.map((r, i) => (input.sf_update === 'partial' && i === 0
    ? { id: r.id, success: false, errors: [{ statusCode: 'INSUFFICIENT_ACCESS_OR_READONLY', message: 'insufficient access rights on cross-reference id', fields: [] }] }
    : { id: r.id, success: true, errors: [] })) };
}
out['Salesforce Update'] = [{ json: sfBody }];
out['Build Owner Messages'] = run('Build Owner Messages', out['Salesforce Update']);
const toSend = out['Build Owner Messages'].filter((i) => !i.json.skip);
if (toSend.length) {
  out['Send Owner Message'] = toSend.map((i, k) => {
    emails.push({ node: 'Send Owner Message', raw: i.json.raw });
    return { json: input.gmail === 'fail' ? { statusCode: 403, headers: {}, body: { error: { message: 'Insufficient Permission' } } } : { statusCode: 200, headers: {}, body: { id: `msg-owner-${k + 1}` } } };
  });
}
out['Build Decision Log'] = run('Build Decision Log', toSend.length ? out['Send Owner Message'] : out['Build Owner Messages']);
out['Read Run Summary'] = [{ json: { total_cost_usd: 0.004, quotes: q.queue.length, cost_per_quote_usd: 0.0005 } }];
out['Done Message'] = run('Done Message', out['Read Run Summary']);
delete out.__current;
process.stdout.write(JSON.stringify({ empty: false, stages: out, emails }));
