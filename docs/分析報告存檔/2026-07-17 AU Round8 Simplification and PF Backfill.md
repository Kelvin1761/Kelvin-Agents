# AU Wong Choi — Round 8: Simplification Question + PF Backfill Feasibility (2026-07-17)

## 1. Kelvin's simplification hypothesis — tested at three levels of cleanliness

"AU has many micro-adjustments vs HKJC's cleaner design — would mass removal
improve performance?" Empirical answer on the refreshed OOS window (363R):

| Model | Gold | any-2 | pos-Good | Miss | Top3 | W-in-T3 | Top1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| production ability | 22 | **149** | 75 | 43 | **45.1%** | **52.9%** | 22.6% |
| pure 7D (post-layers off) | 22 | 143 | **78** | **42** | 44.6% | 51.8% | **23.4%** |
| equal-weight 7 dims | 18 | 149 | 66 | 42 | 44.8% | 51.0% | 24.2% |
| clean 6-feature average | 21 | 145 | 68 | 47 | 44.3% | 50.4% | 18.2% |

Reading:

1. **The machinery earns its keep in aggregate** — every simplification level
   loses somewhere material (equal weights: −9 positional Good; minimal model:
   −4.4pp Top1, +4 Miss). Mass removal would NOT improve performance.
2. **But the system degrades gracefully** — pure 7D is ~95% of production and
   actually wins on positional Good / Miss / Top1. The complexity is not
   load-bearing everywhere; future pruning is safe when maintenance demands it.
3. The one post-7D layer (wet overlay) is a real trade, re-verified post-refresh:
   it buys +4 any-2 on Heavy for −3 positional on Soft, all inside one fold —
   keep, but it is not sacred.
4. Combined with Round 7's component-gate failures: the AU design is
   **locally optimal but not fragile**. The HKJC-style cleanliness instinct is
   right as an engineering principle, wrong as a performance lever.

## 2. pace_figure backfill — feasibility CONFIRMED, full chain mapped

pace_figure (system's strongest signal when present: separation 6.49; default
67%) comes from `pf_metrics.pf_aggregates.l600_delta_avg`, parsed by
`build_au_logic` from PF blocks in the Formguide MD. Probes (6 requests):

- Historical race **form-guide overview pages still render the PF layer** in
  apollo: `CompetitorFormBenchmark.runnerTimeDifferenceL600/L400` (per past
  run, vs benchmark), tempo quantiles, and per-runner `Stats.avgL600`
  (matches the `l600_delta_avg` format, e.g. −0.92).
- Historical sectionals sub-pages additionally carry raw
  `SectionalTime.l600/l400` + `SectionalTimeByPosition` benchmarks.
- Point-in-time integrity is structural: a past race's form-guide only shows
  runs before that race — no future leakage.

### Backfill plan (next build)

1. **Driver** (pattern: `au_results_backfill_driver.py`): per archive meeting
   → race slugs from the results page (already saved in
   `AU_Backfill_Results/*.json` for backfilled meetings) → per race one
   form-guide overview fetch → parse per-runner avgL600 / per-run deltas →
   inject `pf_metrics` into archive Logic (sandbox first).
2. **Semantic validation first**: run on one recent analysed meeting that has
   stored pf_aggregates; require computed avgL600 ≈ stored l600_delta_avg
   before touching history.
3. **Cost**: ~11 requests/meeting × 85 archive meetings ≈ 900+ requests →
   in-chat batches over several days (~3 meetings/hour safe), same guard
   discipline as the results backfill.
4. **Payoff test**: as PF coverage climbs from 33%, re-run
   `au_phase5_candidates.py` + a pace_perf weight retest through the standard
   gate — the 6.49-separation signal starts covering the majority of horses.

## Session request ledger (2026-07-17 evening)

Results backfill batch 5 meetings (~7), probes (~6) — all clean, no blocks.


## 3. PF backfill — first live batch + apply pipeline (2026-07-17 late)

- Second semantic validation (different state/venue): Eagle Farm 2026-05-30
  **37/37 exact** — semantics generalize.
- Batch 1: 2025-08-02 Flemington + 2025-08-09 Randwick staged (219 runner-PF
  records); apply pipeline (`scratch/au_pf_apply_and_gate.py`) injected 229
  horses, re-scored both meetings in a local sandbox — top-4 changed in 18/19
  races (pace_figure = 14.3% of ability once awake). Adoption deferred until
  enough meetings are patched to run the archive-wide gate.
- Data-quality find: 2025-08-09 Randwick is an **abandoned meeting** — racenet
  returns finish_position −8 for every runner; the canonical CSV's corrupted
  "Pos=8" rows came from that. Restored from backup and documented as
  permanently excluded (it never had results); the archive's silent exclusion
  of it was CORRECT behaviour.
- Canonical results CSV audit: 744 races, only those 10 (the abandoned
  meeting) unresolvable — the rest are clean.
