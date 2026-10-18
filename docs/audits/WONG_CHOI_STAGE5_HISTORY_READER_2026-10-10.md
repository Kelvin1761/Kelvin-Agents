# Stage 5 complete-history reader repair — inventory component

## Authority and scope

Local engineering under the active Stage 5 goal, based on production/main
`e508754ab9ca40db059eefcbced8fc1986c164f6`. No commit, push, release,
merge, activation, installer/scheduler change, deletion, model/ruler change,
holdout access, database mutation or promotion. This is not a completed live fix.

Current exact local scope is seven paths: `research_prediction_pages.py`,
`research_prediction_artifacts.py`, `research_prediction_page_runtime.py`,
`research_supervision.py`, matching `test_research_prediction_pages.py` and
`test_research_prediction_page_runtime.py` under `.agents/skills/shared_wong_choi/`,
and this audit. This replaces the earlier four-path inventory component scope;
no save/push/release authority is inferred from the scope description.

## Confirmed failure

The native Central review receipt
`/Users/imac/WongChoiData/WongChoiControl/runs/central/2026-10-09/research-review/165313.437512Z-c7b49a64bd04.json`
is hash-valid but partial. AU/HKJC phase outcomes both raise
`prediction artifact reference limit exceeded`. The legacy reader processes all
domain predictions before checking its 5,000-reference bound. Both independent
label and feature inspectors call that same reader; changing the initial bound
alone would leave blob and compact-report limits unresolved.

## Implemented component

- Freeze a complete canonical, as-of metadata inventory under existing native
  record/byte limits; bind record bytes and model-release parent bytes and
  recheck source directories/files before return.
- Deterministically plan complete bundles with at most 100 records and 5,000
  references per page. Never split a bundle or increase the existing reference
  limit. Oversized bundles fail closed.
- Bind each page to the whole inventory hash, exact page index/count, ordered
  record IDs, limits and next-page index. Rehashed omitted, duplicate,
  reordered or policy-modified plans are rejected.
- The inventory explicitly leaves artifact contents, complete source coverage
  and model promotion unverified/false. A valid plan is not a completed page.
- A whole-source rebuild detects a narrowed but rehashed inventory, changed
  parent/record bytes or appended source. Native checkpoint exceptions remain
  authoritative; no catch converts preemption to success.

## Observed verification

TDD RED: new import missing, collection exit 2. First focused run passed 6 tests.
Expanded run initially had one failure because the test expected `ValueError`
instead of native `ResearchIndexError` for concurrent directory append; corrected
the assertion, not the native fail-closed behavior. Expanded new + legacy artifact
suite: **33 passed**, exit 0. No-cache ruff passed before expanded tests; a final
quick gate subsequently passed, including unchanged AU/HKJC 120-horse goldens.
The first quick invocation was denied ruff cache writes by the sandbox; the same
gate passed after a scoped cache-write escalation, without disabling checks.
Local meeting corpus checks were skipped and do not prove live data quality.
Full gate for this new scope
is not yet complete. The earlier full gate in the separate digest worktree
(`39802`) reached terminal exit 0, all 15 suites passed; it does not cover this
component. The new reader gate can now run separately; do not run a second heavy gate
concurrently or report its result as evidence for these new paths.

Read-only real metadata inventory/rebuild at
`2026-10-10T01:03:13.982158+00:00`:

| Domain | Records | References | Pages | References per page |
|---|---:|---:|---:|---|
| AU | 467 | 18,339 | 5 | 3949, 3835, 3953, 4076, 2526 |
| HKJC | 111 | 8,050 | 2 | 4997, 3053 |

All planned record IDs cover the full inventory once. AU inventory hash:
`5cc36f677d9b02f8805645324b29a6270a75e5ed6510b33e7120e952954b58c4`;
HKJC: `e86f21a31fed9c9ecd333dcada991ae1e84e505c5d6ae5ba5ea3d030b666bd1d`.
No artifact content reads, frozen dataset creation or sample/power authority.

## Required next implementation and acceptance

1. Execute each exact inventory-bound page through native bundle integrity and
   bounded blob reads under the process supervisor/production locks/WARM guard.
   Persist create-only page proofs and reconcile uncertain publication.
2. Verify full ordered page coverage, source identity and final source recheck
   before publishing an all-history projection. Missing/interrupted/tampered pages
   must not produce complete coverage or a sample trigger.
3. Reuse that completed projection across independent AU/HKJC label and feature
   checks, preserving domain-specific semantics and historical missing/corrupt
   source reporting. Address downstream bounded compact-report aggregation.
4. Add blob-budget, interrupted-resume, WARM-offline, production-preemption,
   oversized-bundle and full/small-corpus equivalence regressions; run quick/full
   gates, then use separately authorized exact-scope release/activation.
5. Obtain fresh real supervised review acceptance before enabling digest delivery.
   Task 6 numeric power profiles remain 0/4; real pilots, Dashboard projection,
   E2 installation and Stage 5 exit remain incomplete.

## Page-content and coverage continuation

- Extracted the existing native single-bundle projection into `_project_prediction`
  with no intended semantic change; both legacy and paged readers use it.
- Added exact-page blob inspection using unchanged native file/aggregate read
  budgets, provenance, relocation and manifest checks. Reads and rechecks are
  bounded per page. Each page pins current prediction and model-release bytes;
  no page alone asserts full corpus/sample/PIT coverage.
- Aggregation requires every expected page in exact order, binds plans to the
  complete inventory, and reconstructs each supplied proof from actual source
  bytes rather than trusting a caller's rehashed success claims. Full metadata
  inventory is checked before and after aggregation. Compact aggregate holds
  page hashes/totals; per-record details stay in bounded page proofs.
- Missing blobs remain visibly unverified even when all pages were visited.
  `page_coverage_complete` is distinct from `artifact_contents_verified` and
  both are distinct from PIT/label/source/sample/model authority.
- RED: new page/aggregate APIs absent, collection exit 2. Initial content tests
  plus legacy artifact tests passed 39. Expanded tests passed 43, including real
  fixture blob verification across 5,100 references, but the first implementation
  took 81.53 seconds due to repeated full metadata reads per page.
- Optimized to read only the exact page and pinned parents at page time, retaining
  whole-inventory verification at aggregation boundaries. Updated-source rerun:
  43 passed in 12.81 seconds. No-cache ruff and quick gate passed; corpus checks
  skipped due to absent local meeting data. These times describe this fixture,
  not a production performance guarantee.
- Independent downstream regression selection: AU/HKJC settlement, feature
  provenance and racing-monitoring sample suites, 49 passed in 0.85 seconds.
  `git diff --check` passed. This verifies unchanged legacy fixture behavior,
  not live downstream adoption of the new page reader.
- Not yet implemented: supervised action binding, create-only page persistence,
  uncertain publication/restart reconciliation, full-corpus downstream label/
  feature integration and live acceptance. No release or production switch.
- New-scope full-gate preflight found native AU production worker PID 5116,
  elapsed 11:30, morning `--skip-review --skip-analysis --rounds 2 --round-gap 300`.
  The new heavy gate was not started while that confirmed-live worker ran.
  Resume by checking that specific process/native production state; do not kill
  production or interpret a stale lock alone as proof of liveness/completion.

## Create-only receipt continuation

- Added `persist_prediction_page`: validates the exact plan/full inventory,
  reconstructs current page contents and writes one bounded receipt using the
  existing fsync + atomic hard-link, create-only report writer. Output directory
  must already exist, be non-symlink, and be supplied by a supervised workspace;
  no implicit persistent-state initialization. Existing identical bytes are
  idempotent; conflict never overwrites the existing file.
- Added explicit read-only `reconcile_prediction_page`: selects only the pinned
  plan filename, bounds reads, rebuilds the current source proof and rechecks
  saved bytes. Missing/tampered/stale receipt does not create or repair anything.
  A valid existing page does not grant sample/PIT/model or whole-corpus authority.
- A failure after atomic publication but before acknowledgement remains a raised
  failure with the receipt left intact. A fault-injection test proves read-only
  reconciliation can verify that exact file without a second write; this is not
  automatic retry/publication authorization.
- Reject symlink receipt directories and nonregular receipt paths (including
  FIFO) before opening. Persisted JSON bytes are bounded as well as compact JSON
  representation; no oversized receipt is linked into place.
- TDD RED: persistence/reconciliation APIs missing, collection exit 2. Initial
  new + legacy artifact suite 48 passed; expanded loss-of-ack, missing receipt,
  FIFO and existing tests **51 passed in 13.91 seconds**. No-cache ruff and
  `git diff --check` passed. No live page receipt was written.
- AU native worker PID 5116 was independently confirmed still live at elapsed
  14:12; the new-scope heavy full gate remains not started. No production process
  was interrupted. Supervisor action binding, full-corpus downstream integration,
  supervised live acceptance, full gate and separately authorized release remain
  outstanding; primitive fixture success does not close those requirements.

## Single-page process-supervisor binding

- Added one explicit `prediction-page` action to existing research supervision,
  not any production scheduler or installer. It remains a metadata-only/no-spec
  action, takes the shared heavy-worker lock, inherits production/WARM/capacity
  preflight, external deadline and process termination, and writes only an owned
  WARM attempt page receipt. No experiment/model registry record is fabricated.
- The input inventory must be an existing non-symlink WARM file with an explicit
  SHA-256 byte witness. Domain/root/as-of, exact page index, bounded policy and
  source inventory identity are verified. The parent bounds output reads, pins
  report/receipt identity and exact ordered record coverage, and reuses the native
  per-record shape/authority verifier; bulk blob reads stay in the child.
- Removed three pre-existing unused imports in the modified supervisor module
  (`hashlib`, `json`, `load_dataset_snapshot`) found by strict no-cache ruff.
  No scoring/model behavior change is intended.
- TDD RED: runtime module absent, collection exit 2. Four real-subprocess initial
  tests passed; expanded runtime + page + legacy artifact suite **61 passed in
  13.68 seconds**. Cases include production defer before opening input, WARM
  offline, heavy-worker busy, external deadline, wrong witness, non-WARM input,
  and parent rejection of rehashed promotion/page-identity/coverage forgeries.
- No-cache ruff on changed runtime/supervisor/page source and runtime tests and
  `git diff --check` passed. Legacy prediction/source supervisor regression
  selection: 5 passed, 67 deselected in 2.06 seconds. Quick gate passed with
  unchanged AU/HKJC 120-horse goldens; local meeting corpus checks skipped.
- Same AU production worker PID 5116 remains confirmed live, elapsed 19:33.
  Full heavy gate is still deferred. No operational page scan, scheduler
  activation, production switch, source deletion, Telegram widening or release.
- Still required: supervised inventory production and multi-page coverage
  orchestration, explicit restart/publication reconciliation, complete downstream
  AU/HKJC adoption, resource/fault matrix and real full-corpus acceptance. Single
  page success does not mean the Central AU/HKJC review failure is fixed live.

## Supervised complete-corpus orchestration and fault evidence

- Added explicit `prediction-corpus` action using the existing process supervisor,
  WARM workspace, production preflight and shared heavy-worker lock. The child
  freezes the full metadata inventory, persists each bounded whole-bundle page,
  rebuilds all pages against current source, rechecks the complete inventory and
  only then publishes a compact final coverage proof. The parent verifies every
  planned page, inventory scope and exact compact totals/hash/authority fields;
  bulk source blob I/O stays in the child.
- The successful status is `prediction_corpus_inventory_only`, not sample or
  model authority. Missing source blobs preserve incomplete artifact status even
  when all metadata pages were visited. No registry experiment is fabricated.
- Runtime regression suite: **22 passed in 61.80 seconds**. This includes a real
  supervised fixture with **1,700 records / 5,100 artifact references / 17 pages**,
  beyond the legacy 5,000-reference cap, without raising the per-page native cap
  or dropping older records. This synthetic source reuses fixture snapshots; it
  proves orchestration coverage, not real production corpus performance/PIT.
- Parent fault checks reject missing inventory/page, forged page hashes, reordered
  page coverage, rehashed changed totals and promotion authority. Production
  lock and deadline checks still defer/terminate without a successful receipt.
- Two additional final-publication fault tests passed (2 passed, 22 deselected,
  0.80 seconds): a failure before publication and loss of acknowledgment after
  publication both raise, preserve existing page evidence and never return a
  successful result. A published file alone is not operational success or retry
  authority. Explicit prior-attempt resume/reconciliation remains outstanding.
- Strict no-cache ruff and `git diff --check` passed. Quick gate passed with both
  120-horse goldens unchanged; meeting corpus checks and full suites were skipped
  by quick mode. AU PID 5116 was confirmed still live at elapsed 28:51, so the new
  source heavy full gate has not started. No production process was interrupted.
- Combined page/inventory, legacy artifact and runtime regression run completed:
  **73 passed in 75.21 seconds**, plus the separately run two publication-fault
  tests above. The combined run collected before those last two tests were added;
  it is not a claim that the full repository gate ran.
- Exact local scope remains seven paths, uncommitted/unpushed/unactivated. Native
  AU/HKJC settlement and feature consumers still call the old whole-corpus API;
  supervised real-corpus acceptance and downstream adoption remain necessary.
  Tasks 6–10, numeric power authority, domain pilots and exit review remain open.

## Explicit prior-attempt reconciliation

- Added `reconcile_prediction_corpus`: read-only reconstruction of an explicitly
  selected existing WARM workspace with both inventory and coverage byte SHA-256
  witnesses. It checks the complete planned page set, reconstructs every page
  from current canonical sources, compares the compact proof and rechecks saved
  bytes. Missing/changed inputs do not trigger writes, repair or retry. Its result
  has `retry_allowed=False` and `model_promotion_allowed=False`.
- Added `prediction-corpus-reconcile` to the existing shared supervisor, not any
  production scheduler/installer. Under the same production/WARM/capacity/lock/
  deadline controls it reconciles the prior workspace, copies only the verified
  inventory/page/coverage evidence into a new owned attempt, then reconstructs
  the copied corpus again before acknowledgment. The parent verifies the exact
  prior byte witnesses and bounded full page coverage. The prior attempt and its
  outcome are never rewritten. Status is explicitly
  `prediction_corpus_reconciled_inventory_only`; it creates no sample/promotion
  authority or experiment registry record.
- TDD RED: missing reconciliation function and subsequently missing runner each
  failed collection. The first implementation misplaced the existing `_inputs`
  return and five prerequisite corpus runs failed with a TypeError; corrected the
  placement, then 28 runtime tests passed. This failure was not hidden or saved.
- Expanded read-only matrix: **9 passed**, covering valid reconstruction, wrong
  inventory/coverage witnesses, missing page, concurrent source append, changed
  blob bytes, wrong domain, symlink workspace and production-preemption callback;
  original workspace bytes are unchanged in every case.
- Supervised reconciliation success and failure/resource matrix plus existing
  small runtime cases: **37 passed, 1 deselected in 16.49 seconds**. Wrong witness,
  missing final coverage, production defer before opening prior input and external
  timeout never produce a successful report. The deselected case is the existing
  1,700-record large corpus fixture, included in the separately launched combined
  regression run. Legacy supervisor prediction/source selection: **4 passed,
  68 deselected in 2.63 seconds**. Strict no-cache ruff, diff check and quick gate
  passed; both 120-horse goldens remain unchanged, local corpus checks skipped.
- AU production PID 5116 independently remained live at elapsed 34:31. Full
  repository gate remains not started; no interruption, commit, push, approval,
  activation, operational scan or model change occurred.
