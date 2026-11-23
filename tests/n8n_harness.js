// Run the Code nodes of n8n/workflow-v2.json outside n8n, in workflow order, with the n8n
// helpers they use ($, $input, $json, $execution) stubbed. The HTTP, Postgres and form nodes
// are replaced by the answers the test passes in. Used by tests/test_n8n_routing_workflow.py.
//
// stdin: {workflow, rows, playbook, answers: {lead_id: http result}, execution_id, upsert: "ok" | "fail"}
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
let toLog = out['Apply Decisions'];
if (applied.hubspot.inputs.length) {
  out['HubSpot Batch Upsert'] = input.upsert === 'fail'
    ? [{ json: { statusCode: 400, headers: {}, body: { status: 'error', message: 'Property values were not valid', category: 'VALIDATION_ERROR' } } }]
    : [{ json: { statusCode: 200, headers: {}, body: { status: 'COMPLETE', results: applied.hubspot.inputs.map((x, i) => ({ id: String(9000 + i), new: i === 0, properties: { clay_domain_key: x.id } })) } } }];
  toLog = out['HubSpot Batch Upsert'];
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
  log: out['Build Decision Log'][0].json,
  done: out['Done Message'][0].json,
}));
