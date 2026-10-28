# Activation recovery evidence — code-only safety release

An external restore error could discard its snapshot; a restore-spawn exception
could skip Git recovery/failure recording. A clean concurrent production commit
could also be reset to an older checkpoint. This change keeps the new attempt's
recovery evidence and refuses observed unsafe boundaries.

- [x] Reproduce restore exit/OSError, event-store outage, clean concurrent HEAD
  and failed-status-probe cases in temporary bare-Git/stub-installer fixtures.
- [x] Keep private unique attempt snapshots under Control activation-recovery;
  record the root before runtime actions; retain context/backups on incomplete
  recovery or unavailable failure/success recording. No historical bytes moved.
- [x] Preserve rollback results/errors/status independently of event storage;
  block automatic replay of unresolved outcomes without claiming process liveness.
- [x] Reject failed cleanliness probes; preserve exact NUL path identity and
  reject observed unexpected production HEAD before reset.
- [ ] Fresh full source gate, clean immutable approval/SHA rechecks and normal
  exact-scope controller release; no serialized receipt reuse or gate bypass.
- [ ] Independently verify four-domain code files/exact SHA and installed/loaded
  paths after code sync; record outcome without claiming calendar acceptance.

Scope is exactly this plan, release_activation.py and its regression tests.
Expected activation plan: au/hkjc/nba/tennis code sync, installers empty,
dashboard_deploy false and manual_required false. No launchd install, calendar
change, model/scoring/ruler/holdout, DB/history, credentials or ledger change.
The unfinished forward-only installer, snapshot/ownership and lease work remains
on its separate preservation branch; none of those files is included here.

Final source regressions before isolation: 24 passed in69.83s,
wc-run-ukjp37fn; quick wc-run-gnpfw86p passed, goldens unchanged. These are WIP
tests, not release gates. Fixtures use fake gates/installers, not production.
The independently authorized read-only reviewer found no must-fix issue in the
two-file core patch; this is not immutable release approval. This standalone
plan must also be checked before release.

Preservation checkpoint3411dd0d is pushed on the isolated non-main branch.
The authorized reviewer also checked this standalone plan without a required
correction. Quick recheck wc-run-64iokybc passed. After the observed foreign
release finished, disjoint main28f24137 was merged into this work branch;
production was independently observed at that same SHA. These observations
do not approve the foreign NBA work and do not replace fresh release gates.

HEAD checks are boundary observations, not atomic serialization. Shared cutover
lease/Git CAS and changed-plist ownership remain open. This release does not
complete forward-only installation, research cadence, native firing, pilots,
model improvement or Stage5. It does not retry or retarget any old manifest.

Automatic safety review rejected an optional temporary strict-parser reversion
for RED. No guard change or indirect legacy execution followed. Strict guards
stayed in place; the tracked-file fixture was validated instead. That attempt
is not counted as RED evidence. No further permission is needed for that safe
alternative.
