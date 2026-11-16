# EXP-20261116-16 protocol — tennis total games model (locked 2026-11-16 before fitting or reading any result)

Why: Sportsbet two-way "Match Total Games" is the weakest market we found (market AUC 0.555 on 468
matches, 8.2% margin); our current hold model scores 0.485 there. Totals are driven by serve dominance,
which a book pricing mainly off the match price may under-use.

Population: matches in tennis_wc.db with a completed best-of-three score (match_results.score_json,
winner has 2 sets, all sources agree), fixture not DISPUTED, match_date in 2026.
Target: total games (sum over sets; a tiebreak set counts 13).
Split: dev = match_date < 2026-09-01 (fit everything); holdout = match_date >= 2026-09-01 (report once).

Features, strictly before match_date (same-day matches excluded):
- per player hold / break rate from player_match_history (ACTIVE rows, hold_rate not null, last 365
  days, one row per (date, opponent)), weighted by service_games_played (10 if missing), shrunk to the
  dev tour mean with k = 30 service games. Also each player's stats-match count (coverage).
- Elo closeness q = |p_elo - 0.5|, p_elo from player_elo_history_v2 start-of-day overall rating
  (missing rating -> 1500), p = 1/(1+10^((Rb-Ra)/400)).
- categorical: tour (ATP/WTA/other), tier (props.tier_of: TOUR/CHALLENGER/ITF/other), surface (hard/clay/grass/unknown).

Models (OLS on dev):
- B0: categorical only.
- B1: B0 + q + q^2   ("closeness only" — roughly what a book gets from the match price).
- M : B1 + (hold_a+hold_b) + (break_a+break_b) + (hold_a+hold_b)*(1-q*2) + coverage indicator (both
      players >= 5 stats matches).
P(over L) = 1 - Phi((L - mu)/sigma), sigma = dev residual SD of that model.

Holdout checks:
1. Accuracy: RMSE of M vs B1, paired bootstrap by match (4000, seed 20260826).
2. Market (Sportsbet two-way Match Total Games, earliest pre-start snapshot with both sides, settled by
   the same score): AUC of market fair, of M's P(over), and of (M P(over) - market fair) on the outcome;
   rule "bet the side with larger EV if model EV > 0", 1u, ROI with match bootstrap CI; also EV > 0.05.
Verdict: PROMISING (-> forward shadow 大細精選 arm) only if (1) RMSE M < B1 with CI below 0 AND
(2) gap AUC CI lower > 0.5 or EV-rule ROI CI lower > 0. Otherwise REJECT (or INCONCLUSIVE when CIs
are wide and point estimates favour M). Nothing is tuned on holdout; any change after this = new protocol.

Clarification (same session, before any fit): a final set recorded with a winner score > 7 (match tiebreak,
e.g. 10-8) counts as 1 game, as Sportsbet settles it; a set with impossible scores (both < 6 and not a
retirement-free final, or > 7 in sets 1–2) drops the match.
