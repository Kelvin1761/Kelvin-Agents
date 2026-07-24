# AU Wong Choi — the 90 blindspot winners: exhausted current data (2026-07-24)

Kelvin: don't give up on the 90 (market top-2, our model ranked ≥5, WON).
Ran the strongest untried hypothesis + summarised all checks.

## Fresh investigation this round: first-up / freshness — REFUTED
- first-up horses = 15% of field; actual top-3 finish **25.4%** (LOWER than
  non-first-up 28.8%) → they genuinely run worse; model ranking them ~same
  (6.0 vs 6.2) is correct, not a bug.
- Among the 90: only **6% first-up** vs 15% base → first-up is NOT their pattern.

## All current-data patterns now checked — none isolate the 90
| hypothesis | result |
|---|---|
| lightly-raced | only 28% of the 90 |
| trial existence / top-3 trial | 88% but base rate 75% — not discriminating |
| trial WIN quality | washes out conditional on model |
| missing pace_figure | 77% but base 67% — not discriminating; high-missing races not worse |
| first-up / freshness | 6% vs 15% base — refuted |

The 90 are mostly seasoned horses, with trials, that look mediocre on OUR data,
that the market fancied and that won. Their winning quality is genuinely **not
present in any data we currently hold**.

## Only two ways to catch them (both = new information, not model math)
1. **Market column** (the odds two-track, currently set aside) — catches them
   directly because the market's money already knows.
2. **New data we don't extract yet:**
   - **gear changes (first-time blinkers/tongue-tie)** — classic "market-fancied,
     form-hidden" signal; racenet has a `gearChanges` field we don't use. The
     single most likely common thread among the 90 — TESTABLE if we extract it.
   - stewards / trouble ("checked", "held up") — excuse signals.
   - pedigree (sire/dam aptitude) — for the lightly-raced subset.

## Honest position
This is not giving up — it is having checked every findable pattern in the
current data and found none. Model math cannot recover the 90. Next genuine test:
extract `gearChanges` (racenet) and check if the 90 cluster on first-time gear —
the last plausible odds-free thread. Otherwise the market column is the answer.
