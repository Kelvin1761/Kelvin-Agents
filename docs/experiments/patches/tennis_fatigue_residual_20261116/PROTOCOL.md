# EXP-20261116-17 protocol: does fatigue add anything on top of the closing market? (locked 2026-11-16, before any feature was computed)

Question: does the market price fatigue (recent match load) correctly? Any residual counts only if it beats the
market, not our model (see the edge-route note 2026-11-16).

Data: tennis-data.co.uk 2026 ATP and WTA main-draw files (same files as EXP-20261116-15, sha256 1664f3b7…f356da / 59b12453…b254b5,
re-downloaded 2026-11-16 with identical hashes). Date is the match date.
History (features): every row in the file (Completed, Retired, Walkover, Awarded); walkover counts 0 games / 0 sets.
Only rows with Date strictly before the match date count. Players are keyed by (tour, name string).
Evaluation rows: Comment == Completed, AvgW/AvgL both > 1.
Orientation: A = the alphabetically first name, y = 1 if A won (no winner/loser label leakage).

Market base: Avg closing odds (AvgW/AvgL), proportional de-vig -> fair_A. Sensitivity: Betfair close (BFEW/BFEL) where present.
Features (A minus B):
  F1 (PRIMARY) games played in the 3 days before the match (Date-3 .. Date-1)
  F2 sets played in the 3 days before
  F3 played the day before (0/1)
  F4 matches played in the 7 days before
  F5 games in the most recent match if it was within 2 days, else 0
Expected sign: negative (more load -> lower win probability than the market says).

Model: logistic  logit p = a + b*logit(fair_A) + g*F, fitted on dev only. Baseline = same without F (also fitted on dev).
Split: dev = Date < 2026-08-01; holdout = Date >= 2026-08-01. Nothing is chosen on holdout.
Metric: holdout mean per-match log-loss improvement (baseline LL minus feature LL), bootstrap 4000 draws by match, seed 20260826.
Verdict (F1): CI lower bound > 0 and g < 0 -> PROMISING (next step: test against the Betfair price at bet time, not close).
CI upper bound < 0 -> REJECT. Otherwise NO EVIDENCE (treated as a failed route; reported as such).
F2..F5 are secondary: same metric, Holm-corrected over the 4, descriptive unless they pass after correction.
Known limitation fixed in advance: qualifying and Challenger matches are not in these files, so load is undercounted for
qualifiers and players who came from Challengers; close is not the price we bet at (21:00 is earlier).
