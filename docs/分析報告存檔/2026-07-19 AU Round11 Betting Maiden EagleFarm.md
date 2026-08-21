# AU Wong Choi — Round 11: Betting ROI / Maiden / Eagle Farm R9 (2026-07-19)

Answers to Kelvin's investigative questions #3, #4, #5.

## #4 — Eagle Farm 2026-05-30 R9 (Magic Millions Helen Coughlan Stakes, 2yo fillies)

**We still spot it — Savagery Vibe ($71 winner) is ranked #2.** Actual finish:
1. Savagery Vibe $71 · 2. She's Got Pizzazz $13 · 3. Poster Girl $8.
Current model top-4: **#1 Poster Girl (3rd), #2 Savagery Vibe (1st)**, #3
Paradise City, #4 Cigar Flick. Two of three placegetters in the top-2.

**What we did right on the $71 winner** — its feature profile:
`consistency 100 · sectional 74 · pace_figure 75 · trainer 71` overriding
`rating 47 · form 54` (the market's low view → $71). The heaviest dimension
(stability 0.299) rewarded consistency, and the sectional/pace signals said it
was running fast times. This is the model's core thesis working exactly as
designed: **sectional + consistency finding ability the market underrates.**
Nothing in the upgrades broke this — it survives the facts-refresh, draw fix,
and going refresh.

**The one we now miss:** She's Got Pizzazz (2nd, $13) sits at #9 — strong
sectional (86) but weak pace_figure (53) and lower consistency (78). She is a
sectional-strong / pace_figure-weak profile; the model trusts pace_figure over
raw sectionals here. Given Round-10 showed pace_figure can mislead, she is a
genuine edge case, not a clean fix.

## #5 — Maiden plates: precise diagnosis, but the obvious fix fails

Quantified on 106 maiden races. Lightly-raced (≤2 starts) + good-trial (>65)
horses = 296:
- when the model ranks them top-4 → **52% finish top-3** (vs ~30% base): when
  the model backs them it is very right;
- **47 finished top-3 but were ranked outside top-4** — profile trial 83 (!),
  consistency 58, form 60. Exactly Kelvin's observation.

Structural root cause: **trial evidence is only 0.88% of ability**
(pace_perf 0.188 × trial 0.047), while stability (form+consistency, which need
race history) is 30%. A debutant with a strong trial gets neutral/low
stability — the model treats "no track record" as "weak track record."

**But the maiden-specific trial-boost candidate FAILS** (walk-forward, 65
maiden OOS races): every boost level makes the maiden cohort *worse*
(top1 32%→25%, W-in-T3 62%→57% at boost 0.30). Reason: of the high-trial light
horses ranked >4, **72% do NOT place** — boosting the group promotes more
losers than winners. And the maiden cohort is already the model's *strong*
cohort (W-in-T3 61.5%, Top1 32.3%, both well above archive 52.9% / 22.6%).

**Real conclusion:** `trial_score` is too coarse (a binary-ish threshold
can't separate the 47 winners from the losers). The fix is not re-weighting —
it needs a **sharper trial-quality signal**: trial winning margin, trial
sectional/L600 time vs the trial-field, trial-to-race class context. That is
an extraction-side upgrade (richer trial data), which ties directly to #6.

## #3 — Profitable betting? One real lead, needs forward validation

Flat $1 win bets at SP across 710 archive races, by model rank × confidence
tier:

| Strategy | Bets | Strike | ROI |
|---|---:|---:|---:|
| **tight-tier rank 1** | 249 | 21.7% | **+16.8%** |
| clear-tier rank 1 | 126 | 35.7% | +1.0% |
| ALL rank 1 | 710 | 23.9% | −3.2% |
| medium-tier rank 1 | 335 | 21.2% | −19.7% |
| ALL rank 2 | 710 | 15.6% | −11.5% |

**tight-tier rank-1 is the lead**: in competitive races (top1–top3 ability gap
<2) the market is unsure, so the model's top pick goes off at a longer price
(winner median SP 4.3) than its 21.7% win rate justifies.

Robustness: positive in BOTH date halves (+7.4% first, +26.1% second) — not
one lucky streak. BUT bootstrap 95% CI = **[−15.9%, +53.5%]**, which includes
zero. So: **promising and theory-consistent, not yet confirmed.** Do not bet
real money on 249 samples; paper-trade it forward, and it is exactly the kind
of edge that Betfair exchange pricing (#6, no bookmaker margin) would widen.

clear-tier rank-1 (+1.0%, 35.7% strike) is the other bankable type — barely
positive at SP, likely clearly positive at Betfair prices.
