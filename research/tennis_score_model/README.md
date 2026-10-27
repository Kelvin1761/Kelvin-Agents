# Offline Tennis model experiments (2026-10-27)

These scripts are research only. Production never imports this directory.
EXP07 game-share strength did not clear its registered confirmation criteria.
EXP08 continuous ranking improved historical predictive losses, but LOST to
market probabilities and worsened the fixed-price hypothetical profit control.
Neither candidate is approved for pricing, sizing, deployment or promotion.

All historical observation times remain reconstructed/FLAG. 2025 is reused
research confirmation, not a fresh holdout. Read the three frozen protocols
before rerunning. Do not change an experiment to rescue a result.

Python 3.9 + numpy + openpyxl + pytest. Set PYTHONDONTWRITEBYTECODE=1.

```bash
python score_model.py extract --db FROZEN.db --out score-corpus.json
python score_model.py run --data score-corpus.json --out score-dev
# Only after development_pass=true:
python score_model.py run --data score-corpus.json --out score-final --confirmation
python rank_prior.py augment --db FROZEN.db --data score-corpus.json --out rank-corpus.json
python rank_prior.py run --data rank-corpus.json --out rank-dev
# Only for dev-eligible arms:
python rank_prior.py run --data rank-corpus.json --out rank-final --confirmation
python market_diagnostic.py --predictions rank-final/dev_predictions.json \
 --corpus rank-corpus.json --cache /path/to/immutable/src/data/external --out market
python -m pytest . -q
```

The market files are paired B365 quotes; no quote-time verification, no CLV,
no opening-price assumptions, no live trade returns. Losses have the common
.02/.98 clamp; the hypothetical fixed 1u EV>0 rule uses raw sigmoid forecasts.
All windows, thresholds, folds and feature units were fixed before their
corresponding results. A rejected combined arm is never selected post hoc.
