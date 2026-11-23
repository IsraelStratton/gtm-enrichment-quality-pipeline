// Run the Code nodes of a routing workflow (n8n/workflow-v2.json, or the Salesforce copy) outside
// n8n, in workflow order, with the n8n helpers they use ($, $input, $json, $execution) stubbed.
// The HTTP, Postgres and form nodes are replaced by the answers the test passes in. Used by
// tests/test_n8n_routing_workflow.py.
//
// stdin: {workflow, rows, playbook, answers: {lead_id: http result}, execution_id,
//         upsert: "ok" | "fail" | "partial"}
// The write node is whichever node "Anything to Write?" sends to; its fake reply is in the
// shape that CRM uses (HubSpot or Salesforce).
// stdout: the output of every stage, as JSON.
'use strict';
const fs = require('fs');

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const wf = JSON.parse(fs.readFileSync(input.workflow, 'utf8'));
const nodes = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const out = {};

function run(name, items) {
  const node = nodes[name];
  if (!node || node.type !== 'n8n-nodes-base.code') throw new Error(`${name} is not a Code node`);
  const each = node.parameters.mode === 'runOnceForEachItem';
  const $ = (ref) => {
    const got = out[ref];
    if (!got) throw new Error(`${name}: $('${ref}') has not run`);
    return { all: () => got, first: () => got[0], get item() { return got[0]; } };
  };
  const $execution = { id: input.execution_id };
  const fn = new Function('$', '$input', '$json', '$execution', node.parameters.jsCode);
  const $input = { all: () => items, first: () => items[0] };
  if (each) {
    return items.map((it) => {
      const r = fn($, Object.assign({ item: it }, $input), it.json, $execution);
      return Array.isArray(r) ? r[0] : r;
    });
  }
  return fn($, $input, undefined, $execution);
}

out['Extract CSV'] = input.rows.map((r) => ({ json: r }));
out['DQ Checks'] = run('DQ Checks', out['Extract CSV']);
const failing = out['DQ Checks'].filter((i) => !i.json._dq_pass);
out['Format Quarantine'] = failing.length ? run('Format Quarantine', failing) : [];
out['Playbook Text'] = [{ json: { data: input.playbook } }];
out['Build Requests'] = run('Build Requests', out['Playbook Text']);

const proposals = [];
for (const req of out['Build Requests']) {
  out['Stamp Start'] = run('Stamp Start', [req]);
  const http = input.answers[req.json.lead.lead_id];
  if (!http) throw new Error(`no fake answer for ${req.json.lead.lead_id}`);
  out['Claude Routing Step'] = [{ json: http }];
  proposals.push(...run('Check Proposal', out['Claude Routing Step']));
}
out['Build Review'] = run('Build Review', proposals);

// The reviewer: reject every flagged row, change the first routine row, approve the rest.
const fields = out['Build Review'][0].json.form_fields;
const form = { approver: 'reviewer-01', note: 'harness run' };
let changed = false;
for (const f of fields.filter((x) => x.fieldType === 'dropdown')) {
  const opts = f.fieldOptions.values.map((v) => v.option);
  if (f.fieldLabel.startsWith('Check:')) form[f.fieldName] = opts.find((o) => o.startsWith('Reject'));
  else if (!changed) { form[f.fieldName] = opts.find((o) => o.startsWith('Change to')); changed = true; }
  else form[f.fieldName] = opts[0];
}
out['Review Page'] = [{ json: form }];
out['Apply Decisions'] = run('Apply Decisions', out['Review Page']);

const applied = out['Apply Decisions'][0].json;
const writeNode = wf.connections['Anything to Write?'].main[0][0].node;
const records = applied.write.target === 'salesforce' ? applied.write.body.records : applied.write.body.inputs;
let toLog = out['Apply Decisions'];

function hubspotReply() {
  if (input.upsert === 'fail') {
    return { statusCode: 400, headers: {}, body: { status: 'error', message: 'Property values were not valid', category: 'VALIDATION_ERROR' } };
  }
  return { statusCode: 200, headers: {}, body: { status: 'COMPLETE', results: records.map((x, i) => ({ id: String(9000 + i), new: i === 0, properties: { clay_domain_key: x.id } })) } };
}

function salesforceReply() {
  if (input.upsert === 'fail') {
    return { statusCode: 400, headers: {}, body: [{ errorCode: 'INVALID_FIELD', message: "No such column 'GTM_Route__c' on sobject of type Account" }] };
  }
  // 'partial': the first record is refused on its own, as Salesforce does with allOrNone false.
  return { statusCode: 200, headers: {}, body: records.map((x, i) => (input.upsert === 'partial' && i === 0
    ? { success: false, errors: [{ statusCode: 'INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST', message: 'GTM Route: bad value for restricted picklist field', fields: ['GTM_Route__c'] }] }
    : { id: `001${String(i).padStart(15, '0')}`, success: true, errors: [], created: i === 0 })) };
}

if (applied.write.count) {
  out[writeNode] = [{ json: applied.write.target === 'salesforce' ? salesforceReply() : hubspotReply() }];
  toLog = out[writeNode];
}
out['Build Decision Log'] = run('Build Decision Log', toLog);
out['Read Run Summary'] = [{ json: { run_id: out['Build Decision Log'][0].json.run_id, proposals: proposals.length, total_cost_usd: '0.004700', cost_per_decision_usd: '0.00039167' } }];
out['Done Message'] = run('Done Message', out['Read Run Summary']);

process.stdout.write(JSON.stringify({
  dq: out['DQ Checks'].map((i) => i.json),
  quarantine: out['Format Quarantine'].map((i) => i.json),
  requests: out['Build Requests'].map((i) => i.json),
  proposals: proposals.map((i) => i.json),
  review: out['Build Review'][0].json,
  form,
  applied,
  writeNode,
  log: out['Build Decision Log'][0].json,
  done: out['Done Message'][0].json,
}));
