# AU Wong Choi Targeted Diagnostic Fix Test

Based on deep diagnostics: race_shape overestimated in 80% zero-hit races,
track most underestimated, class_weight negative lift at 3%, Heavy 1.8× zero-hit.

Archive: `316` races

## T1: class_weight_heavy_rating (ablation best)

- Races: `316`
- Champion: `21.5%`
- Gold: `3.5%`
- Good: `17.4%`
- Pass: `36.4%`
- Top3 Place: `41.4%`
- 0-hit: `50`
- 1-hit: `151`
- 2-hit: `104`
- 3-hit: `11`
- Delta: Gold `-0.6pp`, Good `-3.5pp`, Pass `-2.5pp`, Place `-1.3pp`, 0-hit `+2`

## T2: race_shape_light_track (ablation safe)

- Races: `316`
- Champion: `22.2%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `35.1%`
- Top3 Place: `41.1%`
- 0-hit: `49`
- 1-hit: `156`
- 2-hit: `99`
- 3-hit: `12`
- Delta: Gold `-0.3pp`, Good `-3.5pp`, Pass `-3.8pp`, Place `-1.5pp`, 0-hit `+1`

## T3: class_weight_heavy_rating + race_shape_light_track

- Races: `316`
- Champion: `21.8%`
- Gold: `3.5%`
- Good: `17.7%`
- Pass: `35.4%`
- Top3 Place: `40.9%`
- 0-hit: `51`
- 1-hit: `153`
- 2-hit: `101`
- 3-hit: `11`
- Delta: Gold `-0.6pp`, Good `-3.2pp`, Pass `-3.5pp`, Place `-1.7pp`, 0-hit `+3`

## T4: T3 + jt_fit_tempered

- Races: `316`
- Champion: `21.8%`
- Gold: `3.5%`
- Good: `17.7%`
- Pass: `37.3%`
- Top3 Place: `41.5%`
- 0-hit: `52`
- 1-hit: `146`
- 2-hit: `107`
- 3-hit: `11`
- Delta: Gold `-0.6pp`, Good `-3.2pp`, Pass `-1.6pp`, Place `-1.2pp`, 0-hit `+4`

## T5: T4 + formline_purer

- Races: `316`
- Champion: `22.5%`
- Gold: `3.5%`
- Good: `17.7%`
- Pass: `37.3%`
- Top3 Place: `41.5%`
- 0-hit: `52`
- 1-hit: `146`
- 2-hit: `107`
- 3-hit: `11`
- Delta: Gold `-0.6pp`, Good `-3.2pp`, Pass `-1.6pp`, Place `-1.2pp`, 0-hit `+4`

## T6: T5 + heavy dampening

- Races: `316`
- Champion: `22.2%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `37.0%`
- Top3 Place: `41.6%`
- 0-hit: `51`
- 1-hit: `148`
- 2-hit: `105`
- 3-hit: `12`
- Delta: Gold `-0.3pp`, Good `-3.5pp`, Pass `-1.9pp`, Place `-1.1pp`, 0-hit `+3`

### Condition Breakdown

| Good/Firm | 216 | 3.2% | 18.5% | 35.6% | 41.8% | 29 | -1.9 | -5.6 | +1 |
| Soft | 60 | 6.7% | 15.0% | 41.7% | 43.3% | 11 | +3.3 | +6.7 | +2 |
| Heavy | 40 | 2.5% | 15.0% | 37.5% | 37.5% | 11 | +2.5 | +5.0 | +0 |

## T7: T5 + place_off (no place tightening)

- Races: `316`
- Champion: `22.2%`
- Gold: `3.8%`
- Good: `17.1%`
- Pass: `36.4%`
- Top3 Place: `41.1%`
- 0-hit: `53`
- 1-hit: `148`
- 2-hit: `103`
- 3-hit: `12`
- Delta: Gold `-0.3pp`, Good `-3.8pp`, Pass `-2.5pp`, Place `-1.5pp`, 0-hit `+5`

## T8: sectional_speed_heavy + T6

- Races: `316`
- Champion: `21.8%`
- Gold: `3.8%`
- Good: `17.1%`
- Pass: `36.7%`
- Top3 Place: `41.6%`
- 0-hit: `50`
- 1-hit: `150`
- 2-hit: `104`
- 3-hit: `12`
- Delta: Gold `-0.3pp`, Good `-3.8pp`, Pass `-2.2pp`, Place `-1.1pp`, 0-hit `+2`

### Condition Breakdown

| Good/Firm | 216 | 3.2% | 18.1% | 35.6% | 42.0% | 28 | -1.9 | -5.6 | +0 |
| Soft | 60 | 6.7% | 15.0% | 41.7% | 43.3% | 11 | +3.3 | +6.7 | +2 |
| Heavy | 40 | 2.5% | 15.0% | 35.0% | 36.7% | 11 | +2.5 | +2.5 | +0 |
