# EXP-20261015-05 — Comparable AU race phases (discovery only)

Frozen before computing this experiment's results, 2026-10-15.

Question: does changing the measured phase address the distance/acceleration
confounding in total minus L800? Converting m/s to km/h alone cannot do so.

Fixed family (no extra arms after inspecting outcomes):
- E800: start to D−800, previous early-speed geometry control.
- E600: start to D−600, fixed shorter closing exclusion.
- Adaptive: E600 for D≤1200, E800 otherwise. This boundary is a hypothesis,
  not a claimed optimal cutoff.
- Fraction: start to the available timing boundary nearest 40% of race distance.
- Cruise: after the first published section to the Adaptive cutoff; missing if
  no complete section remains. First section is usually 200m but can differ.

Each phase has its own prior-date-only partially pooled course/surface,
distance-curve, going/rating, rail and class-nuisance log(seconds/metre) standard,
with leave-own-race-out historical trackday variants. Class is removed at scoring
(common reference). No current meeting outcome/variant is available to a target.
Use marked distance for progress speed; actual path distance is a separate future
ablation, not a free wide-trip bonus. No interpolation of unobserved split points.

Latest six matched formal starts; same 90-day half-life, distance similarity and
going weights/shrinkage as EXP-04. Missing remains missing. Explicitly compare
all arms on common runner coverage and race pairs; also report natural coverage,
distance buckets and paired date-bootstrap AUC differences (2000, seed 7).
Frozen baseline/form corpus and XML hashes from EXP-04. Reference window stays
2026-09-04–2026-10-14, first 30 days warmup. These outcomes were inspected in
previous experiments, so this is discovery, NOT a fresh holdout or promotion test.
No ranking weights fitted, no model score/rank/dashboard changes. AUC alone does
not establish incremental value over the current model. Historical publication
availability remains FLAG; no production activation.

Independent future validation must freeze phase choice, normalizer, gain and
source capture before collecting new dates. Do not choose a winning phase from
these intervals and describe it as confirmed out-of-sample improvement.

## Standardisation design and remaining blind spots

Use three separate layers, with units and evidence state on every observation:

1. **Measurement**: runner GPS time, marked start/end, measured duration,
   nominal progress distance, actual path distance (when supplied), source timing
   type, course configuration, exact going, rail and capture timestamp. Display
   `km/h = 3.6 * marked_metres / seconds`; this changes units, not comparability.
2. **Context**: each segment gets its own expected log(seconds/metre).
   `I = 100 * exp(log(actual_speed / contextual_par_speed))`; 100 is that
   segment's common-class par. An index of 102 means 2% faster than that par,
   not a 2% greater win probability or a proven interchangeable ability score.
   The stored research score is 1000*log(actual/par). Future calibration should
   also expose prior residual spread and support; never compute confidence from
   the current race's spread alone. Current shrinkage is a heuristic, not a
   calibrated confidence interval.
3. **Prediction**: recency, comparable trip/going, number of usable runs and
   uncertainty; distinguish all-out ability from preferred tactical position.
   A forward horse's early speed can matter through pace compatibility even if
   it is not positively associated with placing as a standalone ability leaf.

Examples (whole 200m timing boundaries):

| Race | total−L800 phase | total−L600 phase | Adaptive | approx first 40% |
|---|---|---|---|---|
| 1000m | 0–200 | 0–400 | 0–400 | 0–400 |
| 1200m | 0–400 | 0–600 | 0–600 | 0–400 |
| 1400m | 0–600 | 0–800 | 0–600 | 0–600 |
| 2000m | 0–1200 | 0–1400 | 0–1200 | 0–800 |

Fraction boundaries use nearest published point, tie to earlier; no invented
480m split at 1200m. A 1666m race may start with a 266m published section, so
"Cruise" excludes that observed section, not a fabricated exact 200m split.
L600 is a candidate for sprint races, not automatically the correct measurement.
Full time, early and late together are algebraically dependent; do not add all
three with free independent weights and call them three independent signals.

Before production, resolve/test separately:

- **Geometry and transfer**: first-section acceleration, run-up and timing start,
  downhill/uphill, straight versus bend, distance to first turn, chute/rail
  configuration, and the discontinuity introduced by the 1200m adaptive cutoff.
  Current distance curve plus coarse course×distance bands are a prototype;
  explicit segment fraction/configuration terms and residual calibration by
  distance are needed before calling the index universally comparable.
