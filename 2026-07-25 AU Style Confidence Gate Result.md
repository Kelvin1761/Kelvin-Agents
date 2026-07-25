# AU Wong Choi — 信心加權跑法輸入 gate result (2026-07-25)

Kelvin asked to extract the remaining meetings and test whether a
confidence-weighted running-style input ("trust front, discount mid") improves
the 走位 score. Done — full extraction + honest gate. Result: no net gain.

## Extraction complete (all archive meetings)
`scratch/au_extract_positions.py` — **82 meetings / 724 races / 7,681
horse-positions** of actual in-running data (settled/800/600/400) from racenet,
one request per meeting, zero blocks. This is now a permanent local asset
(`scratch/au_positions_map.json`).

## Gate result — FAIL (no net improvement)

Leak-free front-runner evidence (share of a horse's PRIOR runs settled in the
front band), added as a confidence-weighted bonus, 363-race validation window:

| variant | Δ頭兩揀齊三甲 | Δ Top3中2隻 | 捉到冠軍 | fold非差 |
|---|---:|---:|---:|---:|
| current | — | — | 52.9% | — |
| front_only +2.0 | −4場 | +1場 | 52.6% | 5/5 |
| **front_minus_mid +2.0** | −1場 | +1場 | **53.4%** (+0.5pp) | 4/5 |
| front_minus_mid +3.5 | −1場 | −1場 | 53.4% | 3/5 |

The best variant (exactly Kelvin's "trust front, discount mid" design) buys
+0.5pp winner-capture but costs 1 race of 頭兩揀齊三甲 — no configuration is a
net win.

## Why it failed (two concrete reasons)
1. **Coverage is only 25%** — just 948 of 3,779 runners in the validation window
   have ≥2 prior observed settle positions. Horses rarely repeat within one
   archive, so the signal reaches only a quarter of the field.
2. **The front-runner advantage is already priced in** — `pace_map_score`
   encodes barrier advantage + empirical venue draw bias, which is largely the
   same thing as "settles forward". Another condition-on-model washout.

## What was still worth it
- The measured accuracy profile stands and is genuinely useful for reading:
  **front-runner predictions are 71% reliable; mid-pack predictions are noise
  (40% = base rate).** That is a human-judgement aid, even though it doesn't
  improve the ranking arithmetic.
- The positions dataset (7,681 records) is now available for any future
  pace/bias研究 without new extraction.

## Standing conclusion (unchanged, now even better evidenced)
Running-style/step-pace features must STAY in scoring (removal costs
頭揀贏 23.4%→18.5% when both dimensions dropped). They are not weak — they are
already extracting what the data supports. The style signal cannot be sharpened
further from settling history at current repeat-coverage.
