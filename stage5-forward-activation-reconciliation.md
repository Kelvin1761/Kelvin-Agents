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
installer. Read-only preview and append-only intent/full-gate observation commands
are implemented in nonmain source. The native executor is wired but explicitly
disabled until exact-source review authorization is implemented; it is not
released or accepted and no production action is done.

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


## Concurrent plist ownership reproduction — 2026-10-29

The separate core delivery above is now complete:244a7bb54187bfc58d86be65fcca5e51451e7d29,
full clean gate1687.25s, independent quick15.8s, approval/merge and code-only
activation succeeded on2026-10-28 at18:53:50/18:53:52/18:54:06 UTC.
No installer ran. This preservation branch is still unfinished and unapproved.

Three new real-installer fixtures deliberately assert rejection before any
launchctl mutation when an independent actor replaces, removes or creates an
allowlisted plist after snapshot. They use isolated HOME, fake launchctl and
unloaded jobs, so a loaded-without-plist guard cannot hide the ownership defect.
These fixtures intentionally remain RED until ownership is implemented; do not
release this WIP or treat its older green test count as current acceptance.

The required fix must bind an attempt identity and snapshot proof hash to exact
candidate plist bytes/absence and mode before any live mutation. Candidate
bytes must come from the same trusted renderer used by the actual installers;
observing arbitrary current bytes and claiming them afterwards is forbidden.
Recovery may touch only that attempt's proved writes. Current state must match
its owned postimage (or already match the original state), otherwise retain
all evidence and stop before pointer restoration, bootout, overwrite or remove.

Hash checks alone do not close the race. Rendering, ownership journal, install
and recovery must participate in shared cutover exclusion with domain jobs;
recheck under that exclusion immediately before each mutation. Test concurrent
replacement/removal both before recovery entry and between verification and
write. Do not call a pre-check plus later cp/rm an atomic CAS. No opportunistic
adoption, forced job stop, external-actor rollback or target rebinding is allowed.
An incomplete ownership helper must not be published as the complete workflow.

Observed RED: all3 assertions failed because the real installer returned0 after
changing the unowned state,41.16s, wc-run-cen8ops0. Quick passed
wc-run-k5uon62w; it does not run these tests or certify installation safety.
No expected-failure marker or relaxed assertion conceals these blockers.
This checkpoint is deliberately incomplete non-main preservation, not delivery.

## Actual candidate rendering source — 2026-10-30

The four real domain/Central installers now expose side-effect-free
`--render-only DEST` entrypoints. HKJC/NBA share their normal template loops,
Tennis shares `install_one`, and Central durability/research use the same
render functions as normal installation. Rendering skips launchctl, script
chmod, runtime/repository log creation, research initialization and receipt
writes. Tennis still checks that its configured runtime inputs exist; it does
not open the fixture database or source provider configuration.

The unified installer also has a render-only mode. It calls those real
entrypoints, requires a new destination and checks exactly its20 allowlisted
labels, plist structure/label, regular non-symlink files, size and mode. It does
not run the ordinary installation path. This removes the need to invent
candidate hashes from arbitrary observed installed bytes. It does not yet
create an ownership journal, hold a shared cutover lease, authorize writes or
complete a compare-and-swap operation. The three ownership REDs remain open.

Actual render-entrypoint RED4 was reproduced before changing source. After
implementation all5 miniature-checkout cases (four families plus unified20)
pass without calling fake launchctl or modifying checkout/runtime files or
creating log directories. Combined selected existing installer/snapshot tests:
37passed,3known ownership cases explicitly deselected,252.20s,
wc-run-q69ux1_n. This is not a claim that the entire WIP suite passes.
Shell syntax checks and quick wc-run-iv8v2ijr pass; goldens unchanged.
No full/immutable gate, release, installation, live job/configuration or model
change was performed. This is unfinished non-main source preservation only.

Next connect these authoritative rendered candidates to a before-write,
attempt-bound journal, shared cutover exclusion and ownership-aware recovery.
Do not accept current files as proof of our writes or publish rendering as the
approved forward workflow. Retain the exact-target provenance/cadence limits.

