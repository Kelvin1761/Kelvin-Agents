# EXP-20261015-06 — Joint pace and full-time capacity (discovery)

Frozen family before this experiment's outcomes, 2026-10-15. Motivation:
EXP-04 full-time A is the reference candidate (Gold +1, Good +3, Pass +3);
EXP-05 does not support a standalone "faster early = better" bonus.

Two fixed corrections to contextual full-time capacity:
- J800: field early intensity P using total−L800; individual relative early
  effort Q = own early speed residual minus field median early residual.
- JAdaptive: same, total−L600 for historical race distance≤1200, L800 otherwise.

P,Q clipped ±3 after dividing log-speed residual by .03. Fit full-time speed
residual on [P,P²,Q,Q²,P*Q], within-horse centred, ridge=100, prior-date-only.
Use contextual full-time and early standards, class nuisance and leave-own-race-
out variants as in EXP-04. At least 100 repeat observations; otherwise zero
correction. IDs from GPS XML when present, no target outcomes or odds.
Per run, corrected capacity = contextual full-time residual minus estimated pace
association, NOT an automatic positive upgrade. Then the fixed EXP-04 six-run
recency/distance/going aggregator and confidence shrinkage. No separate positive
L600 or early-speed bonus, and no double counting total+early+late independent
features. Coefficients are statistical associations, not causal energy costs.

Evaluate fixed arms A, J800, JAdaptive, all reported against production baseline
and paired against A. Same 2496 races/71 dates, first30dates warmup then six
7-date forward windows; gain grid0,.25,.5,1,2 and training-only consensus rule
unchanged. A predictions must reproduce EXP-04 exactly. No OOS arm selection,
no cutoff/weight/metric tuning. Whole-date bootstrap2000seed7 and family Holm.

The time windows have been inspected; this is discovery, not a fresh holdout.
Source capture availability FLAG remains. User accepts the previous modest point
changes, but no automatic production promotion while the provenance and AU v3
contract gates remain unresolved. Freeze a future candidate before prospective
capture. No change to formal evaluation contract, live engine, or dashboard.

Implementation notes, before outcomes: total-time standards use EXP-04's complete
source inventory including the CSV-only meeting; early standards and correction
observations use the same XML-only event set for BOTH J arms. Thus the geometry
comparison is matched, with 5254 valid XML races. The one CSV-only meeting's
field does not carry an invented Adaptive phase. Formal form manifest SHA is
identical to EXP-04/05. Full-time A is loaded unchanged; exact predicted scores
are checked against the frozen EXP-04 predictions, not merely aggregate counts.

The pressure regression is not guaranteed to identify energy cost: fitness,
ageing, field composition, race tactics and track variation remain confounders.
A within-horse fit reduces stable-ability confounding but cannot remove all of
it. Its sign is learned rather than assumed, and the entire corrected capacity
must earn its place against A. No class reward or market information is added.

## Results — no incremental value established

1493 evaluation races / 41 dates; same production baseline Gold288/Good393/Pass749.
Original A predictions reproduce EXP-04 exactly, runner by runner.

| Pipeline | Gold | Good | Pass | Change vs production |
|---|---:|---:|---:|---|
| Production | 288 | 393 | 749 | — |
| A, contextual full time | 289 | 396 | 752 | +1 / +3 / +3 |
| J800, joint adjusted capacity | 288 | 393 | 752 | 0 / 0 / +3 |
| JAdaptive | 288 | 393 | 749 | 0 / 0 / 0 |

J800 versus A loses one Gold and three Good, same Pass. Relative to production,
J800 Gold delta0 (CI[0,0]), Good delta0 (CI[−.2014,+.1905] percentage points).
J800 six window gains0/0/.25/.25/.25/.25; JAdaptive all0 because no positive
training-consensus gain qualifies. This is a fitted zero fallback, not unwired
features. Raw feature AUC J800 .5955 [.5691,.6221]; JAdaptive .6012
[.5772,.6260], both3145 runner appearances/411 comparable races. A reference
.6072 is unchanged. Do not use the best AUC after observing these windows to
select another coefficient or phase.

All family primary Holm p-values are1. No formal PRIMARY_WIN or RANKING_WIN;
canonical decision remains leakage_audit_failed because historical availability
is not certified. Ranking power/MDE has not been established. User accepts the
small A point changes; that preference is preserved, and is not represented as
statistical certification. No new correction supersedes the original candidate.

