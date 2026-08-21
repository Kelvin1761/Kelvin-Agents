# AU Wong Choi — Round 10: PF Backfill Gate Result (2026-07-19)

> Overnight slow-runner backfilled 26 archive meetings (33% → 94% PF coverage
> on those meetings), zero blocks. This is the gate decision on whether to
> adopt the historical pace_figure backfill.

## Result: DO NOT ADOPT — historical PF backfill is net-negative

### Clean isolation (identical current engine, only pace_figure toggled)

230 backfilled races, everything else held constant (draw shrinkage, matrix,
facts-refresh all identical on both sides):

| | good-pos | any-2 | Miss | Top3 prec | W-in-T3 |
|---|---:|---:|---:|---:|---:|
| PF OFF (neutral 60) | 39 | 91 | 26 | 44.3% | 52.6% |
| PF ON (backfilled) | 37 | 88 | 31 | 42.6% | 51.3% |
| **Δ** | **−2** | **−3** | **+5** | **−1.7pp** | **−1.3pp** |

Turning on backfilled PF degrades **every** headline metric.

### Why this is a valid negative (not a data-quality artifact)

- The backfill values are **exactly correct**: validation reproduced stored
  `pf_aggregates` 13/13 (Rosehill 06-27) and 37/37 (Eagle Farm 05-30) to 2dp
  — identical to what the live pipeline stores.
- pace_figure DOES separate positively on these meetings (+4.96 top-3
  separation) — the signal is real univariately.
- Yet its **marginal** contribution, conditional on the other 13 features, is
  negative. This is the Round-7 lesson again: univariate separation ≠
  marginal value. The composite is already extracting placing signal from
  form / sectional / class; a 14.3%-weight field-relative z-score layered on
  top displaces correct picks.
- Internal-weight sweep confirms no pace_figure weight recovers it: the
  PF-off variant holds the best any-2 (91) at every setting tested.

### Reconciling with "pace_figure is the strongest signal (6.49)"

The 6.49 audit was on the production archive, where PF is concentrated on
**recent** meetings that the model was tuned/adopted with. On those, PF is
already priced in and valuable. Forcing PF onto **old** meetings — where the
model was NOT tuned with it and the other features already rank correctly —
adds variance, not signal. PF's value is real but it lives in the **live
pipeline**, not in historical backfill.

## Decisions

1. **Do not adopt** the PF backfill to the Drive archive. Sandbox
   (`/private/tmp/au_pf_apply_sandbox`) and staging
   (`scratch/pf_backfill_staging/`) kept as evidence; Drive untouched.
2. **Stop PF extraction.** No value in spending racenet requests on the
   remaining ~59 meetings. The pre-registered gate did its job — 26 meetings
   of extraction bought a clean NO before committing 60 more.
3. **Nothing changes for production.** Live/recent meetings keep capturing PF
   via the daily pipeline (build_au_logic), where it earns its weight. The
   engine, cache, and Drive archive are unchanged.

## Where AU Wong Choi stands after 10 rounds

**Shipped & live:** canonical eval ruler; pre-score going refresh (`--going`);
facts-refresh evidence recovery (+3.6pp positional Good → HKJC parity);
draw-bias empirical-Bayes shrinkage; results-backfill draw densification;
confidence-tiered betting radar; probability/fair-odds card; signal-map lock.

**Tested & correctly rejected (21 candidates, 1 promoted):** every arithmetic
/ weight / ML / ordering / component-rebalance / PF-backfill candidate. The
model is **locally optimal on current data** — not fragile (pure-7D ≈ 95%),
but not improvable by re-weighting.

**Only remaining levers, both time-based (no code):**
- Live PF + results accrue with each new meeting → re-run the standing
  harnesses (`au_phase5_candidates.py`, `au_pace_role_adjust_test.py`,
  `au_jt_empirical_fill_test.py`) at +100 **new** races. Fast-pace role
  adjust (+1.38pp, 5/5 folds) is first in line.
- Extraction-side new inputs (gear changes, ratings movements) captured
  going forward.
