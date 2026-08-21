# Results — 2026-08-10 · first_set_winner's filter, win_a_set's sides, a fitted hold model

Three questions, in the order they were asked. Every ROI below comes from
`scripts/replay_prop_strategy.py`'s pipeline — the source database is never
written, the tracker is cleared, all 44 stored market dates are priced and
settled in order, and `earliest_odds=True` keeps in-running prices out. The
A/B harness reproduces the reference replay exactly (1,754 settled bets,
+7.79%) before any variant runs.

The chronological split is **2026-07-30**, the same one the audit's holdout
used.

---

## 1. first_set_winner's value filter

### The premise was wrong, and finding out how cost a bug

The brief said Sportsbet offers first_set_winner on 583 matches, we price 568
props and flag 32, so 536 are rejected by our own value filter. Counting them
by tier says something different:

| tier | priced | flagged as value |
|---|---|---|
| ITF | 429 | **0** |
| UTR | 28 | **0** |
| CHALLENGER | 54 | 10 |
| TOUR | 44 | 9 |

**457 of the 555 priced props (82%) are in tiers the system does not stake at
all** — ITF and UTR were excluded on measured model-vs-market skill, not by the
value filter, and no loosening of `ValueProfile` can reach them. The value
filter's actual job is over 98 props, and it passes 19 of them.

### The value filter could not be loosened, because it was never being read

The first A/B — raise `max_odds` from 2.25 to 4.0 — returned numbers *identical
to the baseline*, down to the last settled bet. The cause:

`price_head_to_head` is the one pricer handed Sportsbet's own market key rather
than one it synthesised. Sportsbet calls the first-set market `winner_related`,
and `family_for_market` only resolves that to `first_set_winner` when the market
NAME ("Set 1 Winner") is passed too. Looked up by key alone it returns
`winner_related`, which is in no profile table, so the family silently took
`DEFAULT_VALUE_PROFILE` — and any entry registered for `first_set_winner` was
ignored.

It was invisible because the default was also what it wanted. The only way it
surfaced was an A/B that changed nothing.

Four market keys resolve differently with and without their name
(`winner_related`, `set_betting`, `total_games`, `game_handicap`); the other
three reach `value_profile` through keys the pricer synthesised, so this was
the only live instance. Both facts are now pinned by tests.

### With the filter actually connected

| `max_odds` | FSW settled | FSW ROI | train | holdout | whole replay ROI | drawdown |
|---|---|---|---|---|---|---|
| 2.25 (was) | 30 | +15.80% | +25.55% (11) | +10.16% (19) | +7.79% | −57.97u |
| 3.25 | 49 | +18.35% | +47.25% (16) | +4.33% (33) | +7.95% | −57.97u |
| **4.00 (shipped)** | 58 | +12.40% | +24.00% (19) | +6.74% (39) | +7.81% | −57.97u |

**ROI dilutes, and does not collapse.** Nearly doubling the sample costs 3.4pp
of headline ROI and leaves the held-out window positive (+6.74% against
+10.16%). The rest of the board is untouched: the whole-replay ROI moves by
0.02pp and the drawdown not at all, because `first_set_winner` is
RESEARCH_ONLY — these are paper bets whose only job is to accumulate evidence,
which is exactly what the loosening was for.

The 3.25 setting has the best headline. It is also the one whose training
window is a 16-bet +47% streak, and that is the number in this table least
worth believing.

**Lowering `min_edge` does nothing.** Replaying it is not worth a run: applying
the filter arithmetic directly to the stored model, market and odds for every
priced side, taking `min_edge` from 0.04 to 0.01 gains the bettable-tier
universe **one** settled prop (which lost). The edge floor is not what is
binding; the odds ceiling is, and it rejects 395 of the 623 priced sides.
`max_odds` 2.75 was not replayed either — it sits between two measured points
and the offline marginal band for (2.25, 2.75] is 14 props at +4.65%.

### Why the ceiling stops at 4.0