## Cooperative cutover lease source — 2026-10-30

`runtime_cutover_lease.py` now implements a stable mode600, owner/inode-bound
flock file in Control. It never unlinks the lock file. Normal domain jobs use
shared locks; native snapshots, installation and recovery use exclusive locks.
Busy acquisition returns75 before job/runtime mutation. Inherited exclusive
ownership is verified against both file identity and kernel locking; a shared
or unlocked descriptor cannot authorize an exclusive operation. Invalid proof
fails closed. Child execution retains the descriptor, and the parent holds its
lease until the leased command finishes.

The unified native installer and all five subordinate installation entrypoints
participate in exclusive exclusion. Pure rendering/status stay read-only.
AU/HKJC/NBA/Tennis and Central scheduled shell launchers participate before
configuration/self-update, with nine direct Python CLI entrypoints acquiring
before imports (including Tennis preclose and Central review/durability).
Existing domain daily/preclose locks remain separate and unchanged. The
long-lived AU command bot is not given a lifetime shared lease: it is the
approved controller caller and AU is not reinstalled. Finite AU daily/health
work does participate. No process is force-stopped.

A child created with subprocess close_fds can retain a stale environment FD.
Only a proved EBADF marker is discarded by a scheduler; it must then acquire
a fresh kernel shared lock, so an active exclusive cutover still returns75.
This does not confer inherited exclusive authority. Descriptor identity errors
and unsafe lock paths continue to block. Nested acceptance work that loses an
exclusive descriptor must defer rather than run without protection; complete
native acceptance remains required.

This is cooperative exclusion, not protection against arbitrary nonparticipating
writers or old jobs that started before these entrypoints existed. Complete
active-run discovery and authoritative attempt/write ownership are still open;
the three concurrent-plist ownership REDs are unchanged. No shared-lease source
checkpoint may be called complete installation reconciliation or installation
acceptance. No live installer or scheduler was run for these tests.

Real shared-reader/native-snapshot RED: wc-run-k83umo6a,1failed before wiring.
Kernel lease/real snapshot selected tests then18passed,3ownership cases
explicitly deselected,63.70s,wc-run-nu0gfwep. Actual miniature Python-X,
shell/standalone installer and renderer checks33passed,wc-run-6jqwziv3.
Closed-parent-FD RED2 was reproduced, then fresh-shared reacquisition implemented.
The combined selected run wc-run-vk1om9u9 produced66passed,2fixture setup
failures,3known ownership cases deselected,180.61s. Two miniature research
installer cases lacked the new lease helper. The fixture now copies the real
helper and requires a native command boundary marker for every fault case,
so setup errors cannot masquerade as recovery success. Corrected interruption,
copy failure, bootstrap failure, concurrent writer and success cases all5pass,
10.73s,wc-run-9u3ek8o0. These setup failures are not claimed as runtime REDs.
Final quick wc-run-9vcd5n41 and modified-shell syntax checks pass; goldens
unchanged. None of these results is a full immutable release gate. The3real
ownership REDs remain and forbid installer release or installation acceptance.

## Attempt-bound journal and publisher API — 2026-10-30

`runtime_install_journal.py` now implements a pre-write plan under the verified
exclusive cutover lease. It requires a private owner-bound snapshot, its valid
20-job original-state proof, exactly20 real rendered candidate plists, a full
source-SHA metadata field and an unchanged current observation. The source SHA
is binding metadata; it is not approval or evidence that deployment occurred.
A unique attempt ID, snapshot/agents/domain roots, original proof hash and
candidate hashes/modes are stored in a new mode600 append-only plan, with file
and directory fsync. Existing records are rejected rather than rewritten.

Each job needs a separately bound begin record BEFORE a caller unloads it,
publishes a file or changes flags. Publication reads only the prebound renderer
output, verifies the original target, writes a staged file, rechecks the lease
and target identity, then uses atomic replacement and directory fsync. A target
change detected before replacement retains the staged evidence. These are
cooperative-lease checks, not a POSIX atomic conditional swap against arbitrary
nonparticipating writers. That limitation remains material.

