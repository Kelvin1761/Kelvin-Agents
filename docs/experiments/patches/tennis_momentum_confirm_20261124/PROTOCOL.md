# EXP-20261124-xx — Tennis momentum (F4) confirmation on unseen years — PROTOCOL (locked before any feature is computed)

Locked 2026-11-24 by Claude, before running anything on 2024/2025 data.

## Origin
EXP-20261116-17 found, as a *secondary, post-hoc-direction* result on 2026 holdout, that F4 (main-draw matches played in
the 7 days before, A minus B) has a POSITIVE coefficient on top of the closing market: the busier player wins more than the
market says. Dev effect was weak. That holdout has been seen and must not be reused. This protocol tests it on years never used.

## Data
tennis-data.co.uk ATP + WTA xlsx for 2024, 2025 (and 2026 only as history context — NOT evaluated).
Downloaded 2026-11-24T10:08Z from https://www.tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7/{Y,Yw}/Y.xlsx
sha256: atp2024 d92a4d41…6a, wta2024 0ce3a4e8…53, atp2025 941aaa1a…13, wta2025 aac890b7…c8.

## Rows
Comment == "Completed", AvgW/AvgL both > 1. Orientation A = alphabetically first name; y = 1 if A won.
History for features = all rows (any Comment) of the same tour across 2024–2025 files with Date strictly earlier than the match Date
(so early-January 2025 matches see late-2024 history). 2024 matches in the first 7 days of January have truncated history: drop
2024 rows with Date < 2024-01-08 from fitting.

## Feature (single, primary)
F4 = (# matches with Date in [D-7, D-1] for A) − (same for B). Same definition as EXP-20261116-17 study.py.

## Market base
Primary: Avg closing odds, proportional de-vig → fair_A. Sensitivity: Betfair close BFEW/BFEL where present.

## Fit / confirm split
FIT = 2024 (≥ 2024-01-08). CONFIRM = 2025 full year. Nothing is chosen on CONFIRM.
Model: logit p = a + b·logit(fair_A) + g·F4, fitted on FIT. Baseline = same without F4, fitted on FIT.

## Metric and verdict (primary = Avg close)
CONFIRM mean per-match log-loss improvement (baseline − feature), bootstrap 4000 draws by match, seed 20260826, 95% CI.
- CONFIRMED: g > 0 AND CI lower bound > 0.
- REJECT: g ≤ 0, OR CI upper bound < 0.
- otherwise NO EVIDENCE (counts as a failed route).
Betfair-close sensitivity is reported but cannot rescue a failed primary.

## Pre-registered secondary (descriptive only, cannot change the verdict)
1. Same metric excluding "1st Round" matches (byes and qualifiers make main-draw-only counts misleading there; qualifying
   matches are absent from these files, so qualifiers look under-loaded).
2. By tour (ATP, WTA).
3. Rule "back the busier side when |F4| ≥ 2", flat 1u, on CONFIRM: ROI at Betfair close after 5% commission on winnings,
   and at Avg close; bootstrap CI as above. Report n.
4. Calibration table by F4 bucket (−9..−3, −2..−1, 0, +1..+2, +3..+9): n, actual, fair, gap — for FIT and CONFIRM.

## Known limitations fixed in advance
- Close is not the price we bet at (21:00 Sydney is 10–20 h earlier). Even CONFIRMED only earns a live paper forward test, not
  a model change.
- Qualifying / Challenger / ITF not in files → load undercounted; Sportsbet's book is ~85% ITF which this cannot speak to.
- Main-draw ATP/WTA only.
