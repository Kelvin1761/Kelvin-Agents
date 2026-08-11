# HKJC ML Readiness Report

## Verdict: READY WITH LIMITATIONS

The archive is usable for conservative chronological research after deterministic cleaning. It is not large or pristine enough to justify automatic production promotion.

## Coverage

- 3109 valid runners, 250 valid races, 25 meetings.
- Date range: 2026-04-12 to 2026-07-15.
- Average actual field size: 12.44.
- Invalid races excluded: 3.
- Declared-versus-actual starter mismatches repaired: 22 races.
- Unknown distance rows retained as missing: 10.
- Unknown class rows retained as `Unknown`: 32.

## Race coverage breakdown

| dimension | value | races | share |
|---|---|---|---|
| venue | 沙田 | 161 | 0.6440 |
| venue | 跑馬地 | 89 | 0.3560 |
| surface | AWT | 7 | 0.0280 |
| surface | Turf | 243 | 0.9720 |
| class | Class 1 | 2 | 0.0080 |
| class | Class 2 | 7 | 0.0280 |
| class | Class 3 | 28 | 0.1120 |
| class | Class 4 | 187 | 0.7480 |
| class | Class 5 | 15 | 0.0600 |
| class | Griffin | 2 | 0.0080 |
| class | Group 1 | 2 | 0.0080 |
| class | Group 2 | 1 | 0.0040 |
| class | Group 3 | 3 | 0.0120 |
| class | Unknown | 3 | 0.0120 |
| distance | 1000 | 21 | 0.0840 |
| distance | 1200 | 101 | 0.4040 |
| distance | 1400 | 44 | 0.1760 |
| distance | 1600 | 21 | 0.0840 |
| distance | 1650 | 33 | 0.1320 |
| distance | 1800 | 21 | 0.0840 |
| distance | 2000 | 4 | 0.0160 |
| distance | 2200 | 2 | 0.0080 |
| distance | 2400 | 2 | 0.0080 |
| distance | Missing | 1 | 0.0040 |
| going | Unavailable in aligned archive | 0 |  |

Course/configuration detail is published in `archive_coverage_summary.csv`. Going is explicitly unavailable rather than inferred from post-race descriptions.

## Feature coverage

`feature_dictionary.csv` reports, for every aligned column: coverage, missingness, neutral/default rate and definition, unique values, suspicious-value count, first/last availability date, historical depth, role, and point-in-time treatment.

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

Dataset manifest SHA-256: `ef355a56ce9bcaa29fa1f775e918992974fa8da7e944db8149c22e1818323387`.