The API also binds the snapshot's existing Tennis pointer path, prior bytes/mode
and candidate bytes, with separate pre-write pointer intent and publication.
It never opens or moves the database. Recovery verification checks every changed
job and pointer before any caller mutation, rejects missing/damaged/unknown or
cross-attempt intent records and unowned postimages, and never silently skips
a damaged record merely because the runtime currently matches its old state.
A begin record is planned write intent, not a native-command execution receipt.

Validation uses actual four-family/unified rendering to produce all20 candidate
files in isolated HOME, a fake read-only launchctl observer and real kernel
leases. Core+lease+renderer selection50passed in7.56s,wc-run-qv2ovujr.
After enforcing private snapshot/journal directories, final15 journal cases
passed in5.76s,wc-run-3uwvj16p; quick wc-run-hsc9y5le passed, goldens unchanged.
Fixtures cover unknown replace/remove/create, changed candidate, missing begin,
foreign writes before/after pointer publication, cross-snapshot and symlink/
damaged proofs, no inherited EX authority and positive prebound publication.

IMPORTANT: this API/CLI is not yet wired into the native installer mutation and
recovery paths. No actual installation, release/full immutable gate, historical
proof mutation or deployment was performed. The existing3 real-installer
ownership REDs therefore remain unresolved. This checkpoint must not be
released or represented as an accepted forward workflow. Next wire journal
preparation/begin/publication/recovery into real installers and bind the
controller's outer snapshot to the same attempt; cover pointer and job changes
before every mutation and retain inner backups when recovery is blocked.
Complete old/nonparticipating active-run discovery and independently review
exact source before any normal full/immutable release gates or native acceptance.


## Native ownership integration — 2026-10-30 (unfinished source)

The unified installer and all five subordinate installers now consume the real
journal: prepare from actual rendered candidates, begin before native mutation,
and publish only the prebound bytes. The Central activation controller passes
its exact outer snapshot and immutable expected SHA to the unified installer.
The installer rechecks checkout SHA before preparation and completion; journal
commands reject a different checkout. This binds separate snapshot/install calls
to one attempt, without claiming a controller-wide exclusive lease.

Recovery verifies every job and pointer before any native mutation, rejects
unknown postimages and damaged/missing intents, then rechecks each changed job
before its mutations. A snapshot with no journal can only verify an exact no-op.
Failed attempts retain backups, including blocked recovery. Bound research
installer cleanup delegates recovery to the unified owner instead of executing
its standalone rollback around that owner's gates. No legacy NBA label outside
the allowlist is stopped by a bound attempt.

The three original actual-installer concurrent replace/remove/create REDs now
pass without relaxed assertions. Snapshot/journal final selection passed31 in
130.68s (wc-run-vt6xzbld). A new real pointer test first failed because identical
bytes with a changed mode skipped restoration; recovery now checks the original
mode and verifies pointer plus jobs before success. Controller snapshot/SHA
selection passed6 in11.07s (wc-run-l3cy28o7). The actual installer outer-attempt
success/conflict fixtures passed2 in119.47s (wc-run-rzou9b13), preserving foreign
bytes and evidence before native mutation on conflict. The foreign-calendar
fixture passed with unknown bytes retained and recovery blocked; this is a
safety result, not installation acceptance. Other selected regressions passed67
with11 explicitly deselected native fixture cases (wc-run-5n57nx9o).

All native tests use isolated HOME and fake launchctl/acceptance; no live native
installation, release, merge, model/data/history mutation or full immutable gate
was performed. Full source gates have not been claimed. The before-write checks
and atomic replacement are still cooperative, not POSIX conditional CAS against
arbitrary nonparticipants. Complete discovery of old/nonparticipating active
runs remains open. Next integrate that real active-run guard, then finish the
append-only forward intent/gate/executor and independent exact-source review.
Exact target deployment provenance and the foreign cadence hold remain required;
this unfinished source must stay on its owned nonmain WIP branch.

