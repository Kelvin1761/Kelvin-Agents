# HKJC ML Readiness Report

## Verdict: READY WITH LIMITATIONS

The archive is usable for conservative chronological research after deterministic cleaning. It is not large or pristine enough to justify automatic production promotion.

## Coverage

- 3109 valid runners, 250 valid races, 25 meetings.
- Date range: 2026-04-12 to 2026-07-15.
- Invalid races excluded: 3.
- Declared-versus-actual starter mismatches repaired: 22 races.
- Unknown distance rows retained as missing: 10.
- Unknown class rows retained as `Unknown`: 32.

## Point-in-time decision

- Result labels, result position, market/odds, dividends, ROI, ranks, and static `prior_*` tables are excluded from analysis features.
- Historical engine replay now always receives `race_date`; latest/full-season trainer priors are rejected unless a matching PIT source is injected.
- Race-relative features use only runners declared in the same pre-race card.
- The frozen Matrix score is used as the Champion ranking and is calibrated using training dates only.

## Limitations

1. The 24-meeting archive has already influenced previous Matrix research, so it is development evidence, not a pristine holdout.
2. 2026-07-15 is ML-unseen and chronological, but has only nine races and was previously inspected during Matrix work; it is not globally untouched.
3. Full runner-level timestamped odds and Place-price snapshots are absent, so honest ROI, CLV, and Place betting evaluation are unavailable.
4. Rare classes, AWT, debut runners, and small fields have low effective sample size.
5. LightGBM/XGBoost should remain shallow and regularised; learning-curve saturation matters more than in-sample fit.

## Approved feature groups

- **matrix_7d**: 14 numeric, 0 categorical
- **facts_compact**: 92 numeric, 4 categorical
- **matrix_plus_facts**: 106 numeric, 4 categorical

Dataset manifest SHA-256: `d6eff5139ec09e22e2aed27dab1f7c7ba5bd35c4d9514e8094653e0072a4e1a6`.
