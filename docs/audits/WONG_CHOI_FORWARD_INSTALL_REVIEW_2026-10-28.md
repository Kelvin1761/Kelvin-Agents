# Forward-only installation: independent review blocks cutover

Kelvin approved the forward-only workflow and subsequently authorized one
independent **read-only** subagent review. Reviewer Wegener
`01a1813b-719c-7b22-870f-7a2cd3cb31dd` returned **BLOCKED for installation**.
This records the review, not a new approval or historical evidence rewrite.

## Exact reviewed state

- Original own failed installer: `e7e1d28e0076f9981b8bf135cfc1f42eb90c353f`.
- Observed target: `51ea46ef359f24a87029376a99f944f0c982dab6`.
- Review worktree HEAD: `928c2dd0582d34c598becf0115bfe364c804150a`, plus parent WIP.
- Reviewer observed local origin/main, primary and production HEAD at target.
  Its own live remote check failed DNS; it did not verify server main. The
  parent's earlier actual preview did reach remote main and returned blocked
  on changed dependencies. Neither observation is reusable at activation time.
- No reviewer edits, installs, release events, notifications or approvals.

## Findings

1. **Changed installation behavior.** `315f9ddc` adds NBA timer validation and
   changes the busy regex in `install_production_runtime.sh`. NBA postgame
   template gains a 900-second interval and incremental-results argument.
   `199364e2` expands final refresh from 06:30 to 06:30/08:30/10:00/11:30/13:00.
   New scheduled behavior includes fetching, local market-ledger settlement and
   Dashboard publication. This is not authority derived from old e7. Review
   did not find an external D1 ledger write in that incremental-results path.
2. **Real import dependencies.** Native review imports settlement readers,
   which import `unified_reflector_core`; its import-time label helper loads
   changed renderers/scoring. Scoring drift cannot all be dismissed as noise.
   Possible lazy imports do not prove those routines execute during installation.
3. **Target provenance gap.** Target has hash-valid linked approval/merge, but
   `production_sync_domains: []`; success has `verification: []`, `installers: []`.
   No inspected target event proves four-domain runtime deployment. Matching
   Git HEAD/main membership cannot substitute. Event hashes prove integrity,
   not independent human authorization; inspected manifests have no content hash.
4. **Busy guard gaps.** Target regex misses relative scheduler paths,
   `python3 -X dev /repo/nba_daily_schedule.py`, and Tennis preclose. It is a
   one-time check, not shared exclusion against jobs starting during cutover.
   Startup templates can launch work through RunAtLoad.
5. **Outer rollback risk.** `restore_runtime` bootouts/copies/removes plists
   without comparing concurrent ownership or preserving prior loaded state.
   `--restore` returns before the busy preflight. Existing activation invokes
   it after failure, including busy deferral. Historical failure receipts prove
   this call sequence; they do **not** prove whether a real job was interrupted.
   Do not backdate a clean acceptance or assert a historical interruption.

Source's full gate, linked approval/merge and busy-guard failure were verified.
Target's linked approval/merge is observed historical provenance only; this
chat has not approved that foreign release or its changed scheduled behavior.

## Implementation boundary and next steps

The new `reconcile-installation-preview` is deliberately read-only and cannot
write intents, approve, install or notify. Its dependency check is a conservative
runtime-source superset, not a proved minimal import closure. The first expanded
inventory had 139 changed files; review identified omitted Tennis launchd and
root imports. Those omissions were added to the guard with regression tests;
the final observed inventory count was **140**, not the earlier 139. False positives stop work
for review rather than silently blessing a changed dependency.

The same authorized reviewer then found two preview-only false-eligibility
defects: failed `git status` was treated as clean by a tolerant helper, and
tolerant event loading could omit a damaged negative event. Five RED cases
were reproduced in `wc-run-ltluwbfx`. The preview now checks status exit codes
and strictly reads every selected canonical event, validating hash, schema,
release/commit identity, kind, detail, actor and timezone. The reviewer found
one further ordering defect: a hash-valid rejection could be renamed to sort
before approval. This was reproduced RED in `wc-run-2fmvb1c2`, then fixed by
requiring the canonical writer filename and ordering validated events by aware
timestamp/content hash. The independent reviewer confirmed that narrow fix;
installation remained blocked. No existing status projection or event changed.
Final targeted preview/CLI tests passed **34 in 18.73 seconds**,
`wc-run-i4jr_jxt`. Final quick check passed `wc-run-jvgkjisw`, with unchanged
AU/HKJC scoring goldens and the existing AU-neutral/HKJC-stale-baseline warnings.
The full runner started before these final review corrections; a passing run
plus later focused corrections is WIP validation, **not** immutable release
approval of the final source. A future release still needs its full source and
clean immutable-SHA gates. No gate receipt has been emitted by the preview.
Full check session `94274` is now **terminal exit 0**: all 16 suites passed,
1891 seconds, retained scratch `wc-run-oxqbxio6`. Shared Wong Choi reported
1777 passed; Central 64 passed; Tennis 866 passed. Do not restart that completed
handle or represent its earlier collection as covering the later added cases.

Continue source engineering on the owned non-main branch: specify the actual
dependency inventory and implement shared cutover exclusion, no-op recovery
after preflight deferral, ownership-aware rollback and loaded-state preservation.
Have the authorized reviewer assess the resulting exact changes. Keep existing
immutable activation targets and old manifests intact. No manual installation,
blind refresh, fake source delta, forced job stop or target override.

The append-only intent/gate/executor is **not implemented** by this preview.
Before cutover it must bind the exact target/source, independently reviewed
dependency bytes, existing target approval/deployment provenance and captured
external state; pass fresh full gates and independent SHA rechecks; retain normal
locks, preflights, snapshots and concurrency-safe rollback; verify all4 files,
installed/loaded state, actual calendar and native receipt. Rebinding or new
source means fresh review. Test success is not cadence or Stage5 acceptance.

## Follow-up source correction: unchanged recovery / loaded flags

The same authorized read-only reviewer inspected the new snapshot-state helper
and unified installer changes. It confirmed unchanged-state recovery no longer
mutates launchd, and missing/damaged proof, changed backup bytes and loaded jobs
without restorable plists fail closed. It then identified ignored bootout failure
and bootstrap-before-enable ordering; both were reproduced with a stateful fake
launchctl and corrected. The reviewer confirmed those narrow corrections by
inspection, without running tests or granting deployment authority.

Final isolated installer/snapshot regression suite: **32 passed in 190.11 s**,
`wc-run-_17sv_i7`; quick `wc-run-g9ahdi67` passed. Prior loaded/disabled flags are
now recorded; changed-state recovery touches changed labels only, checks unload/
copy/enable failures, enables before bootstrap and verifies final files and flags.
This does not resolve concurrent ownership of changed plists or shared cutover
exclusion/active-run discovery. It is unmerged WIP, not installed, and the earlier
1891-second full run predates this source. No historical snapshot/event was
rewritten and no live installer/job mutation occurred.
