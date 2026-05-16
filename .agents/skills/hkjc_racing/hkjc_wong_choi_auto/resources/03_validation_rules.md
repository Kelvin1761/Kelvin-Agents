# HKJC Auto Validation Rules

Validation fails if output contains:

- odds/market/value/fair odds/edge scoring fields
- pace score, leader score, on-pace score, backmarker score
- LLM commentary/reasoning/model commentary fields
- `[FILL]`
- score outside 0-100
- ability formula mismatch
- rank or top4 not sorted by live verdict order (`rank_score`, with `ability_score` as secondary key; live includes draw micro tie-break when #3/#4 are within the trigger gap)
- grade threshold mismatch
- empty core logic
- forbidden generic phrases
- matrix reasoning missing or not citing numeric score/source
- missing score provenance
- disabled/unavailable fields used for positive scoring
- user-facing report with banned English labels or classic tick wording

Validation also scans Auto scripts for forbidden model-provider imports/calls.