Final bound bootstrap-failure integration passed1 with28deselected in360.58s
(wc-run-0n3x2ao1). It requires unified recovery ownership, exact original pointer,
only prior AU plists, retained native snapshot and all21 pre-write intents.
This six-minute isolated fixture does not establish production activation or
rollback deadline compliance; timing/timeout recovery remains to be assessed
without weakening existing deadlines. Final quick wc-run-mw6wdzbt passed, all
modified shell syntax checks passed and git diff --check passed. No full gate.


## Native active-run preflight gaps — 2026-10-31 (unfinished source)

The actual installer preflight now recognizes all nine scheduled Python CLI
entrypoints and seven scheduled shell launchers, including relative script
operands, Python -X/-W options and module invocation. Matching is anchored at
the executable and script/module operand so release --path arguments and pytest
filenames do not become running jobs. A process-discovery error now blocks:
only pgrep status1 proves the probe found no match; statuses2/127 no longer
fall through to cutover. The AU long-lived Telegram poller remains excluded;
finite AU jobs are covered. No existing native deadline or lease was weakened.

Before implementation,12 REDs reproduced10 missed commands and2 fail-open
probe errors (3 other tests passed, wc-run-a1x_5sa_). Final24 targeted cases pass
in3.74s (wc-run-jg_0qs5u), including real macOS extended-regex execution and the
actual native preflight detecting an owned harmless relative Python -X sleeper.
The sleeper is a temporary test process; no real scheduler or launchd job runs.

This closes the enumerated command forms, NOT the full old/nonparticipant
exclusion requirement. pgrep observes flattened command text, so arbitrary
quoted paths, dynamic shell/-c invocation and observation-to-mutation races
remain unproven. The next implementation needs exact kernel argv and process
identity/probe failure handling, integrated into native install/recovery rather
than more parallel helper-only evidence. Local SDK sysctl.h confirms CTL_KERN1,
KERN_ARGMAX8 and KERN_PROCARGS2=49; no kernel argv code is implemented yet.
Preserve fail-closed discovery and negative release-scope checks during that
replacement. Timeout/cancellation recovery and production deadline compliance
also remain open; do not lengthen deadlines to make the six-minute fixture pass.
No full source/immutable gate, release, merge, activation or installation
acceptance is claimed by this WIP. All earlier provenance/foreign-cadence holds
and Tasks6–10/latches remain unchanged.

Final affected installer regressions40passed12deselected in48.29s
(wc-run-keq08vga); final quick wc-run-xl4ega70 passed, native shell syntax
and diff checks passed. Original source goldens remain unchanged. Full source
and immutable approval gates remain unrun for this unfinished workflow.


## Forward intent command checkpoint

Central now exposes `reconcile-installation-intent` with explicit source SHA,
target SHA and actor. The command reuses strict preview eligibility, observes it
again before publication, and appends a hashed request binding release IDs,
exact manifest byte hashes, four production roots and rollback SHA. Publication
uses exclusive file creation through a hard link plus fsync. Existing evidence
is retained. The intent is pending a fresh gate and carries installation
authorization false. No live intent was created during implementation.

Focused reconciliation and Central CLI tests passed 38 cases. The preview
retains its read-only behavior. Fresh gate, independent approval, append-only
execution outcomes and the native executor remain required before this workflow
can install anything. Current changed-dependency and target-provenance holds
continue to apply.


## November 8 native executor integration — disabled source WIP

The same previously authorized independent reviewer resumed and identified a
production integration defect: intent manifest hashing assumed commit filenames,
while real releases use encoded release-ID filenames. The fixture now uses the
actual naming convention; the pre-fix test failed with FileNotFoundError. Both
hash sites now resolve the exact manifest through `_load_release`; 38 tests
passed after that repair.