- Downstream adoption must remain genuinely paged: AU/HKJC feature reports have
  independent 256-KiB compact limits, monitoring currently builds whole-record
  maps, and all still call the legacy whole-corpus artifact inspector. Repacking
  all page records into the old 128-KiB prediction report would move the failure
  rather than solve it. Required next work is page-bound feature/label projection,
  exact ordered page coverage with final full source verification and unchanged
  native PIT/earliest-source/settlement gates, followed by real corpus acceptance.
  No cap increase, recent-only window or failed-page-to-zero fallback is allowed.
- Final combined page/inventory, legacy artifact and expanded runtime regression
  run completed: **89 passed in 94.69 seconds**, including the 1,700-record /
  5,100-reference real-supervisor fixture and all new reconciliation/publication
  fault cases. This is focused regression evidence, not a full repository gate or
  production acceptance claim.

## Native AU/HKJC feature-page consumer primitives

- Local engineering scope is now **11 paths**, not the earlier seven. Added
  `research_racing_feature_pages.py` and its matching test, and modified native
  `research_au_feature_provenance.py` / `research_hkjc_feature_provenance.py`.
  Their original whole-corpus entry points are unchanged externally; each now
  delegates the original native per-record projection to a private helper. No
  AU/HKJC model, score, weight, evaluation ruler or production adapter changed.
  This enlarged source scope has no save/push/merge/activation approval.
- The new feature-page inspector first reconstructs the selected bounded native
  prediction page, then calls the appropriate domain's existing feature/PIT
  projection. A versioned wrapper binds inventory, page-plan and prediction-page
  hashes. It preserves the domain report and its blockers; a page never grants
  full source coverage, monitoring samples or promotion. Wrapper size is bounded
  at 256 KiB, and compact final coverage at 128 KiB. Whole bundles are not split
  and no bound is increased to fit a large corpus.
- Complete aggregation requires every deterministic page exactly once/in order,
  reconstructs the current feature proofs and rechecks the full native inventory
  before/after. Final output contains page hashes and counts, not all per-record
  data stuffed back into the legacy report.
- TDD RED: new module absent. Initial native/page comparison suite 40 passed.
  An empty non-racing inventory initially bypassed domain validation; a failing
  test demonstrated it and explicit AU/HKJC validation now rejects it even when
  there are no pages.
- Two additional injected-source tests found a cross-read race: changed Facts
  bytes between prediction verification and feature inspection could otherwise
  leave a native feature claim appearing valid. The new page path now rebuilds
  the prediction page after feature projection and requires identical proof
  bytes. Both domain injection tests reject changes. This does not claim the
  historical whole-corpus entry points were independently repaired for that race.
- Final feature-page plus both native feature suites: **45 passed in 53.30
  seconds**. Each domain's large fixture has 1,300 canonical prediction records,
  more than 5,000 references and 13 pages; every record and feature is covered,
  with no reduced historical window. These repeated snapshot fixtures establish
  engineering coverage only, not real corpus throughput or settled/PIT sample
  acceptance. Modes valid/legacy/future/digest/output/projection exactly preserve
  native per-record decisions. Omitted/reordered/rehashed/count/promotion/source
  append faults are rejected.
- Existing racing monitoring / AU settlement / HKJC settlement suites: **28
  passed in 1.76 seconds**. Strict no-cache ruff, diff check and quick gate passed;
  120-horse AU/HKJC goldens unchanged, local meeting corpus checks skipped.
- AU production PID 5116 remains independently live at elapsed 41:07. Full
  repository gate remains not started. No live feature scan, source mutation,
  deletion, release or activation was performed.
- Still required: supervised feature-page publication/parent receipt binding and
  full-corpus orchestration, paged label/decision joins, native monitoring-sample
  integration, complete resource/fault acceptance and live full corpus proof.
  Production still uses the old whole-corpus API and the live AU/HKJC review
  failure is not yet fixed. Stage 5 Tasks 6–10 remain incomplete.

## Supervised racing feature-page publication and parent binding

- Local history-reader engineering scope is now **13 paths**: added
  `research_racing_feature_page_runtime.py` and its matching runtime tests to the
  previous 11-path scope. These are new local changes, not the earlier E2 13-file
  release. No save/push/merge/activation approval is inferred for this scope.
- Added explicit `racing-feature-page` action to existing process supervision,
  production/WARM/capacity preflight, single-heavy-worker lock and external
  deadline. Input inventory requires an explicit byte SHA-256 witness in WARM.
  The child verifies the complete source inventory before/after its selected page,
  reconstructs prediction and native feature proofs, requires matching prediction
  hash and publishes create-only bounded prediction/feature files to its owned
  attempt. Persisted pretty JSON bytes are checked as well as compact proof size.
- Parent reads only bounded output metadata. It checks exact wrapper keys,
  inventory/page-plan/receipt hashes, validates the companion prediction receipt,
  invokes the native domain feature-report verifier, and checks exact ordered IDs,
  event/cutoff/snapshot/bundle bindings. Opaque source correctness still comes from
  controlled child reconstruction; parent shape checks alone are not a fresh blob
  inspection. No registry experiment, sample authority or promotion is fabricated.
- TDD RED: runtime module absent, collection failed. Initial real-subprocess and
  parent-corruption suite **8 passed in 2.64 seconds**. Expanded suite **15 passed
  in 2.99 seconds**, covering wrong digest, non-WARM inventory, WARM offline,
  production defer before input read, shared-heavy-lock busy and external timeout.
  Rehashed promotion, omitted records, wrong prediction hash, inconsistent feature
  availability and missing companion prediction proof are rejected.
- Publication fault injection before and after feature file linking raises rather
  than returning success. Existing prediction proof and any published feature
  proof remain available for explicit reconciliation; there is no automatic retry
  or rollback/deletion. These are worker-level fault tests, not a live incident.
- Combined existing small prediction runtime plus new feature runtime:
  **52 passed, 1 deselected in 15.05 seconds**. Subsequent record-bound tests for
  both domains: **2 passed, 15 deselected in 5.40 seconds**, preserving exactly 100
  records/features at the declared page bound. No corpus was truncated to pass.
- Strict no-cache ruff and diff check passed. Quick gate passed with both 120-horse
  goldens unchanged; local corpus checks and full suites were skipped. AU PID
  5116 remained independently live at elapsed 45:44; full repository gate was
  not started, and production was not interrupted.
- Still required: full-corpus feature orchestration and reconciliation, native
  paged label/decision joins and monitoring sample adoption, resource/fault/live
  corpus acceptance and authorized release. Single-page success does not close
  the live AU/HKJC review failure or Stage 5 Tasks 6–10.
- Final expanded feature runtime plus selected legacy supervisor regression:
  **21 passed, 68 deselected in 8.00 seconds**. This includes both new 100-record
  page cases; it is not the full supervisor suite or full repository gate.

## Recovery after interrupted full-corpus work and full-gate start

- The attempted next feature-corpus TDD patch was not executed: the approval
  reviewer reported a usage-limit failure before any tool action. Subsequent
  read-only inspection confirms no `RacingFeatureCorpus` import or new corpus
  test appeared. The valid 13-path source remains intact; no partial patch was
  assumed successful and no approval check was bypassed.
- AU PID 5116 is now absent, and a read-only process inventory showed no other
  production schedule, pytest or full-gate process before starting this gate.
  WARM is mounted, with 877 GiB available. Started the first full repository gate
  for the present 13-path history-reader version, command `./檢查.sh`, Node 20.20.2
  and the previously verified WARM TMPDIR. Unified exec session **7881** is live;
  this is IN PROGRESS, not a passing final result. Re-poll that handle rather than
  restart on an observation timeout. No code changes while it runs.
- Initial output confirms unchanged 120-horse AU/HKJC goldens, code/docs checks,
  AU 684, AU daily 366, AU racing 7, HKJC 146, HKJC daily 72 and HKJC extractor 48
  tests passed. Local meeting corpus checks skipped. Remaining suites, especially
  Shared Wong Choi, are not yet proven.
- Independently verified remote `origin/main` and production HEAD are now
  `d52daf7f5627004369db0895dadeb806d00fa512`; production has only the two expected
  mutable AU/HKJC JSON paths dirty. This worktree remains on `e508754ab9ca`.
  Upstream changed release automation, evaluation/domain code and Dashboard but
  not the selected 13 candidate paths. Gate on the old base is useful regression
  evidence only; refresh onto current main and re-gate before any release. Do not
  replace frozen ruler bindings to rescue a candidate.
- User's replacement AGENTS instructions and current production automation config
  authorize automatic immutable-SHA approval after the existing checks. This does
  not bypass gate/evidence/rollback or independently authorize an unconditional
  background push. No release was created/approved/merged/activated here. Pending
  evaluation/automation releases from other workflows are outside this candidate.
- Full feature-corpus orchestration, labels/monitoring integration, live acceptance
  and Stage 5 Tasks 6–10 remain incomplete. Goal remains active.

## Full gate terminal result on original base

- Existing session 7881 completed with exit code 0; all 15 suites passed.
  Shared Wong Choi: 1,338 passed in 658.67 seconds; Tennis: 634 passed in
  41.46 seconds; NBA: 110 passed; Agent scripts: 53 passed, 2 expected failures;
  Dashboard Python: 136 passed, 16 skipped; Dashboard Node: 16 and 62 passed.
- AU/HKJC golden scores and generated model documentation checks passed.
  Local AU/HKJC meeting data-contract checks skipped; this does not prove live
  corpus acceptance, operational health, model improvement or Stage 5 completion.
- This gate tested the original e508754ab9ca base and the local 13-path candidate.
  Current-main alignment and a subsequent gate remain required before release.
  No commit, push, approval, merge or production activation was performed.

- Fast-forwarded this isolated worktree to d52daf7f5627004369db0895dadeb806d00fa512.
  The tracked local diff SHA-256 before/after is identical:
  `227d0eb0812a5c7f5b8415c25a8ddb5115c6e3ee8509911154c8274627116fbb`.
  All nine untracked-file byte hashes were also unchanged during the fast-forward,
  and the exact 13-path dirty scope remained intact. Production was not modified.
  The preceding full gate is not a full gate on this new base.
- Quick gate on the aligned base completed with exit code 0: ruff, both
  120-horse goldens and generated model documentation checks passed. Meeting
  data contracts and full unit suites skipped. Next implementation is supervised
  whole-corpus native racing feature orchestration/reconciliation, followed by
  focused and full gates on the aligned base before any release request.

## Native racing whole-corpus feature orchestration

- Added `RacingFeatureCorpusInspectionRunner` and explicit `racing-feature-corpus`
  supervisor action on the aligned d52daf7f base, preserving production priority,
  WARM/capacity checks, the shared heavy-worker lock and external deadline.
- Child creates complete prediction inventory/pages/coverage first, publishes each
  native feature page with pinned inventory bytes, reconstructs all feature pages
  against current sources and acknowledges only after create-only compact final
  feature coverage publication and a resource checkpoint. Parent checks complete
  prediction coverage, every bounded native feature page and exact final counts,
  hashes and no-authority fields; it does not claim parent shape validation alone
  proves current source bytes.
- TDD initial command lacked package PYTHONPATH and failed collection; corrected
  invocation produced the intended RED: two missing-runner ImportErrors. After
  implementation both AU/HKJC real-subprocess three-page cases passed. Expanded
  feature runtime suite: 25 passed in 6.11 seconds, including missing page,
  rehashed count/promotion/omitted-page coverage and unacknowledged final publication
  before/after atomic linking. Fault artifacts are retained, not retried or deleted.
- Quick gate and git diff check passed; AU/HKJC 120-horse goldens unchanged.
  Meeting corpus checks skipped. No new full gate, live corpus acceptance, scoped
  commit/push or activation has yet established this updated version as deployable.
- Whole-corpus feature reconciliation, large/resource/source-change acceptance,
  native paged labels/monitoring adoption and real Stage 5 pilots remain required.
  The engineering scope remains the same 13 paths; production is unchanged.

## Read-only native feature-corpus reconciliation core

- Added `reconcile_racing_feature_corpus`: explicit inventory, prediction-coverage
  and feature-coverage byte witnesses; existing non-symlink WARM attempt required.
  Reconstructs complete prediction source coverage and every native feature page,
  compares final proof against actual sources, rechecks pinned output bytes and
  returns no retry/promotion authority. No missing output is repaired or created.
  Operational callers still require the supervisor/heavy lock; the supervised
  reconciliation runner has not yet been connected.
- TDD RED: five tests failed with missing-helper ImportError. Initial five then
  passed. Additional fault injection found an actual race: a prior prediction
  page could change after its reconstruction while features were reconstructed.
  First late pin fixed the feature-stage injection but not the earlier
  prediction-stage injection (one failed, one passed). Moved byte pinning before
  prediction reconstruction and recheck after feature reconstruction.
- Final feature runtime suite: 32 passed in 7.68 seconds. Includes both AU/HKJC
  read-only happy paths with prior bytes unchanged, false witness, missing page,
  appended source record and both prediction/feature-stage byte-change injections.
  These are fixture fault tests, not live acceptance or model-quality evidence.
- Quick gate and diff check passed; both 120-horse goldens unchanged; meeting
  contracts skipped. Full gate for this new version remains pending. No commit,
  push, release approval or activation. Next: supervised reconciliation runner,
  large/resource/fault validation, native paged monitoring and live acceptance.

## Supervised feature-corpus reconciliation

- Added explicit `racing-feature-corpus-reconcile` metadata action to parent and
  child supervisor allowlists, native-domain workspaces, bounded receipt checks,
  resource preflight and shared heavy-worker lock dispatch. Payload scope is exact
  and requires all three prior byte witnesses. No experiment registry is created.
- Worker read-only reconstructs the prior complete corpus, copies only verified
  inventory/prediction/feature proof files create-only into a new owned attempt,
  rechecks the prior bytes and reconstructs the copied proof set against current
  sources again before acknowledgement. Parent verifies copied pinned witnesses
  and complete bounded page coverage. Prior attempt/outcome is not rewritten.
- TDD RED: both native-domain tests failed because the runner was absent; both
  then passed. Expanded feature runtime suite: 39 passed in 10.01 seconds.
  Additional production-busy-before-source-read, WARM-offline, shared-heavy-lock,
  incorrect feature-coverage digest and external-deadline cases all reject/defer
  without success and preserve all prior attempt bytes.
- Quick gate and diff check passed, goldens unchanged. Local meeting data-contract
  checks skipped. New full gate, large corpus/scratch acceptance, fault-inclusive
  copied-output reconciliation acceptance, paged monitoring adoption and live
  acceptance remain outstanding. Same 13 local paths, no commit/push/activation.
- Selected legacy source/native-feature supervisor regressions: 6 passed,
  66 deselected in 0.91 seconds; not the full supervisor suite.

## Large supervised corpus acceptance in progress

- Added AU/HKJC 1,300-record runtime cases with more than 5,000 artifact references,
  requiring all 13 feature pages, exact prediction-reference conservation, complete
  final feature coverage and no sample/promotion authority. Fixture records repeat
  a native snapshot; this measures engineering coverage, not independent samples
  or model performance. No legacy limit or production timeout was changed.
- Read-only process inventory showed no production/heavy test before start.
  Started focused pytest on verified WARM TMPDIR with session 21029; IN PROGRESS.
  Estimated fixture scratch is 64 MiB; test-only deadline 240 seconds. No live
  evidence is read or written and no tested source is changed while it runs.
- Independently observed active pytest PID 51428 and AU supervised child PID 51450,
  with CPU activity. AU work directory already contains prediction inventory,
  complete prediction coverage and accumulating native feature pages; those files
  do not prove final coverage or passing exit status. Re-poll session 21029.