Past 4.0 the model is not finding value, it is disagreeing with the book. The
eight settled props above that price carry model probabilities of 0.37–0.55
against market-implied 0.17–0.23 — disagreements of 25 to 37 points — and they
went **0 for 8**. Eight bets prove nothing on their own; the reason to exclude
them is the one already written into `daily.py` for the UTR exhibition that
opened this system's first recommendation: *a 35-point disagreement with the
book is a modelling failure far more often than an edge.* The 0-for-8 is
corroboration, not the argument.

### The ceiling had to bring `min_probability` with it

`min_probability` is read by `meets_formal_profile` — which decides what counts
as evidence — and ignored by `is_value_selection` — which decides what gets
staked. Raising the ceiling alone therefore produced a family that stakes every
prop from 1.30 to 4.00 and counts only those under 1.72 (1/0.58) as evidence:
58 bets, 19 of them visible to the gate, at +24.37%, too few to bootstrap, and
**graduated to EARLY_MAIN on that subset**.

That is the exact failure the `ValueProfile` docstring already describes from
the other direction — the pricer and the gate judging different populations —
and it only surfaced on the final end-to-end run. At `min_probability = 0.0`
the gate sees all 58 at +12.40% with P(ROI ≤ 0) = 0.21 and correctly keeps the
family RESEARCH_ONLY.

**Shipped: `ValueProfile(max_odds=4.0, min_probability=0.0)` for
`first_set_winner` only.**

---

## 2. player_win_a_set — over side only

A/B'd end to end rather than assumed. Against the hold model that was shipped
when the diagnosis was written, it does everything the diagnosis predicted:

| | both sides | over side only |
|---|---|---|
| `player_win_a_set` settled | 370 | **221** |
| ROI, whole record | **+13.08%** | +8.62% |
| ROI, train | +19.71% (262) | +9.09% (154) |
| ROI, **holdout** | **−3.02%** (108) | **+7.53%** (67) |
| whole-replay ROI | +7.79% | +6.69% |
| whole-replay drawdown | −57.97u | **−47.01u** |
| gate tier reached | PROBE (1u) | **EARLY_MAIN (0.5u)** |

The headline gets worse and everything that decides whether to trust it gets
better: the two windows go from disagreeing in sign to agreeing within 1.6pp,
the drawdown falls by 11 units, and the recent window turns from −1.6% to
+10.4%, which is what moves the family off PROBE.

The whole-replay ROI falls 1.1pp because 149 bets that were profitable on the
earlier window are removed. That is the cost, and it is worth paying: those are
the bets the later window says stopped working.

**Shipped.** Section 3 tests it against a different hold model and finds it
stops helping there — but that model is not the one that ships, and the note
is recorded at the end of section 3 rather than acted on.

---

## 3. Machine learning on the hold estimate

