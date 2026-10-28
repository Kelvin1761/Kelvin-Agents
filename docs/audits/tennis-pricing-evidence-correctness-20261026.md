# Tennis pricing evidence and current market correctness

Scope: correctness repairs following `tennis-identity-correctness-20261026.md`. No feature weights, probability formulas, value-profile thresholds, holdout boundaries or promotion criteria are tuned here. Profitability improvement is not claimed.

## Reproduction and frozen evidence

- Consistent research database: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-bugs-20261026/bug_research_baseline.db` (1,849,798,656 bytes, SQLite quick_check OK).
- SHA256: `2e13a17a63871cbd5e108a4c258ec1c7193d1c032752ed74025f8f02249284ac`. Open read-only; do not mutate this baseline or duplicate it per arm.
- Quality-clock diagnostic on this snapshot: 10,333 graded pre-match rows; 10,083 have latest quality >=65%; 10,297 qualify under a first-write proxy; 26 have no proxy. Eligibility differs for 214 rows. This proxy is diagnostic only: pending props can be repriced, so first write does not establish the actual quality at their final pricing.
- Read-only feature assembly previously raised `attempt to write a readonly database` because five feature calculators unconditionally persisted their derived statistics.

## Repairs

1. Pure feature assembly suppresses derived writes while the explicit build/persist entry point retains persistence. A frozen-clock test compares the full feature payload byte-for-byte and asserts no rows were written. Formula values are unchanged.
2. Current quotes use one capture per match/provider/book, including explicit empty captures. Removed lines are not resurrected by MAX-per-contract queries. Preclose captures remain separate and historical opening readers retain MIN(id). Different bookmakers are never joined to manufacture a two-way market. Legacy batch inference is explicitly not proof of quote completeness or availability.
3. Every newly recorded prop freezes its actual pricing time, feature snapshot IDs/qualities, profile values/history IDs supplied by the pricer and uniquely matched quote when available. First-write time remains separate from latest pre-start pricing time. Settled and post-start overwrite guards also protect the receipt.
4. Quality-qualified reliability and formal ROI read the frozen pricing receipt, not today's feature quality or later rebuilt history. Legacy missing receipts are UNKNOWN and remain visible in raw scorecard/ROI; they cannot acquire invented historical quality. This intentionally reduces qualified evidence until new observations mature.
5. As-of reliability, ROI and model scorecard additionally require settlement before the cutoff. A match date alone cannot prove its label was available. SQL failures propagate instead of becoming a successful empty fit.
6. Sportsbook event result lookup resolves IDs from that provider's observed quotes/captures. A composite fixture provider's event identifier is not a sportsbook ID.
7. Prop pricing failures render an error and write a failure observation consumed by readiness. Empty successful boards remain healthy. Connections close on both paths, and new pipeline start markers preserve earlier raw failure records.

## Validation and limits

Native Tennis tests and quick repository checks are run with `PYTHONDONTWRITEBYTECODE=1`. Tests cover empty/replaced captures, bookmaker separation, readonly assembly, receipt immutability under later rebuilds, pre-start repricing, late labels, legacy unknown quality, visible SQL/pricing failures and retained source-error observations.

Release/activation and final test counts must be confirmed from the release manifest; this document does not declare deployment. Current-market repair cannot reconstruct disappeared historical quote batches or exact pricing-time receipts that were never recorded. No old forecasts or graded bets are rewritten.

Still separate work: remaining history-reader causality/invalid-value guards, legacy mislabeled market evidence, scoped current-slate identity readiness, and clean fixed-corpus model research after correctness gates pass. A failed model experiment remains rejected; greater historical row count alone is not evidence of profitable edge.

## Fixed-corpus result (before release)

Both arms use the exact database/checksum above. Baseline source: `6dfe0cec3863e23671a07b402e446a3c0bdf4aee`; candidate integration: `a78dc787` (individual evidence repair `daf33579`). The same driver calls every supported family's `family_reliability(..., as_of_date="2026-10-26")` and `prop_roi_report(conn)` on a read-only connection. Raw ROI here is current-known descriptive history, not an as-of replay or a betting recommendation.

- Raw ROI dictionaries are exactly identical: 1,003 paper recommendations, P/L −146.231 units, ROI −14.58%.
- Formal-profile sample falls from 930 to 0 because no legacy row recorded a pricing receipt. All 1,003 raw rows remain visible under UNKNOWN quality; none are deleted or regraded.
- Every supported reliability fit reports zero quality-verified rows and exposes unverified counts. The registered insufficient-evidence default (10%) is unchanged; some previous fitted zero weights consequently return to that default in research pricing. This is an uncertainty consequence, not a measured accuracy improvement or permission to stake.
- The baseline fitted samples with outcomes have worse raw model Brier than the de-vigged market for every supported family. This does not justify a profitability claim.
- Integration validation: **803 Tennis tests passed**, quick repository checks passed. Full immutable release validation and activation remain to be confirmed separately.

Machine-readable before/after outputs, source-file hashes and checksums are in `tennis-pricing-evidence-20261026.json`. Reproduce with Python 3.9, `PYTHONDONTWRITEBYTECODE=1`, importing each recorded source revision's `src` via `PYTHONPATH`; do not mix source versions or writable databases.