- Monitoring still uses legacy whole-corpus settlement/feature entrypoints;
  passing this runtime test cannot close the live review failure by itself.
  Native paged label joins/monitoring adoption, new full gate and live acceptance
  remain required. No commit, push, approval or activation.

## Large corpus and reconciliation copy-fault terminal results

- Session 21029 completed exit code 0: both AU/HKJC large runtime cases passed,
  39 deselected, in 235.44 seconds. Each preserves 1,300 records, 13 feature pages
  and all more-than-5,000 prediction references without changing the legacy cap.
  AU phase outcome independently records receipt_verified, returncode 0,
  112.7097 child wall seconds and peak RSS 40,336 KiB (Darwin byte conversion).
  These resource values describe this repeated-snapshot fixture only.
- Added copy-publication fault injections before and after feature page atomic
  publication during reconciliation. Both raise rather than acknowledge success,
  retain any new partial proof files and preserve every prior attempt byte. No
  repair, automatic retry, deletion or old outcome rewrite was performed.
- Remaining small feature runtime suite: 41 passed, 2 large cases deselected,
  in 10.62 seconds. Combined with the preceding two large cases this covers all
  43 current feature runtime cases, in separate invocations; not a full repo gate.
- Quick gate and diff check passed; AU/HKJC 120-horse goldens unchanged; meeting
  data-contract checks skipped. Current version still needs full gate and live
  acceptance. Native settlement inventories must be frozen/hash-bound too before
  adopting paged label/feature joins: prediction coverage alone cannot detect new
  settlement records or establish qualified monitoring samples.
- Same 13 local paths, no commit/push/activation; Stage 5 Tasks 6–10 remain open.

## Frozen native settlement metadata inventory

- Added research_racing_settlement_inventory.py and its matching tests; local
  engineering scope is now 15 paths, not an already-approved old release scope.
  Uses independent native AU/HKJC canonical evidence/parent validators and pins
  complete read metadata byte hashes plus collection-membership hashes. Includes
  all settlement states and decision/prediction links as of the declared cutoff;
  future-dated metadata remains pinned, not silently omitted from source identity.
- Verification reconstructs the full metadata inventory, so rehashed narrowed
  settlement lists, changed/added records, missing parents and forged sample or
  promotion authority cannot be accepted. Existing read limits remain unchanged;
  oversized inventories fail closed. This is metadata only, not label artifact
  verification or PIT/sample authority. Operational I/O still requires supervisor.
- TDD RED: module absent, collection failed. Initial inventory suite 9 passed;
  extended future-record/authority cases plus legacy native settlement suites:
  29 passed in 0.49 seconds. Native domain model/label parsing was not changed.
- Supervised settlement inventory, native paged label projection, exact joins and
  monitoring adoption remain required before live acceptance. No new full gate,
  release request, commit, push or activation has been performed for this version.

## Supervised settlement metadata inventory

- Added `RacingSettlementInventoryRunner` and explicit `racing-settlement-inventory`
  action throughout existing supervision: metadata-only no-spec path, native
  domain WARM attempt, strict no-authority receipt, bounded parent output checks,
  shared heavy-worker lock and resource/deadline guards. Source I/O remains in
  the child. Child freezes metadata, create-only publishes and reconstructs the
  complete source inventory again before acknowledgement.
- Parent validates output hash, scope, count bounds, exact authority fields,
  ordered/unique file witnesses, complete RecordKind collections and native
  settlement/decision/prediction identities. Parent shape checks do not prove
  opaque source correctness; controlled child reconstruction supplies that.
- TDD RED: three new cases failed with missing-runner ImportErrors. After wiring,
  16 inventory cases passed. Added forged promotion/sample claims, omitted
  collection, duplicate file witness, wrong root, WARM offline, shared-heavy-lock
  and deadline cases. Combined inventory plus native AU/HKJC settlement suites:
  40 passed in 2.14 seconds. Production lock defers before nonexistent source read.
- Quick gate and diff check passed; both 120-horse goldens unchanged; meeting
  data contracts skipped. Local scope remains 15 paths; no commit/push/activation.
- Native paged label projection must now bind this inventory and prediction-page
  proofs, preserve complete settlement coverage and native parser decisions, and
  only then feed exact feature/label monitoring joins. Full gate and real corpus
  acceptance still pending; Stage 5 Tasks 6–10 are not complete.

## Native paged settlement label projection

- Extracted existing AU/HKJC label bodies into separate private native projection
  helpers. Public whole-corpus entrypoints retain their signatures and full native
  prediction reader; default selection is unchanged. New page calls select only
  labels linked to their exact prediction IDs. No shared parser, scoring, ruler,
  chronology, earliest-source or promotion rule was introduced or relaxed.
- Added research_racing_settlement_pages.py and matching tests. Each page pins
  complete prediction and settlement inventories, reconstructs prediction proof,
  uses its independent native label parser, checks exact selected settlement IDs
  and parent/event/time bindings and then reconstructs prediction and labels again.
  Complete coverage reconstructs every ordered page and proves every frozen
  settled/hit/miss settlement appears exactly once; other frozen states remain
  explicit metadata rather than invented qualified samples.
- TDD RED: page module absent, collection failed. Initial page/native legacy
  suites 25 passed. New after-native-projection result mutation injections failed
  for both domains (DID NOT RAISE), demonstrating a real page-wrapper race gap.
  Added a second native label reconstruction and exact comparison; both now fail
  closed. This does not independently repair the legacy whole-corpus entrypoint's
  analogous post-return race; that remains outside the new page acceptance claim.
- Page/native label/inventory/legacy monitoring regression suites: 63 passed in
  3.52 seconds. Evidenced and adjacent-but-unevidenced decisions match native
  legacy output; cloned multi-page candidates cover exactly once; omitted,
  reordered and rehashed promotion pages reject. Fixture clones are not independent
  samples. Quick gate/diff check passed, AU/HKJC goldens unchanged; meeting
  contracts skipped.
- Scope is now 19 local paths (two native label modules plus new page module/tests
  added to prior 15), uncommitted/unpushed/unactivated. Supervised label publication,
  corpus reconciliation, exact feature/label monitoring join and live adoption
  still required. New full gate and real corpus acceptance remain pending.

## Supervised native label-page publication

- Added research_racing_settlement_page_runtime.py and matching tests; local
  scope now 21 paths. `racing-settlement-page` explicitly uses existing metadata
  supervision, production preflight, WARM attempt, shared-heavy-lock dispatch,
  external deadline and strict no-authority receipt checks. No registry experiment
  is created and no production consumer has switched to this action.
- Requires both prediction and settlement inventory explicit byte SHA witnesses
  inside WARM. Parent checks bounded metadata, exact wrapper/parent identities,
  native label-report shape, companion prediction proof and exact selected
  settlement/decision/prediction/event/time bindings. Source correctness remains
  controlled-child reconstruction, not parent shape validation.
- Child publishes create-only bounded companion prediction and label files,
  reconstructs native labels and both complete inventories again after publication,
  compares exact proofs and rechecks pinned input bytes before acknowledgement.
  Source changes or uncertain publication leave partial outputs without success,
  repair, automatic retry or deletion.
- TDD RED: runtime module absent, collection failed. Both native-domain subprocess
  happy paths then passed. Expanded runtime suite initially 14 passed; added both
  domain source-change-during-publication cases. Runtime/pages/inventory/native
  labels/legacy monitoring suites: 79 passed in 6.09 seconds. Includes production
  defer before missing inventory read, WARM offline, heavy lock, bad witness,
  outside-WARM input, timeout, forged promotion/hash/candidates and missing
  companion prediction proof; publication faults before/after atomic linking.
- Quick gate and diff check passed, goldens unchanged, local meeting contracts
  skipped. Full corpus label orchestration/reconciliation, feature/label monitoring
  join and live acceptance remain required. No new full gate, commit, push,
  approval or activation; Stage 5 Tasks 6–10 still incomplete.

## Supervised complete native label corpus

- Added `RacingSettlementCorpusInspectionRunner` and explicit metadata action
  `racing-settlement-corpus` under existing production/WARM/resource/deadline
  guards and shared heavy-worker lock. Owned attempt contains complete frozen
  settlement metadata, prediction inventory/pages/coverage, every native label
  page and compact final label coverage. No registry or model/sample authority.
- Child reconstructs every native label page and complete source inventories,
  publishes final coverage create-only and reconstructs the complete source proof
  again after publication before acknowledging it. Parent verifies both inventories,
  complete companion prediction coverage, every bounded native label page,
  exact-once frozen settled/hit/miss settlement IDs, counts and no-authority fields.
  Parent metadata checks are not independent opaque source verification.
- TDD RED: both domain cases failed with missing-runner ImportErrors. Patch review
  caught a misplaced `_label_inputs` return after inserting the new definitions;
  restored it before running tests. Initial runtime suite 18 passed, including
  both native three-page corpus cases. Added missing label file, rehashed count/
  promotion coverage and unacknowledged final publication before/after linking.
- Runtime/pages/inventory/native labels/legacy monitoring regression suites:
  86 passed in 8.56 seconds. Quick gate and diff check passed; goldens unchanged;
  local meeting data contracts skipped. Scope remains 21 paths, no commit/push/
  activation and no new full gate. Corpus reconciliation, exact feature/label
  monitoring join, large/runtime/source-race acceptance and live adoption remain
  required. No Stage 5 completion or model improvement is claimed.

## Supervised native label-corpus reconciliation

- Added read-only complete label reconciliation and explicit supervised
  `racing-settlement-corpus-reconcile` action. Requires four explicit byte witnesses
  (prediction inventory/coverage and settlement inventory/label coverage). Pins
  every prior inventory, coverage and prediction/label page before reconstructing
  sources, then rechecks all bytes after complete source reconstruction.
- Worker only copies the verified proof set create-only into a new owned WARM
  attempt, rechecks prior bytes and reconstructs the copied set against sources
  again before success. Parent checks copied pinned witnesses and complete bounded
  native label coverage. No missing file is repaired, old outcome rewritten,
  automatic retry allowed, registry created or model/sample authority granted.
- TDD RED: both native-domain cases failed with missing-runner ImportErrors.
  AU/HKJC three-page reconciliation then passed, preserving prior proof bytes.
  Full label runtime suite: 31 passed in 11.37 seconds. Faults cover missing page,
  false settlement witness, changed evidenced result, production defer before
  missing prior read, and prediction proof bytes changed during either prediction
  or label reconstruction. The injected changes are fixture faults, not live runs.
- Quick gate and diff check passed; goldens unchanged; meeting contracts skipped.
  Scope remains 21 local paths; no commit/push/activation. Feature/label monitoring
  joins, large label corpus/resource acceptance, copied-publication faults, new
  full gate and real corpus/live acceptance remain pending.
- Added direct old phase-outcome byte assertions to both native happy paths;
  2 passed, 29 deselected in 3.40 seconds. Prior phase-outcome and proof bytes
  remain unchanged; this is not a full-gate or production activation result.

## Bounded native feature/label monitoring join

- Extracted the existing settled-race projection into private `_join_reports`;
  the public whole-corpus entry point still invokes its independent native AU
  or HKJC inspectors. Blocker order, race identities, limits and sample-clock
  conversion/source-reverification rules are unchanged.
- Added a bounded monitoring-page inspector which reconstructs feature and label
  pages pinned to the same prediction page and frozen settlement metadata. It
  joins native reports, then reconstructs both sources and the join again before
  returning. A page explicitly has no complete coverage/sample-count/promotion
  authority. Operational supervision and complete-corpus aggregation are still
  required before adopting it in production.
- TDD RED: all six AU/HKJC valid/legacy-feature/missing-label cases failed with
  the absent new module. GREEN: 18 new-page plus existing-monitoring cases passed
  in 0.80 seconds. Added both native result-change-after-join faults and a
  cross-prediction-hash fault; combined page/legacy-monitoring/label-page suite
  passed 32 cases in 1.84 seconds.
- Initial quick gate failed only because sandbox denied ruff cache creation in
  the attached worktree. The authorized rerun passed quick gate, both 120-horse
  goldens and generated model documentation; local meeting contracts skipped.
  Diff check passed. Scope is now 24 local paths, not committed/pushed/activated.
  No new full gate or real corpus/runtime acceptance is claimed. Complete join
  aggregation, supervised runtime/receipt/reconciliation and production adoption
  remain required; Stage 5 is not complete.

## Complete bounded-page monitoring aggregation and snapshot verification

- Added complete ordered monitoring-page aggregation, pinned to both complete
  metadata inventories. Reconstructs all pages twice, with full metadata checks
  around each pass; exact frozen settled/hit/miss identities and globally unique
  settled-race unit IDs are mandatory. Original global 1000-settlement,
  10000-race and 1 MiB monitoring-report bounds remain fail closed; no dropped
  records, increased resource caps or substituted recent window.
- Added sample-clock conversion that re-runs complete source aggregation and
  compares the exact report before returning `SampleSnapshot`. Complete page
  coverage is separate from label/feature eligibility: missing labels or PIT
  features yield blocked candidates, not qualified race samples. Neither output
  grants terminal-label, reevaluation or model-promotion authority.
- TDD RED: 12 new aggregation/conversion cases failed with missing entry points.
  First implementation exposed output/input object aliasing in the forged-report
  test; an explicit input-preservation assertion confirmed it. Aggregate unit
  and candidate projections now copy values, so editing the returned report
  cannot alter supplied page proofs; source/report verification rejects edits.
- Three-page AU/HKJC fixtures preserve native units/candidates in valid,
  legacy-feature and missing-label cases. Cloned fixture identities exercise
  coverage only and are not independent real observations. Faults cover missing,
  reordered, duplicate and rehashed false pages; evidenced result mutation;
  earlier-page source changed after the last page of the first pass; global
  resource bounds; and both domains' source changes after completed coverage
  but before sample-clock conversion.
- Combined monitoring-page/legacy-monitoring/label-page/native-AU-label/
  native-HKJC-label/settlement-inventory suite: 90 passed in 15.68 seconds.
  Quick gate passed; AU/HKJC 120-horse goldens and generated docs unchanged;
  local meeting contracts skipped. Diff check passed. Scope remains 24 local
  paths, no commit/push/activation or new full gate. Supervised monitoring
  runtime/compact parent receipt/reconciliation, large-resource acceptance and
  real corpus/live adoption remain pending; Stage 5 completion is not claimed.

## Supervised bounded monitoring-page runtime

- Added `RacingMonitoringPageInspectionRunner` and explicit
  `racing-monitoring-page` supervisor action through the existing metadata-only
  policy, owned WARM attempt, production-priority preflight, single-heavy-worker
  lock, child checkpoints and external deadline. No spec/registry, scheduler,
  model, evaluation ruler or promotion-policy mutation.
- Worker reconstructs/publishes native prediction, label and PIT-feature
  companions, joins current sources, binds all companion hashes, publishes the
  bounded create-only monitoring proof, then reconstructs native sources again
  and rechecks pinned inputs/companion bytes before acknowledging success.
  Single-page receipt has no complete coverage or sample-count authority.
- Parent checks bounded wrapper/companion hashes, independent native feature
  and label report shapes, exact frozen parent identities, source cutoff scope,
  eligibility blockers and settled-at/event/unit consistency. Heavy source
  parsing remains supervised in the child; parent checks are not claimed as an
  independent opaque-source replay or model evaluation.
