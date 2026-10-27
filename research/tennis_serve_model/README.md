# EXP-20261027-09 — offline opponent-adjusted serve/return point strength

Research only. No production module imports this directory. The candidate failed
the preregistered 5/5 development guard; 2025H2 confirmation was NOT opened.
Both historical observation times and quote capture times remain unverified.
Do not deploy, size bets with these weights, or relabel reused data as holdout.

`serve_protocol.json` is this experiment's frozen specification. `protocol.json`,
`score_model.py`, `market_protocol.json`, and `market_diagnostic.py` are unchanged
EXP07/08 baseline/market helpers included so the research is self-contained.
No model variants or quote thresholds were selected after outcomes.

Python 3.9 + numpy + openpyxl + pytest. Set PYTHONDONTWRITEBYTECODE=1.

```bash
python serve_model.py augment --db FROZEN.db --data PRIOR_RANK_CORPUS.json --out serve-corpus.json
python serve_model.py run --data serve-corpus.json --out serve-results
# Do NOT use --confirmation for this rejected candidate.
python serve_market.py --predictions serve-results/dev_predictions.json \
 --corpus serve-corpus.json --cache /path/to/immutable/src/data/external --out market-results
python -m pytest . -q
```

`serve_market.py` preserves the original binary probability before explicit
legacy-column mapping. It verifies the exact 8,240 matches and both original
binary/rank baselines. The fixed-price diagnostic does NOT represent live ROI.

Opponent-adjusted S/R beats its unadjusted counterpart in all five dev folds,
but loses to the Elo+rank control in 2025H1 logloss. The hypothetical P/L gain
against original binary is small and statistically uncertain; ROI remains
negative and slightly worse. The market probability benchmark remains stronger.

Current operational quote source: Sportsbet only. Existing B365 archived
comparisons do not satisfy Sportsbet execution-time profitability validation.
