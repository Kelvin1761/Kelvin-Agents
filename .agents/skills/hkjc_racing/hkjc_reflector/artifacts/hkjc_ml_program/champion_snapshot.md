# Frozen HKJC Rating Matrix Champion

## Identity

- Research freeze commit: `39155166df7fdba5162b19aa872e6fe004b7f3c3`.
- Scoring source last-touch commit: `9a3e42285f86e592c01690abce362f0a6516ab46`.
- Contract version: `HKJC_7D_CONTRACT_2026_08_01_NORMALIZED_SECTIONAL`.
- Normalized-sectional blend: 5.00% when qualifying evidence exists.
- Production scorer changed by this program: **No**.

## Official seven-dimension weights

| dimension | weight |
|---|---|
| sectional | 0.1849 |
| trainer_signal | 0.2309 |
| stability | 0.1019 |
| race_shape | 0.2260 |
| class_advantage | 0.1435 |
| horse_health | 0.0378 |
| form_line | 0.0749 |

## Frozen feature mapping and score logic

| Dimension | Deterministic definition |
|---|---|
| sectional | speed score 65% + track/going score 35%; optionally blend 5% qualifying normalized L400/total-time evidence |
| trainer_signal | jockey score 55% + trainer score 45% |
| stability | form score 50% + consistency 40% + trackwork trend 10% |
| race_shape | race-shape context 100%, with neutral-safe draw fallback only when context is unavailable |
| class_advantage | class score 75% + carried-weight score 25% |
| horse_health | risk score 55% + weight score 35% + confidence/reliability 10% |
| form_line | form-line strength score 100% |

`ability_score` is the weighted sum of the seven clipped 0–100 dimensions using the official weights above; the normalized-sectional blend changes only the sectional input when its evidence gate passes.

## Grade thresholds

| minimum_score | grade |
|---|---|
| 96 | S+ |
| 92 | S |
| 88 | S- |
| 84 | A+ |
| 80 | A |
| 76 | A- |
| 72 | B+ |
| 68 | B |
| 64 | B- |
| 60 | C+ |
| 56 | C |
| 52 | C- |
| 48 | D |
| 0 | E |

Grades are display-only; numeric `ability_score` controls ranking. `MODEL_TOP_PICK` requires rank ≤2, ability ≥70 and confidence ≥55; `WATCH` requires ability ≥70 but fails a rank/confidence gate. The renderer has an advisory, ranking-neutral radar based on the Top-1/Top-3 ability gap: `<2` points = tight/Top 5, `2–<5` = medium/Top 4, `≥5` = clear/Top 4. The production analysis scorer forbids odds, market, value and edge fields. No executable ROI/stake rule is part of this frozen Champion, so betting rules remain a separate, currently unevaluable layer.
