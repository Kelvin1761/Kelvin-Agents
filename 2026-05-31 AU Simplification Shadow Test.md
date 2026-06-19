# AU Simplification Shadow Test

All variants start from stored archive `python_auto` scores and apply isolated rank/matrix deltas.

## Baseline

- Races: `316`
- Champion: `24.4%`
- Gold: `4.1%`
- Good: `20.9%`
- Pass: `38.9%`
- Top3 Place: `42.6%`
- 0-hit: `48`
- 1-hit: `145`

## confidence_off

- Races: `316`
- Champion: `24.4%`
- Gold: `4.1%`
- Good: `20.9%`
- Pass: `38.6%`
- Top3 Place: `42.6%`
- 0-hit: `47`
- 1-hit: `147`
- Delta: gold `+0.0`, good `+0.0`, pass `-0.3`, place `+0.0`, 0-hit `-1`, 1-hit `+2`

## track_pure

- Races: `316`
- Champion: `24.7%`
- Gold: `4.1%`
- Good: `19.3%`
- Pass: `37.0%`
- Top3 Place: `41.8%`
- 0-hit: `50`
- 1-hit: `149`
- Delta: gold `+0.0`, good `-1.6`, pass `-1.9`, place `-0.8`, 0-hit `+2`, 1-hit `+4`

## track_pure_confidence_off

- Races: `316`
- Champion: `24.7%`
- Gold: `4.1%`
- Good: `19.6%`
- Pass: `37.0%`
- Top3 Place: `41.9%`
- 0-hit: `49`
- 1-hit: `150`
- Delta: gold `+0.0`, good `-1.3`, pass `-1.9`, place `-0.7`, 0-hit `+1`, 1-hit `+5`

## jt_no_fit

- Races: `316`
- Champion: `23.1%`
- Gold: `2.8%`
- Good: `20.6%`
- Pass: `37.3%`
- Top3 Place: `42.6%`
- 0-hit: `39`
- 1-hit: `159`
- Delta: gold `-1.3`, good `-0.3`, pass `-1.6`, place `+0.0`, 0-hit `-9`, 1-hit `+14`

## jt_no_fit_track_pure

- Races: `316`
- Champion: `23.1%`
- Gold: `3.2%`
- Good: `19.6%`
- Pass: `36.7%`
- Top3 Place: `42.1%`
- 0-hit: `43`
- 1-hit: `157`
- Delta: gold `-0.9`, good `-1.3`, pass `-2.2`, place `-0.5`, 0-hit `-5`, 1-hit `+12`

## jt_fit_tempered

- Races: `316`
- Champion: `23.4%`
- Gold: `3.8%`
- Good: `19.3%`
- Pass: `38.0%`
- Top3 Place: `42.0%`
- 0-hit: `50`
- 1-hit: `146`
- Delta: gold `-0.3`, good `-1.6`, pass `-0.9`, place `-0.6`, 0-hit `+2`, 1-hit `+1`
