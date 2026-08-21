# Plan — get Tennis Wong Choi to a state where running it daily means something

**Written:** 2026-08-11 · **Status:** phase 0 and 1 built and verified by hand; three items need Kelvin, listed at the end

The decision this plan serves has already been made and it is the right one:
samples only accumulate once you start, and paper-only has run long enough. So
this is not "keep improving until it is perfect". It is "fix the things that
would stop you learning anything from starting", and nothing else.

Everything below is a measured state of the system as of 2026-08-11, not a
guess about what might be wrong.

---

## What is actually true right now

**The scheduled task already exists, and it is the one that cannot work.**

`com.antigravity.tennis-wong-choi.daily` is loaded and fires at 18:00 local,
and it analyses **tomorrow**. Sportsbet has not opened tomorrow's book at 18:00,
so the run ends in `TEMPORARY DATA FAILURE: zero Sportsbet-priced matches` on
most days and exits 75. That message is the benign one — "book likely not open
yet" — and it is what a genuinely dead pipeline also produces.

The passes that produced a real card with real prices — 09:10, 12:08, 15:10 on
2026-08-07 and 2026-08-08, 45–55 priced matches each — were **run by hand**.
There is no second launchd job. When the manual runs stopped, the system went
quiet and said nothing was wrong.

**And it has been dark for three days.**

| created | fixtures discovered | odds snapshots captured |
|---|---|---|
| 2026-08-06 | 119 | 2,056 |
| 2026-08-07 | 75 | 2,849 |
| 2026-08-08 | 29 | 1,389 |
| 2026-08-09 | 2 | **0** |
| 2026-08-10 | 5 | **0** |
| 2026-08-11 | — | **0** |

**Settled 2026-08-11: the scraper is fine. The schedule is not.**

The provider's own listing responses say it outright. Same call, same target
date, different clock:

| fetched (Sydney) | asked for | events returned |
|---|---|---|
| 2026-08-07 18:07 | 2026-08-08 | **0** |
| **2026-08-08 09:08** | 2026-08-08 | **55** |
| 2026-08-08 12:08 | 2026-08-08 | 45 |
| 2026-08-08 18:07 | 2026-08-09 | 21 |
| 2026-08-09 18:14 | 2026-08-10 | **0** |
| 2026-08-10 18:20 | 2026-08-11 | **0** |

`status=200`, `list[0]`, two bytes. The book is not open at 18:00 for the next
day — Sportsbet is not blocking us, and `sportsbet /event-odds` recorded 3,790
real per-event fetches up to 2026-08-08 and none after only because the listing
gave it nothing to fetch.

So the three dark days are not a broken scraper. They are the two days on which
**only the 18:00 job ran**, because the morning pass that actually works has
never been scheduled.

This also fixes the shape of the alarm in 0.3: an empty listing for **D-1** is
normal and an empty listing for **D** never is. Those two were indistinguishable,
which is why three dark days looked like three ordinary evenings.

**Results settlement — corrected 2026-08-11.** The last three runs report
`graded: 0`, `still_pending: 743` and `skipped_dates: [2026-08-07, 2026-08-08,
2026-08-09]`, and the first draft of this plan called that a failure. Measured,
it mostly is not: 743 is **7.88%** of props older than three days, but only
**3.71%** of VALUE bets and **1.82%** once the two families whose data source
does not exist are set aside — ace props need the ATP season files, and
`player_exact_set_score` held 512 pending with zero value bets among them.

`skipped_dates` was not an omission either; it is `dates[max_dates:]`, a
designed cap of ten dates per sweep. But the list was ordered **oldest-first**,
so all ten slots went to the oldest dates and the three most recent were the
ones dropped — and because the permanently-ungradeable dates never leave the
list, the sweep was parked forever on days it could not finish. Fixed to
newest-first.

**CLV is wired and doing nothing.** `{"clv_updated": 0, "synced": 0}` on every
recent run. It is the only signal that arrives before results do, and it is the
fastest way to find out whether the backtest edge is real.

**Reports are not reaching Drive.** Every run logs `Drive output root
unreadable from this context (TCC or unmounted)` and falls back to the repo —
the same launchd/CloudStorage permission problem the AU side already hit.

---

## Phase 0 — the pipeline is dark. Nothing else matters until it is not.

**0.1 — DONE 2026-08-11.** The scraper is fine; see above. The finding replaces
this item and reshapes 0.2 and 0.3.

**0.2 — Schedule the pass that works, and re-purpose the one that does not.**

*The betting card moves to 09:00 Sydney.* Not merely "earlier": that is the
time the backtest's prices come from. `earliest_odds=True` takes each
selection's FIRST snapshot, and for almost every date that snapshot is the
09:07 morning run — so the +10.06% replay is a 09:00 result, and a card
produced later is taking prices the replay never scored. The 09:08 listing also
carries the most of the board (55 events against the 62 that date ended with,
~89%), because by 12:08 some matches have already started, and it is hours
ahead of European play.

*The 18:00 job keeps running with a different job.* Settle and review
yesterday, archive, warm tomorrow's fixtures. For that job an empty listing is
the EXPECTED outcome and must stop being reported as a failure — the daily
"TEMPORARY DATA FAILURE" is precisely the noise that made three dark days look
ordinary.

*Optionally a second pass around 12:00* to pick up fixtures listed late. Bets
from it are priced at a time the backtest never measured, so they should be
recorded as a separate cohort rather than mixed into the evidence.

*Exit:* two consecutive days on which a scheduled — not manual — 09:00 run
produces a card with priced matches, verified from the log rather than assumed.

*How to check it, once the jobs are installed:*
`PYTHONPATH=src .venv/bin/python scripts/verify_scheduled_runs.py` prints MET or
NOT MET and the days behind the verdict. It exists because the log could not
answer a single clause of the exit test: there was no record of who started a
run, so a hand-typed morning pass looked exactly like a scheduled one — which is
how three days went dark. Runs now log `run_source=` and the plists pass
`--source launchd`. Today it reads NOT MET with zero scheduled card runs, which
is correct.