- TDD RED: 11 new tests failed with missing module. Native AU/HKJC qualified
  source fixtures then passed under supervision. Resource faults cover production
  defer before opening a nonexistent inventory, WARM offline, heavy-lock busy,
  false settlement SHA and external timeout. Rehashed promotion/feature hash/
  unit-event mutations and missing label companions fail parent verification.
- Additional publication tests preserve all three companion proofs, keep any
  newly published partial monitoring proof and raise without success both before
  and after publication acknowledgement; both domains reject evidenced results
  changed during monitoring publication. No old phase outcome or registry is
  rewritten or automatic retry granted.
- Combined monitoring-page runtime and complete label-runtime regression suites:
  46 passed in 15.86 seconds. Quick gate passed, both 120-horse goldens unchanged,
  generated docs current, local meeting contracts skipped; diff check passed.
  Scope is now 26 local paths, no commit/push/activation or new full gate.
  Complete supervised monitoring corpus/parent receipt/reconciliation, larger
  resource acceptance and actual corpus/live adoption remain required.

## Supervised complete monitoring corpus and bounded parent receipt

- Added explicit `racing-monitoring-corpus` action using the existing owned WARM
  attempt, production-priority checks, single-heavy-worker lock, resource
  checkpoints and external deadline. Worker freezes both complete native
  metadata inventories, generates complete prediction coverage and publishes
  every native monitoring page with its prediction/feature/label companions.
- Final coverage is reconstructed from actual sources twice across all ordered
  pages, published create-only and reconstructed again after publication before
  receipt acknowledgement. Input metadata and monitoring proof bytes remain
  pinned/rechecked. Global sample/resource bounds are unchanged and no records
  are dropped to make a corpus pass.
- Parent verifies full prediction coverage, frozen settlement metadata and every
  bounded monitoring page/companion before recomputing the exact coverage
  projection. Extracted the projection into a private helper reused only after
  all source/page checks; no public boolean shortcut or new model authority.
  Receipt counts are sample-trigger-only; terminal-label/reevaluation/model
  promotion flags remain false.
- TDD RED: seven new complete-runtime tests failed with missing entry points.
  First complete runtime suite then passed 22 cases in 23.07 seconds. Added both
  native domains' evidenced result changes during final coverage publication,
  plus complete-runtime production-before-missing-source, WARM-offline and
  external-timeout cases.
- Combined monitoring runtime, complete label runtime, paged joins/aggregation
  and legacy sample-clock suite: 97 passed in 50.45 seconds. AU/HKJC three-page
  fixture outputs retain three settled-race identities with exact coverage;
  cloned fixture identities are coverage tests, not independent real samples.
  Missing pages, forged counts, promotion authority and unacknowledged final
  publication all fail closed, preserving partial attempts without automatic
  repair/retry or registry mutation.
- Quick gate and diff check passed; both 120-horse goldens unchanged; generated
  docs current; local meeting contracts skipped. Scope remains 26 local paths;
  no commit/push/activation or current full gate. Complete monitoring
  reconciliation, large-resource/fault matrix, real-source acceptance and live
  consumer adoption remain pending. Stage 5 is not complete.

## Supervised complete monitoring reconciliation

- Added read-only full monitoring reconciliation with four explicit byte
  witnesses: prediction inventory/coverage, settlement inventory and monitoring
  coverage. All prediction/feature/label/monitoring page bytes are pinned before
  the first source replay, not only after an earlier stage completes.
- Reconstructs complete current prediction and native monitoring sources, checks
  complete bounded companion coverage, then rechecks every pinned old byte.
  Supervised worker copies only the verified set create-only to a fresh owned
  WARM attempt, reconstructs the copied set again and rechecks prior bytes both
  before and after copied-source reconstruction. No missing proof is repaired,
  old phase outcome overwritten, retry granted or registry/model state changed.
- Parent checks all four copied byte witnesses plus complete bounded monitoring
  receipt/companion coverage. Receipt remains sample-trigger-only, with terminal
  label, reevaluation and model-promotion authority false. This is not a fresh
  independent parent opaque-source replay; that replay remains supervised child
  work under the original resource guards.
- TDD RED: six new reconciliation tests failed with absent runner. First native
  AU/HKJC three-page and invalid-prior tests passed six cases in 24.78 seconds.
  Added prior feature-proof byte mutation during either prediction or monitoring
  source replay, plus copied-proof publication failures before/after publication.
  Old proof bytes and actual phase-outcome bytes are preserved in happy and copy
  publication fault paths; partial new attempts are kept without success/retry.
- Complete monitoring runtime suite: 37 passed in 65.74 seconds. Quick gate and
  diff check passed; both 120-horse goldens unchanged, generated docs current;
  local meeting contracts skipped. Scope remains 26 local paths, no commit/push/
  activation or new full gate. A read-only storage check showed HOT 14 GiB free
  and mounted WARM 877 GiB free; no data deleted. Large acceptance must use WARM.
- Live review consumers still call legacy whole-corpus sample APIs; new corpus
  acceptance, safe consumer/router adoption, full gate and production release
  remain pending. Stage 5 and model improvement are not claimed complete.

## Large monitoring acceptance preparation and production-priority wait

- Added AU/HKJC 1300-prediction metadata cases above the legacy 5000-reference
  limit. The tests require the legacy API to fail at its original cap, complete
  new prediction/page coverage, and exactly one qualified original fixture
  settlement/race. Only predictions are cloned, never settlements or independent
  sample counts. No candidate performance inference is made.
- Heavy test preflight initially did not execute: automatic approval review
  returned an account usage-limit failure, not a safety rejection. Did not bypass
  it. A later UTC clock read showed 2026-10-10 11:19:27 UTC, after the stated
  reset time; the justified approval retry succeeded.
- WARM remains mounted with 877 GiB free and the existing dedicated scratch
  directory is present. Process preflight then observed AU production evening
  PID 68933 live. A targeted repeat showed the same process live at 20:31 elapsed.
  Therefore no large research test was started concurrently; this is a verified
  production-priority wait, not a claimed large acceptance result.
- Lightweight quick gate and diff check passed; goldens/docs unchanged; local
  meeting contracts skipped. Scope remains 26 local paths, no commit/push/
  activation or new full gate. Large tests are added but unexecuted. Revalidate
  the actual production process and workload before serial WARM execution.

## Consumer-adoption inspection during verified workload wait

- Revalidated exact AU PID 68933 live at 21:04 and again 22:27 elapsed. Also
  observed shared-suite pytest PID 94063 live; read-only cwd inspection located
  it in `/private/var/folders/h1/br6y1s5j0nb07gfb5rjqxk6r0000gn/T/`
  `wc-release-approval-e65te8o3/checkout`, not this candidate worktree. Repeated
  targeted process check found it still live at 02:24 elapsed. No new heavy test
  started, no other process interrupted, no missing handle assumed terminal.
- Located every live sample-consumer boundary before adopting the new schema:
  `research_review_cursor.py` selects the legacy runner in the racing branch,
  validates prior sample paths with only the legacy attempt prefix, and invokes
  the shared router when reading saved cursor watermarks;
  `research_review_runtime.py` uses the same router both in supervised child
  sample loading and parent summary/reference verification;
  `research_monitoring_samples.py` still routes all AU/HKJC reports to the legacy
  full-corpus source replay. Merely replacing the runner would therefore fail
  schema/ownership checks or re-enter the original whole-corpus cap downstream.
- Adoption requirements recorded: accept only explicitly identified new corpus
  schemas and owned corpus/reconciliation attempt roots; require complete
  companion/metadata binding before sample counts; keep actual native source
  replay under supervisor/deadline/heavy lock; use bounded parent receipt checks,
  not parent opaque-source scans; preserve legacy reports/watermarks and reject
  unsupported or partial pages. No caller-supplied `verified=True` shortcut.
- Required consumer tests before activation: current/previous sample references,
  legacy watermark compatibility, exact cursor generation transaction, missing
  companion, false sample count, changed source, production defer, deadline and
  more-than-5000-reference review path. Tennis/NBA routing and frozen evaluation
  rulers must remain unchanged. Inspection does not claim these tests or adoption
  are complete; large acceptance and full gate remain unexecuted.
- HEAD remains d52daf7f5627; scope remains 26 local paths. Diff check passed. No
  commit/push/merge/activation, storage deletion or model-promotion action.

## Child consumer boundary: test-driven source replay adapter

- Added `source_reverified_paged_monitoring_samples` in the shared router as a
  distinct child-only entry point. It pins coverage and all four byte witnesses,
  delegates complete actual-source replay to the existing reconciliation path,
  compares replay hash/count, rechecks original inputs, and only then converts
  into a settled-race sample snapshot. Operational callers must hold the shared
  supervisor heavy-worker lease; this helper does not acquire that lease itself.
  It is deliberately not wired into parent receipt verification or the cursor
  yet. Existing AU/HKJC legacy routing, NBA and Tennis remain unchanged.
- Six new boundary tests first failed because the entry point did not exist;
  after implementation they passed. A seventh test then exposed reading an
  out-of-scope report before ownership validation. Moved path/name/attempt-root
  validation before the first read; all seven now pass (0.17 seconds).
  Replay is mocked in these boundary tests: they do not prove native corpus
  acceptance, runtime lease ownership, or completed downstream integration.
- Re-ran `./檢查.sh --quick`: ruff, AU/HKJC 120-horse goldens and generated
  model-document freshness passed; local meeting contracts and full unit suite
  skipped. Full gate still not run for this candidate. Exact AU PID 68933 remains
  live at 28:54 elapsed; no heavy native acceptance or full gate started.
- Candidate scope now 28 paths (router modification and one new test file).
  No commit/push/merge/activation, model/ruler/holdout mutation or data removal.
  Next: bounded parent consumer verification, supervised review child adoption,
  legacy cursor compatibility and the actual large native/full-gate acceptance.

## Review worker and bounded parent adoption

- Added a separate bounded paged consumer calling the existing complete
  companion verifier, without opaque-source reconciliation in the parent.
  The source-reverified child adapter and bounded parent share only owned-path
  input validation and snapshot conversion, not a caller-supplied trust flag.
- Added explicit child/parent review dispatch. New coverage schema is checked
  and hashed, source digest/domain/time are bound to the verified snapshots,
  and references are built from the same verified snapshots without repeating
  the legacy full-source scan. Legacy schemas still use their existing domain
  router. No NBA/Tennis source or evaluation contract changed.
- Wired both current and previous sample loading in `run_review_request` to the
  source-reverified child dispatch. Confirmed the actual supervisor review branch
  wraps this worker in `research-heavy-worker.lock`. Wired summary verification
  to bounded new-corpus companion dispatch. Cursor adoption remains incomplete.
- Two native AU/HKJC fixture integration tests first failed with the legacy
  `unsupported index evidence schema` error in the actual child outcome. After
  adoption they succeed with current/previous references equal, one qualified
  fixture race, no sample growth and no model-promotion authority.
- All 18 consumer tests passed in 5.35 seconds. Mocked boundary cases cover
  parent no-native-replay dispatch, missing companion and changed proof input.
  A new hash-binding test exposed accepting an altered in-memory report argument;
  the dispatch now validates its hash before consuming it. The test uses the
  canonical `ResearchIndexError` and asserts the exact hash-mismatch reason.
- Existing review sample compatibility selection passed: 4 tests, 27 deselected,
  2.48 seconds (legacy racing current/previous and NBA/Tennis domain scopes).
  Quick gate passed after integration: ruff, both 120-horse goldens and generated
  docs current; meeting contracts/full suite skipped. Small fixture tests only,
  not native live corpus acceptance or greater-than-5000-reference review proof.
- Revalidated exact AU PID 68933 live at 33:37 elapsed; large WARM acceptance and
  full gate still deferred. Candidate now 29 local paths including review runtime.
  Diff check passed; no commit/push/merge/activation or model/ruler/data mutation.

## Cursor producer, watermark replay and atomic-state acceptance

- Added AU/HKJC fresh-instance cursor tests first: both failed because the
  persisted report still had the legacy monitoring schema. Racing cursor now
  selects the supervised complete corpus producer; NBA/Tennis runners unchanged.
  Owned-path checks accept legacy, corpus and reconciliation attempt prefixes.
  Saved new watermarks use bounded parent companion checks, while the actual
  review worker replays both current and previous native sources under its lease.
- Single-count watermark normalization uses verified parent dispatch in memory
  only; the existing joint transaction still controls durable writes. The legacy
  migration fixture now creates an actual old-schema report with the old runner,
  restores the new producer, then verifies migration to new paged coverage.
- Existing changed-source test originally expected a parent BLOCKED result. The
  source reconstruction now runs in the child and correctly propagates FAILED;
  the test asserts this exact disposition and unchanged calendar/sample state.
  No failure was converted into success, retry authority or cursor progress.
- All 26 consumer tests passed in 38.05 seconds, including AU/HKJC missing feature
  companion, rehashed false sample count and changed native source. Failed fresh
  cursor runs leave both stored generations and prior references unchanged.
  Seven focused existing compatibility/transaction cases passed in 19.22 seconds.
  The complete existing cursor and review-runtime suites then passed: 78 tests,
  46.37 seconds (session 92669 terminal success).
- Quick gate and diff check passed. Goldens and generated documentation unchanged;
  meeting contracts skipped. Large native corpus and complete repo full gate
  remain unexecuted. Exact production PID 68933 was live at 39:34 elapsed; no
  large corpus or full heavy suite started during production.
- Updated the Stage 5 plan's current checkpoint to distinguish this local
  integration from the historical recovery/activation record. Tasks 6–10 remain
  open. Local scope now 32 paths; no commit/push/merge/activation, model promotion,
  evaluation ruler change, storage deletion or ledger action.

## Large-corpus review acceptance preparation during verified production wait

- Exact AU PID 68933 independently verified live at 41:56 and 43:21 elapsed.
  No production process interrupted and no large/full heavy test launched.
  Read-only disk check found HOT about 13 GiB free and mounted WARM 877 GiB free;
  large test scratch must remain on WARM, not the constrained internal disk.
- Extended the existing AU/HKJC 1300-prediction, over-5000-reference acceptance
  cases beyond coverage publication: the actual supervised review child must
  now replay the complete proof as both current and previous sample evidence,
  with bounded parent verification, exactly one original fixture race, no sample
  growth and no promotion. The original corpus proof bytes must remain unchanged.
  Only prediction metadata is cloned; no cloned settlement inflates sample size.
- Collection succeeded: both domain cases collected, 37 other runtime cases
  deselected. Quick gate and diff check passed. These extended heavy cases are
  still UNEXECUTED: neither collection nor the earlier small-native acceptance
  proves large corpus readiness. No production code was modified this turn.
- Scope remains 32 local paths, uncommitted/unpushed/unactivated. Next safe heavy
  sequence when actual production/resource gates permit: serial WARM large
  monitoring/review acceptance, full current-candidate gate, then actual native
  corpus/live acceptance before proposing a scoped release. Tasks 6–10 remain open.

## Combined reader and legacy-API regression acceptance

- Revalidated exact AU production PID 68933 live at 44:10 before starting and
  49:17 after testing. No large corpus case, complete full gate, live research
  job or production mutation was started. Test fixtures use isolated roots.
- Ran the 12 prediction/feature/settlement/monitoring page, consumer, cursor and
  review-runtime test files together. Result: 369 passed, 7 deselected, 275.16
  seconds (session 30371 terminal success). Explicit selection excludes
  `large_monitoring`, `above_legacy_reference` and `above_prediction_reference`.
  This joint pass adds regression evidence across the complete small-fixture
  reader/review chain, not whole native live-corpus acceptance.
