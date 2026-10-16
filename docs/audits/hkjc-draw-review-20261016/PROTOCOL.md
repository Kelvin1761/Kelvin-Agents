# HKJC draw formula review — locked 2026-10-16

Baseline: `2d7ec14c09a3d6fa0bc5733406a730f7dff344ff`; production scoring is unchanged
from the earlier same-session capture at dd22b05d (git diff checked). Fresh replay
is required and paired with the previously locked 325-race canonical runner set.
Do not read 2026-10-11 onward outcomes. Dates through 2026-10-10 only; the actual
last development meeting is 2026-10-07. No tuning or extra arms after results.

Use model-evaluation-contract v3, same production SIP, rounding and whole-field
cap. Four registered ranking metrics: capture@5, NDCG@5, competitive recall@5,
mean actual-top3 model rank. Report Gold/Good and six chronological blocks,
2000 meeting-day bootstrap (seed 7), Holm over four candidates × six metrics.
Compute full-shape neutralization budget and A/A noise halfwidth before results.
Historical archive availability remains an explicit provenance limitation;
statistical screens cannot authorize promotion. Forward outcomes stay closed.

## Four fixed candidate algorithms (non-debut only)

Only replace draw D. Keep F/T, HV surface gain, dimension weights, SIP and cap.
ST turf1000 and AWT have separate identities. Missing/unknown venue: no-op.
Invalid draw: no-op. Context must come from production input, not result labels.
Maximum declared draw is available from the pre-race runner list; do not use
the eventual number of classified finishers as the evaluation field size.

* `percentile`: D = 75 − 25 x + existing PIT rail adjustment, x=(draw−1)/(maxdraw−1),
  reversed for ST turf1000. Fixed rule. This tests the absolute-bucket cliff.
* `pit_group`: D = clip(65 + 100 e,45,85), e = sum(place−3/N)/(n+60), grouped
  by venue × surface × exact distance × relative-draw third. Requires 100 prior
  runners / 20 prior races, otherwise current D. Replaces, rather than adds to,
  existing rail adjustment. All dates strictly before the target date.
* `pit_hierarchy`: same D mapping; first estimate group parent e0 as above;
  exact draw × field bucket (≤8/9–10/11–12/13+) cell e1=(sumr+60 e0)/(n+60);
  then rail-specific e2=(sumr+100 e1)/(n+100). No rail data uses e1.
  Same parent sample floor. This jointly tests a preregistered hierarchical
  estimator; its extra layers are compared with pit_group, not presumed useful.
* `pit_ridge`: regularized least-squares residual estimator, independently by
  venue × surface × exact distance. Features are within-race-centred x and x²,
  x=(draw−1)/(maxdraw−1). beta=(X'X+60I)^−1 X'r. D=clip(65+100X beta,45,85).
  Same sample floor. No hyperparameter search or odds inputs.

Learning candidates are `walk_forward_oos`: recompute on each target date using
only earlier dates in rail_draw_results.csv. Use the same historical store for
all arms, filtered before building features. This is a new dated source versus
the older official-table raw-rate tests; do not repeat those failed static arms.

## Data audit / cohorts

Audit source keys, duplicates, venue, surface, distance, valid positions and
draws. The rail dataset's FieldSize counts classified finishers: report this
limitation and reject promotion unless actual starter denominators are certified.
7 of 8 official Draw_Stats snapshots were scraped after 23:00; time zone / race
start provenance is not certified. Do not score old races with today's table.
Official snapshot test is deferred, not evidence that the official table fails.

Report ST turf, HV turf, AWT, ST straight1000, field buckets, distance buckets,
debut-containing races, going and baseline first-pick SP cohorts where joined.
Venue-only application (ST/HV/AWT) is descriptive marginal ablation, not another
post-hoc candidate eligible for selection. No model code changes in this study.
