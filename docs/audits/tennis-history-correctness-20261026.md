# Tennis history and current-slate correctness

This follows the identity and pricing-evidence repair batches. It changes data admissibility and fixes reproducible integrity bugs; no feature weight, value threshold, holdout split or promotion rule is tuned. No profitability or accuracy improvement is claimed.

## Reproductions and repairs

- Eight form readers (rank/ Elo buckets, tournament level, round, big matches, format, pressure and head-to-head), rest days and the double-fault profile now apply the existing 13-day same-event ingestion guard. Fixture start is passed through the feature context; offset timestamps compare as instants. Nine controlled baseline reproductions counted a late-ingested same-event row as history. Guarded tests exclude it.
- Self-opponent history is excluded at reads, and new ingestion rejects a self-pair. Invalid rates and non-negative count violations become missing measurements, not clamped values. Bad hold samples cannot satisfy the serve-profile sample requirement. Other valid facts, including the result, remain available; raw history is not deleted. The snapshot diagnostic counted 3,425 self rows (3,406 old Unknown Player rows plus 19 known-player rows); rate-field violations were hold 17, break 17, first serve 2, second serve 4, return 2. These are field counts, not a distinct-row sum.
- Generic `total_games` legacy forecasts without a saved feed market name have an unverified contract. Versioned `prop-contract-v1` exclusions report the row IDs and reasons. A proven named-player market priced as a match total has a separate exclusion reason. No line threshold or outcome is used to guess the missing identity. New match-total logs carry the original market, selection and line onto the tracker and pricing receipt.
- Current priced fixtures receive scoped participant/result/subject integrity checks. Confirmed errors are held with a fixture observation, excluded from new pricing, and surfaced as critical readiness failures. Archived errors and unpriced placeholders do not permanently stop today's slate. Direct prop writes reject missing/inactive/self fixtures and foreign subjects.
- Prop subject mapping uses the same exact/unique token matcher as odds mapping. Shared first names and incompatible full names are declined. New full names with a common first name no longer select the first player arbitrarily.
- Empty book listings now retire current quotes for composite-owned fixtures as well as book-owned fixtures. Absence is recorded as a book capture, not a deletion. Provider-specific event IDs remain separate, and a new verified capture restores availability. Current coverage/feature candidates must read the same captures, not historical quote existence.

## Fixed-corpus component check

Database: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db`, SHA256 `2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac`, read-only.

Before inspecting outcomes, twelve fixture IDs were selected deterministically across twelve date strata over 2026-08-01..2026-10-25: 10162, 12099, 13088, 13574, 15254, 16144, 16873, 17560, 18262, 19363, 20182, 21003. Baseline uses the unchanged evidence-repair branch source. Both cached and uncached baseline payloads are exactly identical.

| Arm | Fixtures | Win-probability changes | Maximum absolute change | Assembly errors |
|---|---:|---:|---:|---:|
| Ingestion/self guard only | 12 | 7 | 0.02908567 | 0 |
| Invalid-measurement filtering only | 12 | 0 | 0 | 0 |
| Combined | 12 | 7 | 0.02908567 | 0 |

The component check isolates input effects; it is not an out-of-sample accuracy or ROI trial and cannot qualify a model promotion. Invalid-value tests separately contain the malformed values, which are rare in this probe. The probability formula and weights are unchanged. Scripts and summary hashes are under `docs/audits/support/` and `tennis-history-feature-ablation-20261026.json`. The artifact's historical `validation` key contains returned tournament metadata, not an independent validation verdict.

The existing 13-day guard does not prove availability of every older season-file statistic. Reconstructing an old feature snapshot today still does not establish its exact pricing-time inputs. Original saved receipts/observations remain required for qualified evidence.

## Validation and remaining work

Latest native integration: **824 Tennis tests passed**. Full immutable release checks and activation are not yet confirmed. The first identity release passed its original full gate, then a replay onto newer main failed a shared-corpus 120-second timeout. The unchanged focused test passed in 35.14 seconds on small local test storage. A fresh full gate is being run through the original release refresh process; no timeout was relaxed.

Remaining independent work: canonical historical observations (coarse player/opponent/date groups are not proof of duplication), idempotent round normalization, strategy-document generation, and controlled model research after correctness gates. The WTA direct-history experiment remains rejected and the frozen Elo shadow cannot skip its registered sample requirement.
