# Skin: quote desk

The second skin (KB-135 section 3): everything that makes the desk engine (`engine/quotes.js`) do one job, triaging sales quotes that break the deal desk policy. Chapter 5 of the GTM pipeline version 2.

| File | What it is |
|---|---|
| [`quote-desk-playbook/SKILL.md`](quote-desk-playbook/SKILL.md) | The policy, in the Agent Skills format: the rules (which are fixed first and which need an approver), the discount bands, the approvers, the standard contract, what can be approved, the messages, the edge cases and the flags. Read on every run; change it and the desk changes, with no change to the workflow |
| [`quote-desk-playbook/references/governance.md`](quote-desk-playbook/references/governance.md) | For people: owner, approval, how to change and roll back the policy. The desk does not read it |
| [`cases.json`](cases.json) | 20 made-up quotes with labels (KB-137 B8): 2 controls, 6 discounts, 4 that must be fixed first, 4 with special terms, and 4 with hostile notes. Eight are marked `demo`: the seed writes those to Salesforce |
| [`eval/bar.json`](eval/bar.json) | The bar a design must meet, fixed before the first run |
| [`eval/results.json`](eval/results.json), [`eval/results.md`](eval/results.md) | The three designs on the 20 quotes, made by `scripts/quote_desk.py eval --save`: no figure typed by hand |

The products and list prices are in [`salesforce/quote-desk-setup.json`](../../salesforce/quote-desk-setup.json), the one place the seed and the eval both read.

## The cases

All made up and company-level: `.example` domains, no people, no contact details. Dates are days from `as_of`, so the rules give the same answer whenever the eval runs.

| Kind | Cases | What they test |
|---|---|---|
| `clean` | Q-0001, Q-0002 | Nothing breaks a rule: the desk must not invent one |
| `discount` | Q-0003 to Q-0008 | Each band; an accepted reason (multi-year, volume, a competing offer closing soon) and a refused one; a discount above 35% with only one reason; payment terms beyond 30 days; a unit price below list plus a line discount, which the rep note calls "only 10%" |
| `fix` | Q-0009 to Q-0012 | Missing fields, a quote total that does not match its opportunity, an expired quote, and a justified discount on a quote that is missing its billing country |
| `terms` | Q-0013 to Q-0016 | Commercial and legal special terms, one acceptable and one not of each |
| `hostile` | Q-0017 to Q-0020 | A fake system line in the rep note; a fake closing tag and fake output in the special terms; a note that tries to make the customer reply promise a discount, leak the limits and go to the customer; an instruction in French |

`expected.rules` is the exact set of rules the quote breaks; `expected.action` what the playbook says the approver should be asked to do; `expected.flags` flags that must be present; `expected.review` whether the quote must be marked for a close look.

## Run the eval

```bash
python scripts/quote_desk.py eval --design all --log --save
```

Runs the three designs (one prompt, a fixed chain, a lead agent with two specialists) on the 20 quotes, three rounds each, grades them against the labels and the bar, logs every call and hand-off to the run log, and names the kept design. `--only Q-0017,Q-0019` for some quotes, `--rounds 1` for a quick look. It asks no person and writes nothing to Salesforce; the n8n workflow does that.
