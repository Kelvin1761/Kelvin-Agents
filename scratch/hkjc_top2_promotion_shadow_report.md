# HKJC Top 2 Promotion Shadow Review

## Scope

- Objective: test whether selected current rank-3 horses can safely replace rank 2 for users who only bet the first two recommendations.
- Decision boundary: rank 1 never changes; only rank 2 versus rank 3 is compared.
- Included evidence: speed, form-line strength, class, distance, risk and confidence.
- Excluded evidence: odds, market, going, draw and all rank-4-to-rank-7 horses.
- Status: shadow diagnostic only; no live score or ranking was changed.

## Coverage

- Original archive: 13 meetings / 130 races.
- Independent recent holdout: 11 meetings / 113 races (2026-05-27 to 2026-07-12).
- 2026-07-15 Happy Valley external check: 1 meeting / 9 races.
- Total: 25 meetings / 252 races.
- 2026-05-31 Sha Tin and 2026-06-24 Happy Valley were skipped because a local logic/results pair was incomplete.

## Baseline Finding

- Rank-1 winners: 57/252.
- Rank-2 winners: 38/252.
- Rank-3 winners: 36/252 (14.3%).
- Baseline Top 2 contained the winner in 95/252 races (37.7%).

The rank-3 winner population is large enough to investigate, but it is not explained by one universal factor. In the original 130-race archive, rank-3 winners were on average weaker than rank 2 on speed and form-line, with only a modest distance advantage. In the 2026-07-15 examples, the common signal was instead a very large distance advantage, supported by class or lower-risk evidence.

## Candidate: Dual-Signal Union

Promote rank 3 to the second recommendation only if either gate passes:

1. Balanced evidence gate
   - Weighted evidence: speed 35%, form-line 30%, class 20%, distance 15%.
   - Rank 3 must lead rank 2 by at least 4 points.
   - Rank 3 must beat rank 2 in at least two component signals.
   - Risk and confidence must both be at least 60.

2. Strong distance-context gate
   - Distance score advantage must be at least 10 points.
   - Confirmation requires either class advantage of at least 5 points or risk-score advantage of at least 10 points.
   - Risk and confidence must both be at least 60.

## Shadow Result

- Triggered: 34/252 races (13.5%).
- Helped: 10 rank-3 winners promoted into Top 2.
- Harmed: 2 rank-2 winners removed from Top 2.
- Net winner improvement: +8 races.
- Candidate Top 2 contained the winner in 103/252 races (40.9%), up 3.2 percentage points.
- Total Top-2 actual-place hits: +9.
- Races where both recommendations finished in the actual Top 3: +3.

### Dataset consistency

- Original archive: +2 net winners.
- Independent recent holdout: +4 net winners (5 helped, 1 harmed).
- 2026-07-15 Happy Valley: +2 net winners, promoting R6 `時時開心` and R8 `翠紅`.

## Overfit Assessment

The direction is promising, but the union was assembled after examining the component diagnostics. It therefore has selection bias and is not ready for automatic live ranking changes.

Recommended gate before activation:

- Run the rule unchanged in shadow mode on future meetings.
- Require at least 30 additional races and at least 5 actual triggers.
- Require cumulative helped-minus-harmed to remain positive.
- Reject if it removes two rank-2 winners before producing three additional rank-3 winner promotions.
- Keep odds and market data excluded from scoring.

Until that gate is passed, the safest product treatment is a separate `Top 2 challenger` shadow flag rather than changing the official two recommendations.
