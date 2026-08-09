# AU Wong Choi — Diagnosing the 90 blindspot winners (odds-free) (2026-07-24)

Kelvin: forget odds; find the hidden signal in OUR data for the 90 blindspot
winners (market top-2, our model ranked ≥5, WON). Honest, data-backed result.

## The "worst in field" read was mostly a missing-data artifact

Re-check of the 90:
- pace_figure DEFAULT (missing): **77%** — the earlier "pace percentile 0.00"
  was largely NO DATA defaulting them down, not genuine slowness.
- sectional default 0%, form default 13%; lightly-raced (≤3 starts) only 28%
  (72% are seasoned); **had a top-3 trial: 88%**.

## But base rates kill the cheap signals

| group | top-3 trial % | pace_figure missing % |
|---|---:|---:|
| ALL runners | 75% | 67% |
| all WINNERS | 81% | 69% |
| the 90 blindspots | 88% | 77% |

- "Top-3 trial" describes **75% of the whole field** — the blindspots' 88% is
  only mildly elevated, not a separator. (This is exactly why every trial-boost
  candidate failed the gate: 72% of high-trial horses ranked >4 don't place.)
- Missing pace_figure is ~67% everywhere and is NOT elevated in winners — it
  doesn't predict winning.

**Conclusion:** at our current feature *granularity* there is NO learnable,
odds-free signal separating these 90 from the many similar horses that lost.
The blind spot is the ABSENCE of a discriminating signal, not a hidden one. The
market separated them using information (money / intent / connections'
confidence) that is genuinely not in our data — confirming why 21 model
candidates failed.

## The one credible odds-free lead: trial QUALITY, not trial EXISTENCE

We encode "ran top-3 in a trial" (75% of everyone → useless as a ranker). We do
NOT encode **how** it trialled: winning margin, L600 sectional vs the trial
field, whether it was hard-held/eased. The market reads trial *quality*; our
`trial_score` reads trial *existence*. That coarse encoding is the real gap.

### Concrete next experiment (no odds)

1. Extract per-trial **margin + L600 time** from racenet sectionals pages
   (already shown to carry trial sectionals in the PF work).
2. Build a `trial_quality_score` (dominance-weighted, field-relative) to
   replace the binary-ish `trial_score`.
3. Standard walk-forward gate. Plausible but unproven — and honestly, part of
   the market's edge (money/intent) will remain uncatchable from any data.

This is the only path that respects "no odds" and has a real chance; everything
coarser has already been tested and failed.