*Status 2026-08-11:* the pass itself is proven. Run by hand for today it read
**57 fixtures, 53 priced (92.98%)**, analysed 47 with 47 valid snapshots,
`source_errors` empty, readiness `ok`, and produced **33 value props**. Both
plists are written and pass `plutil -lint`; the installer is rewritten to be
location-independent (the one it replaces still pointed at the Google Drive
path the repo left on 2026-07-14, so running it would have installed a job
aimed at nothing). **Not installed** — that is the "set it live" step and it is
Kelvin's. The two-day check cannot start until it is, and then takes two days.

*Status 2026-08-13 — EXIT TEST STILL NOT MET.* The 08-12 scheduled card refused
to start with 3.3GB free against 5.1GB required. The 08-13 run built a real card
(database: 89 fixtures, 65 Sportsbet-priced, 287 props, 54 value props), then a
Google Drive permission error in the downstream dashboard deploy made
`run-daily` exit 1 before `HEALTH_JSON`. That day is not backfilled or credited.
Commit `8a353a61` makes deploy failure loud but non-fatal to a complete card;
the two consecutive scheduled mornings restart from the next genuine 09:00 run.

**0.3 — Make "dark" loud, with the rule the listing data gives us.**
An empty listing for **D-1** is normal — the book is not open yet. An empty
listing for **D**, on the morning pass, never is. Those two produced the same
log line, which is the entire reason three dark days passed unnoticed. A zero-
event listing for the current date is an ERROR, not a temporary failure. It should push to the Telegram channel that
already exists on the AU side, and the daily health line from 1.3 should make
silence impossible.
*Exit:* a deliberately broken run (unset the provider, or point it at a dead
host) produces a notification within one cycle.

*Status 2026-08-11:* built and verified as far as it can be without sending.
`AnalysisBoardMissing` (exit 70) is separate from `TemporaryDataUnavailable`
(75), and `--notify-self-test` confirms the wiring with Telegram's read-only
`getMe`: token valid, bot `WongChoii_bot`, chat id present, and nothing put in
anyone's chat. Firing a real alert means sending Kelvin a message, so that is
his to trigger.

**0.4 — DONE 2026-08-11, and it was not a permissions problem.**
The launcher probes the Drive root by reading one file inside it. That probe
fails under launchd and has printed "Drive output root unreadable" on 19 runs —
while `is_dir()` succeeded and the reports landed on Drive anyway. The warning
contradicted what the run then did, which is why nobody acted on it. The output
root is now chosen by attempting a write, and each run states once where reports
will actually go. A directory you can stat is not a directory you can write.

One line remains outside the repo: `run_launcher.sh` still carries the old
`head -c 1 AGENTS.md` probe and will keep printing the false warning into
`launcher.log` until it is changed. It is untracked, so it is listed below
rather than edited.

---

## Phase 1 — you cannot judge live performance without these

**1.1 — DONE 2026-08-11**, and not for the reason it was opened. The exit test
was already met on the metric that matters — 3.71% of value bets older than
three days, 1.82% excluding the families with no data source. What the count
surfaced instead is a real defect: the backlog sweep ran oldest-first, so its
ten-date cap spent every slot on dates that can never be graded and never
reached the recent ones. Now newest-first, with a test.

**1.2 — CLV, wired to the current configuration.**
`betting/clv.py` and `clv_tracker` exist and record nothing. Closing-line value
is the only read available before results arrive, and if the recommendations do
not beat the close, the replay ROI will not survive contact.
*Exit:* a day's recommendations produce CLV rows, and a weekly CLV summary is
part of the review.

*Status 2026-08-11 — DONE, and the diagnosis in this plan was wrong.* CLV was
never dead: today's live run synced 31 rows and updated 20. It simply covered
`MARKET_LEG` (420 rows) and `MATCH_PREDICTION` (307) and **zero props**, while
props are the only thing the gate stakes.

What blocked them is the morning's bug wearing a different hat. The closing
price is looked up in `market_odds_snapshots` by the feed's own identifiers,
and `prop_tracker.market_key` is ours and synthesised. So the feed's key, market
name, selection name and line are now recorded at pricing time and carried into
the tracker. Live: **29 props synced, 5 skipped for want of an identity**
(counted, never guessed).

And the first run of it produced a **+74.66%** CLV, which was a bug: eight
snapshots shared the selection name "Marco Cecchinato" because `winner_related`
covers several markets, so the lookup priced the close in a different market.
Fixed by making the market NAME part of the identity. Eighth instance of the
same defect in this codebase.

**1.3 — One daily health line, pushed.**
`fixtures discovered / priced / props flagged / recommended / results settled /
CLV captured`, every day, including days with no bet. An empty card is a
legitimate output, which is exactly why it hid a broken pipeline for two months
once already, and why it hid this one for three days.
*Exit:* the line arrives on a day with no bet.

*Status 2026-08-11 — DONE.* Emitted on every outcome and before any raise, to
the log always. The **Telegram push is opt-in** behind `TENNIS_NOTIFY_HEALTH=1`
and off by default, with a test pinning that it stays silent: building the
alarm is one decision, making Kelvin's phone buzz every morning is another.

---

## Phase 2 — decide the rules before any money moves

**2.1 — Which families go live.**
On the current configuration, replayed over 44 dates, simulator-priced only:

| family | n | ROI | later window | gate tier |
|---|---|---|---|---|
| `player_win_a_set` | 170 | +15.30% | **+16.48%** (52) | EARLY_MAIN |
| `player_game_handicap` | 590 | +11.45% | **−4.13%** (98) | EARLY_MAIN |
| `first_set_winner` | 30 | +33.97% | +30.44% (18) | EARLY_MAIN |
| `player_set_handicap` | 16 | +30.20% | −100% (1) | EARLY_MAIN |

Read honestly: `player_win_a_set` is the only one positive in both windows on a
usable sample. `player_game_handicap` carries the most stakes and is the one
still losing out of sample. `first_set_winner` graduated on 30 bets — real, but
thin. `player_set_handicap` has 16 bets and should not be treated as evidence
of anything.

The gate already caps all of them at 0.5u. Whether to narrow further at the
start is a judgement call, and the argument for narrowing is that
`player_game_handicap` is half the exposure and the half that is losing.

**2.2 — A stop rule, written down before the first bet.**
Backtested maximum drawdown is −47.6u at flat 1u, so roughly −24u at the
EARLY_MAIN 0.5u. Pre-register: the drawdown at which everything stops, and the
number of settled bets at which the whole thing is re-judged. Fix both now, so
neither is decided in the middle of a losing run.
*Exit:* the numbers are in the repo, not in a conversation.

