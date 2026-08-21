# Stop rule — pre-registered 2026-08-11, before the first bet

This exists because of one line in the plan: *fix both numbers now, so neither is
decided in the middle of a losing run.* A stop chosen while losing is not a stop,
it is a mood. Everything here is committed before any money moves.

Implemented in code as `props/strategy.py` constants and evaluated by a tested
checker, not only described here:
`LIVE_STOP_DRAWDOWN_UNITS`, `LIVE_REVIEW_AFTER_SETTLED`,
`LIVE_INTERIM_CHECK_SETTLED`, `LIVE_INTERIM_MIN_ROI`. Check the live state with:

```
PYTHONPATH=src .venv/bin/python scripts/check_stop_rule.py --since YYYY-MM-DD
```

`YYYY-MM-DD` is the first day money was actually staked. It is required: without
that boundary the command would read the fitted paper record and call it live
evidence. The checker returns exit 0 for CONTINUE, 2 for PAUSE, 3 for STOP and
4 when the 200-bet written review is due.
It does **not** place, cancel or disable bets by itself; Kelvin acts on its verdict.

The checker reads only `prop_live_bets`: bets Kelvin explicitly records after
placing them manually. It never assumes every `prop_tracker` recommendation was
acted on. Record an already-placed bet with:

```
PYTHONPATH=src .venv/bin/python -m tennis_wc.cli record-live-prop-bet \
  --prop-id ID --odds PRICE --stake-aud 0.50
```

This command cannot contact a bookmaker or place a wager.

## What is being staked

Two families, from 2.1: `player_win_a_set` and `first_set_winner`. Everything
else — including `player_game_handicap`, which is half of all exposure — is held
back. Both are EARLY_MAIN, so the cap is **0.5u = A$0.50 AUD per bet**. Kelvin
fixed **1u = A$1.00 AUD** on 2026-08-13.

## 1. Hard stop: −20u / A$20 cumulative, at 0.5u stakes

The checker returns STOP and everything stops. No re-sizing, no "one more day", no switching families to
recover it. The number was chosen against the noise, not picked round.

**How deep can a book that has NO edge dig, by luck alone?** Simulated at 0.5u
flat, 6,000 runs per cell, at each family's own typical price:

| horizon | median | 5th pct | −15u fires | −20u fires | −25u fires |
|---|---|---|---|---|---|
| 100 bets @1.90 | −5.0u | −10.3u | 0.3% | 0.0% | 0.0% |
| 200 bets @1.90 | −7.3u | −14.6u | 4.3% | **0.5%** | 0.1% |
| 200 bets @2.40 | −9.3u | −18.3u | 12.8% | **2.8%** | 0.4% |
| 400 bets @2.40 | −13.1u | −25.9u | 37.8% | 16.2% | 6.1% |

So −10u is unusable: a break-even book hits it 25–43% of the time over 200 bets,
and a stop that fires on "not winning yet" is the same as not starting. −20u
fires on luck 0.5–2.8% over the first 200 bets, which is the horizon that
matters.

**And it is far outside what these two families have ever done.** Their own worst
peak-to-trough in the whole record is **−17.82u at flat 1u = −8.91u at 0.5u**, on
426 settled bets over 39 days. The stop is 2.2× that.

**Note on the existing per-family limit.** `MAX_FAMILY_DRAWDOWN_UNITS = −25.0` is
measured on the *research book*, which stakes a flat 1u on every logged prop — a
different and larger quantity than the live 0.5u book. Both stay. They are not
the same number and must not be compared.

`check_stop_rule.py` made exactly that mistake in its first version: it read the
paper record's −18.27u, which is a flat-1u figure, and compared it against this
−20u, which is a 0.5u figure — so a book that had actually dug −9.13u in live
terms read as one bet away from being shut down. It now prints which book it is
in, scales when the mean stake is not the live cap, and a test asserts the
relationship rather than leaving it to a comment.

## 2. Re-judge the whole thing at 200 settled bets

Not "when it feels wrong". 200 is where the question becomes answerable: to
separate a true +15% ROI from 0 at 95% confidence needs n ≈ (1.96 × 1.0 / 0.15)²
≈ 171 bets at a per-bet standard deviation of about one stake unit. 200 gives
margin.

At the replay's rate for these two families — 200 value bets over 44 dates, ~4.5
a day — that is roughly **six weeks**.

At 200 settled bets, all three of these get answered in writing:

1. ROI, with a bootstrap `P(ROI ≤ 0)`, **split by family and by surface**. Never
   pooled: the record's own chronological split is a surface split (38% clay /
   38% grass before 2026-07-30, 74% hard after), and a pooled average has hidden
   an opposite result inside it every time it has been trusted here.
2. CLV on the live bets. It is the only pre-result signal, and it needs the
   18:00 pass to have re-priced — CLV is structurally zero on the morning pass
   because the bet's own price is the last one seen at that moment.
3. Whether the live bets agree with the replay. They are the **only** genuinely
   out-of-sample evidence that exists: five selection changes were fitted on the
   44-day record, so no slice of it is validation any more.

## 3. Interim tripwire at 100 settled bets: pause, not stop

If ROI is below **−10%** at 100 settled bets, staking pauses and the cause is
looked for before continuing. This is not the hard stop — it is the checkpoint
that stops a mechanical fault (a broken price lookup, a mis-oriented selection,
a market renamed) from being mistaken for variance for six weeks. A break-even
book is below −10% ROI at 100 bets about 15% of the time, so this will
occasionally fire on noise; that is acceptable for a pause whose only cost is a
day of reading.

## What would make me widen the allowlist

`player_game_handicap` comes back only on evidence that was not fitted to the
44-day record: **80+ live settled bets on it, positive, with `P(ROI ≤ 0) ≤ 0.10`,
positive on hard courts specifically** — because hard is where it lost (−4.13%
over the later window) and hard is what the next months are.

Not before. It carries half the exposure, and putting half the book on the half
that loses out of sample is how a positive backtest becomes a negative account.
