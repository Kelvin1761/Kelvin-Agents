# Stage5 canonical racing measurement — engineering slice

## Scope and current delivery boundary

Wire the existing research harness to a canonical AU v2 / HKJC v2 seven-metric
measurement callback when no explicit callback is supplied. Existing explicit
callbacks, frozen input projection, postflight label rotation and power guards
remain unchanged. This is engineering, not full-model replay, a registered pilot,
measured model improvement, power/effect approval or Stage5 completion.

The measurement accepts completed ordered `{entity_id, score}` rows and separately
held complete official positions/explicit withdrawals. Context price keys bind
the audited entity universe; price values never affect these ranking metrics.
Missing runners/finishes, incoherent official places, nonfinite or self-reported
metrics and undefined comparable pairs block rather than becoming zero. Native
ranking tie order must be supplied by the reviewed domain adapter, including
HKJC raw ability/horse-number secondary order. AU metric reference parity does
not certify a complete HKJC ranking adapter.

Seven metrics: gold, good_positional, top3_capture_at5,
mean_top3_model_rank, competitive_recall_at5, ndcg_at5, top5_pairwise_auc.
The existing AU pairwise algorithm is extracted without changing its top-three
versus rest universe, top-five boundary, full-field mode or half-credit ties.
No evaluation ruler, model, scoring weight, holdout or golden snapshot changes.

## Actual execution and control boundary

The default path is wired into run_research_harness, including original scoring,
development ablations and the registered whole-label rotation. Before any scorer
call it checks both original and rotated outcome compatibility with every
selected audited field. RED3 proved the old late rejection executed 6/12 scorers
for missing finishes/distinct global horse IDs/different field sizes; corrected
integration rejects all three before any scorer call and creates no output.

Frozen rotation groups by family and does not remap identities or stratify field
sizes. General heterogeneous racing pilots therefore remain blocked. Only an
already registered compatible mapping can run. Do not filter or select races
after seeing incompatibility, pad/rename runners or skip controls. A revised
control/label correspondence requires a separately authorized frozen contract,
execution and verification change. Full raw-resource input projection requires
its own audited contract extension too; neither is authorized by this slice.

## Verification and acceptance

- Unmodified9848 native AU metric references were captured before extraction in
  /private/tmp/stage5-racing-measurement-native-reference.json. Synthetic fixtures
  cover score ties, top-five boundary, positional Good and official dead heats.
- Hand-count legacy AU regression verifies top-five pairs 5/13 versus full-field
  7/15, half-credit ties 1.5/3 and unchanged empty pair behavior.
- Actual harness integration retains input audit/trace, train-label separation,
  development-only controls, component ablations and fail-closed publication.
- Same authorized reviewer inspected source only: no arithmetic must-fix found;
  corrected tie-order wording; confirmed heterogeneous control incompatibility.
  No independent tests, native/PIT/pilot/power/release authority is inferred.
- Before release: final focused tests, quick/goldens and existing Central full
  source plus independent clean immutable approval/ref/rollback gates. Expected
  code-only four-domain synchronization, no installers or Dashboard deployment.
- After release: verify exact scoped bytes and all four required-file projections.
  Loaded/calendar/native firing, authenticated Dashboard, research notification,
  real pilots, power profiles and original Tasks6–10 remain separate acceptance.

No live data, result history, native jobs, configuration, model registry, external
ledger, credentials or incident latch is written by this work. Previous9848 and
244 success notifications must not be duplicated.
