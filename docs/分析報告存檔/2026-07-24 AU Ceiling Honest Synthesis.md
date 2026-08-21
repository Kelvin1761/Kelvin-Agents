# AU Wong Choi — Honest synthesis: at the data ceiling (2026-07-24)

Kelvin pushed on: remove weak signals, re-tune weights, fix 缺數據假象, ensure
every horse has data. All tested on ALL 710 races (not samples), plain terms.

## Terminology (plain)
- 頭兩揀齊入三甲 = our #1 & #2 picks BOTH finish top-3 (the strict "good")
- Top3中2隻 = any 2 of our top-3 picks finish top-3
- 捉到冠軍 = the actual winner is in our top-3
- 頭揀贏 = our #1 pick wins
- 全失 = none of our top-3 finish top-3

## #2 Re-tune weights (full features) — no honest gain
Honest holdout (tune on earliest 60% of dates, test on unseen latest 40% = 316
races):
- current weights: 頭兩揀齊 65場(20.6%), 捉冠軍 50.6%, 頭揀贏 23.4%
- re-tuned weights: 頭兩揀齊 63場(19.9%), 捉冠軍 50.3%, 頭揀贏 22.8%
Re-tuning slightly WORSE out-of-sample. Current weights already generalise well.
(The per-fold "big gain" earlier was optimisation overfitting.)

## #3 缺數據假象 — real in the data, but NOT hurting accuracy
- Missing (default-60) rates: pace_figure 67%, trainer 40%, trial 25%, class 22%,
  fit 18%.
- Three handling fixes tested (renormalise present-only / down-weight low-coverage
  dimension / both): ALL neutral-to-worse. The current "missing = neutral 60" is
  already the right default (field-relative scores return neutral when they can't
  compute — rank-safe).
- **Decisive diagnostic:** races grouped by missing rate — high-missing races are
  NOT scored worse (mid-missing 25-40% actually slightly better: 頭兩揀齊 21% vs
  low-missing 19%, 全失 7% vs 13%). Missingness is usually SHARED across a field
  (whole race of first-starters), so it doesn't distort the relative ranking.
- So "scoring is meaningless without data" is not borne out — the model degrades
  gracefully and missing data isn't costing accuracy.

## #4 Remove weak / micro-adjustments — slightly worse, not better
Honest holdout: lean model (drop weight/class/sectional/trial) + re-tuned =
頭兩揀齊 61場(19.3%) vs current 65場(20.6%). The weak features net-contribute a
little; the "remove 3 was better" was a per-fold artifact.

## The honest bottom line
Every lever Kelvin proposed — remove weak, re-tune, simplify, backfill data
(Round 10), handle missing data — has now been tested on all races and NONE
improves out-of-sample. **The model is at the ceiling of what the current data
supports.** Across ~24 rounds, only TWO things moved the number: the
facts-refresh evidence recovery (+3.6pp, shipped) and the market/odds column
(orthogonal, but Kelvin wants odds-blind).

## What's actually worth doing now
1. **Maintainability clean-up (no perf change):** weight_score direction already
   fixed; optionally remove class_score (validated free) + retire form_line
   dimension (weight 0). Cleaner model, same performance — matches Kelvin's
   dislike of clutter.
2. **Live data quality going forward** (not backfill): make sure NEW meetings get
   full pace_figure/trainer/trial coverage at extraction — that's where fuller
   data actually reaches the races being bet, unlike historical backfill.
3. The genuine new-signal lever remains the market column (set aside by choice).
Stop running predictable-fail arithmetic/removal experiments — they cost time
without moving the number (Kelvin's own #5).
