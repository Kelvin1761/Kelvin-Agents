# HKJC Auto Validation Rules

Validation fails if output contains:

- odds/market/value/fair odds/edge scoring fields
- pace score, leader score, on-pace score, backmarker score
- LLM commentary/reasoning/model commentary fields
- `[FILL]`
- score outside 0-100
- ability formula mismatch
- rank or top4 not sorted by official `rank_score` descending；hybrid 未啟用時先 fallback `ability_score`（ability 再加馬號只係 deterministic exact-tie key；冇 live micro tie-break 或 safety swap）
- grade threshold mismatch
- empty core logic
- forbidden generic phrases
- matrix reasoning missing or not citing numeric score/source
- missing score provenance
- disabled/unavailable fields used for positive scoring
- user-facing report with banned English labels or classic tick wording

Validation also scans Auto scripts for forbidden model-provider imports/calls.

Full-rank ML validation additionally fails if model checksum/version/features,
70/30 weights, per-runner components, or `(0, 1.0001]` rank-score range do not match
the frozen ranking contract.
