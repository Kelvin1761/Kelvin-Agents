# Forward-only installer reconciliation — proposal, not authority

## Problem

Session release e7 is merged but its installer was safely deferred by the
active-run guard. Production/main is now newer 9f. Existing refresh refuses
already-merged releases; activation pins the original SHA and correctly
refuses downgrade. Do not manufacture no-op source edits to force installation.

## Proposed decision

Request explicit approval to implement and test a new Central controller
reconciliation action, then release it through existing engineering gates.
This is a new activation-target workflow, not permission inferred from the
previous immutable approval. Do not alter an existing manifest or run a manual
installer. No reconciliation implementation or production action is done yet.

## Required invariants

- Only this chat's failed/deferred engineering installer release may be the
  source intent. It must already be an ancestor of current approved main;
  prove its allowlisted installer/required dependency bytes are unchanged, or
  stop for independent review. No foreign release is approved here.
- New append-only immutable intent binds the original release, current exact
  remote main/production SHA, installer scope and captured rollback/external
  state. Prove current target's existing approval/deployment provenance; never
  infer approval solely from main membership.
- Fresh clean full gate on the exact target, independent immutable approval
  recheck, normal release/activation locks, allowlist, all production preflights,
  transactional snapshots and rollback remain mandatory. Main/branch/production
  movement invalidates the attempt; no silent retargeting or gate reuse from logs.
- Do not merge/promote models or change scores/rulers/holdouts, credentials,
  DB bytes, historical evidence, retention, ledger or bankroll. Do not stop
  active domain jobs, increase deadlines or skip/relax the busy guard.
- Failure restores captured external state without erasing concurrent writes.
  Never downgrade newer Git state. Success requires all4 installed/loaded paths,
  required files/exact SHA, actual calendar and native receipt acceptance.
  Calendar configuration alone is not observed firing/SLA or Stage 5 completion.

## Tasks after approval

- [ ] Specify append-only intent/status and strict current-SHA eligibility;
  reject stale/foreign/model intents and changed installer dependencies.
- [ ] RED tests: moved main/branch/production, busy guard, overlap, stale gate,
  rollback/concurrent writes, repeat invocation, old-manifest immutability.
- [ ] Implement using existing controller locks/snapshot/verifiers; keep old
  activation semantics unchanged. Test read-only preview before side effects.
- [ ] Focused + quick/full-gated exact-scope engineering release; no automatic
  reconciliation merely because the new command has been installed.
- [ ] Run explicitly authorized reconciliation with fresh target proofs, then
  independently verify actual runtime/calendar/native receipt and record outcome.

Until approved: source-only proposal is preserved non-main, not activated.
