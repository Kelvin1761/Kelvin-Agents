# EXP-20261007-02 — HKJC overall-strength core with context overlay

Status: **REJECTED ON DEVELOPMENT; TERMINAL NOT OPENED**.

## Hypothesis

The production 7D blend lets trainer, race-shape and health/context dominate the horse's repeatable ability. A majority horse-strength core may generalise better while retaining bounded conversion context.

## Locked definitions

- Core: sectional, stability, class advantage, form line, preserving their production-relative weights.
- Context: trainer signal, race shape, horse health, preserving their production-relative weights.
- Fixed post-matrix adjustments and debut logic are unchanged.

## Locked ablation and selection order

1. `core60_uncapped`: 60% core + 40% context.
2. `production_share_cap4`: production 44.97/55.03 share, but context movement from core capped at ±4 ability points.
3. `core60_cap4`: 60/40 share plus the same cap.

The first eligible candidate in this simplicity order may open terminal. This order is fixed before results.

## Locked evaluation

Same chronological split and gate as EXP-20261007-01. Gold and Good are the primary no-regression metrics; ranking metrics are secondary. Terminal stays closed when no development candidate is eligible.

Decision: no live promotion from this experiment alone; any pass must survive a prospective shadow and full release gate.

## Result

All three locked candidates failed the development no-regression gate over 162 validation races.

| Candidate | Gold delta | Good delta | Capture@5 delta | NDCG@5 delta | Eligible |
|---|---:|---:|---:|---:|:---:|
| core60_uncapped | -2.47pp | +1.23pp | +1.23pp | +0.79pp | No |
| production_share_cap4 | -3.70pp | -1.23pp | -0.41pp | -0.73pp | No |
| core60_cap4 | -3.70pp | -1.23pp | +0.21pp | -0.13pp | No |

**Decision:** do not alter the live 7D weights or add a hard context cap from this experiment. The uncapped 60/40 arm improved several smooth ranking metrics but lost four Gold races per 162, showing that a simple reallocation is not sufficient. The next architecture test should strengthen horse-level core evidence first (surface suitability, overseas/dirt evidence and repeatable speed/class signals), then retest a smaller prospective overlay change rather than forcing a 60/40 split.
