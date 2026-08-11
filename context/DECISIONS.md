# Decisions

## HKJC ML program

1. Keep analysis and betting as separate layers. No odds, market rank, dividends, ROI, or post-race information may enter analysis-model features.
2. Freeze the deterministic Matrix Champion before training challengers.
3. Use chronological splits and expanding-window walk-forward only; no random cross-validation.
4. Define Place using applicable HKJC field-size rules and exclude races without a valid Place target.
5. Treat score bands as calibrated competitiveness tiers, evaluated by observed win/place rate and ranking capture—not as cosmetic grades.
6. Make a research commit regardless of promotion outcome. Change production only when the strict promotion gate passes.

## AU Wong Choi failure analysis and ML program

1. Investigate cold runners finishing last and missed successful favourites before proposing scoring changes. SP/results are retrospective labels only and never scoring inputs.
2. Fix the reproducible Facts refresh misalignment: current Facts-authoritative scalar fields replace stale Logic values instead of filling only missing fields.
3. Promote the historical Performance Quality transport recovery at 10% reliability because it passed the canonical chronological gate; primary captured evidence always takes precedence.
4. Do not use slot-specific reranking. Any future improvement must strengthen point-in-time ability evidence and be evaluated across all ranking slots.
5. Keep odds completely outside Logistic/LightGBM/XGBoost and Matrix+ML analysis. Introduce SP only after analysis-model selection for the separate betting scorecard.
6. Keep the Rating Matrix in production. XGBoost and the 50% Matrix/XGBoost hybrid failed the full probability/ranking/walk-forward/bootstrap/betting promotion gate.
7. Preserve unsuccessful ML results. The current evidence says added model complexity does not compensate for missing point-in-time information, especially shallow-form wet-track evidence.
