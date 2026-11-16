# EXP-20261116-12 protocol — Sportsbet match winner vs Pinnacle close (locked 2026-11-16 before reading any price)

Question: is Sportsbet's tennis match-winner price ever better than Pinnacle's de-vigged fair price often
enough, and by enough, to pay? (A "soft book lags sharp book" test; needs no model.)

Data: tennis-data.co.uk 2026 ATP (2026/2026.xlsx) + WTA (2026w/2026.xlsx); columns PSW/PSL = Pinnacle
closing. Only Comment == "Completed". Sportsbet: tennis_wc.db odds_snapshots (bookmaker Sportsbet,
match_winner), fetched_at strictly before matches.start_time_utc.
Matching: same tour (ATP/WTA), tennis-data Date within [match_date-1, match_date+1], both players'
surnames match (normalised, accents stripped); ambiguous or reused pairings dropped.
Fair: Pinnacle proportional de-vig (primary); power de-vig as sensitivity.
Rule (primary): at the EARLIEST pre-start Sportsbet snapshot, bet 1u on any side with
  sb_odds * p_pin_fair - 1 > 0  (at most one side per match: the larger EV).
Secondary (descriptive only): LATEST pre-start snapshot; EV thresholds 0.02 / 0.05.
Split: dev = Date < 2026-09-01; holdout = Date >= 2026-09-01. Nothing chosen on holdout.
Verdict (holdout, primary rule): ROI 95% bootstrap CI (by match, 4000, seed 20260826) lower bound > 0
 -> PROMISING (needs live forward with a real-time sharp feed). CI upper < 0 -> REJECT. Else INCONCLUSIVE.
Caveat fixed in advance: Pinnacle CLOSE is unknown at bet time, so this measures whether Sportsbet's
early price beats the sharp close (expected value), not an executable strategy by itself.

## Amendment A (2026-11-16, after checking column coverage, BEFORE any Sportsbet join or outcome)
PSW/PSL (Pinnacle) exist only for 2026-01 (172 rows) — none overlap our Sportsbet window (2026-05-08 on).
Reference therefore becomes Betfair Exchange close BFEW/BFEL (present every month, ~95% of rows),
proportional de-vig (primary), power de-vig (sensitivity). Everything else unchanged.
Files: atp2026.xlsx sha256 1664f3b7…f356da, wta2026.xlsx sha256 59b12453…b254b5,
downloaded 2026-11-16T09:09:53Z from https://www.tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7/{2026,2026w}/2026.xlsx
