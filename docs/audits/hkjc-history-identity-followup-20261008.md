# HKJC source identity follow-up — 2026-10-08

## October 9 continuation

The 803 recovery candidates have now passed identity/name, frozen profile hash,
fetch-timestamp equality, pre-meeting fetch cutoff and dated pre-meeting history
checks. They were materialized only under `/tmp/hkjc-recovered-profiles-20261009`,
with per-runner provenance and `/tmp/hkjc-recovered-profiles-20261009/verification.json`.
Production caches/Logic/Dashboard were not changed.

95 candidates retain unknown raw non-finish status; 30 have possible history gaps
(the cache predates the earliest rich formguide run or that window is absent).
The overlap is two records: 123 have either flag, 680 have neither of these two
flags (still not a full-feature certification). No record was silently dropped or treated as a complete
history merely because its identity/time checks passed. The 3,463 original
meeting-cache matches below are identity matches, not a new certification of
their cache timestamps or all feature provenance.

Focused source/engine tests: 75 passed, 2 existing expected failures.
October 9 final `./檢查.sh`: exit 0, all discovered suites passed. Golden
scores unchanged. AU/HKJC corpus contracts were skipped in the isolated checkout,
so this result is not a data-completeness or model-promotion certificate.
Supplemental durable validator patch:
`docs/experiments/patches/hkjc_profile_recovery_validator_20261009.patch`.
The validator also passed five smoke checks: valid input, wrong identity, changed
fetch time, future history and undated history. Script:
`scratch/hkjc_verify_profile_recovery.py`; reproduce from candidate checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scratch/hkjc_verify_profile_recovery.py /tmp/hkjc-profile-recovery-manifest-20261008.json /tmp/hkjc-recovered-profiles-fresh
```

The full refit is still withheld under the data-quality/leakage rules. This work
recovers auditable evidence and fixes pipeline defects; it does not establish a
predictive improvement.

Candidate only, not committed/pushed/deployed. Baseline remains
`60c951acd672a811515a2ff0e66112c53b919946`. Continuation of EXP-20261008-07.

## Implemented

- Racecard-authoritative runner reconciliation: do not give a declared runner a
  standby horse's form; exclude withdrawn card runners; record replacements.
- Profile IDs keyed by actual horse number. Missing IDs and empty CLI slots no
  longer shift every subsequent profile onto the wrong horse.
- Verify returned profile name before accepting enrichment. A replacement without
  a verified profile blocks Facts publication instead of silently becoming a debut.
- Profile-only completed history adapter preserves sparse evidence and prevents
  a horse with known history being described as a debut. No invented sectionals.
- Same-name/conflicting-brand identity fails closed.
- All five previously failing standalone alignment tests now pass and are
  included in standard test discovery. Focused run: 72 passed, 2 existing xfails.

## Corrected coverage diagnosis

The previous 2,227 unresolved count was a limitation of the first lookup, not
proof that 2,227 race records had no data. Reconcile archived racecards first,
then match both full HK IDs and short brands, requiring matching names.

| Audit stage | Count |
|---|---:|
| Original archived Logic cohort | 351 races / 4,408 runner records |
| Racecard ID + name matched in meeting cache | 3,463 |
| No matching ID in meeting cache | 940 |
| Of those, earlier cache candidate in another folder | 803 |
| Only later or undated cache candidate | 89 |
| No matching cache in any scanned meeting folder | 48 |

Racecard reconciliation also identifies six removed runner records and one
added/replaced record. The post-reconciliation denominator is 4,403, not 4,408.
Do not silently change the evaluation cohort to improve reported coverage.

The 803 candidates are **not yet certified replay inputs**: the manifest records
the source path, cache key, fetch timestamp and profile SHA-256. Selection is the
latest matching cache strictly before Hong Kong midnight on race day. Still
check date cutoffs, required fields and completeness before scoring. Later data
are not used as substitutes. The 137 remaining cases cannot be called recovered.

Artifacts:

- `/tmp/hkjc-profile-recovery-manifest-20261008.json`
- `/private/tmp/wc-dashboard-all-scores-20261008/scratch/hkjc_profile_identity_audit.py`
- Cumulative durable patch: `docs/experiments/patches/hkjc_history_identity_candidate_20261008.patch`
  (apply to the clean baseline; supersedes the previous candidate patch, not on top).

Reproduce the read-only scan from the candidate checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scratch/hkjc_profile_identity_audit.py '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing' /tmp/hkjc-profile-recovery-manifest-fresh.json
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q .agents/scripts/test_hkjc_fact_source_alignment.py .agents/scripts/tests
./檢查.sh --quick
./檢查.sh
```

## Replay and remaining gate

October 7 replay succeeded for all nine races:
`/tmp/hkjc-history-identity-final-20261008`. Seven of 108 runner inputs change
relative to the original source logic. No new performance gain claimed; no weight
or ranking-formula change. The archived evening Logic version is still not a
frozen pre-off prediction for earlier races.

Next: verify/materialize the 803 earlier-cache candidates in an isolated replay
manifest, resolve or explicitly account for the 137 remaining cases, and lock the
actual pre-off evaluation inputs. Data-quality/leakage gates still prohibit a
promotion claim or a silent subset-only refit. Neither production data nor the
Dashboard was rewritten.
