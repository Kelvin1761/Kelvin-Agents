# External TMPDIR release-gate fixture recovery — 2026-10-09

## Observed failure

The exact five-path NBA adapter refresh based on
`6b3b9563c3446e3e8cf3557144616406a359e3e4` exited 1 with
`full gate failed; no files were staged` (controller session `51544`). No new
commit, push, merge or activation resulted. Diagnostic full gate `16985` is
completed with exit 1: Shared Wong Choi failed three tests (1,215 passed),
while all fourteen other suites passed, including NBA 110 and Tennis 614.

Collection order identified the first failing item as
`test_unavailable_warm_root_blocks_without_mutating_source`. Isolated execution
under the external TMPDIR reproduced `DID NOT RAISE ArtifactArchiveError`:

```text
env TMPDIR='/Volumes/Kelvin Hardisk 1/WongChoi-Archive/central-release-gate-20261009.AmUutw' \
  python3 -m pytest .agents/skills/shared_wong_choi/tests/test_artifact_archive.py::test_unavailable_warm_root_blocks_without_mutating_source \
  -q -p no:cacheprovider
```

The old fixture supplied a nonexistent child directory below `tmp_path`.
`archive_copy` deliberately checks the volume-level directory for `/Volumes`
paths and creates missing archive subdirectories on an available volume. Here
the parent volume was genuinely mounted. The fixture did not represent an
offline volume. The other two failures were
`test_storage_status_flags_unmounted_warm_and_hot_pressure` and
`test_supervised_review_rejects_storage_report_after_source_changes`, which
also assumed a missing archive child meant an unavailable volume. Both were
independently reproduced (two failures, session `7076`).

## Isolated correction

Only three test fixtures are changed. The archive and storage-status tests
explicitly supply a synthetic volume path and stub its filesystem availability
to false, delegating all other directory checks to the real implementation.
The archive test asserts that the mount was checked, the source bytes remain
unchanged and no catalog is created; storage status explicitly checks
`not_mounted` alongside HOT pressure. The supervised storage-report test now
changes the configured WARM source to a uniquely named, verified absent volume
after capture (and is named accordingly),
so both worker and parent must reject the outdated report independent of where
fixtures live. No host mount operation or production data write is performed.

No archive implementation, mount policy, release policy, model, ruler,
installer, scheduler, ledger, retention or deletion logic is changed. Keep this
four-path correction separate from the NBA adapter's original five-path scope.

## Validation checkpoint

- Before correction: isolated offline test failed, 1 failed (session `81408`).
- After correction: all eight archive tests pass with the external TMPDIR
  (0.14 seconds) and with `/private/tmp` (0.10 seconds).
- An intermediate attempt changed WARM to another existing directory on the
  same volume. That did not alter the bounded storage-health projection (which
  intentionally contains availability/configuration, not archive paths), and
  the review test still failed on both filesystems. The final test changes
  availability to a verified absent volume, propagated through the inherited
  environment; no production projection/schema change was made.
- Final focused selection (archive, storage status, supervised changed-source
  test) passes all 12 tests with external TMPDIR (3.29 seconds) and
  `/private/tmp` (0.48 seconds). Capture must succeed before injecting the
  unavailable-source fault; this is not a test that passes merely because
  initial evidence was missing.
- Quick gate completed successfully; AU/HKJC scoring goldens remain 120/120
  unchanged. No local meeting corpus is present in the isolated checkout, so
  data-contract corpus checks are not production-data acceptance.
- Full gate of this corrected four-path payload, session `91029`, completed
  with exit 0 using the external TMPDIR and Node 20. All 15 suites pass:
  Shared Wong Choi 1,218, NBA 96, Tennis 614, Dashboard Python 135 (16 skips),
  Dashboard Node 16 + 62. Agent scripts retain two expected failures. Goldens
  remain unchanged and missing-corpus checks remain skipped. The diagnostic
  gate of the uncorrected NBA tree is not used as corrected-payload evidence.
- Scoped delivery remains pending at this source checkpoint. The release
  controller's docs/tests quick gate will recheck the audit update before
  saving; the full source regression result above was observed independently.
- Production remains unchanged; no activation was attempted by this repair.

Verify and deliver the correction through the existing exact-scope release controller
before refreshing the original NBA release on the new main.