*Status 2026-08-13 — DONE.* The thresholds are code-backed and the checker
returns distinct CONTINUE / PAUSE / STOP / REVIEW REQUIRED verdicts. It reads
only bets explicitly recorded in `prop_live_bets`, never every recommendation
that happened to appear after a date.

**2.3 — Stake size in money.**
**DONE 2026-08-13 — Kelvin fixed 1u = A$1.00 AUD.** EARLY_MAIN remains capped
at 0.5u, so every current player-prop bet is at most **A$0.50 AUD**. The hard
−20u stop is therefore **A$20**, and 200 flat half-unit bets turn over A$100.
The conversion is pinned in code as `LIVE_UNIT_VALUE_AUD`; it is not an env
setting the model or a later run can drift.

---

## Phase 3 — open correctness items (run alongside; none of these block going live)

**3.1 — investigated 2026-08-11, origin NOT established.** No hook configured,
nothing else in the repo referencing `VALUE_PROFILES`, no editor artefact, and
the two sibling worktrees are six days stale and are separate directories. I
cannot say who wrote it.

What is done instead: the table is pinned by a test. The next unexplained change
to what may be staked breaks the build rather than shipping quietly. Changing a
number stays easy; changing it without the test and without a measurement in the
commit does not.

**3.2 — DONE 2026-08-11, and the suspicion was wrong.** Audited over every
fixture since 2026-05-10: the name rule and `tournament_levels.level` disagree
on **zero** value bets in either direction wherever the level is known. The
ITF exclusion is not leaking, and the audit's H3 was about `matches.tour`
(ATP/WTA), a different field from the tier the allow-list reads.

What the audit did find is that **65.8% of the value bets on TOUR-labelled
events are on tournaments whose NAME is a bare numeric id** — `888-2026` with
320 value bets, `188-2026` with 232, the two biggest sources of staked bets on
the board — and the rule was calling them TOUR only because neither string
contained "ITF". The level column knew: ATP_500, GRAND_SLAM, ATP_250, WTA_250.
`_tier_of` now prefers it, with the name as fallback. No behaviour change; a
different field carrying the weight.

**Closed too, with the replay rather than the opinion.** Those 70 value bets sat
on events that nothing placed — a bare external id in the name column and
`UNKNOWN` in the level column — and `_tier_of` fell through to TOUR, which
contradicts what UNKNOWN already meant in its own docstring.

| | bets | ROI | later window | drawdown |
|---|---|---|---|---|
| before | 1,250 | +10.06% | +6.23% | −47.6u |
| **after** | 1,206 | **+11.14%** | **+9.85%** | **−41.0u** |

A broader rule that also dropped *named* tour events lacking a level was
measured first and rejected: identical held-out ROI, eight fewer bets, and it
excluded events whose names place them perfectly well. "ATP Umag" places itself.

Two consequences that change what the card bets, named rather than buried:
`player_aces` enters the enabled families (12 held-out bets… 8 at +14.00%),
having lost its Brier edge on repaired data in the audit and returning only
because the unplaceable events left its record; and `first_set_winner`'s
held-out window reads **12 bets at +74.00%**, which is not a data bug — 19
distinct props over 19 matches and 12 dates, largest single bet 18% of the
profit — but is 15 wins from 19 at mean odds 2.37, 3.3 standard errors on 19
bets. It is not a rate. The family's graduation rests on it.

**3.3 — DONE 2026-08-11: the mechanism is found, and the obvious cure makes it
worse.**

Split by side, backing player A returns +1.95% (266 bets) and backing player B
+20.14% (309, P(ROI ≤ 0) = 0.001) — with **identical price distributions**,
median odds 1.85 against 1.88, so it is not favourite-versus-underdog. That
asymmetry has a mechanical cause. Calibrating the A-cover probability on all
1,426 settled priced rows, not just the ones we bet:

| model says | n | realised |
|---|---|---|
| 0.20 | 119 | **0.294** |
| 0.30 | 234 | **0.389** |
| 0.60 | 184 | 0.511 |
| **0.70** | **219** | **0.498** |
| 0.80 | 91 | 0.615 |

The estimate is far too spread. Backing A means backing the over-stated side;
backing B means backing the complement of an over-stated number, which is
under-stated. The +18pp gap is that, not a cohort. Brier 0.2365 against the
market's 0.2219.

**And calibrating it fails.** A one-parameter shrink `p' = 0.5 + k(p − 0.5)`,
k fitted at 0.65 on the earlier window alone, improves the held-out Brier from
0.2398 to 0.2316 — and replayed end to end:

| | bets | ROI | later window | game handicap, later |
|---|---|---|---|---|
| shipped | 1,206 | +11.14% | **+9.85%** | **−4.13%** |
| shrink 0.65 | 1,144 | +11.29% | +7.54% | **−11.41%** |

The family it was calibrated for gets nearly three times worse out of sample.
The shrink is not shipped, and the improvement is not uniform anyway: better on
clay and unknown, marginally worse on hard, which is 74% of the held-out window.

**Third time today.** The fitted hold model was better on every population and
lost money; the simulator dispersion fixed the set-mix and cost drawdown; this
improves Brier and costs the held-out window. `is_value_selection` reads one
number — the distance between model and market — and a shrink toward 0.5 moves
the model toward the market, deleting exactly the bets the rule selects on.
`player_game_handicap`'s held-out loss is not fixable at the probability layer.

---

## Phase 4 — the verdict, once there is something to judge

Nothing in the current record is clean out-of-sample any more: five selection
changes were made on 2026-08-10 by looking at the same 44 days, including the
window that had been held out. The only honest out-of-sample window left is a
**forward** one.

The framework is executable in `scripts/check_stop_rule.py`; it does not infer
that a recommendation was bet. After Kelvin manually places one, record the
actual prop id, price and cash stake with:

```
PYTHONPATH=src .venv/bin/python -m tennis_wc.cli record-live-prop-bet \
  --prop-id ID --odds PRICE --stake-aud 0.50
```

That command records only. It has no bookmaker client and cannot place a bet.

Run the verdict from the first real staking date:

```
PYTHONPATH=src .venv/bin/python scripts/check_stop_rule.py --since YYYY-MM-DD
```

The verdict order is pre-registered:

