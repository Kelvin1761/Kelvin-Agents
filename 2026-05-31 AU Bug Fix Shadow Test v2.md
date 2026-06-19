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

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `14.3%`
- Pass: `21.4%`
- Top3 Place: `32.1%`
- 0-hit: `8`
- 1-hit: `14`

## runtime_fixed_good_only / archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.4%`
- Pass: `35.4%`
- Top3 Place: `41.1%`
- 0-hit: `50`
- 1-hit: `154`
- Delta: gold `-0.3`, good `-3.5`, pass `-3.5`, place `-1.5`, 0-hit `+2`, 1-hit `+9`

## runtime_fixed_good_only / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- Delta: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`

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

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- Delta: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`

## health_removed / archive

- Races: `316`
- Champion: `20.9%`
- Gold: `3.8%`
- Good: `17.7%`
- Pass: `34.8%`
- Top3 Place: `41.0%`
- 0-hit: `49`
- 1-hit: `157`
- Delta: gold `-0.3`, good `-3.2`, pass `-4.1`, place `-1.6`, 0-hit `+1`, 1-hit `+12`

## health_removed / 05-30

- Races: `28`
- Champion: `25.0%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `32.1%`
- 0-hit: `8`
- 1-hit: `14`
- Delta: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`

## sign_anomalies_fixed / archive

- Races: `316`
- Champion: `20.3%`
- Gold: `3.8%`
- Good: `17.1%`
- Pass: `35.1%`
- Top3 Place: `41.1%`
- 0-hit: `49`
- 1-hit: `156`
- Delta: gold `-0.3`, good `-3.8`, pass `-3.8`, place `-1.5`, 0-hit `+1`, 1-hit `+11`

## sign_anomalies_fixed / 05-30

- Races: `28`
- Champion: `28.6%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `33.3%`
- 0-hit: `7`
- 1-hit: `15`
- Delta: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+1.2`, 0-hit `-1`, 1-hit `+1`

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

- Races: `28`
- Champion: `28.6%`
- Gold: `3.6%`
- Good: `17.9%`
- Pass: `21.4%`
- Top3 Place: `32.1%`
- 0-hit: `8`
- 1-hit: `14`
- Delta: gold `+0.0`, good `+3.6`, pass `+0.0`, place `+0.0`, 0-hit `+0`, 1-hit `+0`
