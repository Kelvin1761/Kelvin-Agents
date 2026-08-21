# AU Wong Choi — Round 7: Component Audit, Rebalance Gates, Probability Calibration (2026-07-17)

> Requested re-review of remaining improvement space, part by part. All on the
> refreshed archive; every candidate through the standard pre-registered gate.

## Part 1 — Per-feature predictive audit (post-refresh, first ever)

Within-race top-3 separation (placegetters' mean minus others'), 710 races:

| Feature | default% | separation | separation when present |
|---|---:|---:|---:|
| consistency | 0% | **4.18** | 4.18 |
| form | 5.8% | 3.32 | 3.43 |
| trial | 24.9% | 2.25 | 1.67 |
| **pace_figure** | **66.9%** | 1.88 | **6.49** |
| rating | 4.5% | 1.73 | 1.77 |
| jockey | 0.2% | 1.61 | 1.62 |
| sectional | 0% | 1.41 | 1.41 |
| trainer | 40.0% | 1.22 | 0.52 |
| track | 0% | 0.64 | 0.64 |
| pace_map | 0% | 0.52 | 0.52 |
| jockey_horse_fit | 18.0% | 0.47 | 0.37 |
| health | 16.9% | 0.10 | 0.11 |
| weight | 6.2% | **−0.41** | −0.45 |

Headline: **pace_figure is the strongest signal in the system when present
(6.49) but absent 67% of the time** — its coverage growth (PF sectionals
accumulating since 2026-07) is the single biggest scheduled upgrade in the
pipeline. Several allocations looked misaligned (fit 0.52 weight vs 0.47
separation; weight_score negative) — tested below.

## Part 2 — Intra-dimension rebalance gates: ALL FAIL (formula locally optimal)

The component splits were calibrated in the blind era, so all four suspicious
allocations were walk-forward tested (fidelity of recompute vs stored mx_*:
100%):

| Candidate | Result | Verdict |
|---|---|---|
| S1 stability (form/consistency grid) | gp −2.48pp | FAIL |
| J1 jockey_trainer (reduce fit 0.52) | g2 −1.10pp | FAIL |
| C1 class_weight (drop negative-sep weight_score) | all ±0.0 | FAIL (pure no-op — separation was confounded) |
| P1 pace_perf coverage-adaptive fallback | gp −2.48pp | FAIL — when PF is missing, redistributing to sectional/trial misleads |

Interpretation: univariate separation ≠ marginal value. The hand-calibrated
composite has already absorbed the cross-feature correlations. With Rounds
1–7 combined, **the arithmetic layer over current data is exhausted with
high confidence** (19 candidates killed by the same gate; 1 passed).

## Part 3 — Probability calibration + betting reference card (NEW layer, shipped as analysis)

Walk-forward calibrated (train folds only) win/top-3 rates by model rank ×
confidence tier, with OOS realization alongside (`scratch/au_probability_calibration.py`):

| Tier | Rank | win% cal / OOS | fair win odds | top3% cal / OOS | fair place odds |
|---|---:|---|---:|---|---:|
| clear | 1 | **37.7% / 35.2%** | **$2.7** | 60.6% / 60.0% | $1.7 |
| clear | 2 | 18.7% / 15.2% | $5.4 | 51.8% / 45.7% | $1.9 |
| tight | 1 | 21.5% / 23.4% | $4.6 | 47.8% / 47.9% | $2.1 |
| tight | 2–5 | 10–16% | $6–10 | 32–45% | $2.2–3.1 |
| medium | 1 | 24.4% / **14.0%** ⚠ | $4.1 | 49.8% / 46.3% | $2.0 |

Usage (odds never enter the model — compare at bet time only):
- **clear-tier rank 1 is the bankable bet type**: well-calibrated 35%+ win;
  market win odds above ~$2.90 or place above ~$1.75 = value.
- tight-tier: skip win bets on ranks 1–2; the 圍捕 radar (top-5) place/exotic
  structure fits the 47%/35%/40%+ top3 spread better.
- medium-tier rank 1 shows calibration drift (24%→14% OOS) — treat its win
  price guardedly until more data stabilizes the cell.

## Remaining improvement inventory (honest, prioritized)

1. **pace_figure coverage growth** — strongest known dormant signal (6.49);
   arrives free with each new meeting extraction.
2. **Backfill batches** (in-chat, on request) — feeds J/T retest, draw matrix
   density, and shrinks calibration noise (e.g. the medium-tier cell).
3. **Watch-list retests at +100 races** — fast-pace role adjust (+1.38pp,
   5/5 folds) is first in line to clear the gate as data grows.
4. Renderer integration of the fair-odds card (optional, reporting layer —
   zero model risk) if Kelvin wants it on the dashboard.
