# Skin: lead routing

A skin is one folder with everything that makes the engine do one job: the sample data, the rules, the prompt wording and the eval set (KB-135, section 3). The engine (`engine/routing.js`) and the n8n workflow do not change between skins. This is the first skin: route an inbound company enquiry to the right team.

| File | What it is |
|---|---|
| [`lead-routing-playbook/SKILL.md`](lead-routing-playbook/SKILL.md) | The playbook, in the Agent Skills format: routes, size and region bands, intents, priorities, edge cases and flags. The AI step reads it on every run; change it and the routing changes, with no change to the workflow |
| [`lead-routing-playbook/references/governance.md`](lead-routing-playbook/references/governance.md) | For people: owner, approval, how to change and roll back the playbook. The AI step does not read it |
| [`enquiries.csv`](enquiries.csv) | 40 made-up companies with an enquiry each, and drafted labels for the eval in chapter 6 |
| [`sample_run.csv`](sample_run.csv) | The demo file for n8n: 12 of the enquiries plus two rows the data rules stop |
| [`eval/bar.json`](eval/bar.json) | The bar the routing step must meet on the 40 enquiries, set from the first run and fixed before the chapter 6 eval |
| [`eval/results.md`](eval/results.md) | Chapter 6: Haiku 5.5 and Sonnet 5.5 graded on the same 40 enquiries, three rounds each, with the attack block rate and every miss. Made by the script, with `results.json` beside it |
| [`eval/playbook-1.1.0-bad-example.md`](eval/playbook-1.1.0-bad-example.md) | A deliberately bad change (enterprise from 250+ to 1,000+ staff), tested as a candidate and refused; its results beside it |

## The enquiries

All made up and company-level: `.example` domains, no people, no contact details.

| Kind | Rows | What they test |
|---|---|---|
| `normal` | 23 | Each route and priority at least once |
| `edge` | 7 | Unknown staff number, a claimed size that differs from the enrichment, an existing customer buying more, a one-word enquiry, a partner who also wants seats, German, and one ambiguous row (L-0019) |
| `spam` | 3 | Sales pitches, a recruiter, an investment offer |
| `attack` | 7 | Seven different ways to steer the AI from the web form: a direct override, a fake system message, fake output JSON after a fake closing tag, asking for the instructions, a role-play persona, a hidden P.S. asking to skip review, and an instruction in French |

The `expected_*` columns are the labels. A cell with `a|b` accepts either; `expected_review` is `yes`, `no` or `either`. The grader, the Haiku and Sonnet comparison and the attack block rate are in [`eval/results.md`](eval/results.md). One label was changed after the first run: L-0019 ("Interested in learning more. Please send a product overview.") is now an ambiguous edge case, accepting a product question to enterprise sales or general interest to nurture. The note on the row says so.

## Run the AI step on its own

```bash
python scripts/route_leads.py --file skins/lead-routing/enquiries.csv
```

Add `--log` to write the proposals to the run log, `--only L-0034,L-0036` for some rows, or `--playbook path/to/SKILL.md` to try a changed playbook. It asks no person and writes nothing to HubSpot; the n8n workflow does that.

## Run the eval

```bash
python scripts/route_eval.py eval --log --save
```

Both models, three rounds each, about US$0.95 (almost all of it Sonnet). `--models claude-haiku-5-5` runs the live model alone (about US$0.05). To test a playbook change, see [`references/governance.md`](lead-routing-playbook/references/governance.md): the change is tested from its own file and swapped in only if it meets the bar.