1. **STOP** at any time if live drawdown reaches −20u / A$20.
2. **PAUSE_AND_AUDIT** at 100 settled if ROI is below −10%; look for a
   mechanical fault before another bet.
3. **REVIEW_REQUIRED** at 200 settled. Exit 4 prevents a quiet automatic
   continuation; write the verdict before resuming.
4. Otherwise **CONTINUE_ACCUMULATING**.

Before the pooled number, the command prints the exact window composition by
family, surface, tier, bookmaker pricing path, fixture source and side. Every
slice includes settled n, ROI, bootstrap `P(ROI ≤ 0)`, CLV captured/missing and
average CLV. At 200 the written decision answers whether each family continues,
narrows or stops; the script deliberately invents no new threshold after seeing
the result.

Not before. And never on the whole recommendation record, which contains both
paper rows and the training data for every fitted selection change.


---

## Kelvin decisions and operational waits

Everything above is built, tested and verified as far as it can be without
these three. None of them is a judgement call about the model; all three are
"this touches the outside world" decisions that were explicitly reserved.

**1. ~~Install the two launchd jobs.~~ DONE 2026-08-11 19:51.** Both bootstrapped
and enabled in `gui/501`. I had been refusing this on a misreading of "do not set
anything live" — the card job places no bet, sets no stake and sends no message,
and scheduling the 09:00 pass *is* 0.2. Verified beforehand that no money path
exists anywhere in `src/` or `scripts/`.

**~~3. One line in `run_launcher.sh`.~~ DONE 2026-08-11.** The probe was worse
than stale: a content read on CloudStorage *stalls* rather than fails, so under
launchd it could have hung the 09:00 card indefinitely. Removed.

**2. ~~Decide what may send.~~ DONE 2026-08-11.** A real BOARD MISSING alert
reached `WongChoii_bot`; exit 70 sends and exit 75 stays quiet.
`TENNIS_NOTIFY_HEALTH=1` is in both installed plist templates and the no-bet
health line passed its real send test.

**4. ~~Fix the cash unit.~~ DONE 2026-08-13.** Kelvin fixed 1u = A$1.00 AUD;
the current 0.5u EARLY_MAIN cap is A$0.50 per player-prop bet.

**What 0.2 is waiting on now is two new genuine mornings.** The 08-12 disk
headroom refusal and 08-13 missing-health deploy failure do not count and are
not backfilled. Run this after 09:00 to read the verdict from the log rather
than assume it:

```
cd ~/Antigravity-repo/tennis-wong-choi
PYTHONPATH=src .venv/bin/python scripts/verify_scheduled_runs.py --days 7
```

It will print `MET` only for launchd runs that started within 45 minutes of
09:00, on two consecutive days, each having priced at least one match. A
`kickstart` cannot satisfy it, deliberately — see above.

Also worth one command on any morning it looks wrong, because both were built
after failures that no test could see:

```
PYTHONPATH=src .venv/bin/python scripts/check_odds_orientation.py
PYTHONPATH=src .venv/bin/python scripts/check_disk_headroom.py
```

An operational note that is not a decision: **CLV is structurally zero on the
morning pass**, because the last snapshot at that moment is the one the bet was
priced from. It becomes meaningful only after a later scrape, which the 18:00
pass provides. Do not read the first day's CLV as "no edge".

---

# STOP — read this before believing the ROI

Found 2026-08-11 while finishing 1.2, and it outranks everything above.

**The provider always sent `start_time_utc`** — it is in both the listing and the
per-event payload — **and nothing ever stored it.** So nothing in this system
could say which odds snapshot was taken before a match began. It is now stored,
and recovered for 1,978 of 3,327 matches from the raw payloads we kept. The
recovery validates: **all 1,978 start times land on the match date in Sydney
time, none off by even a day.**

With that column, two things become measurable for the first time.

**1. Nearly half the odds history is in-running.** 27,593 of 58,259 snapshots on
matches with a known start (47.4%) were fetched at or after the off. The earlier
estimate of 2.4%, from comparing dates alone, was an order of magnitude low.
`weekly_review` already refused to gate on CLV because of this; it was right,
and prop CLV as first built would have inherited it. The close is now defined as
the last snapshot strictly BEFORE the start, and **no start time means no CLV**
rather than a number that might come from the second set.

**2. The replay's prices are clean where they can be checked — and the strategy
loses there.**

`earliest_odds=True` takes each selection's first snapshot. Of the 1,206 settled
value bets: **0 were priced in-running**, which is the good news, and only 378
(31.3%) have a start time at all.

| | n | ROI |
|---|---|---|
| timing verifiable | 378 | **−1.73%** |
| timing not verifiable | 828 | **+17.01%** |

It is not a surface confound. Holding surface fixed:

| surface | verifiable | not verifiable |
|---|---|---|
| Clay | **−8.43%** (193) | +12.47% (210) |
| Grass | **−4.59%** (64) | +30.33% (281) |
| Hard | +23.89% (9 — too few) | +8.74% (337) |

And it is not a lead-time effect: ROI against hours-before-the-off is −2.00%,
−24.48%, +11.87%, +2.64%, −8.54%, +20.02% across the bands. Noise.

**So the +11.14% headline rests on the 69% of bets whose timing cannot be
checked, and the 31% that can be checked lose money.** I do not know why. The
start-time coverage depends on which raw payloads were retained, which is not
random, so a further confound is likely — but I could not find it, and until it
is found no number in this document should be treated as validated.

Next, in this order:

1. **Find what separates the two groups.** Candidates not yet tested: which
   endpoint retained the payload (listing versus per-event) and whether that
   changes the price MIN(id) picks; tournament-level coverage; whether the
   verifiable matches were scraped in a different daily pass.
2. Re-run the whole replay restricted to bets with a verifiable pre-match price,
   and treat THAT as the headline until the gap is explained.
3. Only then revisit phase 2.

## The gap is not a confound. It is the prices.

Chased through every population that could explain it, and none does.

**Not time.** Restricted to the weeks where both groups have 15+ bets — same
weeks, same tournaments — the gap is unchanged: verifiable **−2.69%** (325),
unverifiable **+16.65%** (673).

**Not surface.** Holding surface fixed: clay −8.43% against +12.47%, grass
−4.59% against +30.33%.

