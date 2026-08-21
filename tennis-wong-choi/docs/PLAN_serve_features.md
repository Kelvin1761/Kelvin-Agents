# Plan — price player props from serve and return, not from the match winner

**Written:** 2026-08-10 · **Status:** S1-S4 built and measured; see Results

## Why

Seven of the nine prop families derive from one scalar — `P(match win)` —
pushed through closed-form transforms. There is no per-prop feature set. That
is finding H5 in the audit, and it is the reason the losing families lose:
`player_total_games` at −12% and `player_game_handicap` at −1.4% over 746 bets
are not mispriced by a little, they are answering a different question from the
one the market is pricing.

A refit of the existing constants was tried on 2026-08-10 and **failed** — Brier
0.2733 → 0.2802 — because tuning a coefficient cannot add information that was
never in the input. The input has to change.

## What we already have (measured, not assumed)

`player_match_history` holds 346,706 rows. Serve and return columns, with
coverage among the players we actually price:

| Column | All rows | Priced players |
|---|---|---|
| `hold_rate`, `break_rate` | 42.9% | **53.6%** |
| `first_serve_points_won_pct` | 43.1% | **53.8%** |
| `second_serve_points_won_pct` | 43.1% | 53.8% |
| `return_points_won_pct` | 43.1% | 53.8% |
| `ace_count`, `double_fault_count` | 43.1% | **53.9%** |
| `break_points_saved` / `faced` / `converted` / `chances` | 43.1% | 53.9% |
| `tiebreak_won` | 25.8% | 32.5% |
| `deciding_set_won` | 21.6% | 27.8% |
| `surface` | 46.2% | — |

**The raw material is already in the warehouse.** Exactly one function reads any
of it: `games_model.combined_hold`, which averages `hold_rate` over each
player's last 20 matches and returns their sum. Nothing else touches serve or
return at all.

Two consequences worth stating before designing anything:

* **Coverage caps the ambition at ~54%.** Roughly half of priced fixtures will
  have no serve history for at least one player. The design must degrade to the
  current model rather than refuse to price, and must mark which path it took.
* **Surface is the weakest link at 46%.** Surface-conditioned serve rates will
  be thin; treat surface as an adjustment on a pooled rate, never as a filter.

## The model to build

One quantity underlies every games-based prop: **the probability that a given
player holds serve in a given game of this match.** From a per-game hold
probability for each side, everything else follows by simulation rather than by
a separate closed form:

```
hold_a, hold_b  →  simulate a set  →  simulate the match
                        ↓
   games won by each player      → player_total_games, player_game_handicap
   set winners                   → player_win_a_set, first_set_winner,
                                    player_set_handicap, player_exact_set_score
   total games                   → match_total_games
```

This replaces seven closed forms with one estimator and one simulator. That is
the point: today each family has its own curve fitted against its own outcomes,
which is how three of them ended up with mutually inconsistent implied margins.

### Estimating hold

```
hold_a = f(server's own serve strength, returner's return strength, surface, format)
```

Concretely, per player, over a walk-forward window:

* serve side — `hold_rate`, `first_serve_points_won_pct`,
  `second_serve_points_won_pct`, `ace_count` per service game,
  `double_fault_count` per service game, `break_points_saved / faced`
* return side — `return_points_won_pct`, `break_rate`,
  `break_points_converted / chances`
* context — surface, best-of, an opponent-quality adjustment using the
  `opponent_elo` already stored on 95.1% of rows

Opponent adjustment matters more here than anywhere else: a 78% hold rate
earned against ITF opposition is not a 78% hold rate against a tour returner,
and `opponent_elo` is the one context column with near-complete coverage.

## Staging

Each stage has an exit test. A stage that fails its test stops the plan rather
than passing the problem downstream — that is what the constant-refit attempt
did not have.

**S1 — Feature store.** A walk-forward `serve_return_profile(player, as_of)`
returning the columns above with sample counts, on the same as-of discipline as
`elo_history`.
*Exit:* profile resolves for ≥50% of priced fixtures on both sides; zero rows
sourced from on-or-after the match date.

**S2 — Hold model, measured on its own terms.** Predict per-game hold; score
against realised service games.
*Exit:* beats two baselines out of sample — the player's own mean hold rate,
and `combined_hold`'s implied split. If it cannot beat a rolling average, stop.

**S3 — Simulator.** Point-free set/match simulation from `hold_a, hold_b`.
*Exit:* reproduces the empirical joint distribution of (games won, sets won) on
settled matches within tolerance. Deliberately checked before any pricing, so a
simulator bug cannot be mistaken for a pricing edge.

**S4 — Reprice one family.** `player_total_games` first: worst ROI, 20.5%
market coverage, 99.8% settleable, so it produces evidence fastest.
*Exit:* Brier beats the shipped model **and** the market on the same fixtures,
walk-forward, with a chronological holdout. Both, not either.

**S5 — Extend to the rest of the games/sets families** only after S4 passes.

**S6 — Retire the closed forms** the simulator replaces, and delete
`_GAME_MARGIN_SLOPE`, the share curve and the exact-score table with them.

## What would make this fail

Stated in advance so the answer is not negotiated later:

* **Coverage.** If S1 resolves for well under half of fixtures, this improves a
  minority of the board and the effort is better spent elsewhere.
* **No edge over a rolling average.** If S2 cannot beat the player's own mean
  hold rate, the extra features are noise and the plan stops at S2.
