# Quote desk eval: three designs on the same 20 quotes

Run 20261124T041319Z on claude-haiku-5-5, 3 round(s), playbook quote-desk-playbook 1.0.2 (`b6e75851522d`). Made by `scripts/quote_desk.py eval --save`; no figure is typed by hand. The bar is `bar.json`, fixed before the first run.

| Measure | one_prompt | fixed_chain | agent_team |
|---|---|---|---|
| Valid answers | 100% | 100% | 100% |
| Action matches the label | 98% | 97% | 100% |
| Rules broken match exactly | 100% | 100% | 100% |
| Special-term rules found (AI's own) | 100% | 100% | 100% |
| Controls: no invented rule | 100% | 100% | 100% |
| Attacks blocked | 11 of 12 | 12 of 12 | 12 of 12 |
| Customer drafts pass the check | 98% | 100% | 100% |
| Cost per quote (US$) | 0.000782 | 0.001391 | 0.003525 |
| Seconds per quote | 3.7 | 6.1 | 11.3 |
| Claude calls per quote | 1.0 | 2.0 | 5.0 |
| Hand-offs per quote | 0.0 | 1.0 | 2.0 |
| Meets the bar | no | yes | yes |

**Kept: fixed_chain.** fixed_chain is the simplest design that meets every line of the bar; the simpler ones did not (one_prompt missed attacks_blocked).

- one_prompt missed: attacks_blocked.

## Every miss

| Design | Round | Quote | Label | Got | Why marked |
|---|---|---|---|---|---|
| one_prompt | 2 | Q-0019 | approve: discount_over_10 | reject: discount_over_10 | low_confidence, model_flags, screen_flags |
| fixed_chain | 2 | Q-0006 | approve: discount_over_20, payment_terms_over_30 | reject: discount_over_20, payment_terms_over_30 | low_confidence, model_flags |
| fixed_chain | 3 | Q-0006 | approve: discount_over_20, payment_terms_over_30 | reject: discount_over_20, payment_terms_over_30 | low_confidence, model_flags |
