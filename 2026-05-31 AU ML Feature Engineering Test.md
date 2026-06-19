# AU ML Feature Engineering Test

Dataset: `3482` horses in `316` races
Features: `22` (16 feature scores + 7 matrix scores)

## Approach

- Input: 16 hand-crafted feature scores per horse
- Additional: 7 matrix dimension scores
- Target: binary (1 = top-3 finish, 0 = not)
- Models: XGBoost + LightGBM ensemble
- Evaluation: 5-fold cross-validation (race-level split)

## Baseline (Current Engine)

- Champion: `19.3%`
- Gold: `4.1%`
- Good: `38.9%`
- Pass: `38.9%`
- Top3 Place: `42.6%`
- 0-hit: `48`

## ML Ensemble (5-fold CV)

- Champion: `23.2%`
- Gold: `2.5%`
- Good: `35.6%`
- Pass: `35.6%`
- Top3 Place: `39.0%`
- 0-hit: `66`

## Delta

- Champion: `+3.9pp`
- Gold: `-1.6pp`
- Good: `-3.4pp`
- Pass: `-3.4pp`
- Top3 Place: `-3.6pp`
- 0-hit: `+18`

## Feature Importance (GradientBoosting)


## Verdict

**ML does not outperform the current engine on this dataset.** The hand-crafted engine is already well-calibrated for the available data. More data or features needed.