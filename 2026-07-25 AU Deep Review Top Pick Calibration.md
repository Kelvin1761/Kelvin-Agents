# AU Wong Choi — 深度覆盤：頭揀校準 + 數據障礙根因 (2026-07-25)

Kelvin: (1) fix the data barriers — is 實測步速 fixable, why is 練馬師 40% missing;
(2) review again against historic results to find what we got right/wrong.

## #1 Data barriers — root causes now identified

### 實測步速 (pace_figure) — ALREADY FIXED going forward
Coverage by month: 0% (2025-08→2026-04) → 84% (2026-05) → 95.3% → **95.7% (2026-07)**.
The 67% figure is a historical average. Live meetings today capture the model's
strongest signal (separation 6.49) at ~full strength. Historical backfill was
tested (Round 10) and FAILED, so forward-coverage is the correct posture.
**Action: coverage monitoring only** — alert if a meeting's PF extraction drops.

### 練馬師 (trainer_score) 40% missing — ROOT CAUSE FOUND
`_trainer_score` looks the trainer up in a **hand-curated list of 57 trainers**
(`resources/AU_Trainer_Ratings.csv`). Anything outside → default 60. Jockeys are
0% missing because the jockey pool is concentrated (60 listed names cover nearly
all rides), but the **trainer pool is far wider** — so 22–72% of runners get no
trainer rating, and it is getting WORSE (2026-07: 72%).

**The fix is available in the data we already extract:** the engine already
carries `trainer_ly` (last-year official rides/wins/places per trainer) but only
uses it for narrative text, NOT for scoring. Filling unlisted trainers with their
own empirical last-year strike rate would cut the 40% barrier to near-zero using
data already in the Logic files.
**Blocked right now:** Drive access is `PermissionError`, so I cannot read
`trainer_ly` values to validate the fill before implementing. This is the single
most concrete, highest-confidence data-barrier fix outstanding.

### The other barriers are low value
trial 25%/sep 1.67, class 22%/0.76, fit 18%/0.37 — all weak-when-present, so
closing them is low-payoff. weight is covered but has negative separation
(direction already fixed).

## #2 Deep review vs historic results — where we actually lose

**Top-pick performance (710 races): 頭揀贏 23.9%, 頭揀入三甲 50.0%.**

When the top pick fails (355 races), where was the real winner?

| real winner's model rank | share |
|---|---:|
| **2nd–4th** | **50%** |
| 5th–7th | 32% |
| 8th+ | 18% |

**Half the failures are near-misses** — we nearly had it, the ordering was just
slightly off. That is exactly Kelvin's "missing slightly on the top picks".

But the feature comparison is sobering: in those races the real winner scores
LOWER than our top pick on every major feature (consistency −11.0, form −10.0,
sectional −9.2, pace_figure −7.0). **The winners we miss are horses that look
genuinely worse in the data** — this is racing's irreducible randomness, not a
missing signal. (Consistent with ~25 candidate tests all washing out.)

## The one actionable calibration finding

Top-pick win rate depends on its GAP over the #2 pick:

| gap (#1 − #2 ability) | races | 頭揀贏 | 頭揀入三甲 |
|---|---:|---:|---:|
| **< 0.5 pt** | 157 (22%) | **17.8%** | 47.1% |
| 0.5–1.5 | 230 | 27.0% | 49.6% |
| 1.5–3 | 173 | 23.7% | 51.4% |
| ≥ 3 | 150 | 26.0% | 52.0% |

**When the top two are within 0.5 points (22% of races), the top pick wins only
17.8% — a third below normal.** The #2 pick in those races is NOT better (15.3%),
so the correct reading is *"these two are effectively tied — do not favour #1"*,
not "swap them".

This is a real, честный calibration insight that can be surfaced in the report
(the existing confidence-tier line already does something similar at the top1–top3
level; this adds the sharper top1-vs-top2 case).

## Priority list after this review
1. **練馬師 empirical fill** (needs Drive access) — the one concrete barrier fix.
2. **PF coverage alert** — protect the strongest signal on live meetings.
3. **Top1≈Top2 tie flag** in the report — free calibration honesty.
4. Venue-level pace-shape bias from the 7,681 extracted positions — untested new object.
