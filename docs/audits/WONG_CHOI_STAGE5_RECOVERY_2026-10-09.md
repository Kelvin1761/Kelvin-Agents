# Stage 5 recovery checkpoint — 2026-10-09 Sydney

## Authoritative observations

- Locally tracked main and read-only `git ls-remote origin refs/heads/main` both return `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d` at this checkpoint.
- `/private/tmp/wc-stage5-dtennis-adapter-20260920`, `wc-stage5-dnba-adapter-20260920`, `wc-stage5-e2-review-runtime-20260921`, and `wc-stage5-roadmap-refresh-20260921` are missing/prunable. Their uncommitted bytes have not been recovered. Git worktree registrations were preserved.
- Main retains D producers, AU/HKJC adapters, power authority binding and E1. Later Tennis/NBA production adapters and E2 template/wrapper are absent from the main tree.
- Read-only installed-plist and launchctl probe with production root `/Users/imac/wongchoi-scheduler`: four domains and Central durability aligned/loaded. `launchctl print gui/501/com.antigravity.central-wong-choi.research-review` exits 113: service missing.
- Central status reports current AU/Tennis success, HKJC dormant, NBA partial and attention for NBA SLO, pending/failed releases, D1 WARM backup and artifact COLD backlog. Registry model stages remain AU/HKJC production and Tennis/NBA shadow; historical registry commit labels are not proof of current live model bytes.
- Current release registry has four unrelated pending records: `7aa8cda63dde`/`9c055061ef6c` (model), `8b93e87f6a95`/`165f923a1aa4` (code). No newly prepared Stage 5 recovery release exists. They were not approved/rejected/refreshed by this checkpoint; heartbeat authority does not permit bulk approval or approval of model releases.

## Recovered E2 inspection behavior

New `review_runtime_status` and CLI `--status [--receipt PATH]` inspect existing state without initialization or repair. Cursor configuration/schema/hash/authority must match all four frozen bindings and contain every required table. An explicitly selected receipt must be a bounded regular file under Central runs, without symlink components, matching its canonical hash, schema, release, path and exact four-domain set. Invalid/future time, inconsistent aggregate disposition and promotion/delivery authority fail closed. Success older than 36 hours is stale; a genuine failed/deferred/partial pass remains visible and blocked rather than being rewritten as success.

The four-lock wrapper and daily 07:10 Sydney launchd template are restored. `install_research_review.sh` initializes explicitly and requires a verified successful first-pass receipt before publishing the job; failed acceptance retains the append-only run evidence. It snapshots the old research plist/loaded state and guards rollback against concurrent plist bytes. Unified cutover explicitly enables this installation and snapshots both Central labels. Ordinary durability installation does not implicitly initialize research. Installed-path verification and unified rollback now also cover the current HKJC intraday/lineup jobs, absent from the earlier label lists.

## Validation and remaining work

- Central review focused tests: 21 passed, including non-mutating inspection, missing tables, correctly rehashed invalid release/authority/domain/time, tamper, symlink, oversized receipt, stale success and faithful blocked receipt.
- Quick gate passed; both scoring goldens 120/120 unchanged. Data-contract corpus checks skipped in isolated checkout because no local meeting corpus is present; this is not production-data verification.
- Initial sandboxed full-gate invocation cannot establish readiness: cache and runtime-directory writes were denied. Full gate was re-run with approved filesystem access; completion is recorded separately when observed.
- Central review/maintenance focused tests: 28 passed. Combined review/maintenance/runtime focused tests: 36 passed; final runtime recheck including exact all-label rollback assertion: 8 passed. Successful and blocked first-pass acceptance are isolated fixtures, not live research evidence. Shell syntax/plist parsing and final quick gate pass.
- E2 source full gate is complete. Real production acceptance, Tennis/NBA adapter recovery, F/C acceptance, numeric power readiness, real pilots and exit gate remain incomplete.
- Final-source full invocation with Node 24: all 14 Python suites pass, including Shared Wong Choi 1,214 tests; Node wrapper fails because Node 24 emits the spec reporter while `run_tests.sh` expects TAP `# pass`/`# fail`. Direct Node execution passes all 78 tests. No test-wrapper change was made to hide this incompatibility.
- Official final full gate: `env PATH="/Users/imac/.nvm/versions/node/v20.20.2/bin:$PATH" ./檢查.sh`, run in `.codex/worktrees/wc-stage5-runtime-recovery-20261009`, terminal session 2616 exited 0. All 15 suites passed (14 Python suites and Dashboard Node 16 + 62 tests); Shared Wong Choi 1,214 and Tennis 570 passed. AU/HKJC scoring goldens remained unchanged. Existing expected failures/skips and absent-corpus data-contract skips remain disclosed; this source gate does not establish live acceptance.
- No commit, push, approval, merge, activation, scheduler installation or production-state write performed by this recovery checkpoint.

