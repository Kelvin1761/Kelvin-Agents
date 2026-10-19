# Stage 5 settlement provenance repair

Goal: preserve exact settlement artifact versions across reflector reruns,
without falsifying history or weakening full-corpus research verification.

- [x] Diagnose native receipt: AU has 10 drifted artifact references; HKJC was
  production-preempted and Tennis/NBA deferred. Evidence is in the matching
  2026-10-20 audit. No cursors advanced.
- [ ] Obtain source-only authorization for production capture changes; freeze
  exact paths before implementation. No release, activation or historical
  migration is implied. Separate release approval follows successful tests.
- [ ] Add immutable, bounded, atomic artifact capture before evidence append.
  Verify copy hash before/after publication; refuse collisions, source mutation,
  symlinks, partial writes and offline storage. Keep original event identity,
  capture clock, canonical result filename and all domain provenance checks.
  Hash-pinned backups/restoreability must not rely on a mutable mirror path.
- [ ] Wire AU capture and compatible research reading, with isolated TDD tests
  proving source rewrites cannot alter earlier evidenced bytes, retries remain
  idempotent, and corrupt/missing versions still block. Check HKJC separately;
  do not silently change all four domain producers or their contracts.
- [ ] Inventory exact-hash recovery candidates for the ten old references.
  Read existing backups/provider history only; keep current files and evidence.
  Propose verified mappings to immutable recovered bytes. Unrecoverable versions
  remain explicit blockers, not missing samples silently excluded. Obtain
  separate approval before any source restore or evidence migration.
- [ ] Verification last: focused mutation/fault/legacy/replay tests, quick gate,
  full gate, immutable release recheck, four-domain runtime verification and
  rollback plan; then native review under existing production/heavy-worker locks
  and WARM limits. Reconcile partial publication before retry. No installer,
  model/ruler/holdout change or model promotion is included.

Done only when original pinned artifacts remain reproducible and a complete
native review verifies them; deployment alone is insufficient. The repair does
not complete power readiness, real pilots, scheduler/Telegram/Dashboard acceptance
or Stage 5 exit.
