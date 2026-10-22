# NBA reflector DB relocation

Human approval in this chat covers source repair and controlled relocation only;
model/ruler changes and research incident unfreezing remain out of scope.

- [x] Confirm unexpected production DB and available HOT/WARM storage.
- [x] Test HOT-only DB creation, existing history preservation and fail-closed legacy/storage handling (27 tests; quick gate passed).
- [x] Verify no active producer or release controller; stop on concurrent writes.
- [x] Copy exact bytes to a new HOT destination and a mounted external backup;
  verify SHA-256, SQLite integrity and table counts before recoverable relocation.
- [x] Run quick/full source gates and exact-scope Central release with immutable
  SHA/current-main checks; preserve rollback code and all database copies.
- [x] Verify production paths and four-domain runtime alignment; then reconsider
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
still retained the earlier 36/1 state at that checkpoint; see the later
independent WARM copy below.

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

## Independent latest-state backup (cutover still pending)

Without executing any rejected rotation/replacement, acquired the existing NBA
scheduler flock and a read-only SQLite transaction, then used the production
Central `archive_copy` implementation to append a new content-addressed WARM
version. Production source was not moved, removed or modified.

- Latest bytes: `4d153e76d9eba0cc0d23eca7548fa58731268ce64e747ed599dea55a61c4cfb3`.
- Both source and WARM: SQLite quick-check `ok`, 150 legs / 2 model runs.
- WARM: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/nba/reflector-runtime-recovery/9bad595328f6/nba_reflector.db`.
- Artifact: `wc-artifact:2ad4a78e0bff222ab80ce88e`.
- Immutable catalog record: `/Users/imac/WongChoiData/WongChoiControl/storage/catalog/records/wc-artifact%3A2ad4a78e0bff222ab80ce88e.json`.
- Verified source hash unchanged before/after copy and identical WARM hash.

This is an independent copy, not a hard-link, and preserves the postgame state.
It does not prove future freshness, COLD replication, a restore drill, cutover,
release acceptance or model improvement. Initial HOT and WARM snapshots are
untouched. The explicit HOT-snapshot rotation decision remains pending.

## Explicit rotation approval and completed data cutover

Kelvin explicitly approved: 「批准封存本次建立嘅舊 HOT 副本，再搬遷最新完整 DB；
保留所有舊副本，驗證後才發佈」. This supersedes the pending rotation decision,
not any model/ruler/promotion/incident-unfreeze restriction.

Under the existing NBA scheduler exclusive flock, confirmed no direct producer,
verified production source and independent WARM with the latest `4d153e76…`
bytes, and preserved initial HOT bytes `a01d4c04…` using an exclusive hard-link
at `/Users/imac/WongChoiData/NBA/recovery-20261022/pre-cutover-verified-copy.db`.
Only then removed the initial HOT pathname (all bytes retained at that recovery
path), ran the tested relocation helper, and verified the final HOT and WARM
SQLite/count/hash proofs. Production source pathname is now absent; original
bytes remain at `recovery-20261022/nba_reflector.original.db`.

All initial WARM versions and the latest independent WARM version remain.
Production git status now contains only the two expected mutable JSON paths;
no DB ignore rule, mutable-path policy or release gate was changed.

Code activation is still pending. Legacy production code must not be allowed
to create a new empty checkout DB during a prolonged gate. Recheck before the
next NBA postgame slot (Sydney 21:30); if source code has not activated, stop
the session-owned release safely and restore the original DB pathname under
the NBA lock without overwriting any new path. On activation failure, preserve
any newer HOT writes and restore latest complete data for the rollback code;
never blindly overwrite with the earlier 36/1 snapshot.

## Released and independently verified

Controller session 6065 reached terminal exit 0 (do not restart it).
Five-path release `wc-release:a5911388ffc8:2026-10-22T081957.871451_0000`
passed the source full gate and immutable-SHA approval recheck, was pushed and
merged, then activated at `2026-10-22T08:51:06Z` (Sydney 19:51, before 21:30
postgame). Manifest check/push exit codes are both 0. Approval event content
hash: `9a30baab76e7e2a5133ca65c72e016db37e768500e5b5e0f2a0256f5cf0d5163`.
Only NBA code sync was selected; no installer or Dashboard deployment. The
existing authorized Telegram path reported one successful part/target.

Independent post-activation probe at current runtime
`c931673c09818e8d8223e0313d35473391a91ca5` proves the released commit
`a5911388ffc83727df530dcfa027058dd2622749` remains an ancestor. Actual installed
AU/HKJC/NBA/Tennis and Central launchd status is `aligned`, attention empty.
Imported production `DB_PATH` resolves to the HOT database above; read-only
SQLite quick-check is `ok`, with 150 legs / 2 model runs, and the legacy
checkout database is absent. Current runtime advanced through other agents'
work; that work was not approved or released by this session.

Latest WARM restore to the fresh external scratch path
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/stage5-nba-db-restore-20261022/nba_reflector.db`
passed SQLite, exact byte hash and 150/2 count checks without touching live DB.
All earlier HOT/WARM recovery versions remain. This does not prove COLD
replication or freshness after future writes. Four-domain job success, research
incident clearance, reviewed power profiles and real pilots are separate:
Stage 5 Tasks 6–10 remain open and no model improvement/promotion is claimed.
