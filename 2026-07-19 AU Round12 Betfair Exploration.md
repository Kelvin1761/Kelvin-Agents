# AU Wong Choi — Round 12: Betfair Exploration Phase 1 (2026-07-19)

Offline research only — no live API, no live betting. Kelvin's constraint:
**analysis is done one day BEFORE the race**, which shapes everything below.

## Data source CONFIRMED and accessible (free, no login)

- `https://promo.betfair.com/betfairsp/prices/dwbfpricesauswin{DDMMYYYY}.csv`
  (+ `...ausplace...` for place). Filename date = race date **+1**
  (settlement day); the harness keys on the in-file `menu_hint` race date, so
  the offset is handled automatically.
- Columns (lowercase): `bsp, ppwap, morningwap, ppmax/min, ipmax/min,
  morningtradedvol, pptradedvol, iptradedvol` + menu_hint/event/selection.
- Harness `scratch/au_betfair_research.py` — parser validated, **joined 16/16
  runners** on Eagle Farm 2026-05-30 R9. Track-alias map still needed for
  multi-word tracks (Rosehill vs "Rosehill Gardens").

## Three fields, three distinct uses (critical given day-before workflow)

| Field | Available when | Use |
|---|---|---|
| `bsp` (exchange SP) | race time only | **research/validation** — sharpest price, can't be a feature (leaks) |
| `morningwap` | ~morning, near Kelvin's analysis | **the realistic bet price** — report ROI here, not just BSP |
| `morningtradedvol` + open→morning drift | pre-race | **money-flow FEATURE** (orthogonal to matrix) |

## Two quantified wins from the 2-day sample

**1. Betfair has zero margin.** Measured field overround Σ(1/BSP) = **1.000**
(130 races) vs bookmaker SP ~1.20–1.25. The +16.8% tight-rank1 SP edge (Round
11) was measured against prices carrying ~20% takeout — at Betfair pricing the
same picks return materially more. This is the single strongest reason the
edge is likely real.

**2. Eagle Farm R9 money-flow story (the $71 winner).**

| model rank | horse | morning | BSP | drift | result |
|---:|---|---:|---:|---:|---|
| 1 | Poster Girl | $6.5 | $8.7 | 1.3× | 3rd |
| **2** | **Savagery Vibe** | **$22.4** | **$91.9** | **4.1×** | **1st** |
| 3 | Paradise City | $21.1 | $39.4 | 1.9× | — |

The model's #2 pick **won at a $22 morning price** — bettable the day before.
It then drifted 4.1× (money abandoned it) yet won: money-flow is real
information but **NOT a naive "follow the steamers" rule** — here following the
money would have faded the winner. It is complementary, not dominant.

## Money-flow feature design (for the standard gate, later)

Pre-race-only signals (no leakage): open→morning price drift ratio, morning
traded volume rank within field, morning-implied-prob vs model-prob gap.
Hypothesis: these are **orthogonal** to the 7 matrix dimensions (the reason
every prior candidate failed was redundancy) — the market's money is genuinely
new information. Gate it exactly like every other candidate.

## Next steps (need Kelvin's call on scope)

1. **Full BSP pull** — ~90 daily win+place files (one per archive meeting
   date +1), ~30-50 MB total, to run the real tight-/clear-rank1 ROI at BSP
   **and morningwap** with a proper bootstrap CI. This settles #3.
2. **Track-alias map** — build once (Rosehill↔Rosehill Gardens, etc.) so the
   join covers all venues, not just exact-name matches.
3. **Money-flow feature** — extract morning drift/volume for the archive,
   retrodictive check, then walk-forward gate.
4. Live API (odds + automated staking) — **Kelvin-only**, last, needs auth
   this session cannot perform.

Sample BSP files kept locally in `scratch/betfair_bsp/` (not committed —
third-party data).
