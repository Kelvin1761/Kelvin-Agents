# AU Wong Choi — Trial sectional sources feasibility + redundant-scoring decision (2026-07-24)

## Redundant features → text-only? Measured answer: only class_score is free

Removing from scoring (keeping the computed value for display), 363-race OOS:

| remove | Δgp | Δg2 | ΔwT3 | folds | verdict |
|---|---:|---:|---:|---:|---|
| **class_score only** | 0 | +1 | 0 | **5/5** | free — remove |
| sectional only | 0 | +2 | −0.6 | 4/5 | borderline |
| trial only | **−3** | +1 | +0.6 | 3/5 | costs — keep |
| class+sectional+trial | **−1** | 0 | **−0.8** | 3/5 | net loss — do NOT |

**Recommendation:** demote **class_score** to text-only (genuinely free, 5/5,
+1 g2). Keep sectional_score and trial_score in scoring — removing them (esp.
together) costs ~1 gp + 0.8pp W-in-T3 + fold stability; they carry a little
non-overlapping signal in combination. "Redundant" was true individually, not
collectively.

## Trial sectional (L600) sources — feasibility

Kelvin: trials are on Racing NSW / Racing Australia; also check Punting Form /
Punters for extra useful data.

Probed 2026-07-24:
- **racenet** (our existing pipeline): trial L600 = **null** for all 20 trials
  on both overview + sectionals pages. racenet does not sectionally time trials.
- **Racing NSW** barrier-trials page: 404 (site restructured); official bodies
  publish trial **results/positions/margins** but per-horse **sectional L600 is
  not standard** — many trial venues aren't sectionally timed at all.
- **Punting Form**: sells **race** "200m sectional benchmark data" + speed
  ratings (Professional tier, paid API). Trials not specified; product is
  race-focused. Same signal *family* as our existing pace_figure (racenet PF),
  so it's a coverage/quality play, not new signal.
- **Punters**: not fetchable (blocked to this tool).

**Honest verdict:** no free, comprehensive per-horse **trial** L600 source
found. AU barrier trials are inconsistently sectionally-timed (metro sometimes,
provincial/country usually not). The only plausible source is a **paid provider
(PF Professional API)** with **partial coverage** and needing Kelvin's
subscription/auth. Given the whole review's pattern (every non-market signal
washes out conditional on the model), expected value is **low**.

## Where the genuinely NEW, useful information actually is

Of everything on these platforms, the one input that is **orthogonal** to our
odds-blind model (not a re-encoding of form/sectional/class we already have) is
the **market — money flow / price**, which the Round 13-15 work already showed
is the biggest lever. Race sectional/speed products (PF/racenet PF) are the
same family we already use; richer trial data mostly isn't published.

## Recommendation

1. Demote **class_score** to text-only (free simplification). Keep sectional/trial.
2. Do **not** build a trial-L600 scraper against Racing NSW/Australia — the data
   isn't reliably there; only a paid PF subscription might have partial coverage.
   Pursue only if Kelvin already subscribes and wants to close the loop.
3. The real new-information lever remains the day-before **market** feed
   (racenet live odds rank = free; Betfair = money-flow + betting edge).
