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
Reviewer Wegener (`01a1813b-719c-7b22-870f-7a2cd3cb31dd`) assessed the
exact e7 → 51ea dependency changes and returned BLOCKED for installation.
It subsequently confirmed narrow source safety corrections below, without
approving deployment. Separately, direct provenance inspection found 51ea lacks
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

## Source checkpoint: no-op recovery and prior launchd state

The real unified installer now captures a bound `.launchd-state.json` alongside
its copied plists: exact20 non-AU labels, agents root/domain, file hashes/modes/
absence and observed loaded/disabled flags. Damaged/legacy-missing proof,
changed backup bytes and loaded jobs without restorable plists fail closed.
No historical snapshot was modified or restored. The helper only reads launchd;
its writes are new metadata inside the current controlled snapshot directory.

An unchanged snapshot now returns without bootout/bootstrap/enable/disable.
Changed-state recovery touches changed labels only, preserves prior unloaded/
disabled flags, checks unload/copy/enable failures, enables before bootstrap and
requires a final full state comparison before success. The independent reviewer
confirmed these narrow corrections by inspection, not production acceptance.

RED2 real-installer fixture failures: `wc-run-khop6wn8` (unnecessary job mutations,
missing loaded-state proof). Stateful launchctl RED2: `wc-run-9ijdi4i0` (ignored
bootout failure and bootstrap while disabled). Final installer/snapshot fixtures:
**32 passed in 190.11 s**, `wc-run-_17sv_i7`; final quick passed
`wc-run-g9ahdi67`, goldens unchanged and existing contract warnings retained.
Native read-only grammar probe initially rejected macOS `enabled`/`disabled`
tokens; parser was corrected and the repeated sanitized probe parsed successfully,
with no owned labels disabled at that observation. That is not runtime acceptance.

This remains incomplete source WIP. **Changed-plist ownership, shared cutover
exclusion and complete active-run discovery are still open.** No new full or
immutable release gate has approved this source; the earlier terminal94274
full run predates it and must not be reused. Do not release/activate the installer
while these findings and foreign-cadence/target-provenance restrictions remain.

Keep this incomplete work on its non-main preservation branch. Do not release
the preview as though it completes the approved workflow or cadence acceptance.

## Separate core recovery-evidence checkpoint

Owned core changes in `release_activation.py` and its regression tests can be
reviewed/released independently from the unfinished unified installer. They
retain failed recovery snapshots under a private unique Control
`activation-recovery` attempt directory, link that root in the start/failure
events, persist rollback results/errors/status before recording failure, and
continue Git recovery after restore-spawn exceptions. Unrecorded completed
runtime actions retain context/backups and block automatic replay; they are not
reported as a successful deployment.

Production status probe failures now block sync/reset. Raw NUL path identity is
preserved, including whitespace, with rename pairing disabled. Expected-current
HEAD checks reject an observed concurrent clean commit at rollback boundaries;
they are **not atomic** and do not replace the still-open shared lease/Git CAS.

Actual RED evidence: restore exit/OSError `wc-run-bnr4cf6n`, clean concurrent
HEAD `wc-run-y6uat9el`, failure-event outage `wc-run-z1hp0zmj`, status128
`wc-run-8gjjjbqb`. The success-event fixture initially selected an unchanged
deploy.sh and was corrected; that setup failure is not a RED reproduction.
The original whitespace fixture already blocked an untracked directory. An
optional attempt to revert the strict parser for RED was rejected by automatic
safety review; no guard change was applied, no bypass or legacy execution
followed. Strict guards stayed in place; only the isolated tracked-file fixture
was improved. Final core/process tests: **24 passed in 69.83 s**,
`wc-run-ukjp37fn`; quick `wc-run-gnpfw86p` passed. The same independent reviewer
found no required correction in the narrow core patch, without approving release.

Next safe delivery is an exact three-path **code-only** release (core, tests,
standalone plan) from current main through normal full/immutable gates. Its
activation plan must contain four-domain code sync and `installers: []`, no
Dashboard deploy and no manual installer requirement. This is not a no-op delta
or an old release replay. The unfinished preview/installer/ownership/lease/intent
work stays on this preservation branch. Code synchronization does not prove the
research calendar, native firing, pilot, model or Stage5 acceptance.