- Separately ran six original public-API test files: prediction artifacts,
  AU/HKJC feature provenance, AU/HKJC settlement sources and racing monitoring
  samples. Result: 65 passed, 1.50 seconds (session 68819 terminal success).
  New paged proofs did not replace these legacy compatibility checks.
- Testing was separated into mocked boundaries, actual native fixtures and
  deferred large cases. No claim of model improvement, completed full gate or
  large-test acceptance follows from these scoped results. No own test session
  remains active. Candidate stays at 32 local paths, uncommitted/unpushed/
  unactivated; Tasks 6–10 remain incomplete.

## Fresh production power-readiness and base-version inspection

- Production checkout read-only inspection at 2026-10-10T11:53Z found HEAD
  `0c0f9e1f0c53627bd09a946200378fd797a80096`; the candidate still has HEAD
  `d52daf7f5627004369db0895dadeb806d00fa512`. Production advanced via other
  releases. Current candidate tests cannot establish release readiness against
  that newer base; align/reverify before an immutable release proposal.
- Executed production's `inspect_power_applicability()` with production-local
  imports and no writes. Its four-domain reconstruction and report verifier
  returned `profiles_verified=0`, all four `power_profile_missing`,
  `power_applicability_verified=false`, `model_promotion_allowed=false`.
  Production report content hash:
  `072d1b455e322d2ceab6378f9a1083f38b9e00631f372386f4681569a07e8f2f`.
- Independently inspected candidate applicability. Its AU/HKJC/Tennis/NBA ruler
  byte hashes exactly match production's respective hashes. No ruler drift or
  numeric power profile was invented to close Task 6. NBA remains descriptive
  only and its ruler does not allow promotion. Needed independent evidence:
  domain-specific dev/forward variance plus separately reviewed material-effect
  assumptions, with actual authority bytes hash-pinned before profile acceptance.
- Explicit-state-root Central status reported latest AU running, HKJC dormant,
  Tennis succeeded and NBA partial; model registry stages AU/HKJC production,
  Tennis/NBA shadow. Dashboard configured, D1 backup status ok, HOT 13.26 GiB,
  WARM available and COLD catalog 10/13 verified. Its runtime collector was
  not_configured in this invocation: that is not evidence that installed jobs
  are absent, and no new loaded-state/alignment claim is made.
- AU PID 68933 was independently verified live at 52:27 elapsed. No heavy test,
  numeric profile, model/ruler/policy edit, release approval, runtime change,
  backup upload or deletion was performed. Candidate remains 32 local paths,
  uncommitted/unpushed/unactivated; Task 6 and Stage 5 exit remain not ready.

## Preserved-dirty fast-forward to approved current base

- Compared candidate dirty scope against upstream `d52daf7f5627..0c0f9e1f0c53`:
  upstream's 30 changed paths do not overlap any of the 32 local candidate paths.
  Verified ancestry and empty staged index before alignment. Candidate is a
  detached worktree, not production and not the primary shared dirty checkout.
- Pinned the tracked binary diff digest plus byte hashes of every tracked dirty
  and untracked candidate file, then performed only
  `git merge --ff-only 0c0f9e1f0c53627bd09a946200378fd797a80096`.
  After alignment the diff digest and all 32 file byte hashes were exactly
  unchanged. No stash, reset, commit, push, model proposal or activation occurred.
  Already-approved upstream model/Dashboard updates are part of the new base,
  not part of this candidate's own research-platform payload.
- On the newly aligned base, quick gate passed: ruff, both 120-horse goldens and
  generated model docs current; meeting contracts/full suite skipped. Re-ran all
  consumer cases and six legacy public-API files together: 91 passed in 28.42
  seconds (session 52604 terminal success). Earlier 369-case joint acceptance
  remains historical d52 evidence, not a full gate for this new base.
- Revalidated exact AU PID 68933 live at 57:13 elapsed. Nonblocking read-only
  shared-lock observation returned `production_lock_held`. Large/full acceptance
  stays deferred. Candidate remains 32 uncommitted/unpushed/unactivated paths,
  now based on 0c0f9e1f0c53. Diff check passed; no own test session remains live.

## Remaining aligned-base regression acceptance and concurrent main advance

- On pinned candidate base `0c0f9e1f0c53`, ran the remaining 11 reader/review
  files, excluding the 26 consumer and 65 legacy cases already reverified on
  this base. Result: 343 passed, 7 large-reference cases deselected, 224.37
  seconds (session 67632 terminal success). Together with the prior new-base
  91-case pass, this proves 434 scoped regressions on this base, not a complete
  repo gate or the deliberately unexecuted large acceptance.
- After testing, exact AU PID 68933 remained live at 01:02:48 elapsed and a
  nonblocking read-only shared-lock observation returned `production_lock_held`.
  No large test, installer, scheduler change, commit/push or activation occurred.
- The same post-test check found origin/main advanced concurrently to
  `fdd4e34ae9a717563bf23bfb5249d6420b2e7d39`. Its five changed paths are HKJC
  engine_core and Dashboard timeline files, not any of the 32 local candidate
  paths. Candidate stays pinned to the actually tested 0c0f9e1f0c53 for now;
  these passing results are not represented as acceptance of fdd4e34ae9a7.
- Next release gate must use a freshly inspected immutable base and preserve
  the scoped dirty payload again. Actual heavy acceptance remains contingent on
  live production/resource preflight. Diff check passed; no own test session
  remains active. Numeric power readiness, real pilots and Stage 5 exit are open.

## Second preserved-payload base alignment

- Re-inspected candidate HEAD `0c0f9e1f0c53` and cached origin/main
  `f7d07b035a5dd4e156c73d5146a3987a0458bbf5`. Verified ancestry, empty staged
  index and no overlap between the 15 upstream changed paths and all 32 local
  candidate paths. The primary shared checkout and production were not changed.
- Pinned tracked binary diff SHA-256
  `8d58f5dc3fd84300805d520ffd27bd244e9537f8f1bea658bbc3e42d6b7630fd`,
  every tracked dirty/untracked file byte hash and exact porcelain status.
  Performed only fast-forward to that immutable SHA; all pinned values matched
  exactly afterward. No stash, reset, own commit, push or activation occurred.
  These two audit/plan updates were made afterward to record the alignment.
- Existing 434 scoped test passes certify only the earlier pinned 0c0 base.
  They do not certify f7d, actual large/native corpus acceptance, or full gate.
  Those verifications remain required before release. Known AU PID 68933 was
  independently verified live during alignment; no heavy test was started.
  Reviewed power profiles, domain pilots and Stage 5 exit remain incomplete.

## Pinned f7d bounded compatibility and fresh operational inspection

- Candidate HEAD remained `f7d07b035a5dd4e156c73d5146a3987a0458bbf5` before
  and after tests. `./檢查.sh --quick` exited zero: ruff, both 120-horse goldens
  and generated model documentation passed. AU/HKJC meeting contracts skipped
  because this checkout has no scored meeting corpus; full suite skipped.
- Ran `python3 -m pytest -q -p no:cacheprovider` with
  `PYTHONPATH=.agents/skills`, `PYTHONDONTWRITEBYTECODE=1` and WARM TMPDIR
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/central-release-gate-20261009.AmUutw`.
  Explicit files under `.agents/skills/shared_wong_choi/tests/`:
  `test_research_paged_monitoring_consumer.py`,
  `test_research_au_feature_provenance.py`,
  `test_research_hkjc_feature_provenance.py`,
  `test_research_prediction_artifacts.py`,
  `test_research_au_settlement_source.py`,
  `test_research_hkjc_settlement_source.py`, and
  `test_research_racing_monitoring_samples.py`.
  Session 29317 terminated successfully: 91 passed in 74.49 seconds. These are
  bounded fixtures, not large-reference or live corpus acceptance. Remaining
  scoped suite, all large cases and complete repo gate still require this base.
- Read-only Central status at `2026-10-10T12:20:33.697593+00:00` reported
  production checkout and origin/main at f7d, only two expected mutable runtime
  paths, no unexpected dirty paths. Its latest f7d docs release record says
  activation `not_started`; checkout equality is not substituted for an
  activation receipt. This reader payload remains uncommitted/unpushed and has
  no release. The five existing evaluation/automation pending records are not
  this candidate's releases and were not approved or altered.
- Latest canonical run records: AU running within its 39600-second deadline,
  HKJC watch succeeded, Tennis daily succeeded, NBA postgame partial. Read the
  exact NBA attempt-3 record: settle exited 75, `temporary_failure`, reason
  `live_analysis_has_no_prediction_snapshot`; no errors array entries. This is
  unresolved production evidence debt, not a license to synthesize a snapshot.
  Registry stages remain AU/HKJC production, Tennis/NBA shadow; these legacy
  records alone do not certify current engine weights. Runtime collector was
  `not_configured`, so this invocation does not prove installed/loaded alignment.
- Dashboard was configured; D1 backup status ok, approximately 20.01 hours old,
  restore/WARM verified but latest COLD unverified. HOT free 13.24 GiB (critical),
  WARM available with 877.31 GiB free, catalog COLD verified 10/13. No ledger,
  retention, deletion, upload, model promotion or production mutation occurred.
- Independently re-polled exact AU PID 68933 live at 01:21:34 elapsed and the
  read-only nonblocking shared-lock probe returned `production_lock_held`.
  Heavy acceptance remains deferred. Both own inspection/test sessions are
  terminal; no own test process remains pending. Diff check passed.

## Read-only NBA snapshot-gap isolation

- Traced the exact postgame failure into `nba_daily_schedule.run_postgame`:
  nonempty live analysis without an existing manifest is deliberately blocked;
  it never creates a retrospective prediction. Existing tests distinguish an
  empty failed-extraction directory from partial/complete unsnapshotted reports.
- Production log `run-20261009-210012-pregame.json` for target 2026-10-10
  recorded orchestrator exit 75 with player markets not open. Later
  `run-20261010-063643-pregame.json` recorded successful odds refresh, followed
  by orchestrator exit 1: the MEM_CHI validator blocked FW-06 (no verified priced
  player history) and FW-08 (zero rendered odds), with FW-07 short-file warning.
  Therefore snapshot creation was never reached; postgame failure is downstream
  evidence protection, not evidence that a snapshot writer lost a valid report.
- In the existing live folder, extractor data contains MEM 17 and CHI 15 player
  histories in previous-season-reference mode, PRESEASON/shadow. Current odds
  name set is only Cameron Boozer and Caleb Wilson; the report marks both
  `unmatched_current_roster`, and neither appears in extracted history names.
  Thus the priced/verified-history intersection is zero. This does not prove
  whether the external market identities or roster data are correct; upstream
  source/identity validation remains open and no external source was rerun.
- Reproduced read-only with the existing production validator:
  `PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/nba/nba_wong_choi/scripts/validate_nba_output.py '2026-10-10 NBA Analysis/Game_MEM_CHI_Full_Analysis.md'`.
  Exit 1, same two blocks and one warning. No report, snapshot or model code was
  generated or changed. Input SHA-256 values matched before/after:
  odds `3e59d9171e01a27d9f4d2982608df7bb57330cd8c23e1e370ff0ae5834800850`;
  extractor `4c3ac1300bd269ca4e7bcc16d5b348cb3911ad4435a334873142b171901c3aca`;
  report `45aa0b63dc38d23901aedd6aaf48a1ac8e3bef0d31dbf25574f8c83bb38044b0`;
  final-refresh log `bb73265d9abc0498db12918a788b01a2d51b9c65ab9d00251ad7d535a05aca5f`.
- Stage 5 must not count this partial live day as accepted forward evidence or
  completed pilot. Correct next work is upstream market/roster identity diagnosis
  and a genuinely pregame snapshot on a future eligible run, not disabling the
  validator or manufacturing historical provenance. No production, ledger,
  release policy, scoring, ruler, retention or promotion action was taken.

## e122 alignment and bounded acceptance — 2026-10-11 Sydney

- Read current candidate HEAD f7d and locally observed origin/main
  `e122c13a15835c4b7af0757516c684b2355eb114`. The 23 upstream changed paths
  were disjoint from all 32 local dirty/untracked candidate paths. Fast-forward
  to the exact pinned SHA preserved every local SHA256, binary diff hash, path
  list and empty staged index. The same preservation checks passed after tests.
  No reset, stash, candidate commit, push or production checkout change.
- Guarded bounded compatibility command used `PYTHONPATH=.agents/skills`,
  `PYTHONDONTWRITEBYTECODE=1`, `python3 -m pytest -q -p no:cacheprovider`, the
  same seven explicit files documented in the previous f7d acceptance, and
  `/Users/imac/Antigravity-repo/.agents/scripts/wongchoi_external_run.py`.
  Actual scratch was external `scratch/command-runs/wc-run-h0wxnv_n`.
  Session 64970 completed with exit zero: 91 passed in 70.04 seconds.
- On the same base, guarded `./檢查.sh --quick` exited zero: ruff, both
  120-horse goldens and generated model documentation passed. Local meeting
  corpus and full suite were skipped; this is not live corpus quality proof.
- AU PID 68933 was independently observed alive at elapsed 02:26:12 before
  bounded acceptance. No large-reference tests, full gate, scheduler switch or
  production restart were performed. Previous large/full requirements remain.
- These results replace no historical evidence: earlier scoped tests certify
  only their pinned bases. Remaining suite, seven large acceptance cases,
  actual supervised full-history review, numeric power profiles, domain pilots
  and Stage 5 exit still require fresh evidence. No model improvement claimed.

### Remaining e122 bounded regression completed

- Ran the remaining eleven explicit reader/review test files with the same
  external command guard, `PYTHONPATH=.agents/skills`, no bytecode and no pytest
  cache. Selection excluded only `large_monitoring`, `above_legacy_reference`
  and `above_prediction_reference`. All selected fixture temp data was beneath
  external `scratch/command-runs/wc-run-lv5sb1wm`.
- Session 83253 reached terminal exit zero: **343 passed, 7 deselected in
  444.70 seconds (07:24)**. With the 91 disjoint consumer/legacy cases, this
  proves 434 scoped regressions on pinned `e122c13a1583`.
- The longer duration was observed, not interpreted as a hang. During the run,
  PID 44154 (pytest) and PID 52796 (fixture supervisor child) were confirmed
  alive, low CPU, with fresh progress output. AU PID 68933 remained alive at
  elapsed 02:33:46. No process was killed/restarted or observation timeout
  mistaken for terminal completion.
- This is not the full repo gate, seven-case large acceptance, actual full-corpus
  replay, supervised live review, pilot or model-performance evidence. These
  requirements and Tasks 6–10 remain open. No release or activation occurred.

### Seven-case large-reference acceptance started — 2026-10-11 Sydney

- Candidate HEAD remains `e122c13a15835c4b7af0757516c684b2355eb114`.
  An escalated read-only process inventory found no active daily scheduler or
  pytest process before starting this offline fixture run.
- Session 44453 runs four explicit files: prediction page runtime, racing
  monitoring page runtime, racing feature pages and racing feature page runtime.
  Selection is `large_monitoring or above_legacy_reference or
  above_prediction_reference`; no bound is reduced to make the tests pass.
- Command uses the external command guard, `nice -n 10`,
  `PYTHONPATH=.agents/skills`, `PYTHONDONTWRITEBYTECODE=1` and
  `python3 -m pytest -q -p no:cacheprovider`. Scratch is
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-qf_2wmgx`.
- Status is **in progress**, not a pass or full-gate result. No source removal,
  production change, model promotion, commit, push or activation was performed.

#### First large case failed closed; remainder still running

