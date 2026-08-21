# AU Wong Choi — 全矩陣數據障礙掃描 + 跑法去留定案 (2026-07-25)

Kelvin: (1) scan the whole matrix for the same data-barrier problem, (2) how to
better leverage 跑法/步速, (4) should we remove 跑法 since its only confident part
is already covered?

## #1 Full matrix data-barrier scan (710 races / 7,530 horses)

| feature | missing | separation when present | diagnosis |
|---|---:|---:|---|
| **實測步速 pace_figure** | **66.9%** | **6.49** | 🔴 highest-value signal, worst coverage |
| 練馬師 trainer | 40.0% | 0.52 | 🟡 missing + weak |
| 試閘 trial | 24.9% | 1.67 | 🟡 |
| 班次 class | 22.5% | 0.76 | 🟡 |
| 騎馬配合 fit | 18.0% | 0.37 | 🟡 weakest signal |
| 負磅 weight | 6.2% | −0.45 | 🟢 covered, no signal (direction already fixed) |
| 形態 form | 5.8% | 3.43 | 🟢 |
| 評分 rating | 4.5% | 1.77 | 🟢 |
| 騎師 jockey | 0.2% | 1.62 | 🟢 |
| 場地/段速/走位/穩定性 | 0.0% | 0.64/1.41/0.52/4.18 | 🟢 full coverage |

**Only ONE cell is "high value + high missing": pace_figure (6.49 separation,
1.5× the next best, but 67% missing).** Everything else is either well-covered
or weak-when-present — i.e. the data-barrier problem is NOT widespread; it is
concentrated in exactly one feature.

## The good news — that one barrier is ALREADY closing

pace_figure coverage by month:

| month | coverage |
|---|---:|
| 2025-08 → 2026-04 | **0%** |
| 2026-05 | 84.0% |
| 2026-06 | 95.3% |
| 2026-07 | **95.7%** |

The "67% missing" is a HISTORICAL AVERAGE artifact. Since 2026-05 the live
pipeline captures pace_figure for ~95% of runners. **Every meeting Kelvin
analyses today already has the model's strongest signal at full strength.**
(Historical backfill of the old months was tested in Round 10 and FAILED — so
the correct posture is exactly what we have: full coverage going forward, no
backfill.)

## #4 — Should we remove 跑法? Two answers

**(a) The low-confidence part is ALREADY out of the score.** The genuine
running-style role adjustment (`_pace_bias_adjustment`) is **disabled by default**
(`WC_PACE_BIAS=0`) — switched off in 2026-06 after A/B showed it was a wash.
Kelvin's instinct was already implemented before this session.

**(b) What remains (`pace_map_score` = 走位) must stay.** It is barrier advantage
+ empirical venue draw bias (shrunk), not a style label. Honest holdout (316
races never used in any tuning):

| | 頭兩揀齊三甲 | 捉到冠軍 | 頭揀贏 |
|---|---:|---:|---:|
| keep 走位 | 65場 (20.6%) | 50.6% | **23.4%** |
| remove 走位 | 61場 (19.3%) | 48.7% | **20.6%** |

Removing it costs 2.8pp of winner-picking. So: the noisy style component is
already gone; the empirical draw/barrier component is load-bearing.

## #2 — Better leveraging 跑法/步速: the honest options

Tested and failed: confidence-weighted front-runner evidence (Round 31, only 25%
coverage + already priced into pace_map). What remains genuinely open:

1. **Race-level pace scenario** (not per-horse): we have 7,681 actual settled
   positions — we can measure, per venue+distance, whether races were won from
   the front or off the pace, and whether that repeats. A *venue-level* pace-bias
   table is a different object from a per-horse style label and is not yet in the
   model (current draw bias is barrier-based, not pace-shape-based). Worth one
   test.
2. **Keep pace_figure coverage at 95%+** — monitoring, not modelling: if a
   meeting's extraction misses PF, the model loses its best signal for that race.
   A coverage alert at analysis time is cheap and high-value.

## Conclusion
The "data barrier" is a one-cell problem (pace_figure) that has already been
fixed forward from 2026-05. 跑法's noisy part was already removed; its
empirical remainder is load-bearing. Best remaining pace work = venue-level
pace-shape bias + PF coverage monitoring.
