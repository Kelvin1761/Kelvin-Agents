# AU Wong Choi — 跑法/步速準繩度實測 (2026-07-25)

Kelvin asked: how accurate are we on 步速/跑法, and should we remove them from
scoring if weak? Both questions now answered with data.

## Data barrier SOLVED — actual in-running positions now extracted
`scratch/au_extract_positions.py` — racenet results page carries every runner's
`CompetitorPositionSummary` (settled / 800m / 600m / 400m). ONE request per
meeting (cheap), gentle pacing, resumable, bypasses the Drive permission issue
by reading the meeting list from the local cache.
**Extracted: 48 meetings / 399 races / 4,159 horse-positions.**

## Finding 1 — running-style预测 is 46.7% accurate, but VERY unevenly

Predicting a horse's settle band (front / mid / back) from its own prior settled
positions, 259 horses with >=2 prior observed runs:

| predicted | actual front | actual mid | actual back | accuracy |
|---|---:|---:|---:|---:|
| **front** | **71%** | 26% | 3% | **strong** |
| mid | 26% | 40% | 34% | ~useless (base 36%) |
| back | 19% | 32% | 49% | moderate |

Overall 46.7% vs a 36% base rate. **The actionable detail: "front-runner"
predictions are reliable (71%), "mid-pack" predictions are worthless.** Front
runners have stable habits; mid-pack horses are the most variable.

## Finding 2 — but DO NOT remove 步速 or 走位 from scoring

Kelvin's instinct (remove what doesn't deliver) is right in principle, but these
two are among the model's most valuable dimensions. Removal test, 363-race
validation window:

| config | 頭兩揀齊三甲 | 捉到冠軍 | 頭揀贏 | 全失 |
|---|---:|---:|---:|---:|
| current | **78場 (21.5%)** | **51.8%** | **23.4%** | 42場 |
| remove race_shape (走位) | 74場 (20.4%) | 50.1% | 21.2% | 45場 |
| remove pace_perf (步速) | 70場 (19.3%) | 49.9% | 21.8% | 44場 |
| remove both | 66場 (18.2%) | 48.8% | **18.5%** | 45場 |

Every removal is worse across the board; dropping both collapses 頭揀贏 from
23.4% to 18.5% (a fifth of the winner-picking ability).

## Why "48% style accuracy" and "valuable scoring" are NOT contradictory
- **步速 (pace_figure_score) is a MEASURED TIME** (L600 vs benchmark), not a
  style prediction. How fast a horse ran has nothing to do with whether it
  settles front or back. It is the model's 2nd most important feature
  (removing it costs 頭兩揀齊三甲 −10場, 全失 +21場 in the earlier audit).
- **走位 (pace_map_score) is a barrier/position SCORE**, blending barrier
  advantage + venue draw bias (empirical, shrunk) — not a binary style label.
  Even with only moderate style predictability its net contribution is positive.

## The real opportunity this opens (improvement, not removal)
Because "front" predictions are 71% reliable while "mid" is noise, the honest
upgrade is **confidence-weighting the style evidence**: trust the front-runner
signal, discount mid-pack assignments. Combined with the newly-extracted actual
settling history (48 meetings and growing), this is a genuine data-backed
improvement path — unlike the arithmetic experiments that all washed out.

Next step (if Kelvin wants): extract the remaining ~34 meetings, then test
whether a settling-history-derived, confidence-weighted style input improves
pace_map_score through the standard honest-holdout gate.
