# HKJC Stability Residual Shadow Runbook

## Status

- Approved for opt-in shadow monitoring.
- Not approved for production ranking, Grade, verdict, Top Pick or betting recommendation.
- Mainline contract remains `HKJC_7D_CONTRACT_2026_08_01_NORMALIZED_SECTIONAL`.

## Frozen contract

- Model version: `HKJC_STABILITY_RESIDUAL_SHADOW_V1`
- Target: Win competitiveness probability
- Dimension: `stability`
- L2 penalty: `1.0`
- Log-odds cap: `±0.05`
- Model SHA-256: `c6928b9dfbf7e19bc5493e708512fb207be15dd0e6bbe5c2cf53ea88b8472b12`
- Training data ends: `2026-07-12`
- External diagnostic meeting: `2026-07-15`

The runner validates the checksum, dimension, target, cap and exact 15-feature
list before loading the model. It also verifies that the stored mainline rank
still matches the official ability order. A mismatched artifact or stale rank
fails closed.

## One-command use

```bash
python3 .agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py \
  <meeting-folder-or-Race_X_Logic.json> \
  --stability-residual-shadow
```

The opt-in shadow requires pandas, NumPy, SciPy, scikit-learn and joblib.
Default Auto runs do not load these research dependencies.

## Standalone use after Auto scoring

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_stability_residual_shadow.py \
  <meeting-folder-or-Race_X_Logic.json>
```

Optional post-race evaluation:

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_stability_residual_shadow.py \
  <meeting-folder> \
  --results-file <full-day-results.json>
```

Results are attached only after shadow probabilities and ranks are computed;
they never enter the feature frame or model.

## Outputs

- Meeting: `HKJC_Stability_Residual_Shadow.csv` and `.json`
- Single race: `Race_X_Stability_Residual_Shadow.csv` and `.json`

The CSV contains mainline/shadow probability, rank, bounded logit delta,
`entered_top2` and `exited_top2`. The JSON records the frozen contract and
race-level Top-2 changes. Neither output is consumed by mainline rendering.

## Promotion rule

Do not promote because of an attractive individual swap. Review the frozen
shadow collectively after new local meetings. At minimum:

- 0/1-hit severity must improve;
- Winner@3, Top-3 capture@5 and NDCG@5 must not regress materially;
- probability Log Loss/Brier must remain non-regressive;
- helped races must materially exceed harmed races;
- no new course/distance/class micro-rule may be fitted after seeing results.
