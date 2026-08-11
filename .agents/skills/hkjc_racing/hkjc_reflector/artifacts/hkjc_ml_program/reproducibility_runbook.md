# HKJC ML Reproducibility Runbook

## Frozen inputs

- `scratch/hkjc_ranking_dataset_current.csv`
- `scratch/hkjc_ranking_dataset_2026_07_15_current.csv`
- Source hashes and split dates: `dataset_manifest.json`
- Random seed: `20260811`

## Runtime

Python 3.9 with NumPy, pandas, scikit-learn, joblib, LightGBM 4.6, XGBoost 2.1 and SHAP 0.49. On macOS, LightGBM/XGBoost also require the LLVM OpenMP runtime (`libomp`). The research script fails closed if either tree package cannot load.

Run from repository root:

```bash
python3 .agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_ml_program.py
```

The script deterministically rebuilds this artifact directory. It does not write production scoring weights or odds into the analysis layer.

## Verification

```bash
python3 -m unittest discover -s .agents/skills/hkjc_racing/hkjc_reflector/tests -p 'test_*.py'
python3 -m unittest discover -s .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests -p 'test_*.py'
```
