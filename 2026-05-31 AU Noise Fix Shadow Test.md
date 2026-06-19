# AU Noise / Logic-Fix Shadow Test

Baseline uses stored live `python_auto` scores already saved in logic files.
Candidate variants rerun the current engine with targeted patches.

## Stored Archive Baseline

- Races: `316`
- Champion: `24.4%`
- Gold: `4.1%`
- Good: `20.9%`
- Pass: `38.9%`
- Top3 Place: `42.6%`
- 0-hit: `48`
- 1-hit: `145`

## Stored 05-30 Baseline

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`

## runtime_fixed_good_only / archive

- Races: `316`
- Champion: `20.6%`
- Gold: `3.2%`
- Good: `17.7%`
- Pass: `35.1%`
- Top3 Place: `40.5%`
- 0-hit: `53`
- 1-hit: `152`
- Delta: gold `-0.9`, good `-3.2`, pass `-3.8`, place `-2.1`, 0-hit `+5`, 1-hit `+7`

## runtime_fixed_good_only / 05-30

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`
- Delta: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## confidence_demoted / archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `35.4%`
- Top3 Place: `41.1%`
- 0-hit: `50`
- 1-hit: `154`
- Delta: gold `-0.3`, good `-3.5`, pass `-3.5`, place `-1.5`, 0-hit `+2`, 1-hit `+9`

## confidence_demoted / 05-30

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`
- Delta: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## health_removed / archive

- Races: `316`
- Champion: `20.6%`
- Gold: `3.2%`
- Good: `18.0%`
- Pass: `34.5%`
- Top3 Place: `40.3%`
- 0-hit: `53`
- 1-hit: `154`
- Delta: gold `-0.9`, good `-2.8`, pass `-4.4`, place `-2.3`, 0-hit `+5`, 1-hit `+9`

## health_removed / 05-30

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`
- Delta: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## sign_anomalies_fixed / archive

- Races: `316`
- Champion: `19.6%`
- Gold: `3.2%`
- Good: `17.4%`
- Pass: `34.5%`
- Top3 Place: `40.5%`
- 0-hit: `51`
- 1-hit: `156`
- Delta: gold `-0.9`, good `-3.5`, pass `-4.4`, place `-2.1`, 0-hit `+3`, 1-hit `+11`

## sign_anomalies_fixed / 05-30

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`
- Delta: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## bundle_all / archive

- Races: `316`
- Champion: `20.6%`
- Gold: `4.1%`
- Good: `17.4%`
- Pass: `34.5%`
- Top3 Place: `41.0%`
- 0-hit: `49`
- 1-hit: `158`
- Delta: gold `+0.0`, good `-3.5`, pass `-4.4`, place `-1.6`, 0-hit `+1`, 1-hit `+13`

## bundle_all / 05-30

- Races: `0`
- Champion: `0.0%`
- Gold: `0.0%`
- Good: `0.0%`
- Pass: `0.0%`
- Top3 Place: `0.0%`
- 0-hit: `0`
- 1-hit: `0`
- Delta: gold `+0.0`, good `+0.0`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`