Important limitation: full time includes early time algebraically. A regression
of full performance on early effort can remove mechanically shared variation
as well as an actual pace penalty. Within-horse centring does not identify a
causal energy cost. These candidate failures do not disprove a joint pace
hypothesis; they reject keeping these particular corrections in the candidate.

## Independent data diagnostic: GPS clock versus race-header clock

`au_gps_clock_audit_20261015.py` only includes runners already passing complete
split/own-finish reconciliation; an untracked winner is not silently included.
Of5254 eligible XML races,5227 have one validated winner and header time:
5216 differ by>.05s,5087 by>.5s. Header−winner GPS median1.92s;5th–95th
percentile .687–5.603s, with extreme outliers (max2801.181s). One race has
GPS-order versus rank inconsistency>.05s;27 lack a unique validated winner.
49544 validated runners are marked IsFinishTimeOfficial=true,59false; this
flag alone does not make the two clocks interchangeable.

This is NOT a statement that the race header is an official photo-finish clock,
nor that every GPS time is wrong. Header semantics and time origin are not yet
certified. The current research never uses header time as a predictor or clock
anchor. Do not automatically add the difference, discard it as noise, or treat
GPS speed as a fully calibrated official speed rating. Verify the publisher's
clock definitions and cross-check against independent official results first.
Only after that should a clock-alignment candidate be pre-registered, ablated,
and evaluated on fresh dates. This is higher priority than adding more free
pace coefficients.

## Validation and preservation

29 research unit tests pass (including untracked-winner exclusion, same-day/
future invariance, within-horse intercept invariance, common pairs and original
geometry). Focused ruff and repository quick/full checks pass; final logs saved
with artifacts. No live engine, weights, deployment settings or dashboard edited.
Research is preserved on a non-main branch; no automatic promotion.

Artifacts: `/Users/imac/.codex/visualizations/2026/10/15/01a13d68-afa0-77b3-a25d-8a74906a0796/`
under `AU-phase-speed-research/` and `AU-joint-pace-research/`; frozen source cache
remains `AU-contextual-speed-research/official/`, not duplicated. Full results
include venue cohorts; compact checked-in evidence excludes those bulky rows
and records the full artifact SHA256. Feature files include the original source,
form/reference hashes, per-date coefficients and actual predictions.

Reproduce from this research branch with `PYTHONDONTWRITEBYTECODE=1`,
`OPENBLAS_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1`:

```bash
python3 scratch/au_phase_speed_20261015.py build --root <AU-data-root> --cache <frozen-official-cache> --reference <EXP04-features> --out <phase-features>
python3 scratch/au_phase_speed_20261015.py evaluate --features <phase-features> --out <phase-results>
python3 scratch/au_joint_pace_capacity_20261015.py build --root <AU-data-root> --cache <frozen-official-cache> --reference <EXP04-features> --out <joint-features>
python3 scratch/au_joint_pace_capacity_20261015.py evaluate --features <joint-features> --previous-predictions <EXP04-predictions> --out <joint-results>
python3 scratch/au_gps_clock_audit_20261015.py --cache <frozen-official-cache> --out <clock-audit>
PYTHONPATH=scratch python3 -m unittest scratch/test_au_gps_clock_audit_20261015.py scratch/test_au_joint_pace_capacity_20261015.py scratch/test_au_phase_speed_20261015.py scratch/test_au_contextual_gps_speed_20261015.py scratch/test_au_measured_runner_time_20261015.py
```

### Publisher cross-check narrows the clock concern

Downloaded the official 2025-01-01 Sunshine Coast sectional PDF and official
post-result form guide. Race1 Caxton Lass: published runner Overall59.08,
published field time59.08, official result form59.08; XML horse FinishTime59.08,
while XML RaceSummary FinishTime61.643. Thus this independently checked sample
supports the existing per-runner input and does NOT support adding the header
difference to every horse. The publisher sectional PDF explicitly says timing
is based on position data. Do not describe header offsets as demonstrated GPS
errors or infer their unverified meaning from the element name.

Sources:
- https://www.racingqueensland.com.au/RacingFile.ashx?path=/Sectional/20250101_Sunshine_Coast_T.pdf
- https://www.racingqueensland.com.au/RacingFile.ashx?path=/ThoroughbredMeetingFiles/fra_SCST_20250101.pdf

Original PDFs, extracted first-three-page text and SHA256 manifest are preserved
with the joint artifacts. This is one publisher cross-check, not certification
of every historical source or its publication/capture availability.