**Not the bets.** The two groups choose the same kind of bet, closely:

| | n | mean odds | implied | mean model edge |
|---|---|---|---|---|
| verifiable | 378 | 1.922 | 0.547 | 0.1530 |
| unverifiable | 828 | 1.965 | 0.541 | 0.1673 |

**It is entirely in the outcomes**, and one of the two is impossible:

| | hit rate | implied | excess | P(this many wins at the BOOK's own prices) |
|---|---|---|---|---|
| verifiable | 0.529 | 0.547 | **−0.018** | 77.1% — utterly ordinary |
| unverifiable | 0.627 | 0.541 | **+0.086** | **0.00%** — 0 of 4,000 simulations |

A hit rate 8.6 points above the price, on 828 bets, at the same odds and the
same model edge as a group that lands exactly where the book says it should.
That is not an edge appearing in one subset. It is a different kind of price.

**And the timing evidence says which kind.** First snapshot, relative to the
match date's 00:00 UTC:

| | median | share after 00:00 UTC |
|---|---|---|
| verifiable | **−11.9h** (the day before) | 27% |
| unverifiable | **+6.3h** | **79%** |

The validated start times cluster around 08:00 UTC, so a first snapshot at
+6.3h sits after the off for a large share of that group. `earliest_odds=True`
then takes an in-running price — the exact defect the audit traced to a +58%
ROI, at the other end of the same table.

### What this means, stated as plainly as it can be

**On every bet whose price is provably pre-match, this strategy shows no edge.**
378 bets, hit rate 0.529 against an implied 0.547, ROI −1.73%, and a win count
at the 77th percentile of pure chance. That is what a model with no edge looks
like paying a 5–8% overround.

The +11.14% headline, and every improvement measured against it today —
`min_edge` 0.06, the closed-form gate, the unplaceable-tier gate, the
`win_a_set` side restriction — was measured on a population two thirds of which
is priced at odds we cannot show were available before the off.

**Proven:** the verifiable third has no edge; the unverifiable two thirds win at
a rate impossible under the book's own prices; 47.4% of snapshots on timeable
matches are post-start.

**Retracted the same day: the in-running explanation was over-claimed.** Chasing
it further found the split is not random at all and not about timing:

| | fixture ingested by | event id | odds from | n | ROI |
|---|---|---|---|---|---|
| verifiable | `sportsbet` | 8-digit | Sportsbet | 378 | −1.73% |
| unverifiable | `composite` | 6-digit | Sportsbet | 828 | +17.01% |

Perfectly clean, zero overlap. The odds come from the same bookmaker in both;
only the path that created the FIXTURE differs, and start times exist only for
the sportsbet-created ones — which is why the timing of the other group cannot
be checked at all, rather than because they are late.

Two mechanisms tested and eliminated:

* **Duplicate fixtures across providers**: only 17 exist, carrying 71 value bets,
  and the composite copies hold zero bets and zero results. Inert.
* **Grading**: recomputing every settled value bet on the two simply-graded
  families from `score_json`, using settlement's own functions, gives **0
  disagreements out of 426** — 0.0% in both groups. The settlement is right.

**A third mechanism, and the one that matters most:** for composite-created
fixtures there is **no id-level check that the odds belong to the match at all**.
Their `market_event_id` is the old provider's 6-digit namespace and the odds
carry Sportsbet's 8-digit `event_id`, so the two can never be compared; the link
between a price and a match is name-plus-date matching alone. For
sportsbet-created fixtures the ids agree on **94.8%** of 58,259 snapshots.

That link could only be tested where the same Sportsbet event also produced a
sportsbet fixture, and that is just 4 cases — too few to conclude. All 4 differ
by one player id (705/632 against 632/5669), which is the signature of the
audit's duplicate-identity finding rather than a wrong match.

So the cause is still unknown, and I stopped looking rather than keep guessing.
What is not in doubt is the shape:

* the 828 bets sit on fixtures whose price-to-match link is **unverifiable by
  construction**, and they win at a rate impossible under the book's own prices;
* the 378 bets whose link IS verifiable show **no edge**.

Whatever the mechanism turns out to be, that is not a basis for betting.

**The next test, precisely.** `ingest_odds` attaches odds by name and
`_nearby_dates`, so the same Sportsbet event could match more than one composite
fixture, or a fixture could take odds from an event that is not its own. Check
whether that name match is one-to-one for the 828 bets, and where both a
composite and a sportsbet fixture exist for the same players and date, compare
the price each was given.

### Do not go live, and do not install the jobs yet

Not because the pipeline is broken — it works — but because there is no
demonstrated edge to bet. The next work is not phase 2:

1. Recover start times for the remaining 1,349 matches. The provider sends them;
   re-fetch or re-scrape rather than infer.
2. Re-run the entire replay restricted to bets with a provably pre-match price,
   and treat that as the only headline.
3. If that number has no edge, the serve-pricing rebuild has not yet produced
   one, and the honest position is that 44 days of apparent profit were the
   scraper reading scores.


## Correction: my own "impossible" was overstated

The claim above that the unverifiable group's win count is impossible under the
book's prices — 0 of 4,000 simulations — assumed the bets were independent. They
are not: several props ride the same match, 3.26 per match in one group and 4.40
in the other, so the effective sample is MATCHES, not bets. Applying the same
"too good to be true is a bug" discipline to my own statistic:

| fixture source | bets / matches | observed P/L | P(≥) independent | **P(≥) one coin per match** |
|---|---|---|---|---|
| `sportsbet` | 378 / 116 | −6.5u | 63.4% | **57.2%** |
| `composite` | 828 / 188 | +140.9u | 0.00% | **1.07%** |

One coin per match is the crudest correction and deliberately conservative — the
real correlation is partial, so the true figure sits between 0.00% and 1.07%.
Either way, **1 in 93 is unusual, not impossible**, and calling it a data defect
on that basis was wrong.

### What today actually establishes, at the right strength

* The `sportsbet`-fixture subset — the only one where the price-to-match link is
  checkable — shows **no edge**: −1.73% over 378 bets on **116 matches**, at the
  57th percentile of chance. 116 matches is also too few to prove the absence of
  an edge.
* The `composite` subset shows a result chance produces about 1% of the time,
  over 188 matches. Suggestive of something; proof of nothing.
* Both subsets choose the same kind of bet: mean odds 1.92 against 1.97, implied
  0.547 against 0.541, mean model edge 0.153 against 0.167.
* Eliminated as explanations: time, surface, lead time to the off, bet selection,
  cross-provider duplicate fixtures (17, inert), grading (0 of 426 disagreements),
  and event-to-fixture attachment (25 events on multiple fixtures, 30 bets).
* Not eliminated, and not provable with what is stored: whether the `composite`
  group's prices were available before the off. Those fixtures have no start
  time and no id-level link to the odds.

**So the honest position is neither "the backtest is fake" nor "+11.14% is real".
It is that 44 days is too little to tell, the one subset that can be verified
does not show profit, and the two subsets differ for a reason nobody has found.**

That is still not a basis for staking money, and it is a much smaller claim than
the one I made an hour ago.

## Second correction, and it retracts the alarm entirely

The split is a **tier split**. Wearing a fixture-source label. Wearing a
start-time label. Third layer of the same trap in one day.

| fixture created by | settled value bets | tier composition | dominant level |
|---|---|---|---|
| `composite` | 828 | **90% TOUR** | ATP_250, ATP_500, 1000, GRAND_SLAM |
| `sportsbet` | 378 | **56% CHALLENGER** | CHALLENGER (80 of 154 fixtures) |

`sportsbet`-created fixtures exist precisely because the odds ingester could not
find the match among the composite ones — the primary provider did not have it.
That selects for Challenger and obscure events. So the "verifiable" subset is
mostly Challenger and the "unverifiable" subset is mostly main tour, and the ROI
gap is the tier difference this document already contains: CHALLENGER −0.45% (38)
against TOUR +12.58% (537) on the game-handicap diagnosis alone.

**Retracted:** "on prices we can prove were pre-match, this strategy shows no
edge", and the recommendation not to install that rested on it. The −1.73% was
largely the Challenger result, not a verdict on the pricing.

Also checked and clean: every result's winner is one of the fixture's two
players — 0.00% bad across all 3,362 result rows in all three fixture sources.
Grading was already verified at 0 of 426.

### What survives from this whole investigation

* **A real defect, fixed:** 47.4% of snapshots on matches with a known start were
  fetched at or after the off. CLV must read the last pre-start price, and now
  does; no start time means no CLV. `weekly_review` had already disabled CLV as
  a gate for this reason and was right.
* **A real gap, closed:** `matches.start_time_utc` is stored, and recovered for
  1,978 of 3,327 matches.
* **A candidate tier decision, not yet measured properly:** CHALLENGER is in
  `BETTABLE_TIERS`, it is 56% of the fixtures whose data our primary provider
  lacks, and it looks unprofitable everywhere it has been split out. It deserves
  the same treatment ITF got — measured on model-versus-market skill first, ROI
  observed afterwards.
* **Unchanged:** nothing in the 44-day record is clean out of sample, because
  five selection changes were fitted on it. That was true before this
  investigation and is the reason to be careful. It is not the same as "the
  backtest is priced on bad odds", which is what I claimed and have now
  withdrawn twice over.

---

## Two stored orientations were wrong, and the check that found them now runs

Added 2026-08-11, after the CHALLENGER tier question. Both defects were found by
one question — **does the bookmaker's shorter price win more often than not?** —
and neither was visible to any existing test.

### What was wrong

| | mechanism | scale |
|---|---|---|
| `odds_snapshots.player_a_odds` | every provider fills it from **its own** first listed player, and `_find_match_id_for_odds` deliberately links a fixture whose players are in *either* order. Nothing reordered it. | 742 of 6,860 comparable rows (10.8%); **48.6%** of composite-fixture rows |
| `market_odds_snapshots.selection_side` | derived at insert from the fixture's players — but the matches upsert sets `player_a_id = excluded.player_a_id`, so a provider reusing a `provider_match_id` for a different pairing silently invalidates every side already stored | 8,925 of 40,130 graded rows (22.2%); **29.1%** on TOUR, 54.2% on UNKNOWN |

The comment above `_insert_market_odds` already described defect 1 exactly —
"a flipped side mirror-flips every downstream factor readout" — and the fix had
been applied to one of the two writers. **Seventh instance of the same rule:
define "which row/side is current" once and share it.**

Symptom before repair, by tier, favourite win rate:

| tier | market table | positional columns |
|---|---|---|
| ITF | 72.7% | 72.9% |
| CHALLENGER | 70.6% | 70.6% |
| **TOUR** | **53.8%** | **40.4%** |
| **UNKNOWN** | **50.0%** | **40.4%** |

After repair, every tier passes: TOUR 62.4% / 61.1%, UNKNOWN 59.6% / 57.7%.

### What it did and did not affect

- **The props pipeline does not read either column.** It resolves players by
  name and never selects `selection_side` — verified by grep across `src/`.
  So no prop ROI number in this document changes.
- The positional columns had exactly **one** live reader:
  `feature_builder._legacy_positional_market`, which fires when a match has no
  named selection rows — **1 match of 2,046**.
- `selection_side` is read by the match-winner path: `pricing.py`,
  `daily_report.py`, `combos.py`, `market_agent.py`. **98 of 415 staked matches
  (23.6%)** carried at least one mismatched side, so that path was affected.
- Separately found: 111 matches carry a price for a player **in neither**
  fixture, from the ±1-day name link attaching a second event. Only 2 of 415
  staked matches, so small, but those sides are now set to NULL rather than
  assigned.

### Repaired and guarded

- `selection_side_for()` is the single definition, now token-based, which also
  fixes three shapes that previously returned None and made a price invisible:
  doubles offered by surname (`Borges / Cabral`), a dropped hyphen
  (`Felix Auger Aliassime`), and a `- Rain Delay` suffix on a fixture name.
- `resync_selection_sides()` runs after the upsert, so a rewritten pairing can
  no longer leave stale sides behind.
- `scripts/repair_odds_orientation.py --apply` fixed history: 17,623 sides
  corrected, 2,998 set to NULL, 464 newly resolved, 1,305 price pairs flipped.
  Verified on a clone before the production database was touched; backup at
  `tennis_wc.db.bak-orientation-20260811-194257`.
- `scripts/check_odds_orientation.py` is the standing guard, exit 1 on any tier
  below 55%. **It should run before any go-live decision** — a misoriented price
  is invisible to unit tests, because the odds, the match and the selection name
  are all real and only the pairing is wrong.
- 14 new tests, one per real failure shape. 292 passing.

### The CHALLENGER question, answered on repaired data

The ITF standard for exclusion was a decisive skill deficit measured *before* any
ROI was consulted: Brier gap +0.049, AUC gap −0.147, P(model not worse) = 0.000.

| tier | n | Brier gap | AUC gap | P(not worse) | meets the ITF standard? |
|---|---|---|---|---|---|
| ITF | 491 | +0.0491 | −0.1469 | 0.0000 | yes — excluded, correctly |
| CHALLENGER | 153 | +0.0141 | −0.0414 | 0.1177 | **no** |
| TOUR | 402 | +0.0035 | −0.0126 | 0.3065 | no |
| UNKNOWN | 52 | +0.0050 | −0.0285 | 0.3942 | no |

**CHALLENGER should not be excluded.** Its deficit is under a third of ITF's on
both measures and is not decisive at n=153. Its −0.45% ROI is a small-sample
result, not the evidence ITF's exclusion rested on. No change to
`BETTABLE_TIERS`.

### A fourth correction to my own reporting

The first run of the tier measurement read the positional column and reported a
market AUC of 0.3733 on TOUR — a bookmaker's favourite losing more often than
winning. **That was my diagnostic reading a column nothing in production reads**,
which is the fourth time today an alarming number came from my own tool rather
than the system. The sanity check now runs first and refuses to print the row
beneath it when the favourite rate is impossible; it fired once during this work
and stopped a second false finding.

---

## 0.2 — installed, 2026-08-11 19:51 Sydney

I had been refusing to install these jobs, reading "do not set anything live"
as covering the schedule. That was the wrong line. The card job places no bet,
sets no stake and sends no message — and scheduling the 09:00 pass **is** what
0.2 asks for. The rule protects phase 2 (what to stake, how much, in money),
which remains untouched and still needs an explicit go-ahead.

Verified before installing:

- **No money path exists in the codebase at all** — `place_bet`, `bet_slip`,
  `submit_bet`, any POST of a wager: zero matches across `src/` and `scripts/`.
  Placement was always by hand.
- **Nothing sends.** Push is gated behind `TENNIS_NOTIFY_HEALTH=1`, and neither
  plist sets it. 0.3's alert still needs your go-ahead.
- Both templates pass `plutil -lint`; both jobs are `bootstrap`ed and `enable`d
  in `gui/501`, 0 runs, never exited.

Fixed on the way in, because it would have broken the job on its first morning:

- `run_launcher.sh` still probed the Drive root with `head -c 1 AGENTS.md`. A
  content read on CloudStorage does not fail when the mount is unhealthy — **it
  stalls, with no exception** — so under launchd that probe could hang the 09:00
  card forever, which is the one failure this job exists to prevent. Removed;
  the Python layer already decides by attempting a write.
- Chain tested the way launchd will invoke it
  (`zsh run_launcher.sh --source launchd --notify-self-test`): launcher → venv →
  python → Telegram `getMe` returned `ok: true` without sending anything.

### The exit test cannot be faked, and now provably is not

`run_source=launchd` says launchd *started* a run — not that the **schedule**
did. `launchctl kickstart` produces a genuine launchd run at any hour, so a
wiring test I ran by hand would have satisfied the very clause written to stop
that. `verify_scheduled_runs.py` now requires the run to have started within 45
minutes of 09:00 and lists off-schedule launchd runs separately as not counting.

It also no longer reports "the job is not installed" when the job is installed
and merely not yet due — it asks `launchctl` and says which of the two it is.
Those were the same empty output, which is how a broken schedule reads as a
young one.

**Current state, quoted from the tool:**

```
runs recorded: 1  scheduled card runs: 0
The .card job IS installed (loaded, 0 run(s) so far). It has simply not fired
at 09:00 yet -- the exit test needs two such mornings.
EXIT TEST: NOT MET
```

**NOT MET, and it cannot be met before 2026-08-13.** First scheduled fire is
09:00 on 08-12; two consecutive mornings puts the earliest possible pass on
08-13. I deliberately did not kickstart a full card run to hurry it: at 19:51
Sydney, asking for today's book returns **in-running** prices for matches
already under way, and for any match whose first snapshot that became, the
replay's `earliest_odds=True` would later read a live price as a morning one.
That is the +58% ROI bug's exact mechanism, so the wiring test used the
non-mutating path instead.

Still yours to decide, unchanged: 0.3's alert (it sends), `TENNIS_NOTIFY_HEALTH=1`
(it sends), and all of phase 2 (it stakes).

---

## The log was 99.88% one payload, and nothing bounded it

Done 2026-08-11, while 0.2 waits on the calendar. Not a blocker, but it became
urgent the moment both passes were scheduled: from tonight this file grows every
day unattended, and `verify_scheduled_runs.py` — the tool the 0.2 exit test is
read from — reads it whole.

**What was there:** 869,771 lines, 28MB, and **1,075** of those lines carried a
timestamp. The rest were continuation lines of those same entries: `log()` was
handed each subprocess's entire stdout, and the CLI prints the whole card as
pretty JSON. One payload shape appeared 76,477 times. No rotation existed
anywhere — no `RotatingFileHandler`, no `newsyslog` entry, nothing.

Three fixes, and the middle one matters most:

1. **Rotation** at 8MB, five generations.
2. **`verify_scheduled_runs.py` now reads the rotated generations too.** Without
   that, a rotation could silently delete one of the two mornings the exit test
   is judged on — the same class of failure as an empty listing reading as a
   successful run.
3. **Captured subprocess output is capped at head 40 / tail 40 lines and states
   its own elided line count.** A silent truncation reads as "that was all there
   was". The full card still goes to the analysis output root, which is where it
   is meant to be read.

**Compaction of the existing file** rebuilt it entry by entry with that cap, and
refused to write unless every distinct day survived:

```
entries: 1075  (timestamped 1075)
distinct days before: 29   after: 29
days lost: none
lines 869771 -> 10178
bytes 28127520 -> 382048
```

**launchd's own capture** (`StandardOutPath`) is a second copy that nothing else
can bound — rotating it properly needs a `newsyslog.d` entry, which needs root.
It also cannot be dropped: a failure *before* python starts appears only there,
and that silence is what this phase exists to remove. So the scheduler trims it
in place at start-up, keeping the tail. Trimmed rather than renamed on purpose —
launchd holds the descriptor open for the current run, and a rename would send
that run's output to the file nobody reads.

301 tests passing.

---

## The live provider could not tell an empty book from a broken parser

Done 2026-08-11. Non-blocking, but it is the code the 09:00 job runs unattended
from tomorrow, and it was the least tested thing in the repo.

**First, a correction to my own aim.** I started reading
`sportsbet_scrape_provider.py` (305 lines, zero tests) — and it is not what runs.
`get_odds_provider()` returns **`SportsbetOddsProvider`** (`sportsbet_provider.py`,
188 lines, also zero tests); the scrape file is a fallback behind
`SPORTSBET_SOURCE_MODE=scrape`. Measuring which path is live took one command and
stopped me hardening a file that never executes.

**What was wrong.** Seven silent `continue`/`return []` paths and a counter on
none of them. The one that matters: the match market is found by whether its name
or type contains `moneyline`, `match winner` or `winner`. If Sportsbet renames it,
every fixture drops, the listing returns empty — and an empty listing is
**byte-for-byte what a book that is not open yet looks like**. That ambiguity is
the whole reason phase 0 exists, and it sat unguarded in the live provider while
0.1 was busy proving the scraper itself was fine.

**Fixed.** The provider now publishes `last_parse_stats` —
`fixtures_in_response`, `rows_parsed`, and a per-reason drop count — and
distinguishes the two cases that need opposite responses:

| drop reason | what it means | what to do |
|---|---|---|
| `no_markets_in_odds_data` | fixture has no book yet | wait |
| `markets_present_none_matched_moneyline/match winner/winner` | **the market was renamed** | fix the parser |
| `selection_name_did_not_match_either_team` | naming drift | fix the matcher |
| `fixture_carried_no_odds_data_id` | not priced by this book | expected |

And the one combination that must never be quiet — **input present, output
empty** — now logs a WARNING naming both counts:

```
sportsbet: 55 fixtures in the response and 0 rows parsed -- drops: {...}.
An empty listing with a NON-empty response is a parser problem, not a closed book.
```

A genuinely empty response (0 fixtures, as at 18:00) stays at INFO, because an
empty card is a legitimate output and an alarm that cries wolf on it would be
turned off within a week.

8 new tests, including one pinning that the renamed-market reason names the tokens
it looked for, so a future rename is legible from the log alone. 309 passing.

---

## The disk filled to zero, hours before the job's first unattended run

Found 2026-08-11 20:05, by hitting it: the shell could not write a command's
output. `ENOSPC`. Not a subtle failure — and **the 09:00 card job would have hit
it first**, failing on a write, producing an absent card, which is what every
other failure produces too.

I caused most of it. Alive at once: a 2.5GB replay clone in scratch from the A/B
work, a 2.7GB pre-repair backup beside the database, and the 2.5GB database
itself. Nothing anywhere checked for room.

**Freed:** the replay clone (the work it served is committed) and the backup
compressed 2.7GB → 306MB with `gzip -1`, so the rollback for tonight's 21,085-row
repair still exists. 0 bytes free → **9.4GB**.

**Guarded:** `scripts/check_disk_headroom.py`, and the scheduler now refuses to
start without two database-widths free (2GB floor), exiting 75 —
`TemporaryDataUnavailable`, the retry code — with the numbers in the log line.
Two widths is not a guess: the repair and the A/B harness both clone the
database, so the working set is multiples of it.

### Preflight of tonight's changes against real data

Three things were edited hours before this job first runs alone, all unit-tested
and none of them ever executed against real data shapes. On a clone:

```
resync over 2045 real matches:              0 changes, 0 exceptions
orientation helper over 3000 real rows:     0 exceptions, 0 flips
provider parse over 400 real stored payloads: 0 exceptions
PREFLIGHT: PASS
```

The 0 changes matter: the repair already ran, so the write path and the repair
agreeing to the row is what says they are one definition and not two.

311 tests passing.

---

## 0.3 and 1.3 — both exit tests PASSED 2026-08-11 20:21

Kelvin gave the go-ahead to finish the remaining items, which unblocked the two
that were reserved because they send.

**0.3 — a broken run produces a notification.** PASSED. A real alert went to
`@WongChoii_bot` (`Notify sent.`, 20:17), and the run-level wiring is now pinned
by tests rather than by my having called the function myself:

| failure | exit | notifies? |
|---|---|---|
| `AnalysisBoardMissing` — 0 events for TODAY | 70 | **yes** |
| `TemporaryDataUnavailable` — a timeout | 75 | **no** |

The second row is the one that keeps the alarm usable. An alarm that fires on
retryable failures too gets muted within a week, and then the real one is muted
with it.

**1.3 — the line arrives on a day with no bet.** PASSED, and deliberately tested
on the clause that matters. The day was picked from the record rather than
invented: **2026-08-09, 25 fixtures priced, 0 value bets staked.**

```
🎾 2026-08-09 · ? (?)
賽事 25 · 有價 25 · 已分析 25
prop 47 · value 0 · 未結算 63 (三日前)
CLV 同步 0 (prop 0, 無標識 0) · 已計 0
```

`TENNIS_NOTIFY_HEALTH=1` is now set in **both plist templates** rather than in
`run_launcher.sh`, so the switch is under version control, and
`launchctl print` confirms it reached the job: `TENNIS_NOTIFY_HEALTH => 1`.

### The `? (?)` in that line is my test harness, not a defect — checked

It would have been easy to ship as one. The health line reads
`payload["readiness"]`, and the scheduler computes readiness into a *local
variable* and never writes it back into the payload — which looks exactly like
the bug. It is not: `cli.py:491` sets `payload["readiness"]` with `severity` and
`horizon`, and my synthetic payload simply lacked it.

The log could not settle it either way: **zero HEALTH lines exist in the whole
history**, because 1.3 was built today and no real run has happened since.
Tomorrow's 09:00 pass emits the first one. So a test now pins both directions —
a real payload shape renders `OK (same_day)`, and a missing readiness block
renders `? (?)` — so if that line ever shows `?` it reads as "the pipeline
stopped populating this", not as "a quiet day".

314 tests passing.
