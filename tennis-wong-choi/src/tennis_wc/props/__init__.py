"""Tennis PLAYER-PROP engine (NBA-Wong-Choi style, ported to tennis).

Rationale (see the 2026-07-04 build): tennis MATCH-WINNER cannot beat the sharp
closing line, because the whole market (serve/return/form/H2H) is public and
efficiently priced. NBA Wong Choi profits instead by attacking a SOFT market
(player props on a recreational book) and setting the line comfortably BELOW the
player's recent form so the "N+" leg hits often. This package brings that same
structure to tennis:

  * We only price props on the SOFT book we actually collect (Sportsbet) -- never
    against Pinnacle close.
  * The flagship prop is TOTAL MATCH ACES, which is the truest tennis analogue of
    an NBA player prop (a serve stat, not a re-skin of the match-winner signal).
  * The ace model is empirically CALIBRATED on 27k historical matches
    (player_match_history), so P(over line) is a realised frequency, not a
    parametric guess. See `ace_model.CALIBRATION_CURVE`.

CRITICAL HONESTY: prop ROI is NOT yet verified. Odds coverage exists (~71 ace
matches) but settled outcomes overlap on only ~16, so we cannot backtest edge.
This engine therefore ships as a soft-market, LIVE-VALIDATE product: every prop
it surfaces is logged to `prop_tracker` and graded after the match, so real ROI
accumulates. Do not treat its edges as proven until the tracker has a few hundred
settled legs. (Same discipline the NBA memory flags as missing there.)
"""
