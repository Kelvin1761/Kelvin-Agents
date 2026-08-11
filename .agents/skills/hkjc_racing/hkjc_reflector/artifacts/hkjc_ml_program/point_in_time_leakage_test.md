# Point-in-time Leakage Test

## Result: PASS

- Features tested: 110.
- Forbidden feature violations: 0.
- `prior_*` static full-season tables: excluded.
- `finish_pos`, Win/Place/Top-3 labels: targets only, excluded from X.
- odds, market rank, dividends, ROI: excluded from analysis layer.
- chronological split: training date is strictly earlier than test date in every fold.
- preprocessing/imputation/calibration: fitted inside each training fold only.
- historical trainer/jockey priors: latest snapshots neutralised unless matching PIT metadata is present.

No leakage blacklist violations found.