`props/hold_model.py` was a rolling average plus two weights (0.35 on the
returner's return-points rate, 0.04 on an Elo gap), each fitted by a grid
search over one column. It now has a ridge regression over the whole
serve/return profile, fitted by `scripts/fit_hold_ml.py` on **59,804
walk-forward matches** and exported as plain coefficients.

### The measurement problem, and how it is handled

A single match's realised hold rate is roughly ten Bernoulli trials. Over the
held-out window that binomial noise accounts for **46.8% of the variance in
the target**, which is why S2's exit test read "real and worthless": mean
absolute error against a quantity that is half noise moves in the third
decimal whatever the model does. Scoring against the floor instead says what
share of the *achievable* variance each model captures.

Trained through 2026-05-09, scored on 5,536 matches from 2026-05-11 to
2026-08-03 — the window that has never been fitted on:

| | MAE | RMSE | share of achievable variance | P(no improvement vs rolling) |
|---|---|---|---|---|
| rolling average | 0.13875 | 0.17629 | 8.1% | — |
| hand-set weights | 0.13761 | 0.17452 | 11.7% | 0.000 |
| **fitted ridge** | **0.13095** | **0.16678** | **27.0%** | **0.000** |
| boosted tree (measured, not shipped) | 0.13059 | 0.16665 | 27.2% | 0.000 |

The gradient-boosted tree was fitted and is **not shipped**: it scores within
0.003 of the ridge on every population large enough to read, and it would cost
the daily path numpy and scikit-learn at runtime plus a pickled artifact to
version. A dict of floats costs nothing.

The gain holds on every population, split rather than pooled:

| population | n | rolling | hand-set | fitted |
|---|---|---|---|---|
| ATP_250 | 828 | −0.009 | +0.017 | **+0.165** |
| ATP_500 | 302 | +0.211 | +0.250 | +0.263 |
| CHALLENGER | 3,616 | −0.001 | +0.033 | **+0.217** |
| GRAND_SLAM | 534 | +0.353 | +0.503 | **+0.628** |
| clay / grass / hard | 3,388 / 1,106 / 1,042 | +0.038 / +0.050 / −0.058 | +0.069 / +0.116 / −0.013 | +0.234 / +0.234 / +0.145 |
| server has 5–14 matches | 898 | −0.091 | −0.080 | **+0.261** |

(share of achievable variance; the hand-set model is at or below zero on four
of these — it is not distinguishable from a league constant there.)

### What the coefficients say about the hand-set version

| term | hand-set | fitted |
|---|---|---|
| returner's return points won | −0.35 | **−0.750** |
| opponent-quality Elo gap | −0.04 | −0.085 |
| server's first-serve points won | not used | +0.349 |
| server's second-serve points won | not used | +0.186 |
| server's own hold rate | 1.00 (the baseline) | +0.209 |

Both hand-set weights were pointed the right way and set to roughly **half**
the size the data supports, and the two strongest serve columns were not read
at all — the model's own hold rate carries less weight than its first-serve
points won.

### Surface is deliberately absent

Surface one-hots added +0.0024 of explained variance. They also train on
history rows, which carry a surface 99.9% of the time, and would serve on
fixtures, where `tournament_levels` resolves one for 70% of the priced board.
Blanking surface on a model fitted with it drops the score from 0.272 to
**0.161** — worse than useless. A feature the serving path cannot supply
faithfully trains on one distribution and predicts on another, so it is not in
the feature set. `serve_return_profile` already narrows its own window by
surface where a player has the matches for it.

### Effect on the board

On the 580 priced fixtures where both sides resolve a hold, the fitted model
moves the hold **gap** by more than 0.02 on 412 of them (5th–95th percentile
−0.080 to +0.089). This is not a rounding change.

### And then the replay, which says no

Four full replays, one variable at a time, `first_set_winner` pinned at its
2.25 ceiling in all four so the section-1 change cannot contaminate this:

| whole-replay ROI | hand-set hold | fitted hold |
|---|---|---|
| **whole record** | **+7.79%** (1,754) | **+4.96%** (1,672) |
| earlier window (to 2026-07-29) | +10.40% (1,401) | +5.14% (1,336) |
| later window (from 2026-07-30) | −2.57% (353) | +4.28% (336) |
| max drawdown | −57.97u | −45.07u |

The later window turns from losing to profitable, and that is the tempting
number. **It is not the right one here**, and the reason is specific to this
change: the coefficients were fitted on data ending 2026-05-09, so *both*
windows are already out of sample for them. There is no contaminated window to
discount — the usual argument for reading the holdout and ignoring the rest
does not apply, because the thing being tested never saw either. Over all
1,754 bets the fitted estimator is worse by 2.8pp.

### Per-bet, the mechanism is unambiguous

Comparing the two runs prop by prop rather than as two averages:

| | n | hand-set | fitted |
|---|---|---|---|
| props **both** variants stake | 1,475 | +8.64% | +8.64% — outcome differs on **0** |
| only the hand-set model stakes | 279 | +3.32% | — |
| only the fitted model stakes | 197 | — | −22.54% |

Stakes are flat, so a changed probability changes nothing at all unless it
changes **selection**. Every unit of difference between the two replays comes
from the 476 props where the two models disagree about whether there is value.

And that disagreement's sign reverses between the windows:

| | earlier window | later window |
|---|---|---|
| props only the hand-set model stakes | +13.45% (223) | −37.03% (56) |
| props only the fitted model stakes | −29.82% (158) | +6.97% (39) |

A difference that is strongly negative in 2.5 months and strongly positive in
the following 11 days, on 39 and 56 bets, is not an edge that one window
happened to hide. **`USE_FITTED_HOLD = False`.**

Extending the fitted estimator to `player_total_games` as well — which the
unification in the next section does automatically — makes it worse again:
that family goes +4.36% to −3.05% and the whole replay to **+2.95%**. Three
families, three chances to help, and the whole-record number falls each time.

### One definition of the hold, found by the estimator changing

`player_total_games` came back **bit-identical** between the first two
variants, while every other games family moved. It should not have: it is
priced from the same simulator. `_serve_based_player_games` was building its
own hold estimate with the hand-set weights hard-coded, so `daily.py` held two
definitions of "the hold for this match" and only one of them was under the
flag. It now reads `_holds_for` like everything else — a no-op while the flag
is off, and the reason the fitted model's third family showed up at all.

This is the same defect class as the odds snapshots, the feature snapshots and
the result rows: a quantity with more than one definition. Fixed the same way —
one function, everyone calls it.

### Why a better estimator can select worse bets

`is_value_selection` reads one number: how far the model's probability sits
from the market's. A hold model that is closer to the truth is, on a market
priced at 5–8% takeout by people with the same serve statistics, also closer to
the market — so it disagrees in *different places*, not in better ones. The
selection layer has no way to prefer a well-founded disagreement over a
badly-founded one of the same size, and that, not the estimator, is what the
44 dates measured.

The model, its coefficients, its fitting script and its tests are kept and
wired behind the flag rather than deleted. It is the right estimator; the value
filter is what cannot use it.

### What this does to section 2

The side restriction was diagnosed against the hand-set hold model and it
survives, because that is the model that ships. For the record, under the
fitted hold it stops helping — `player_win_a_set`'s later window goes +5.93%
(both sides) to +1.45% (over only) — which is consistent with the under side
being a 2-0-sweep price and therefore the outcome most sensitive to the hold
estimate. Two changes that each repair the same symptom are substitutes, and
only one of them is shipping.

---

## What shipped

| change | evidence |
|---|---|
| `price_head_to_head` takes the caller's family | `first_set_winner` could not be given a ValueProfile at all |
| `_serve_based_player_games` reads `_holds_for` | two definitions of "the hold for this match" in one file |
| `first_set_winner` `max_odds` 2.25 → 4.0 | 30 → 58 settled paper bets, +15.80% → +12.40%, later window still +6.74% |
| `player_win_a_set` over side only | later window −3.02% → +7.53%; drawdown −57.97u → −47.01u |
| fitted hold model, **flag off** | better estimator (11.7% → 27.0% of achievable variance), worse betting (+7.79% → +4.96%) |

---

## End state, replayed

Everything above, together, against where the day started:

| | before | shipped |
|---|---|---|
| settled value bets | 1,754 | 1,633 |
| whole-record ROI | +7.79% | +6.72% |
| earlier window | +10.40% (1,401) | +8.44% (1,301) |
| later window | −2.57% (353) | **−0.02%** (332) |
| max drawdown | −57.97u | **−47.01u** |

| family, whole record | before | shipped |
|---|---|---|
| `first_set_winner` | 30 @ +15.80% | **58** @ +12.40% |
| `player_win_a_set` | 370 @ +13.08% | **221** @ +8.62% |
| everything else | — | unchanged |

| gate | before | shipped |
|---|---|---|
| `player_game_handicap` | EARLY_MAIN | EARLY_MAIN |
| `player_set_handicap` | EARLY_MAIN | EARLY_MAIN |
| `player_win_a_set` | **PROBE** (1u) | **EARLY_MAIN** (0.5u) |
| `first_set_winner` | RESEARCH_ONLY, 30 bets, P(loss) 0.18 | RESEARCH_ONLY, **58** bets, P(loss) 0.21 |

The headline ROI is 1.1pp lower and every property that decides whether to
believe it is better: the later window is flat instead of losing, the drawdown
is 11 units smaller, `player_win_a_set` is staked at half the size on the half
of itself that works in both windows, and `first_set_winner` accumulates
evidence at nearly twice the rate without being staked on it.

---

# Part two — what the diagnosis found

Three follow-ups to the section above: the game-handicap hole, a prop-level
score for the fitted hold, and whatever the two of them turned up. They turned
up more than was asked for.

## The chronological holdout is a surface split

Before any of it. The two windows used throughout part one:

| window | Clay | Grass | Hard |
|---|---|---|---|
| earlier, to 2026-07-29 (1,301 bets) | 37.9% | 37.7% | 13.3% |
| later, from 2026-07-30 (332 bets) | 7.2% | **0%** | **73.5%** |

The tour runs clay → grass → hard, so **a date split in tennis is a surface
split**. Every "worse earlier, better later" reading in part one has to be
re-read as "worse on clay and grass, better on hard", and at least one of them
changes meaning when you do.

The audit already recorded this exact trap for ITF — "a chronological split
here compares two different strategies, not one strategy over time" — and it
recurred on surface without anyone noticing.

**Re-reading the fitted hold model with it.** Split by surface rather than by
date, on the props each variant stakes and the other does not:

| surface | props only the hand-set model backs | props only the fitted model backs |
|---|---|---|
| Clay | −11.51% (100) | **−41.17%** (61), P(ROI ≤ 0) = 1.00 |
| Grass | +29.30% (65), P = 0.008 | **−33.24%** (60), P = 0.99 |
| Hard | +13.83% (75) | +9.63% (50) |

It is not better anywhere. The later window flattered it because that window is
three-quarters hard court, and hard court is where it merely does no harm.
`USE_FITTED_HOLD = False` stands, on a better reason than the one recorded
above.

## The simulator makes matches too competitive

Feeding the model's own holds into the simulator and comparing to what
happened, on 996 settled matches:

| | actual | simulated | gap |
|---|---|---|---|
| finish in two sets | 60.9% | 55.2% | **+5.7pp** |
| total games, Clay | 23.27 | 24.15 | −0.88 |
| total games, Grass | 24.21 | 24.31 | −0.09 |
| total games, Hard | 23.19 | 24.33 | **−1.14** |
| games given two sets | 19.28 | 19.62 | −0.34 |
| games given three sets | 29.60 | 29.84 | −0.24 |

Conditional on the number of sets the game counts are nearly exact, so the
defect is the **mix**, not the level: the simulator does not produce enough
one-sided matches. The shortfall is the same size on clay (+4.7pp), grass
(+4.5pp) and hard (+4.2pp).

**Stage 3 passed this simulator because it checked the wrong thing twice.** It
compared `hold_a = hold_b = 0.75` — the one matchup with no favourite to
under-back — against "the settled record's mean match total, 25.16". Measured
today that record is **22.49** over 1,954 completed best-of-three matches, and
22.92 over the bettable tiers. 25.16 belonged to some other population. Third
instance today of a check and its subject looking at different populations.

**The fix is one parameter and it generalises.** The missing ingredient is that
the hold estimate is an estimate: on the day one player is better or worse than
their rolling profile, and that dispersion is what makes blowouts common. One
shift per match, drawn once, applied antithetically so the gap moves and the
total does not. Fitted to the straight-sets rate on 454 matches before
2026-07-15 and scored on the 542 after, it takes the rate from 0.552 to 0.613
against an actual 0.609 — **and corrects the total-games bias it was not fitted
on, from −1.17 to −0.17 games.** Over the whole record all three surfaces want
the same value, 0.06, independently.

**And it does not help the props.** `player_win_a_set` Brier over 728 settled
props: 0.2097 at σ=0, 0.2084 at σ=0.06, P(no better) = 0.43. The same on every
surface. Which makes sense once stated plainly: the shift makes blowouts
commoner without saying *whose*. It is a variance correction, and a prop like
"does this player take a set" needs a ranking one.

`HOLD_GAP_DISPERSION = 0.0`, with the fitted 0.06 kept beside it. The corrected
stage-3 test stays either way — it was wrong about its target regardless.

## min_edge was set below the vig

The one change that worked, and it is not a model change.

ROI rises monotonically with the size of the model's disagreement, over the
1,633 settled bets of the shipped configuration:

| edge band | n | ROI | earlier | later |
|---|---|---|---|---|
| **0.04–0.08** | 381 | **−3.17%** | +1.58% | −22.57% |
| 0.08–0.15 | 572 | +6.62% | +3.60% | +19.46% |
| 0.15–0.25 | 428 | +9.74% | +14.82% | −7.60% |
| 0.25+ | 251 | +16.50% | +19.19% | +5.93% |

The marginal band is the lowest in **both** windows and the worst band in four
of the five families with enough bets to read, so this is not one cohort picked
after seeing its result. And it has an arithmetic mechanism rather than a
story: these markets run 5.3–7.8% overround, which is 2.65–3.9pp of vig per
side, so a 4pp disagreement leaves between 0.1 and 1.4pp of edge before the
model is wrong about anything. `0.04` was a global default; it was never a
number derived from what these markets cost.

| replayed | whole record | later window | drawdown |
|---|---|---|---|
| min_edge 0.04 | +6.72% (1,633) | −0.02% | −47.0u |
| **min_edge 0.06** | **+8.16%** (1,452) | **+2.33%** | **−44.5u** |

And it holds at every simulator setting tried beside it — +6.72→+8.16 at σ=0,
+7.00→+9.21 at σ=0.06, +6.10→+8.45 at σ=0.07 — so it is not an artefact of one
pricing path.

## The pattern, stated once

| change | is the model more accurate? | does it make money? |
|---|---|---|
| fitted hold model | **yes**, 11.7% → 27.0% of achievable variance, every population | no, +7.79% → +4.96% |
| simulator dispersion | **yes** on moments, no on props | no, drawdown worse in every pairing |
| min_edge 0.04 → 0.06 | unchanged | **yes**, +6.72% → +8.16% |

Two accuracy improvements, both blocked. One selection-rule change, immediately
effective. `is_value_selection` reads one number — how far the model sits from
the market — and against a book pricing the same statistics at 5–8% takeout, a
more accurate model is a *closer* one. Accuracy has no route into profit
through a rule that only rewards disagreement.

That is where the next work is, and it is not in the models.

---

## End state, replayed

| | session start | after part one | now |
|---|---|---|---|
| settled value bets | 1,754 | 1,633 | **1,449** |
| whole-record ROI | +7.79% | +6.72% | **+8.03%** |
| earlier window | +10.40% | +8.44% | +9.48% |
| **later window** | **−2.57%** | −0.02% | **+2.33%** |
| max drawdown | −57.97u | −47.01u | **−44.5u** |
| P(ROI ≤ 0) | 0.002 | 0.0035 | **0.0005** |

Later window, by family — the window nobody had looked at when the day started:

| family | session start | now |
|---|---|---|
| `player_game_handicap` | −10.07% (121) | **−3.81%** (107) |
| `player_win_a_set` | −3.02% (108) | **+6.94%** (64) |
| `player_total_games` | +4.22% (89) | +6.63% (76) |
| `first_set_winner` | +10.16% (19) | +5.39% (33) |

Every family with volume improves out of sample, on 17% fewer bets, and the
held-out window is positive for the first time. It is still one window, it is
still three-quarters hard court, and `player_game_handicap` — the family
carrying 47% of the stakes — is still losing in it. That is the next thing.

---

# Part three — the last population nobody had split

`_holds_for` returns None whenever either player lacks a usable serve profile,
and every games/sets family then falls back to the closed forms the serve plan
was written to replace. The two paths had never been scored apart.

| path | n | ROI | earlier | later | P(ROI ≤ 0) |
|---|---|---|---|---|---|
| simulator | 1,251 | **+10.12%** | +11.22% | +5.81% | 0.000 |
| closed form | 198 | **−5.12%** | −1.33% | −21.07% | 0.734 |

The closed form is the losing half in three of the four families with volume,
on both tiers, and on three of four surfaces:

| family | simulator | closed form |
|---|---|---|
| `player_game_handicap` | +11.45% (590) | −5.66% (98) |
| `player_win_a_set` | +15.30% (170) | −8.67% (40) |
| `first_set_winner` | +33.97% (30) | −13.57% (21) |
| `player_total_games` | +2.28% (355) | +4.42% (39) |

**The argument is not that −5.12% is significant.** On 198 bets it is not —
P(ROI ≤ 0) = 0.734. It is that the closed form was *already measured* to be the
weaker predictor before any of these ROI numbers existed: stage 4 scored it out
of sample on 357 held-out `player_total_games` props at Brier 0.2554 and AUC
0.5224 against the simulator's 0.2485 and 0.5742. The split just says that
difference reaches the money, with a 15pp contrast that is consistent across
families, tiers and surfaces.

Same shape of decision as ITF: excluded on measured model skill, ROI observed
afterwards rather than used to choose the slice. Pricing and logging continue
so the path can earn its way back if the serve corpus ever covers it.

**`STAKE_CLOSED_FORM_FALLBACK = False`.**

One bug found on the way in: `player_exact_set_score` sits inside the same loop
and has no `holds` of its own, so gating it the same way would have read
whatever the first-set block left behind — a different match's answer to a
different question. It is priced from the match probability either way and is
left ungated, with the reason written where the temptation is.

## End state

| | session start | part two | now |
|---|---|---|---|
| settled value bets | 1,754 | 1,449 | **1,250** |
| whole-record ROI | +7.79% | +8.03% | **+10.06%** |
| earlier window | +10.40% | +9.48% | +11.03% |
| **later window** | **−2.57%** | +2.33% | **+6.23%** |
| max drawdown | −57.97u | −44.5u | −47.6u |
| P(ROI ≤ 0) | 0.002 | 0.0005 | **0.000** |

Later window by family: `player_win_a_set` −3.02% → **+16.48%** (52),
`player_total_games` +4.22% → +8.48% (73), `first_set_winner` +10.16% →
+30.44% (18), `player_game_handicap` −10.07% → **−4.13%** (98).

Two things to say plainly about that table.

**`first_set_winner` graduated, on 30 bets.** Removing its 21 closed-form bets
leaves 30 at +33.97%, recent window +27.72%, P(ROI ≤ 0) = 0.0525, and the gate
opens it at EARLY_MAIN and 0.5u. Checked rather than assumed: 30 distinct
props over 30 matches and 15 dates, 18 wins at mean odds 2.38, largest single
bet +2.60u and largest single day +2.48u — a real 60% hit rate against a 42%
implied, which is two standard errors on 30 bets. Honest, thin, and staked at
half size, which is what the EARLY_MAIN tier is for.

**Drawdown went up**, −44.5u to −47.6u, while ROI improved. Staking a new
family adds variance before it adds evidence. Worth watching rather than
worth reversing.

**`player_game_handicap` is still losing out of sample** — −4.13% over 98 held-out
bets, on the family carrying 47% of the stakes. It is better than the −10.07%
the day started with and it is not yet fixed.
