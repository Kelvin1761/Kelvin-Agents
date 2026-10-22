# Preserve a Stage 5 release's full immutable payload on refresh

Tennis release `86d88875cc38` records three paths but its tip commit changes
only the audit. Earlier WIP commits contain the code/tests. Replaying only the
tip fails closed at exact-scope selection instead of recovering that release.

- [x] Reproduce with local bare-remote fixtures, without production writes.
- [x] Replay the rollback-target-to-candidate tree delta, reject out-of-scope
  bytes and retain normal three-way conflict/union handling.
- [x] Verify multi-commit code preservation, hidden earlier conflicts and
  malformed scope rejection, plus existing refresh/replay tests and quick gate.
- [ ] Full Central exact-scope release; immutable SHA/main recheck, existing
  approval/activation/rollback controls unchanged; record acceptance.
- [ ] Refresh the original Tennis manifest via that controller and continue
  weekly-cadence work serially. Do not manually duplicate pending releases.

No ruler, model, authority/allowlist, gate threshold, data retention or ledger
change is in scope. Test fixture gates do not constitute the real full gate.

## Evidence and bounded implementation

Base: `f727aafa6fe472825a928c22877228b6ad393e70`. Original RED run: 3
failures, 11 deselected, 6.69 s. The real topology is confirmed read-only:
`git show --stat 86d88875cc38` contains only nine audit lines, while its gated
rollback-to-candidate diff has code, tests and audit (three recorded paths).
No attempted real refresh or new Tennis manifest was created by this diagnosis.

Fix: verify that all rollback-target-to-candidate changed paths belong to the
original recorded scope, before any checkout. Create an unpublished synthetic
single-parent commit with the SAME immutable candidate tree and recorded
rollback target as parent, then use the existing Git three-way cherry-pick.
The resulting actual candidate still requires normal exact-scope prepare,
fresh source full gate, new immutable remote SHA and approval clean-clone
recheck. Existing overlap, union driver, replay limit and rollback controls
are unchanged. The synthetic object is not itself a release or approval.

GREEN: 39 tests passed in 51.77 s across `test_release_refresh.py`,
`test_release_replay.py`, `test_release_approval.py`, `test_release_manager.py`.
New regressions cover multi-commit audit-tip source preservation, earlier
conflicts with clean failure, unrecorded-path rejection, exact binary bytes,
earlier deletion, and automatic replay gating the actual merged NEW SHA.
Quick gate passed; AU/HKJC goldens unchanged. Existing AU sparse/new-field
and HKJC stale-baseline warnings remain; no calibration was changed.

Dry-run exact four-path scope: code/full, four-domain code sync, no installer,
Dashboard deploy or manual reason. Real full release and production verification
remain pending; neither Stage 5 completion nor model improvement is inferred.