- **Pace and energy**: fast early can indicate high ability OR excessive effort;
  fast late after a crawl is not equivalent to sustaining fast pace. Finishing
  speed percentage `100*(late_metres/late_seconds)/(D/full_seconds)` is a useful
  descriptive ratio but must be compared against course/distance/phase par and
  assessed jointly with absolute full-time performance. It is not automatically
  a positive bonus. EXP-04's learned tempo correction did not establish value.
- **Trip and tactics**: GPS path speed describes exertion; nominal progress speed
  describes advancement toward the finish. Distance lost, cover, wind, blocked
  running, easing, jockey intent, gate and race-position changes can explain
  speed. Do not turn a wide trip into an automatic merit upgrade.
- **Measurement and sample selection**: clock versus GPS, missing splits, GPS
  errors, rounding, inconsistent advertised distance, scratched/nonfinishers,
  and region/course coverage. Missing is not poor performance. RQ coverage does
  not validate interstate transfer; the current source sample is Queensland.
- **Confounding**: trackday variants can absorb class/pace/weather as well as
  surface speed. Partial pooling regularises sparse cells but cannot identify
  these causes or create support for an unseen configuration.
- **Availability and identity**: past-only event dates are necessary but source
  publication/capture and revisions must also be proven. Horse IDs exist in XML;
  current form joins still use normalised name plus exact event. Match ambiguity
  must be quarantined before live use. No market-price proxy is introduced.
- **Evaluation**: paired identical runners/races, time blocks, distance/going
  cohorts, dependency on existing speed/form/PQ, gain after shrinkage, family
  multiplicity and power budget, then frozen prospective collection. Natural
  coverage AUC cannot be compared as if its sample were identical.

External methodological references (not transplanted AU coefficients):
[Timeform sectional timing introduction](https://www.timeform.com/horse-racing/features/sectionals/An_introduction_to_Sectional_Timing_Part_2)
uses finishing speed relative to whole-race average and course/distance par;
[RQ official sectionals](https://www.racingqueensland.com.au/industry/thoroughbred/thoroughbred-sectionals)
provides the GPS source family. HKJC's standard-time idea remains a conceptual
reference; neither its current formula nor its weights are copied into AU.

## Results

1493 races / 41 dates; matched 3145 runner appearances, 411 comparable races,
4774 placed/unplaced pairs, identical for all six measurements:

| Phase | AUC | date-bootstrap 95% interval |
|---|---:|---|
| E800 | .5408 | .5232–.5595 |
| E600 | .5356 | .5182–.5547 |
| Adaptive | .5308 | .5114–.5525 |
| Fraction | .5300 | .5093–.5532 |
| Cruise | .5066 | .4853–.5290 |
| Full-time EXP-04 reference | .6072 | .5848–.6306 |

No evidence here that replacing early L800 with L600 improves standalone
prediction: paired E600−E800 AUC −.00524 [−.01819,+.00856]. This is not a
rejection of using L600 for description or as part of a joint pace model.
The current-trip ≤1200m subgroup has E800 .5890 versus E600 .5730; difference
−.01605 [−.03444,+.00583]. Subgroups classify today's trip; matched past trips
remain similarity-weighted, not restricted to the same bucket.
Stayers >1700m (52 comparable races / 411 runner appearances) have E800 .4430
and full time .4837, latter interval .4230–.5492. This warns against assuming
an early-speed bonus transports across distance; it does not identify a new
cutoff. Cruise removal loses information; acceleration can itself be predictive.
All intervals exploratory/unadjusted; no ranking or promotion conclusion.

Source: XML-only 5254 valid races / 49603 runners. The single CSV-only meeting
is explicitly excluded here because this parser uses XML phase boundaries;
EXP-04 retained it. E800 geometry is the control, not a byte-identical source
inventory. Matchable target coverage and E800 AUC are unchanged. Full-time
reference is loaded unchanged from EXP-04, with hash recorded.

Validation: 24 research unit tests pass, focused ruff passes, repo quick/full
checks pass. No production scoring code, model settings or dashboard changed.
