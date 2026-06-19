# AU Wong Choi Targeted Post-Hoc Fix Test

Post-hoc approach: start from stored rank_score, apply targeted adjustments.

Archive: `316` races

## Baseline

- Gold: `4.1%`
- Good: `20.9%`
- Pass: `38.9%`
- Top3 Place: `42.6%`
- 0-hit: `48`

## Results

| Variant | Gold Δ | Pass Δ | Place Δ | 0-hit Δ | Verdict |
|---|---:|---:|---:|---:|---|
| P1: race_shape dampen | +0.0pp | +0.0pp | +0.0pp | +0 | ✅ |
| P2: track boost | +0.0pp | -2.5pp | -0.7pp | -1 | ❌ |
| P3: class_weight rebalance | +0.0pp | +0.0pp | +0.0pp | +0 | ✅ |
| P4: heavy dampening | +0.3pp | -0.6pp | -0.1pp | +0 | ✅✅ |
| P5: soft adjustment | +0.6pp | +0.9pp | +0.5pp | +0 | ✅✅ |
| P6: near-miss promote | +0.0pp | +0.0pp | +0.0pp | +0 | ✅ |
| P7: overrated shield | +0.0pp | +0.0pp | +0.0pp | +0 | ✅ |
| P8: field-size adjust | +0.0pp | +0.0pp | +0.0pp | +0 | ✅ |
| COMBO: All fixes | +0.6pp | -3.2pp | -0.9pp | +1 | ❌ |
| COMBO: Safe (P1+P2+P4+P6) | +0.0pp | -3.5pp | -1.2pp | +0 | ❌ |

---

## Fix Descriptions

- **P1**: Dampen race_shape when it's dominant but hard signals are weak (80% of zero-hit)
- **P2**: Boost horses with strong track ability (most underestimated dimension)
- **P3**: Penalize when class_weight is weak but stability/form_line are high
- **P4**: Heavy track: dampen stability/sectional, boost track (1.8× zero-hit rate)
- **P5**: Soft track: milder version of P4
- **P6**: Promote horses ranked 4-6 with strong hard signals but weak soft signals
- **P7**: Stronger overrated shield for stability+form_line traps
- **P8**: Field-size based score compression/expansion