Central exposes `reconcile-installation-execute --intent HASH --actor TEXT`.
The actual executor holds one serial release lock through fresh clean immutable
full and independent quick gates, then one kernel EX cutover lease through native
snapshot/install/status/recovery. `_run_installer` explicitly passes the verified
lease FD and environment marker. A real child interpreter verifies inherited EX;
separate orchestration fixtures use isolated repositories and fake native actions.
A durable per-intent directory claims the attempt before native work. Claimed
attempts cannot replay, including after interruption or unavailable outcome
storage. Snapshot120/install300/status60/restore300 deadlines are unchanged.
Native recovery never syncs/resets Git or rewrites historical release events,
and retains snapshots/outcomes. Recovery validates local exact-target source and
native journal ownership without requiring remote availability. Both live gate
receipts are checked again under EX before the claim and after snapshot, before
installation begins. This is cooperative exclusion, not POSIX conditional CAS
against nonparticipants.

**Native execution is explicitly disabled:** `_require_installation_review`
raises before gates/claim/native calls because exact-source immutable review
binding is not implemented. Actor text, historical approvals and saved gate JSON
cannot bypass this guard. Orchestration tests explicitly replace this disabled
guard; they are not runtime authority. Even the positive orchestration outcome
is `installed_pending_acceptance` with native acceptance false. Exact target
provenance/dependency review, process-boundary limitations, independent final
source review and separate calendar/native-receipt acceptance remain mandatory.
No live intent, installer, job/configuration, model/data/history mutation,
release/merge/activation or full immutable gate was run for this checkpoint.

Final affected reconciliation/activation/Central CLI selection: **76 passed in
54.59s**, log `/private/tmp/stage5-forward-executor-final.log`. Quick checks and
`git diff --check` passed; scoring goldens unchanged. The same authorized reviewer
confirmed the narrow recovery/freshness/disabled-authority corrections by source
inspection, with no further must-fix for this disabled WIP; this is not independent
execution verification or installation approval. No full source gate was run.


## November 8 native acceptance integration — authority still disabled

Actual research receipt publication now adds installation attempt ID, plan hash
and source SHA before hashing and create-only publication whenever running under
the verified native installation journal. Normal unbound research runs retain
existing behavior. A new plan timestamp requires acceptance receipts to postdate
preparation; timestamp alone is not accepted as attempt identity.

The bound research installer records `.native-acceptance.json` through the
existing journal. Both recording and verification invoke the authoritative
native read-only status wrapper directly, preserving the kernel EX descriptor.
No caller-supplied `verified` report is accepted. The verifier returns the SHA256
of bytes read by its own receipt descriptor. Journal checks compare that hash,
full parsed receipt and installation identity to the plan and immutable proof.
This detects the reviewed A/B/A substitution case. Receipt paths must be
canonical absolute paths inside the existing Central run root, without `..` or
symlink components. Proofs are create-only, private and retained with the outer
snapshot; mismatched, stale, cross-attempt or changed receipts block acceptance.

Unified `--acceptance-status SNAPSHOT` rechecks that receipt, actual installed
calendar, loaded runtime and receipt continuity. The actual forward executor now
calls that boundary after the four-domain exact-SHA required-file checks. Its
positive *isolated orchestration fixture* may project `installed_verified` only
after this boundary succeeds; failed acceptance uses the existing owned native
recovery and never writes a success outcome. This is source engineering and
fixture evidence, not production acceptance, scheduled firing or SLA evidence.

The same authorized read-only reviewer initially identified caller-report
trust, receipt-read continuity and missing native run identity. All three were
corrected, and that reviewer found no further must-fix in this narrow source
scope. Reported tests were not independently run by the reviewer.

**Review authority remains unavailable and native execution remains disabled.**
The reviewer inspected existing release events, evidence stores and approval
code: hashes, actor text, local mode600 files and clean gates do not independently
authenticate a reviewer assessment. Existing authenticated Telegram identifies a
human command, not the independent review result. Do not manufacture a key,
credential, actor allowlist or caller-pasted transcript as a trust boundary.
Pending review request/assessment interfaces must bind exact intent/source/
target tree/manifests/roots and per-dependency deltas, preserve explicit blocked
and unresolved decisions, and remain nonauthorizing until a real trusted
publication boundary exists. Owned hardening review must not bless foreign NBA
cadence; existing target deployment provenance remains independently mandatory.
`_require_installation_review` still unconditionally blocks native execution.

