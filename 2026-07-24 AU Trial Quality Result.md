# AU Wong Choi — Trial-Quality Experiment Result (2026-07-24)

Kelvin: pursue trial QUALITY (not existence) to catch the blindspot winners,
odds-free. Done — disciplined offline-first (no wasted racenet requests).

## Trial WIN discriminates univariately (real, better than binary trial)

Top-3 finish rate by trial quality (6,202 horses with parsed trial positions):

| trial quality | top-3 finish % |
|---|---:|
| **won a trial** | **33.0%** |
| best trial 2nd | 26.5% |
| best trial 3rd | 25.3% |
| no trial data | 22.9% |

Lightly-raced (≤3 starts): won-a-trial 35.8% vs no-trial 24.7%. So "won a
trial" is a genuine ~10pp signal that our binary-ish `trial_score` blurs.

## But it washes out conditional on the model — the recurring wall

- **Walk-forward gate:** every trial-win boost lifts gp/g2 (best: gp +2.2,
  g2 +3.0 at boost 5) but adds **misses (+8)** and fails fold stability. Targeted
  rescue (boost only buried trial-winners) is worse (+7..+16 misses) — it
  displaces the model's correct picks with trial-winners that mostly don't place.
- **Odds-free rescue shortlist** (model top-3 ∪ trial-winners ranked 4-8):
  covers 1.98/3 vs 1.67/3, BUT the rescued horses place at **31% = the base
  rate**. Conditional on model rank, trial-win adds NOTHING — the 33% headline
  was mostly the correlation between trial-wins and higher model rank, which the
  model already captures (trial feeds it, if weakly).

## Honest conclusion

This is the 22nd candidate area and it lands where the others did: the signal
exists on its own but is **base-rate once you condition on what the model
already knows**. Our data's information is essentially fully extracted.

## The one untested sliver (low expectation)

Trial *finish position* is already reflected in the model. The only genuinely
new data-based trial signal left is trial **sectional TIME / L600** (how fast,
not just where it finished) — which needs racenet trial-sectional extraction.
Given how consistently conditional-on-model signals wash out, expectation is
low; I did NOT spend the extraction budget on it pre-emptively. Recommend
pursuing only if Kelvin wants to formally close the loop.

## Best use of the trial-win signal (zero risk)

Not a re-ranker — a **display flag** ("won last trial" / trial record) shown on
the analysis for the human eye, and an optional odds-free candidate in a
widened shortlist. Informative context; never touches the ranking.
