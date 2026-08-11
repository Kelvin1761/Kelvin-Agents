# HKJC WONG CHOI ML RESULT

Current Production Model:
HKJC_7D_CONTRACT_2026_08_01_NORMALIZED_SECTIONAL

Best Independent Analysis Model:
Logistic Regression

Best Analysis Hybrid:
Matrix+Logistic Regression α=0.25 (research only; failed promotion gate)

Historical Dataset:
250 races / 3109 runners

Final Out-of-Sample Test:
9 races / 107 runners (chronological ML-unseen block; not globally pristine)

ANALYSIS PERFORMANCE

Primary figures below are strict expanding-window walk-forward results across 161 races; the nine-race external block is reported separately in `model_comparison_scorecard.csv`.

WIN

Current Matrix Top-1:
24.84%

Best ML Top-1:
24.22%

Difference:
-0.62 percentage points

Current Matrix Top-3:
53.42%

Best ML Top-3:
52.80%

Difference:
-0.62 percentage points

Current Matrix Win Brier:
0.069533

Best ML Win Brier:
0.069566

Improvement:
-0.048%

Current Matrix Log Loss:
0.255374

Best ML Log Loss:
0.254912

Improvement:
+0.181%

PLACE

Current Matrix Place Brier:
0.168201

Best ML Place Brier:
0.164769

Improvement:
+2.041%

Current Matrix Place Log Loss:
0.511811

Best ML Place Log Loss:
0.502814

Improvement:
+1.758%

WALK-FORWARD ANALYSIS

ML improved vs Matrix:
7 / 16 periods

ML underperformed Matrix:
9 / 16 periods

Period comparison uses the pre-declared analysis selection score: Top-3 capture@5 + winner Top-3 + 0.25×NDCG@5 − 0.20×Log Loss.

BETTING PERFORMANCE

WIN

Current Matrix Betting ROI:
N/A

Best ML Betting ROI:
N/A

Difference:
N/A

PLACE

Current Matrix Betting ROI:
N/A

Best ML Betting ROI:
N/A

Difference:
N/A

RISK

Current Matrix Max Drawdown:
N/A

ML Max Drawdown:
N/A

CLV

Current Matrix:
N/A

ML:
N/A

Complete fixed-time Win/Place odds, official dividends and settlement metadata do not exist in the archive; no betting number is fabricated.

SEGMENT FINDINGS

ML stronger:
race_class_label=Class 5 (+0.093), race_confidence_band=High ≥5pp (+0.076), course=B (+0.039)

Matrix stronger:
race_confidence_band=Medium 2–5pp (-0.163), race_class_label=Class 3 (-0.089), race_confidence_band=Low <2pp (-0.080)

Segment labels are descriptive and not standalone promotion claims.

FINAL VERDICT

KEEP CURRENT MATRIX

The best ML marginally improves probability loss but does not improve Top-1/Top-3 ranking, raises walk-forward 0-hit rate, and regresses external Top-5 contender capture. The current Matrix therefore remains production Champion; ML stays research-only.