## Latest-main integration

- Verified remote main and production advanced through another approved/merged/activated release to `2b692cff1ef3eff253b8dc4b65206b82e4d8e9ef`. Isolated E2 branch fast-forwarded to this existing commit with all uncommitted recovery paths preserved and no overlap. No new commit/push/main merge/activation/install performed by this task.
- On this updated base, exactly the Central review, daily-maintenance and runtime-installer test files pass 32 tests. This narrower selection is not the earlier 36-test combined selection nor latest-main full-gate proof. Previous `2616` gate is historical; a refreshed full gate is still required.
- Current baseline runtime checker (without E2's added labels) reports four installed domain mappings and Central durability aligned. E2 preview's missing research-review/intraday requirements represent pending E2 acceptance/installation, not an assertion that the baseline's installed jobs are broken.

## Exact recovery scope / authorization checkpoint

Read-only `changed_paths` + existing `classify_release`/`activation_plan`, without calling release preparation (which fetches/stages/saves):

| Separate recovery | Exact paths | Policy | Inferred activation |
|---|---:|---|---|
| D-Tennis plus optional shared writer guards | 7 | code / full | Sync four domains; no installer or Dashboard deploy |
| D-NBA adapter | 5 | automation / full | NBA sync; no installer or Dashboard deploy |
| E2 inspection/launchd/installer plus roadmap audits | 13 | automation / full | Four-domain sync; unified production-runtime installer; no Dashboard deploy |

- `auto_push=true` is a controller capability, not human save authorization. No release preparation, staging, commit, push, approval, main merge or activation was invoked by this scope check.
- All three scopes fail the heartbeat's narrow research-only auto-approval condition: Tennis/NBA are production adapters; NBA/E2 also have automation risk; E2 includes launchd/installer. Do not relabel paths, split tests out to sneak activation through, or infer approval from a heartbeat.
- Current explicit E2 instruction remains source implementation only, no commit/push/activate. Request fresh exact-scope save authority before delivery; immutable SHA activation approval remains separate.
- Each latest-main full gate must complete on its own actual scope. Tennis publication/no-bet gate `88112` exited 0, all 15 suites passed (Shared 1,218, Tennis 614). NBA gate `47839` also exited 0, all 15 suites passed (Shared 1,213, NBA 102, Tennis 570). E2 latest-base full gate started only after NBA completion, terminal session `49830`; completion is not yet observed. Poll the same handle rather than restarting on observation timeout. Source/full-gate success is not live pilot evidence, power authority readiness or Stage 5 exit.
- Heartbeat pending-release recheck found `07a49d4224ee` (AU automation/domain-engine/launchd), `2a3cb4ec0f0e` and `9c055061ef6c` (HKJC model; latter also Dashboard). None is a qualifying task-created research-only release. All left pending; authorized production Telegram notification returned `ok=true`, `status=sent`, one target/part. Message explicitly requests separate immutable-SHA decisions and fresh recovery scoped-save authority; no release approval or activation attempted.

## Installer interruption / partial-copy recovery

- E2 gate `49830` reached terminal exit 0 (all 15 suites; Shared 1,214, NBA 88, Tennis 570, Node 16 + 62). Goldens unchanged; missing-corpus contract checks skipped. This gate predates the following fixes and is not final-payload proof.
- Real installer in isolated mini-repo, fake launchctl and fake copy: signal immediately after unloading left the old job unloaded; partial copy left the installed plist truncated. Before fixes: two failures, three passes (session `75716`). No host launchd or production receipt was used.
- Fix sets recovery boundary before unloading, prepares complete candidate bytes beside destination before any unload, then publishes by same-filesystem rename. Cleanup accepts unchanged previous bytes as well as candidate bytes for restoring previously loaded state; concurrent different bytes still block rollback. Pre-publication destination checks refuse detected concurrent changes. These checks do not claim a general cross-process filesystem compare-and-swap lock.
- After fixes: 37 focused tests pass (`4568`), including interruption, partial-copy failure, bootstrap failure, concurrent-write refusal and success; quick gate passed. No new paths beyond the 13-path E2 scope; no save/push/install/activation. Refreshed full gate still required before handoff.
- Fault-inclusive refreshed full gate `24490`, using Node 20, reached terminal exit 0: all 15 suites passed (Shared 1,219; NBA 88; Tennis 570; Node 16 + 62). Code checks and both scoring goldens pass; missing AU/HKJC corpus checks remain skipped. This proves source regression readiness, not production installation or live pilot acceptance.
- Post-gate read-only verification: remote main and production both remain `2b692cff1ef3eff253b8dc4b65206b82e4d8e9ef`; baseline runtime `aligned`. At 07:54 UTC, AU/Tennis succeeded and HKJC/NBA dormant; stages AU/HKJC production, Tennis/NBA shadow. Dashboard configured; D1 snapshot 37.58 hours old with WARM pending, HOT free 23.69 GiB warning, WARM available, COLD catalog 10/11 verified. No runtime/backup/ledger write performed.
- Production power-applicability inspection recomputed content hash `072d1b455e322d2ceab6378f9a1083f38b9e00631f372386f4681569a07e8f2f`: all four frozen rulers found, zero reviewed profiles verified, each domain blocked by `power_profile_missing`; no sample or promotion authority granted. Task 6 and full Stage 5 exit remain incomplete.
- Next delivery action requires fresh human authorization for separate Tennis 7 / NBA 5 / E2 13 exact-path saves via the existing release manager; activation remains a separate immutable-SHA decision. No qualifying research-only recovery release exists for heartbeat approval. Do not substitute unrelated pending releases or bypass source-only E2 restrictions.

## Authorized three-batch delivery

- Kelvin explicitly authorized Tennis 7 / NBA 5 / E2 13 exact-path scoped commit/push, with no merge/activation. All three controller dry-runs showed exact scope, no unrelated dirty paths, full gate and `auto_merge=false`, `auto_activate=false`.
- Remote `refs/heads/codex` already exists, preventing Tennis's slash-prefixed branch from being pushed. Renamed only the isolated recovery branch to `codex-stage5-tennis-adapter-recovery-20261009`; source scope unchanged.
- Tennis controller save (`27542`) exited 0, full gate 0, push 0, Telegram sent. Commit `6a6e97f34781d77526bda9c5b60852b24002edf6`, seven paths, status `pushed`, activation `not_started`. Independently verified remote branch equals this SHA, worktree clean and remote main remains `2b692cff1ef3eff253b8dc4b65206b82e4d8e9ef`.
- NBA controller save `94129` exited 0, full gate 0, push 0, Telegram sent. Commit `239195dce6380cd93a62d5ed296b886ca52fea02`, five paths, status `pushed`, activation `not_started`.
- E2 is the final authorized 13-path save; no merge/activate authority was granted. Controller re-runs full gate before staging, committing and pushing. This audit records the pre-save checkpoint; the resulting immutable manifest, not a predicted SHA in this file, is authoritative for its eventual save outcome. All three releases require separate activation decisions and fresh main/rollback checks.
