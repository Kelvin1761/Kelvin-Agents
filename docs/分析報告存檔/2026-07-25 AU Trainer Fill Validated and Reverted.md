# AU Wong Choi — 練馬師填補：驗證後回退 (2026-07-25)

Drive access was restored (Kelvin granted Full Disk Access to the Claude app), so
the trainer fix could finally be validated properly. Result: **coverage improved
dramatically, accuracy did not — reverted.**

## What was measured (whole archive, not a sample)
Re-scored **87 meetings** through the fixed engine and compared against the
stored pre-fix scores on **708 comparable races** using real results.

- **Coverage: worked exactly as intended.** 2,957 / 7,547 runners (39%) moved
  from a flat default 60 to an evidence-based trainer score. Local spot-check:
  trainer default rate 35% → 1%.

## But performance got slightly worse

| 708 races | 頭兩揀齊三甲 | Top3中2隻 | 捉到冠軍 | 頭揀贏 | 全失 |
|---|---:|---:|---:|---:|---:|
| before fix | 134場 (18.9%) | 288場 (40.7%) | 51.8% | **23.9%** | 85場 |
| after fix | 132場 (18.6%) | 281場 (39.7%) | 50.8% | **22.3%** | 87場 |

Split-half unstable too: 前半 +6場 / 後半 −8場.

## Scaling it down looked better in-sample — and failed the honest holdout
| magnitude | 頭兩揀齊三甲 | Top3中2隻 | 捉到冠軍 |
|---|---:|---:|---:|
| 0 (no fix) | 134場 | 288 | 51.8% |
| 0.5× | **140場 (+6)** | 296 (+8) | 51.1% |
| 1.0× | 132場 | 281 | 50.8% |

Tempting — but choosing the magnitude on the earliest 60% of dates and testing on
the **284 unseen races** gave: 頭兩揀 19.0% → **16.9%**, 捉到冠軍 50.7% → **47.2%**.
The in-sample "+6場" was overfitting.

## Why (the recurring lesson, now with a clean example)
Unlisted trainers are mostly small stables. Their last-year strike rate largely
**re-expresses the quality of the horses they happen to train** — which form,
consistency and rating already capture. Filling the hole therefore adds noise and
double-counts an existing signal. **Coverage ≠ accuracy.**

## What was kept
1. **The real bug fix stays:** `_load_jockey_trainer_combo_stats()` no longer
   crashes the whole scoring run when the Drive CSV is unreadable (this was
   breaking 5 tests for days).
2. `_trainer_empirical_base()` is kept but **unused**, so the analysis is
   reproducible; tests lock the revert (unlisted trainers stay neutral).
3. All 36 AU tests pass.

## Honest scoreboard for the whole review
~27 candidates tested, 1 promoted (the facts-refresh evidence recovery, +3.6pp).
The model is at the ceiling of what current data supports. The two stable,
verified betting edges (WIN model-top2 ∩ market-top2 +8.5%; PLACE model#1 =
market#1 +3.8%) remain the most practically valuable findings.