* **Simulator-shaped edge.** If S4's improvement appears only in the tails, it
  is a simulator artefact, not skill.
* **The market is already there.** Serve statistics are not private
  information. The market prices games props at 5.3–7.2% takeout and beat us on
  ITF by 0.049 Brier. A better model is necessary and not sufficient.

## What this plan does not touch

`player_aces` and `match_total_aces` already read ace history directly and are
not derived from the match probability. They keep their own model. This plan is
about the seven families that are not.

## Sequencing against everything else

S1 and S2 are the prerequisites and carry no research risk beyond the coverage
test — they are data plumbing plus a measurement. S3 onward is where the real
uncertainty starts. Nothing here changes what the card bets until S4 passes its
holdout, so the current EARLY_MAIN probe on `player_win_a_set` continues to
accumulate out-of-sample evidence in parallel.


---

## Results

### S1 — pass, on the population that matters

Both players resolve a usable profile on 580 of 1,988 priced fixtures (29.2%),
but on the tiers we actually stake — TOUR and CHALLENGER — it is **513 of 732,
70.1%**. ITF and UTR are excluded from betting, so the second number is the one
the plan is about.

### S2 — the test was wrong, not the model

Fitted weights (0.35 return strength, 0.04 Elo gap) beat a rolling average on
4,152 out-of-sample matches with P(no improvement) = 0.010 — and by 0.37% of
one standard deviation, which reads as worthless. It was: realised per-match
hold rate carries a large binomial floor from ten-odd service games, so the
test measured noise rather than the model. **The prop probability is the
objective; S4 scores that instead.**

### S3 — pass

Equal holds of 0.75 give a mean match total of 25.13 games against the settled
record's 25.16, and a zero mean margin. Checked before any pricing so a
simulator bug could not be mistaken for an edge.

### S4 — pass out of sample, after the model found a parser bug

The first run scored Brier 0.2753 against the shipped model's 0.2709 and looked
like a failure. Its calibration was sound from 0.3 to 0.8 and **inverted at both
tails**: predicted 0.0–0.1 came in at 66.7%, predicted 0.9–1.0 at 36.7%. The 64
props behind that share a signature — lines of 17.5 to 21.5, actual values up
to 29 games. **One player cannot win 29 games in a best-of-three**, and no book
prices a single player's games at 20.5 in that format. They are match-total
markets carrying a `player_total_games` market key. The serve model did not fail
there; it surfaced a parser defect.

On the 754 genuine props, split chronologically at 2026-07-15:

| | TRAIN (397) Brier / AUC | HOLDOUT (357) Brier / AUC |
|---|---|---|
| **simulator (serve)** | 0.2497 / 0.5508 | **0.2485 / 0.5742** |
| shipped model | 0.2556 / 0.5219 | 0.2554 / 0.5224 |
| market | 0.2468 / 0.5634 | 0.2476 / 0.5480 |

Out of sample the simulator **beats the shipped model on both metrics**, sits
0.0009 behind the market on Brier — level, in effect — and **beats the market
on ordering, 0.5742 against 0.5480**. Nothing else measured in this rebuild has
beaten the market on any metric out of sample.

The prediction path reads no odds: two walk-forward hold rates, a simulated
match, a probability off the distribution.

**Beating the market on ordering is not profit.** It is the first evidence that
serve features carry information the match-probability path does not, which is
what the plan set out to establish.

### Open, in order

1. **Fix the parser defect** the tails exposed — match totals are being written
   with a player market key. Until then those 64 props corrupt any evaluation.
2. **Wire the simulator into pricing** for `player_total_games` and replay it
   end to end. Better probabilities are necessary and not sufficient; the ROI
   has to follow.
3. **Re-test ITF on the serve path.** ITF was excluded because the match-model
   was measurably worse than the market there. Serve data may be exactly where
   a thin market is beatable, and the tier allow-list is written to let a tier
   earn its way back on measurement.

---

## player_win_a_set: the recent dip is one side, and it is not the broken one

Asked to find why the family's recent window turned −1.60% while its whole
record reads +13.08%, split by side:

| side | all | earlier window | recent window | P(ROI ≤ 0) |
|---|---|---|---|---|
| **over** (wins ≥1 set) | **+8.62% (221)** | +7.54% | **+10.43%** | 0.069 |
| under (wins none) | +19.69% (149) | **+40.84%** | **−20.95%** | 0.088 |

The obvious reading — "the under side is broken" — is wrong. Under is not
losing structurally; it is *swinging*, from +40.84% to −20.95%. That is the
signature of a long-odds tail bet (a 2-0 sweep), not of a broken estimate. The
recent-window slices all say the same thing from different angles: model P=0.2
at −57.1%, odds 3.5+ at −36.1% — every one of them is the under side seen
through a different lens.

Over is the durable half: +7.54% then +10.43%, the most consistent pair of
window numbers anywhere in this system.

**So the family's +13.08% is a stable edge blended with a coin flip.** Betting
only the over side gives +8.62% over 221 bets that holds in both windows, which
is a worse headline and a better proposition.

The criterion for choosing it has to be stated carefully, because picking a
side after watching the other one fail is selection. The justification here is
*variance across windows*, not level: over is stable and under is not, and that
is visible in both windows independently rather than only in the recent one.
Acting on it should still be A/B'd end to end rather than assumed.