- Session 44453 emitted its first `F`. The native phase outcome for
  `test_supervised_corpus_above_l0`, phase `prediction-corpus-7cw5j543`, records
  `disposition=timed_out`, return code -15 and wall time 122.122854583 seconds.
  User/system CPU were 18.916516/9.961887 seconds; reported peak RSS was
  38,432 KiB. These timings do not by themselves identify the bottleneck.
- Only 14 prediction-page files were present, against the required 17; the
  outcome correctly reports `publication=unconfirmed_reconcile_before_retry`
  with null result. There is no accepted final coverage proof.
- The first case's existing helper uses a 120-second deadline. No timeout,
  reference limit, corpus size or assertion was altered. Remaining cases are
  still running in the same session; source is unchanged during execution.
- Large-reference acceptance is therefore not green. Investigate the measured
  read/verification path and resource contention before any retry; preserve the
  failed workspace and do not promote partial publication into success.

#### One retained-inventory profile — heartbeat 2026-10-11T09:59Z

- Read-only process inventory found no active daily scheduler, pytest or research
  supervisor. Profiled one `verify_prediction_inventory` call against the
  retained failed 1,700-record fixture using `cProfile`, with no bytecode writes
  and no source change. Session 32393 exited zero; verification matched source.
- Profile recorded 2,765,227 calls (2,697,110 primitive) in 2.432 seconds;
  verification cumulative time was 2.435 seconds. `_Reader.read` ran 3,402
  times, `posix.read` 6,804 times (1.537 seconds) and `posix.lstat` 47,713
  times (0.215 seconds). This establishes the per-scan work in that single
  clean observation, not whole-phase attribution or a before/after improvement.
- Current source repeats complete inventory verification for each persisted
  page; the cost is material. A fix must retain canonical source binding,
  post-read mutation detection and final complete replay rather than trusting
  supplied inventory or reducing coverage. No runtime or test code was changed.

#### Resource-checked inventory profile — 2026-10-13 Sydney

- Before profiling, read-only process inventory found no active daily scheduler,
  pytest or research supervisor. Data-volume free space was approximately
  23 GiB; no deletion or cleanup by this task explains that external change.
- Session 22679 reverified the same retained 1,700-record inventory with each
  reader checkpoint calling the native `_resource_status` on the runtime and
  registry reconstructed from its original request. No persistent state was
  created; the diagnostic excludes historical parent-PID/deadline checks and
  is not a supervised run or deadline acceptance.
- Exit zero, 11,911 resource checkpoints, 5,314,185 calls in 4.429 seconds.
  Verification cumulative time was 4.433 seconds, native resource checks
  1.089 seconds, `posix.read` 2.082 seconds; `lstat` ran 178,734 times.
  This directly demonstrates checkpoint overhead in addition to the complete
  per-page metadata scans. The earlier 2.432-second observation occurred at a
  different time/load and is not a controlled A/B performance comparison.
- Do not fix this by bypassing production/preemption or WARM safety checks.
  First target redundant complete-inventory reconstruction across pages within
  one bounded phase, with source mutation tests and end-to-end deadlines still
  enforced. No model, ruler, release policy or runtime source changed here.

#### First large acceptance passes in standalone rerun

- With the same candidate source and no observed parallel scheduler/pytest,
  ran only `test_supervised_corpus_above_legacy_reference_cap_is_not_truncated`
  via external storage guard, `nice -n 10`, no pytest cache and no bytecode.
  Session 66559 exited zero: **1 passed in 71.31 seconds**. Scratch retained at
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-9vqvju46`.
- This unchanged test still uses 1,700 records, 5,100 artifact references,
  17 pages and its original 120-second phase deadline. No limit, timeout,
  assertion, code or production configuration changed to obtain this pass.
- The earlier combined-run timeout remains valid failed evidence. Standalone
  success disproves inevitability of this timeout, but does not isolate every
  environmental contribution or demonstrate a source-code improvement.
  Original AU/HKJC monitoring failures still require independent acceptance;
  no full gate, live review, pilot, model benefit or release readiness claimed.

#### AU monitoring standalone acceptance started — 2026-10-13 Sydney

- Candidate HEAD is still `e122c13a15835c4b7af0757516c684b2355eb114`.
  Before this run, the native process inventory found no active daily scheduler,
  pytest or research supervisor. No source or assertion changed after the
  seven-case run; standalone execution is an environmental isolation check.
- Session 65268 runs only the AU parameter of
  `test_large_monitoring_corpus_above_legacy_reference_limit_keeps_one_real_fixture_label`,
  with external guard, `nice -n 10`, no bytecode and no pytest cache. Original
  1,300 predictions, >5,000 references, one genuine settlement and 600-second
  per-phase deadline remain unchanged, including the supervised review replay.
- Scratch is retained at
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-pyr81lq7`.
  PID 70424 (pytest) and PID 70431 (AU corpus supervisor child) were observed
  live. Status is in progress, not accepted coverage or a passing test.
- HKJC standalone monitoring acceptance, full gate, actual full-history review,
  power authority and live domain pilots remain unproven. No commit, push,
  release approval, activation or source removal was performed.

#### AU standalone result and clock-observation discrepancy

- Session 65268 reached terminal exit 1: `1 failed in 123.25s`; the corpus
  result was `TIMED_OUT / phase_timeout`, so review replay did not run. The
  native outcome records child exit zero carrying an interruption receipt,
  null accepted report, unconfirmed publication and executor wall time
  115.9748825 seconds; user/system CPU were 52.40212/24.237507 seconds.
- Do not interpret this as proof the caller's 600-second deadline was reduced:
  read-only source tracing confirms `run` passes it to `_phase`, which computes
  `_deadline_now() + timeout_seconds`, and child checkpoint uses that deadline.
  Request birth/mtime was 2026-10-13T01:07:26+1100; outcome birth/mtime was
  01:25:40+1100, a calendar interval of 1,094 seconds, unlike executor elapsed.
- A fresh read-only parent/child clock probe returned POSIX clock readings
  25116.871095 / 25116.891404 (delta 0.020309 seconds), but Python monotonic
  readings 0.027965166 / 0.010660375 (delta -0.017304791). This validates the
  existing requirement not to share Python 3.9 process-relative monotonic
  timestamps across processes; the request uses the existing POSIX clock.
- Machine sleep/pause is a hypothesis for the elapsed/calendar discrepancy,
  not a proven attribution. Need an uninterrupted runtime observation and
  clock-consistent timing before proposing a deadline or resource-control fix.
  Do not expand the deadline, reduce coverage or promote this interrupted run.

#### AU sleep-controlled standalone observation started

- Read-only process inventory again found no active daily scheduler, pytest or
  research supervisor. Started the unchanged AU large monitoring test under
  `/usr/bin/caffeinate -i`, whose idle-sleep assertion lasts only for the invoked
  command. No scheduler/plist, system power setting or phase deadline changed.
