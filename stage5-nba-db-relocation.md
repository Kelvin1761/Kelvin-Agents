# NBA reflector DB relocation

Human approval in this chat covers source repair and controlled relocation only;
model/ruler changes and research incident unfreezing remain out of scope.

- [x] Confirm unexpected production DB and available HOT/WARM storage.
- [x] Test HOT-only DB creation, existing history preservation and fail-closed legacy/storage handling (27 tests; quick gate passed).
- [ ] Verify no active producer or release controller; stop on concurrent writes.
- [ ] Copy exact bytes to a new HOT destination and a mounted external backup;
  verify SHA-256, SQLite integrity and table counts before recoverable relocation.
- [ ] Run quick/full source gates and exact-scope Central release with immutable
  SHA/current-main checks; preserve rollback code and all database copies.
- [ ] Verify production paths and four-domain runtime health; then reconsider
  the preserved Tennis and weekly-cadence candidates serially.

Production DB is small and actively mutable, so it remains HOT. Its recovery copy
belongs on WARM. No historical evidence or external ledger is rewritten.

## 2026-10-22 execution checkpoint — not released

Initial exact-byte copy had SHA-256
`a01d4c04d56815ab9f591c0c8a5c96dcf56e4120c9d62ef5cdf86ab3e8cd62f0`,
36 `reflector_legs` and 1 `reflector_model_runs`; SQLite quick-check passed.
HOT copy: `/Users/imac/WongChoiData/NBA/nba_reflector.db`.
WARM copy: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/recovery/nba-db-20261022/nba_reflector.db`.

The execution command printed an active NBA postgame producer but did not
conditionally stop before calling relocation. This was an execution error.
Immediately restored the original checkout DB pathname with an exclusive
hard-link (no destination overwrite). No producer was killed. Original history
remained available; the producer completed normally. The helper now requires
the existing NBA scheduler flock, checks for direct producer processes, and
holds a SQLite exclusive transaction. New tests cover these blockers.

Current production source and its same-inode local recovery path
`/Users/imac/WongChoiData/NBA/recovery-20261022/nba_reflector.original.db`
have SHA-256
`4d153e76d9eba0cc0d23eca7548fa58731268ce64e747ed599dea55a61c4cfb3`,
150 legs and 2 model runs; quick-check passed. The hard-link recovery is NOT
an independent immutable backup of these newer bytes. Initial HOT/WARM copies
still retain the earlier 36/1 state, so no current WARM durability is claimed.

Auto-review rejected moving the initial HOT copy aside to enable another
cutover: the existing-destination/no-overwrite restriction requires a new
explicit decision. That command did not execute and must not be retried via a
workaround. Await authority to recoverably archive this session-created old
HOT copy, copy/verify the latest source to the fixed HOT destination and a NEW
WARM version, then remove the source pathname recoverably under the locks.
Never replace or delete the earlier WARM version.

Five-path scoped release dry-run: risk `code`, full gate, NBA code sync only,
no installer, no Dashboard deployment or manual reason. Full source gate and
approval recheck have NOT run. No commit on main or activation is claimed.
The change only fixes storage placement; it is not evidence of model improvement.