Focused journal/reconciliation/native research status tests: 108 passed in40.23s
(`/private/tmp/stage5-native-acceptance-continuity.log`). Actual outer-cutover
fixture using real journal/native publication/status code and fake launchctl:
1 passed in31.12s (`/private/tmp/stage5-native-acceptance-bound-run.log`), including
receipt-byte tampering rejection before native calls. Separate unit binding tests
explicitly mock native outcomes; they do not provide authority. Quick checks,
modified shell syntax and diff checks passed; scoring goldens unchanged. No full
source/immutable release gate, live review/intent, installation, job/configuration,
DB/history/model mutation, merge or activation was performed.

Final actual installer plus snapshot-recovery selection: **72 passed in370.81s**,
log `/private/tmp/stage5-native-acceptance-installer-recovery.log`. All7 isolated
full-cutover cases ran through the existing controller deadline300; slowest
bound-bootstrap failure68.11s, acceptance failure62.72s, outer success29.84s.
Cancellation, native ownership and restore regressions passed. This remains
focused fixture evidence, not a full source/immutable gate or production-native
acceptance. The final source was unchanged throughout that selection.


## November 8 pending review request — no authority granted

Central now exposes `reconcile-installation-review-request` with explicit source
SHA, target SHA and requester. A shared internal observer still requires the
owned failed source, current remote main, ancestry, canonical source and target
approval/deployment provenance, exact remote release branches and four explicit
clean production roots. Changed dependencies can reach only
`pending_independent_review` in this request path after those checks pass. Public
strict preview continues to block changes; gate-ready intent creation and native
execution are not enabled by this pending state. Target provenance is never
waived merely to obtain a request.

The create-only private request binds pending intent material and its digest:
source/target/release IDs, raw canonical manifest byte hashes, all roots,
rollback target and installer allowlist. This is not an execution intent and is
stored separately. Material includes immutable source/target tree IDs, NUL-safe
raw Git dependency paths, AMDT change kinds, old/new modes, blob identities,
exact binary-byte SHA256/size, inventory digest and binary full-index patch
digest. Added/deleted/mode-only changes are represented explicitly. Unsupported
object modes and oversized individual blobs block preparation. Binary bytes are
read as bytes, not decoded text. No gate, native runner, approval or notification
is invoked. There is no assessment publication or approval CLI.

The reviewer found that Git pathspec magic could select different patch inputs.
An actual fixture named `:(exclude)shadow.py` with a decoy reproduced a missing
patch digest (1 failed/1 passed); global `--literal-pathspecs` fixes the path
identity. Bracketed and newline filenames remain covered. A separate interleaving
fixture reproduced manifest bytes changing during material collection. Manifest
bindings are now captured before material generation and compared last after the
second material observation. Requests reobserve refs/provenance/roots and exact
material before publication; this is observation, not an atomic remote-state CAS
or permission to execute later without fresh validation.

All request authority fields remain false: installation, gate, authenticated
assessment and execution-intent creation. Request hashes are rejected as
execution intent selectors. `_require_installation_review` remains unconditional.
Future assessment/trusted-publication integration must strictly reload and
recompute these bindings, preserve blocked/unresolved per-delta decisions and
never turn a caller-supplied actor, pasted transcript or ordinary hash into
review authority. Foreign cadence/model scope and target provenance holds remain.

Final reconciliation plus Central CLI selection: **65 passed in31.71s**, log
`/private/tmp/stage5-review-request-green.log`. The same authorized read-only
reviewer confirmed the narrow pathspec and manifest-ordering corrections with no
further required correction in this scope; tests were not independently run.
No live request/intent, gate, installation, release, merge, activation, Telegram,
model/data/history or production configuration writes occurred. This remains
unfinished nonmain workflow engineering, not Stage5 or installation acceptance.

Final quick and diff checks passed; scoring goldens unchanged. No full source or immutable release gate was run for this unfinished checkpoint.