- Session 99687 uses external scratch
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jomdlogj`,
  the same original 600-second per-phase limit, 1,300 prediction records and
  one genuine settlement, no bytecode/cache and `nice -n 10`.
- Caffeinate PID 71218, pytest PID 71220 and AU corpus child PID 71229 were
  independently observed live. Status is in progress, not a successful test.
  This prevents idle sleep only, not user-forced sleep or every suspension;
  clock/calendar and terminal outcome still need checking.

#### Sleep-controlled AU run terminal: performance failure reproduced

- Re-polled original session 99687 through completion; exit 1, **1 failed in
  607.16 seconds (10:07)**. Unchanged AU monitoring corpus result is
  `TIMED_OUT / timed_out`, with no accepted report. It did not reach the review
  replay assertions. No deadline, data, source or assertion was relaxed.
- During this run, caffeinate PID 71218's active idle-system-sleep assertion
  was verified with `pmset -g assertions`; pytest 71220 and child 71229 were
  independently observed alive and CPU-active, including child elapsed 09:35
  before terminal timeout. No parallel scheduler/pytest was observed before
  starting. This reproduces a sustained-computation deadline failure, so
  sleep/pause alone cannot explain the large monitoring acceptance problem.
- Keep this failed external workspace and earlier sleep-discrepant evidence.
  Next action is a targeted bounded verification-cost repair with mutation,
  omitted-page, forged-proof and complete-corpus regression tests; do not raise
  the 600-second deadline, reduce references, skip source safety or approve a
  release on prior small tests. Full gate and Stage 5 exit remain unproven.

#### Native monitoring page profile isolates settlement reconstruction

- Session 7271 ran a read-only `cProfile` of the first 100-record monitoring
  page against retained `wc-run-jomdlogj` inventories. No output/state was
  published, sources were unchanged and this diagnostic used the primitive's
  no-op resource checkpoint: it is not supervised acceptance.
- Exit zero: one qualified race, 29,520,733 calls in 17.478 seconds.
  Monitoring cumulative time was 17.531 seconds; its two reconstruction passes
  spent 16.292 seconds in settlement-page inspection. The profile records
  four complete prediction-inventory verifications (5.762 seconds), four
  complete settlement-inventory verifications (4.869 seconds), eight native
  `_evidence` scans (5.539 seconds), 33,664 metadata reads and 74,632 POSIX reads.
  Cumulative figures overlap and must not be summed as independent costs.
- This isolates repeated full metadata/parent reconstruction in the settlement
  path as a dominant component of the sampled page, in addition to earlier
  measured resource checkpoints. Do not remove independent source rechecks or
  accept arbitrary caller-supplied cached records to reduce the count.
- Repair design must bind any phase-local verified snapshot to exact root,
  domain, as-of and canonical file/directory digests; reject forged, mutated,
  incomplete or cross-scope snapshots; recheck bytes/listings before reuse and
  before accepting final coverage. Native labels/feature checks and complete
  final replay remain mandatory. The existing sleep-controlled 600-second
  large acceptance is a reproduced RED test, not a missing test to weaken.
- No performance fix, source-code improvement or passing full gate is claimed
  from this diagnostic. No commit, push, release approval or activation.

#### Phase-local native snapshot primitive — RED/GREEN

- Added `research_native_evidence_snapshot.py` and matching isolated tests.
  Constructor accepts only root/domain/as-of, not caller-provided records or a
  serialized authority flag. It invokes the correct AU/HKJC native graph parser
  once, preserving their different return formats and validation rules.
- Every reuse uses a fresh bounded `_Reader` to match all original directory
  listings and source digests, then rechecks the read bytes/listings before
  returning detached metadata. Scope changes, future appends, deletion,
  whitespace-only byte changes, symlink replacement and missing parents block;
  production preemption checkpoint is still called, not memoized. This is only
  metadata reuse, never a blob/label/sample/promotion grant or persisted cache.
- RED session 31489: all initial 20 tests failed because the module was absent.
  GREEN session 11478: 20 passed. Added mid-read mutation and constructor parent
  regressions, then session 36949 ran new 24 cases plus existing 24 settlement
  inventory cases: **48 passed in 4.83 seconds**, terminal exit zero.
- External-guarded `./檢查.sh --quick` passed after each code/test change; both
  120-horse scoring goldens and documentation freshness remain unchanged.
  Local meeting data contracts and full unit suite were skipped. This is not
  the full gate or production corpus quality evidence.
- Primitive is NOT wired into monitoring/native settlement readers yet;
  the sustained 600-second AU failure remains unresolved. Integration must
  validate snapshot type/scope and retain complete source rechecks and final
  replay. No runtime benefit, performance improvement, full acceptance, commit,
  push, release approval or activation is claimed. Own reader scope grows from
  32 to 34 paths with these two additions, not other agents' work.

#### Native settlement reader integration — RED/GREEN

- Added six AU/HKJC integration cases: byte-identical native report parity,
  rejecting a caller dictionary masquerading as a verified snapshot, and
  source metadata mutation during label parsing. RED: all six failed because
  the native readers had no snapshot input, with 24 prior tests deselected.
- Native readers now optionally accept the exact private snapshot type, scoped
  to their own domain/root/as-of. Default behavior is unchanged. A private
  begin-read returns the detached native graph plus a fresh bounded reader;
  the original native end-of-label `reader.recheck()` is retained, avoiding
  extra full rechecks before and after the same inspection. No blob, chronology,
  result parsing, label criterion, scoring or authority rule changed.
- Session 17478 ran all 30 snapshot cases plus 16 existing AU/HKJC settlement
  source cases: **46 passed in 0.79 seconds**, exit zero, external fixture
  workspace `wc-run-lpnln8lh`. This includes the existing public uncached path.
- External-guarded quick gate passed after integration: both scoring goldens
  and generated documentation unchanged; local meeting corpus/full suite
  skipped. Native readers support the verified reuse, but supervised monitoring
  still must create/propagate a phase-local snapshot. No full large acceptance
  or performance improvement is established yet; the reproduced 600-second
  failure remains open. No commit, push, approval, activation or data removal.

#### Monitoring corpus snapshot propagation — RED/GREEN and fault regressions

- Added AU/HKJC corpus propagation tests: initial session 77524 failed both
  because all native label calls received `None`. The tests also require the
  real one-settlement corpus to produce exactly one qualified sample and no
  registry initialization; source primitives are not mocked out.
- Monitoring corpus now constructs one native snapshot in its supervised
  phase and passes it through page workers, settlement-page primitives and
  both final aggregate/replay calls. Complete prediction/settlement inventory
  verifications, native blob/label checks, source mutation comparisons,
  create-only publication and final reader rechecks are retained.
- Snapshot/propagation suite: session 8269 **32 passed in 1.67 seconds**.
  External-guarded quick gate passed, with unchanged scoring goldens; local
  corpus data contracts and full suite were skipped as before.
- Wider session 53584 ran five explicit snapshot, settlement-page/runtime and
  monitoring-page/runtime test files under external guard and command-scoped
  idle-sleep prevention: **138 passed, 2 deselected in 282.31 seconds (4:42)**,
  terminal exit zero. The two deselected cases are the original AU/HKJC large
  monitoring acceptance cases, not ignored failures; they remain required.
  Scratch retained at `wc-run-97wxto5g`; no source changed while tests ran.
- This is bounded/fault compatibility evidence, not a full gate, performance
  A/B or large deadline acceptance. Review/reconciliation replay still needs
  its own phase-local snapshot integration before large full-loop acceptance.
  No commit, push, approval, activation, ledger mutation or data deletion.

#### Read-only monitoring replay snapshot integration — RED/GREEN

- Added two AU/HKJC replay cases requiring a fresh snapshot for each replay,
  one shared instance inside that replay, and exact preservation of prior
  workspace bytes. RED session 40759: both failed because native label reads
  received `None`; existing prior generation/replay still executed normally.
- `reconcile_racing_monitoring_corpus` now constructs a new native snapshot
  from current canonical source after pinned companion loading and prediction
  replay, and passes it to the existing complete monitoring aggregate. It does
  not deserialize cached graphs or share snapshots across processes/attempts.
  All inventory verification, native replay, prior proof equality, receipt
  validation and reader end rechecks remain in place.
- GREEN session 29517: **34 passed in 22.81 seconds**, terminal exit zero,
  external scratch `wc-run-y28weuf9`, command-scoped idle-sleep prevention.
  This includes the 32 snapshot/native/corpus cases and the two replay cases.
- External-guarded quick gate passed again, unchanged scoring goldens and
  generated docs; meeting corpus checks/full suite skipped. The earlier wider
  138-case result predates this replay delta, so do not count it as current
  whole-suite proof. Need current fault replay/consumer tests, controlled
  large-reference timing, original deadlines and full repo gate before release.
  No source-cost improvement, model benefit, commit, push or activation claimed.

#### Same-process ABBA diagnostic: warm benefit is marginal, not large

- Session 24828 re-read the retained first 100-record AU monitoring page in
  baseline/snapshot/snapshot/baseline order, same process/source/current code,
  command-scoped idle-sleep protection, no publication and no source writes.
  Snapshot construction took 0.844585667 seconds. Primitive resource checkpoint
  was a no-op for both modes; this is not supervised deadline acceptance.
- Timings were 10.004126541 / 5.754468958 / 5.759937833 / 5.8267365 seconds.
  All four complete proofs were exactly equal, hash
  `8cb3d8c39c620f4af90dbfe90b9394a1e76318b5487b58544a372a0d0d46c2d1`,
  with one qualified race. The first baseline clearly differs from its warm
  repeat; do not present cold-vs-warm difference as candidate speedup.
- Warm baseline versus snapshot is only about 1.1–1.2 percent in these two
  observations, without uncertainty estimation and excluding snapshot build.
  This does not demonstrate a substantial repair of the 600-second timeout.
  Keep the result as weak/marginal engineering evidence, not model benefit.
- Current consumer/reconciliation fault run session 59580 is in progress,
  explicit two-file selection `paged or reconciliation`, external workspace
  `wc-run-278dmt2g`. Large supervised acceptance remains required; reconsider
  the added mechanism if complete runtime evidence does not justify its cost.

- Consumer/reconciliation session 59580 subsequently reached terminal exit
  zero: **36 passed, 29 deselected in 191.19 seconds (3:11)**. Selection was
  the two explicit paged-consumer/monitoring-runtime files with
  `paged or reconciliation`; deselected cases are outside that focused query,
  not a full-suite or full-gate exemption. No source changed during the run.
  Native replay, pinned prior companions and fault cases pass on current code.
  Large deadline acceptance and substantial performance benefit remain unproven.

#### Snapshot candidate AU full large acceptance started

- Before launch, read-only process inventory found no active daily scheduler,
  pytest or research supervisor. Candidate base remains `e122c13a15835c4b7af0757516c684b2355eb114`.
  Session 45401 runs the unchanged AU large monitoring test, original 1,300
  predictions, >5,000 references, one genuine settlement and 600-second
  per-phase deadline, including the downstream supervised review assertions.
- Uses external scratch `wc-run-t9t43h96`, `nice -n 10`, no bytecode/pytest
  cache and command-scoped idle-sleep prevention. Pytest PID 75218, corpus
  child 75226 and caffeinate PID 75217 were independently observed live.
  Status is in progress. No source changes during execution are authorized.
- Source hashes captured for after-run preservation check:

```text
b0f3eed588d3445e4a4b5f9bc36556e5e92fae0b7eac09760d20ef43c4477638  .agents/skills/shared_wong_choi/research_native_evidence_snapshot.py
ec9509261de2ed9c511e51c637654eee72431134d1d51d022e5c90a72a44a3b8  .agents/skills/shared_wong_choi/research_au_settlement_source.py
cfdec982634711bdeb150e4135f7ba3770ef765b9fb8a34131de28e3fd07e704  .agents/skills/shared_wong_choi/research_hkjc_settlement_source.py
873af702e0578c835d883b68f6b6515c327f34368c203da3c7f38b6411b54c8a  .agents/skills/shared_wong_choi/research_racing_settlement_pages.py
5ab69be1793f93c09ab8691909568a69c22019d9c45f0dcf72af9ee938329bec  .agents/skills/shared_wong_choi/research_racing_settlement_page_runtime.py
62b96ede5aee9b876c5a82d5a863e71336d0006aab99f48abad025c424eb5fdd  .agents/skills/shared_wong_choi/research_racing_monitoring_pages.py
75377b1f84363e8ab6c5efd95468d95e27f60fbb55f754bbfe390cde144a7183  .agents/skills/shared_wong_choi/research_racing_monitoring_page_runtime.py
38ee3b4b96466900449155ea4727b89d5ec9823ec56db8678241c90d0f08842d  .agents/skills/shared_wong_choi/tests/test_research_racing_monitoring_page_runtime.py
```

- Do not count prior bounded passes or the marginal ABBA diagnostic as this
  run's success. Keep the original deadline failure and all unsuccessful
  experiments visible; no release, model benefit, commit, push or activation.

#### Snapshot candidate large AU acceptance failed: mechanism insufficient

- Original session 45401 reached terminal exit 1: **1 failed in 605.23 seconds
  (10:05)**, corpus `TIMED_OUT / timed_out`, no accepted report. Review replay
  was not reached. The original 600-second deadline and all fixtures/assertions
  remained unchanged; no source edit or restart occurred during the run.
- Source SHA256 comparison matched all eight pre-run hashes exactly. Native
  outcome records 597.458730416 seconds, return code -15 and null result,
  with unconfirmed publication. Preserve the external failed workspace
  `wc-run-t9t43h96` and outcome, not a partial success.
- Native graph snapshot reuse is insufficient to solve the deadline failure;
  warm-page ABBA already showed only marginal benefit. Do not release this as
  a performance fix or count bounded compatibility tests as large acceptance.
- Next design must address repeated complete-inventory work per bounded page,
  preserving full metadata/parent validation, source byte/listing binding,
  selected native label/feature provenance, final complete replay and rejection
  of forged/omitted/mutated evidence. No raising deadline, shrinking history or
  bypassing resource/promotion controls. Stage 5 remains incomplete.

#### Combined complete inventory verification — RED/GREEN and timing

- Twelve new RED cases failed because `verify_inventories` did not exist.
  They require one canonical build of both full inventory witnesses per phase,
  but complete source byte/listing rechecks on every reuse; rehashed narrowed
  prediction/settlement inventories, authority flags and future appends block.
- Snapshot now lazily derives canonical encoded witnesses from both native
  inventory constructors, never from supplied reports. A single bounded reader
  binds their union to the original complete native source, then rechecks all
  bytes/listings and caller report bytes before retaining those witnesses.
  Label-page before/after checkpoints use this combined check only with the
  exact private snapshot type. Uncached callers keep the original two complete
  semantic rebuilds; source/blob/native-label/final replay checks remain.
- Session 58641 GREEN: **46 passed in 25.37 seconds**, terminal exit zero,
  external scratch `wc-run-2dr2s9qp`. Quick gate passed, scoring goldens and
  model docs unchanged; corpus/full suite skipped. Wider fault/large/full-gate
  acceptance still needs current evidence after this delta.
- Same-fixture same-process ABBA session 19834, exit zero: snapshot build
  0.894163417 seconds; page timings baseline/snapshot/snapshot/baseline were
  10.020339625 / 4.378053125 / 3.637233083 / 5.766541042 seconds. All complete
  proofs matched exactly, hash
  `8cb3d8c39c620f4af90dbfe90b9394a1e76318b5487b58544a372a0d0d46c2d1`,
  one qualified race. Warm comparison shows lower cost in this page observation;
  do not use the cold first baseline to inflate the effect or infer whole-loop
  deadline acceptance. Diagnostic omits resource checkpoints equally in both
  modes. This is engineering timing evidence, not model-performance benefit.
- No deadline, corpus limit, evaluation ruler, holdout, model or production
  setting changed. No commit, push, approval, activation or data deletion.

#### Current combined-check fault/consumer regression completed

- Session 86294 ran six explicit snapshot, settlement-page/runtime,
  monitoring-page/runtime and paged-consumer files. Terminal exit zero:
  **178 passed, 2 deselected in 367.88 seconds (6:07)**. Only the two
  `large_monitoring` acceptance cases were deselected for separate original
  deadline runs; none of the selected fault cases was skipped to mask failure.
- Used command-scoped idle-sleep protection, external guard, `nice -n 10`,
  no bytecode/pytest cache; scratch retained at `wc-run-hej5u14i`. Source was
  not edited during execution. This covers current publication, reconciliation,
  source-change and paged-consumer compatibility after combined validation.
- This is not the full repo gate, large deadline acceptance, actual corpus
  review, reviewed power evidence or domain pilot. No commit/push/activation.

#### Combined-check AU large acceptance started

- After the 178-case regression completed, fresh native process inventory found
  no active daily scheduler/pytest/research supervisor. Session 83158 runs the
  unchanged AU large monitoring test with full downstream review assertions,
  original 1,300 predictions, >5,000 references, one true settlement and
  600-second per-phase deadline. Base remains pinned e122.
- External scratch is `wc-run-ssjqkkl_`, with the same command-scoped idle-sleep
  protection, `nice -n 10` and no bytecode/pytest cache. Eight source/test SHA256
  values were captured in `stage5_combined_large_hashes` for after-run comparison.
  Snapshot source hash is `b2aa0b2a5c2f593ba9c08c7be13e8bf8db54f405b6a3fb1e47fa4a5c595cdc6c`;
  settlement-page hash is `e1942b41cdf3e58260ce267ab78f3f9d03b7ff483f1c24c40479ab5cc6abbc6e`.
- Status is in progress, not accepted coverage or successful performance repair.
  Do not modify source while this attempt runs. No commit, push, approval,
  production activation, ledger mutation or source removal.

#### Combined-check large AU still fails at whole-corpus completion

- Session 83158 terminal exit 1: **1 failed in 604.86 seconds (10:04)**.
  Native phase outcome is `timed_out`, return code -15, null result and
  `publication=unconfirmed_reconcile_before_retry`; executor wall was
  597.538689583 seconds, user/system CPU 344.725059/173.786834 seconds.
- All eight captured source/test SHA256 values matched after the run. Source,
  fixtures and original 600-second deadline were unchanged during execution.
- The failed workspace contains all **13 monitoring page files**. This proves
  page publication progressed, not accepted whole-corpus coverage, verified
  monitoring samples or completed review. Inspect complete coverage receipt
  and final replay boundary before proposing another repair; keep failed data.
- Read-only coverage-file inventory found only `prediction-coverage.json`, not
  `racing-monitoring-coverage.json`. The first monitoring aggregate therefore
  had not reached complete coverage publication when the phase was terminated.
- Same-page engineering timing improved but did not meet the requested complete
  deadline. Do not release as a solved performance fix or infer model benefit.
  Required next work targets redundant final corpus replay with complete source
  binding/mutation/fault coverage intact. No commit, push or activation.

#### Remove nested duplicate corpus replay while retaining two complete passes

- Two new RED cases traced native joins in ordered three-page AU/HKJC corpora:
  existing aggregation rebuilt each page twice inside each of two full passes,
  yielding four rounds. Both failed the required `page_ids * 2` ordered trace.
- Extracted private `_inspect_racing_monitoring_page_once`. Public single-page
  inspection still reconstructs twice and compares complete encoded proofs.
  Corpus aggregation still performs two complete ordered passes, compares each
  page to supplied canonical proof on both, and revalidates full metadata before
  and after each pass. No caller skip flag or authority input was introduced.
- Private rebuild validates native feature, settlement and monitoring report
  hashes before constructing the unchanged page proof. Cross-prediction binding,
  native source/provenance checks, page bounds and false promotion flags remain.
- Existing cross-page mutation test injection moved from the public single-page
  wrapper to the actual private corpus rebuild entry point; trigger after the
  last page of the first full pass and rejection assertion are unchanged. No
  weakened expectation, smaller corpus or increased deadline was used.
- Session 61215 GREEN: **75 passed in 64.66 seconds**, terminal exit zero,
  explicit monitoring-pages and snapshot test files, external scratch
  `wc-run-zoigvd_j`. Quick gate passed with unchanged scoring goldens and docs;
  local meeting corpus/full suite skipped. Current runtime/consumer fault and
  original large deadline acceptance remain required, not inferred from this.
- No model/ruler/holdout/promotion/release policy change, commit, push,
  activation, data deletion or claimed completed Stage 5.

#### Current two-pass replay fault/consumer regression complete

- Session 14447 completed the same six explicit snapshot, settlement-page/runtime,
  monitoring-page/runtime and paged-consumer test files after replay extraction.
  Terminal exit zero: **180 passed, 2 deselected in 318.20 seconds (5:18)**.
  Only original AU/HKJC `large_monitoring` cases were deselected for separate
  unchanged-deadline acceptance. Existing fault expectations were not relaxed.
- External scratch `wc-run-o2aminzy`, command-scoped idle-sleep prevention,
  `nice -n 10`, no bytecode or pytest cache. No source edits during execution.
  This is current scoped safety/compatibility proof, not whole-repo gate,
  large deadline success, actual corpus review, power authority or model benefit.
- Next required observation is the original large corpus-plus-review case.
  No commit, push, release approval, production activation or source removal.

#### Two-pass replay AU large acceptance started

- After scoped regression exit zero, native process inventory again found no
  active daily scheduler/pytest/research supervisor. Session 27668 runs the
  unchanged AU large corpus-plus-review test: 1,300 predictions, >5,000 refs,
  one genuine settlement and original 600-second phase deadlines. No synthetic
  prediction copy is counted as an additional independent settled sample.
- External scratch `wc-run-0w84c8tt`, command-scoped idle-sleep prevention,
  `nice -n 10`, no bytecode/pytest cache. Eight source/test hashes captured as
  `stage5_replay_large_hashes` for after-run comparison; monitoring-page source
  hash is `0c8f3d495d486c458bd307aebc83f58ab8371ea18ca3ad08b59cac660ed16862`.
- Status is in progress, not accepted full coverage, review or model benefit.
  Source must remain unchanged throughout the run. No commit, push, approval,
  deployment, ledger mutation or data deletion.

#### Two-pass replay large AU: coverage published, confirmation still timed out

- Original session 27668 terminal exit 1: **1 failed in 602.52 seconds (10:02)**,
  corpus `TIMED_OUT / phase_timeout`. Native child exited zero with an
  interruption receipt, not a successful coverage result. Executor wall was
  599.976488625 seconds; user/system CPU 344.415763/173.107361 seconds.
- All eight pre-run source/test SHA256 values matched exactly afterwards.
  Both `prediction-coverage.json` and `racing-monitoring-coverage.json` are now
  present, unlike the prior failure. Coverage existence is not acceptance:
  publication remains `unconfirmed_reconcile_before_retry`, and the original
  assertion fails before the downstream review starts.
- This moves the observed failure beyond initial coverage publication. The
  source-heavy post-publication aggregate/confirmation boundary still exceeds
  the unchanged phase deadline. Keep the failed workspace `wc-run-0w84c8tt`;
  do not resume by treating its unconfirmed coverage as trusted or deleting it.
- Next repair must retain complete source/receipt revalidation after publication
  and reject changes to earlier pages, metadata, native blobs and optional
  companion availability. A receipt-only or mtime-only shortcut is not allowed.
  No performance-complete, model-benefit, full-gate, commit/push or activation
  claim is supported by this run. Stage 5 remains incomplete.

#### Read-only timeout investigation (no fix claimed)

- `run_prediction_corpus_request` freezes all metadata once and calls
  `persist_prediction_page` for every planned page. That function calls
  `verify_prediction_inventory`, which rebuilds the full inventory with native
  file and directory rechecks. Thus 17 pages entail at least 17 additional
  complete metadata scans before final aggregation; this call structure is
  confirmed in source, not a measured wall-time attribution.
- Final aggregation also rebuilds the inventory and replays every page's blob
  proof against current source. Those checks protect against source mutation,
  omitted metadata and forged publication and must not be silently removed.
- An independent shared-suite pytest process (PID 13593) was observed running
  concurrently, outside this candidate's external fixture workspace. No other
  session was stopped or changed. Resource contention remains an unexcluded
  explanation; no profile or clean comparison has isolated its contribution.
- First investigate scan counts and phase timings using the retained failed
  fixture after this run becomes terminal. No timeout expansion, raised read
  budget, narrowed corpus, trusted caller skip flag or source edit was made.

- During the still-running AU monitoring fixture, a two-second native
  `sample 18763 2 10` completed (session 58647, exit zero). Output is retained at
  `/tmp/Python_2026-10-11_123701_ALx1.sample.txt`. It sampled 180 main-thread
  stacks and reported 41.5 MiB footprint, 43.2 MiB peak. Collapsed top-of-stack
  counts include `lstat` 40, Python frame evaluation 32, `open` 15 and `stat` 12.
  Python function names are not resolved by this native sampler: this is
  evidence of active metadata/path-related work in that short interval, not
  proof of which Python call dominates the entire phase or causes the earlier
  prediction timeout. No program or source was changed by sampling.

#### Heartbeat recheck — 2026-10-11T01:51Z

- After the interrupted observation, session 44453 remained live with pytest
  PID 13427; a second `F` was emitted. The AU monitoring phase
  `racing-monitoring-corpus-dp909wsb` has a terminal native outcome:
  `timed_out`, return code -15, wall 597.853639417 seconds, user/system CPU
  306.759594/150.713663 seconds, peak RSS 45,888 KiB. Result is null and
  publication remains unconfirmed. This is a second failed large acceptance,
  not a successful monitoring proof. Remaining pytest cases are not yet terminal.
- Fresh Central status still lists the same five pushed evaluation/automation
  releases, none eligible under this heartbeat's code/docs_tests research-only
  approval. No release was approved, merged or activated.

#### Seven-case run terminal — heartbeat 2026-10-11T05:53Z

- Re-polled the original session 44453, not a restarted test run. Terminal
  exit code is 1: **3 failed, 4 passed, 137 deselected in 1587.09 seconds
  (26:27)**. The failures are the 1,700-record prediction corpus case and
  both AU/HKJC large monitoring corpus cases, all reporting `timed_out`.
- The four passing cases cover feature page primitive/runtime large-reference
  behavior only; they do not establish monitoring acceptance, full gate or
  complete Stage 5. The timeout assertions, corpus sizes and safety checks were
  unchanged. No source fix has been attempted during the run.
- Required next work is to measure redundant inventory/metadata verification
  and repair the bounded runtime while retaining source mutation detection,
  full history coverage, unchanged deadlines and fail-closed publication.
  Preserve all failed workspaces; do not overwrite them or claim a release is
  eligible from the earlier 434 scoped passes.

#### Detached native page projection — continuation 2026-10-13

- Reduced metadata copying only: `_begin_read` projects selected predictions,
  their decisions/settlements and model-release parents before deep-copying.
  Public `read` remains complete and detached. Every projection still digests
  ALL original metadata files and verifies ALL recorded directory listings;
  native end-of-read recheck remains unchanged. No blob or label cache added.
- Native reports retain the full validated graph count, not the projected
  count. AU and HKJC keep their distinct tuple/record formats. Exact report
  parity covers selected, empty, unknown and wrong-kind selections.
- TDD RED: 6 failed / 2 passed (unsupported selection argument), external
  scratch `wc-run-yexez6qd`. GREEN: snapshot plus both native settlement suites,
  70 passed in 19.91s (`wc-run-ths87_9p`); added selection edge cases,
  14 passed / 46 deselected in 0.43s (`wc-run-gnzer94o`). Tests cover changes to
  unselected source bytes both before reading and during the final recheck.
- Settlement and monitoring page suites: 40 passed in 51.73s
  (`wc-run-vsyfoen9`). Quick gate passed twice; AU/HKJC 120-horse scoring
  goldens unchanged. Worktree lacks live meeting corpus, so quick data-contract
  checks are skipped; full repository gate and large acceptance remain unproven.
- Pre-acceptance hashes: snapshot `5ca244dc45ec9581cf36dcda6daa2c9327ee9ec7a46fe3d67f6c0fee0be07198`,
  AU native `f1546c5bdfebefb5cdc9c77b3291d579020fcb05f63ccc35d649f659b0424bd9`,
  HKJC native `8f6c24af5bbdeff181ce176efb73afb613243430be573788fea883ef3e955cd3`.
  Large monitoring test unchanged:
  `38ee3b4b96466900449155ea4727b89d5ec9823ec56db8678241c90d0f08842d`.
- No commit, push, merge, activation, ruler/model changes or source removal.
  This is engineering verification, not evidence of model performance gains.

#### Projected-copy AU large acceptance failed — 2026-10-13

- Re-polled original pytest session 58956 to terminal exit 1; no restart or
  concurrent source edits. Original 1,300 predictions / >5,000 references /
  600-second corpus and review limits unchanged. Result: **1 failed in 604.66s**.
- Authoritative phase outcome at external scratch `wc-run-9gqx14kt`, phase
  `racing-monitoring-corpus-t_v7ogpm`: `timed_out`, child returncode -15,
  wall 597.709005542s, user 331.619853s, system 175.763063s, peak RSS 62,160 KiB.
  Result null; publication `unconfirmed_reconcile_before_retry`. Preserve this
  workspace as failed evidence; no review success or monitoring proof claimed.
- All 13 monitoring page files existed; only prediction coverage was confirmed
  present during observation. Page file presence does not establish final
  corpus acceptance. The test stopped before the review assertions.
- Post-run snapshot/AU-native/HKJC-native/large-test hashes exactly match the
  pre-run hashes recorded above. Reduced copying alone is insufficient.
- Next diagnosis: settlement page inspection still invokes complete prediction
  page inspection twice, alongside before/after complete metadata validation and
  native label inspection. Measure that repeated work before another change;
  retain whole-source mutation detection and post-publication confirmation.
  No deadline increase, corpus narrowing, release or model authority change.

#### Remaining settlement-page profile — 2026-10-13

- Read-only cProfile of the first retained 100-record AU page in
  `wc-run-9gqx14kt`, with a fresh native snapshot and pre-bound canonical
  inventories. Real `_resource_status` ran at every checkpoint (35,774 calls
  inside the profiled inspection). No source/registry/report writes, deadline
  reuse, persisted cache or operational success claim.
- One `inspect_racing_settlement_page`: 6.814678792s; 13,468,431 calls;
  one native settlement candidate; report hash
  `36d24ca9c6465d5432facfddbf6960f03432c86f62f6e867ab772dbdb4ab76f9`.
  Overlapping cumulative times: two native label calls 3.979s; 11,026 metadata
  reads 3.732s; 816 blob reads 2.634s; resource checks 2.274s; two complete
  metadata verifications 1.851s; two prediction page calls 0.983s.
  These times overlap and must not be summed or extrapolated as a speedup.
- Prediction-page cost alone is not the main repair target. Source inspection
  shows page runtime invokes the public two-pass monitoring inspector before
  publication and again after publication (four native join rebuilds), while
  already publishing and verifying the native companions. Candidate next
  step: use the existing private one-pass join within this before/after pair,
  preserving BOTH complete native rebuilds, companion checks, original public
  two-pass behavior and post-publication mutation rejection. Prove two-pass
  execution plus fault parity in RED/GREEN tests before implementing; no
  caller-controlled skip-validation flag or checkpoint throttling.

#### Paired page-publication replay — 2026-10-13

- New AU/HKJC trace tests first failed: actual native joins were
  `[before, before, after, after]` rather than `[before, after]` (2 failed,
  39 deselected in 3.50s; external scratch `wc-run-cv_2diip`).
- Page runtime now invokes the existing one-pass native join before publication
  and again after publication, compares complete proof bytes, then retains
  companion recheck, input binding and final checkpoint. Public two-pass
  inspector and corpus two-pass replay are unchanged; no skip flag added.
- Scoped regression terminal: **94 passed, 2 large cases deselected in
  237.51s** (`wc-run-k5umfjju`), covering page runtime, native monitoring pages
  and paged review consumers, including source mutation at publication,
  missing/forged companion and resource-failure cases. Quick gate passed;
  scoring goldens unchanged; absent meeting corpus checks skipped.
- Full gate and original AU/HKJC large acceptance remain unproven. This change
  is uncommitted/unpushed/unactivated, with no ruler/model or production change.

#### AU large corpus phase passes; review still live — 2026-10-13

- Original pytest session 2959 remains live, external `wc-run-a6a6r0l7`.
  Corpus phase `racing-monitoring-corpus-ly7m4fhw` now has authoritative
  `succeeded / receipt_verified`, returncode 0, wall 517.293831041s, user
  287.573332s, system 151.22918s, peak RSS 62,208 KiB. Original 600s deadline,
  1,300-record/>5,000-reference corpus and all acceptance assertions unchanged.
- Receipt content hash:
  `18e5f780a16231e2bc8491ea3f101c959c18a4bc59ea0acca59cec41b0ecae7b`.
  Receipt reports one verified monitoring sample and no model-promotion,
  reevaluation-promotion or terminal-label authority.
- Process inspection confirms original pytest PID 90690 now owns live review
  child PID 91655, request `review-3g16h4fp/request.json`. Do not restart or
  edit source while it runs. This is corpus-phase success only, not terminal
  pytest/review acceptance, HKJC coverage, full gate or Stage 5 completion.

#### AU large corpus AND real review terminal pass — 2026-10-13

- Original session 2959 terminal exit 0: **1 passed in 851.83s (14:11)**.
  No restart, source edits, deadline expansion or corpus narrowing during run.
  Original fixture checks 1,300 predictions/>5,000 refs/13 pages, exactly one
  real label, complete coverage and no model-promotion authority.
- Corpus outcome remains `succeeded / receipt_verified` at 517.293831041s.
  Review phase `review-3g16h4fp` independently succeeded with verified receipt:
  wall 291.747630708s, user 149.523748s, system 76.139358s, peak RSS 64,080 KiB,
  returncode 0; summary hash
  `d699de148b9665561ffb10917236e3eb857ffcefad4ba6e31f01cdff240fc243`.
  Both phases remain below their separate original 600s limits.
- Terminal test also proves current/previous native projections match with one
  qualified unit, no fabricated sample growth/promotion, and unchanged bytes
  of all completed corpus companion files after real review-child replay and
  bounded parent verification. Telegram delivery remains unconfirmed/false;
  this is not production notification acceptance or a real-domain pilot.
- Post-run snapshot, both native settlement modules, monitoring runtime and
  runtime tests exactly match pinned hashes recorded above. External failed
  and passing workspaces retained. HKJC counterpart, other large regressions,
  current-base full gate, live acceptance and Tasks 6–10 remain open.

#### HKJC large corpus passes; real review still live — 2026-10-13

- Original session 7524 remains live in external scratch `wc-run-t2v6k3q2`.
  Authoritative corpus outcome `racing-monitoring-corpus-yn5txvvx` is
  `succeeded / receipt_verified`, returncode 0, wall 536.584739750s,
  user 289.932769s, system 155.280666s, peak RSS 59,184 KiB. Original 1,300
  predictions/>5,000-reference corpus and separate 600s limits unchanged.
- Corpus receipt hash:
  `2f6ef4fa5e265e531683a018be83e6155e8be9aebe2e37ee964d1aa900c53dcd`.
  One verified monitoring sample; no model-promotion, reevaluation-promotion
  or terminal-label authority. Output existence alone was not accepted.
- Original pytest PID 92341 now owns live review child PID 94647 at
  `review-dz4_azbx/request.json`. Keep source pinned while this runs. HKJC
  terminal review/pytest acceptance, full gate and Stage 5 exit remain unproven.

#### HKJC large corpus AND real review terminal pass — 2026-10-13

- Original session 7524 terminal exit 0: **1 passed in 873.63s (14:33)**.
  Same original 1,300-prediction/>5,000-reference/13-page fixture; corpus
  536.584739750s and actual review child 296.614859667s each fit separate
  unchanged 600s deadlines. No concurrent source edits or restarts.
- Review `review-dz4_azbx` outcome `succeeded / receipt_verified`, returncode 0,
  user 149.299486s, system 78.025632s, peak RSS 62,720 KiB; summary hash
  `f8d237b6dc4b0e707052d6e964c739fea8587fd90ee382011beefb113cae1bac`.
  Original terminal assertions verify one real sample, identical current/prior
  projections, no sample growth/promotion and unchanged completed companion
  bytes after review. Telegram delivery remains unconfirmed/false.
- AU and HKJC large acceptance now both pass on pinned `e122c13a1583` plus the
  unsaved reader payload. Neither is a real pilot or full repository gate.
  Local origin/main is now `c9620bd0f373`; upstream changes are outside the
  current reader paths. Fresh remote recheck, byte-preserving base alignment
  and full gate on that base are required before any release claim.

#### Fresh-base alignment and gate preflight — 2026-10-13

- Fresh `git fetch origin main` confirms `c9620bd0f37381a7b3634e3b8d2e2f8b5247c6f1`.
  All 150 upstream changed paths are disjoint from the 34 unsaved reader paths.
  Isolated worktree fast-forwarded from `e122c13a1583` only; all dirty/untracked
  file SHA256s, tracked binary-diff digest, path inventory and empty staged
  index were identical before/after. No push or production checkout change.
- New-base AGENTS storage rule read: large scratch stays on mounted external
  disk; Mac headroom >10 GiB required. Disk preflight found Mac 25 GiB,
  external 828 GiB available. AU morning production PID 95395 became active,
  so the heavy full gate was NOT launched then. Subsequent heartbeat process
  recheck finds that PID absent and no domain/research heavy process active.
- Full gate will run all original suites including large cases, no exclusions,
  through the external-run guard. Prior e122 fixture passes are historical
  evidence, not a full gate for this newer base. Candidate remains unsaved.

#### Full repository gate terminal pass on c962 — heartbeat 2026-10-13T09:15Z

- Original full-gate session 73750 terminal exit 0. Exact command:
  `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents/skills /usr/bin/caffeinate -i python3 /Users/imac/Antigravity-repo/.agents/scripts/wongchoi_external_run.py -- nice -n 10 ./檢查.sh`.
  Isolated HEAD `c9620bd0f37381a7b3634e3b8d2e2f8b5247c6f1`; scratch
  `wc-run-8nn9xer2` on mounted external disk; no `-k` exclusions.
- All 15 suites passed: Python 4,519 passed, 2 expected failures, 16 Dashboard
  skips; Node 84 passed. Shared Wong Choi **1,602 passed in 2858.19s (47:38)**,
  including original large prediction, feature and AU/HKJC monitoring/review
  cases. Tennis 634 passed in 151.64s. Ruff, both 120-horse scoring goldens
  and model-description freshness also passed.
- Meeting data-contract checks skipped because this isolated checkout has no
  local scored meeting corpus. Dashboard skips and known parser return-value
  warnings remain reported, not converted into live acceptance. Full code
  gate does not establish production health, reviewed power or real pilots.
- Post-run every Python payload SHA256 matches pre-alignment capture; HEAD
  unchanged, staged index empty, `git diff --check` clean. No source change
  during the gate. This records engineering gate only, not model improvement.
- No own pending immutable release exists: payload still 34 unsaved paths.
  Heartbeat cannot create/save a release or approve unrelated evaluation/
  automation pendings. Require explicit 34-path scoped save/push direction;
  subsequent approval must independently satisfy all heartbeat conditions.

- Fresh Central status now lists **6** pending evaluation/automation releases,
  including new `8719f64f7c88` (automation). None qualifies for this heartbeat's
  code/docs_tests scope. All retained pending; no approval attempted. Existing
  Telegram path delivered the full-gate/scoped-save notice and corrected the
  initial historical five-pending count to six. Required human decision is
  explicit 34-path history-reader scoped commit/push, not blanket approval.
