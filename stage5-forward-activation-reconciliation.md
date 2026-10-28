# Forward-only installer reconciliation — approved design, implementation incomplete

## Problem

Session release e7 is merged but its installer was safely deferred by the
active-run guard. Production/main is now newer 9f. Existing refresh refuses
already-merged releases; activation pins the original SHA and correctly
refuses downgrade. Do not manufacture no-op source edits to force installation.

## Human decision

Kelvin explicitly replied `批准 forward-only 安裝對賬流程` on 2026-10-28.
Implement and test a new Central controller reconciliation action, then release
it through existing engineering gates.
This is a new activation-target workflow, not permission inferred from the
previous immutable approval. Do not alter an existing manifest or run a manual
installer. A read-only eligibility preview is now under test. The intent/gate/
installation executor is not implemented or released; no production action is done.

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

## 2026-10-28 dependency checkpoint

Fetched main and actual production both observed at
`51ea46ef359f24a87029376a99f944f0c982dab6` before implementation. Original e7
installer dependencies are **not unchanged**. Unified installer now adds an NBA
result timer preflight and changes the active-run matching expression. NBA's
installer output also changed, and its postgame/final-refresh plist templates
changed. Broader scheduler/native-review dependency inventory must also be
reviewed; a two-script diff is not a complete dependency review.

The approved invariant therefore blocks installation until independent review.
This is distinct from the resolved human workflow approval. Do not treat this
session's own inspection, main membership, an idle process probe or a full test
pass as that independent review. No override flag or refreshed old manifest.

Kelvin subsequently authorized one read-only independent subagent review.
Reviewer Wegener (`01a1813b-719c-7b22-870f-7a2cd3cb31dd`) is assessing the
exact e7 → 51ea dependency changes and provenance. Starting that review is not
an approval result. Separately, direct provenance inspection found 51ea lacks
four-domain exact-SHA deployment verification; no new event was written to
fill that gap. The final preview uses a conservative runtime-source superset,
including domain engines and Tennis package imports used by native review.

`reconcile-installation-preview --source-commit <full SHA> --target-commit <full SHA>`
is read-only: current remote refs, existing linked source/target provenance,
conservative dependency diff and production identity/dirty state. It cannot
write an intent, grant approval, invoke a gate/installer or send Telegram. Even
`eligible_for_fresh_gate` explicitly carries `installation_authorized=false`.
The later executor still needs immutable intent, locks, fresh gate/rechecks,
preflights, snapshots, concurrency-safe restore and independent acceptance.

## Safety implementation sequence after review

1. Keep the read-only preview separate from all mutation paths. Its successful
   fixture result means only eligible for fresh gates. Reject missing/invalid
   event bytes and failed production cleanliness probes rather than projecting
   a clean/approved state from incomplete observations.
2. Add RED tests against the actual installer boundary: active relative/-X/
   preclose invocations, an active run beginning after the first probe, a busy
   deferral followed by outer recovery, prior unloaded jobs, and concurrent
   plist replacement/removal. Tests must use fake HOME/launchctl/process lists.
3. Implement shared cutover exclusion and ownership-aware snapshot/recovery.
   Preflight deferral without external mutation must not bootout anything.
   Failed recovery must retain backups and report blocked, never overwrite
   another writer or claim rollback success from the old event wording.
4. Review resulting exact source independently, then implement the append-only
   intent and fresh gate/approval executor. Do not merge controller code with
   an installation request or implicitly activate foreign NBA cadence changes.
5. Only perform a real cutover after exact-target provenance and the independently
   reviewed installer/dependency scope are satisfied, using existing controller
   locks, allowlist, preflights, acceptance and rollback controls.

Keep this incomplete work on its non-main preservation branch. Do not release
the preview as though it completes the approved workflow or cadence acceptance.
