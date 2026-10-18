# Stage 5 reader release recheck — 2026-10-18

## Decision

PENDING. The initial controller full gate passed, but the mandatory clean-clone approval gate failed. No approval, main merge or activation is established for this reader release. Do not substitute the earlier integration gate for the approval gate.

## Immutable identity and scope

- Reader commit: `92004edd5bbae6d240477cc95f40bda5d2417c03`.
- Release: `wc-release:92004edd5bba:2026-10-18T033851.038240_0000`.
- Remote branch: `codex-stage5-reader-release-20261018`.
- Rollback target and last observed remote main: `f852b3d5149790aad4b611e41a432cb6db07aa59`.
- Exactly 36 selected paths: shared Stage 5 history reader, matching tests, two Stage 5 audit documents and `wong-choi-stage-5-plan.md`.
- Byte-for-byte comparison against saved integration reader `80823162beb722bfe038bace31aa8f856e9ce7ac` succeeded before release; the independently approved storage test correction is already in the base, not in this scope.
- Policy: `code`, `full`; four-domain code sync, no installer, no Dashboard deploy, no manual reason. This classification is not approval.

## Controller outcome

`保存.sh` ran via the mounted-external-scratch wrapper and `nice -n 10`. Its initial full gate returned zero, then exact-scope commit and push succeeded. The controller subsequently returned `approval recheck gate failed`, `automation_status=blocked`, activation `not_started`. Terminal execution handle: `38306`, exit 1. The manifest preserves `check_exit_code=0`, `push_exit_code=0`; neither proves approval acceptance.

Controller scratch: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-04u_esfw`.

The existing approval helper captures subprocess output and raises only a generic failure; its temporary clean checkout is removed on exit. The failing suite and root cause are therefore **unknown**, not inferred to be a timeout, resource issue or the previously fixed TMPDIR test. No timeout or assertion has been changed.

## Diagnostic reproduction in progress

The unchanged `_run_gate_in_clean_clone(repo, reader_commit, "full")` is being rerun. A temporary observer calls the original `_run` unchanged and prints the gate's captured stdout, stderr and exit code. It does not approve, merge or activate, and does not change the command, return value, timeout, scope or tests.

- Launcher: `/private/tmp/wc-reader-approval-diagnostic-20261018.py`.
- Execution handle: `79783`.
- Retained log: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-wpaeu2_s/approval-diagnostic.log`.
- Last observation: process and Shared Wong Choi test child live; no terminal result. Empty log while capture is in progress is not success or failure.
- A separate Claude test run was observed in `/Users/imac/wt/claude-au-trial-report-20261018`; it was not terminated or modified. Parallel load is an observation, not an established cause.

Re-poll the same live handle. If it fails, isolate the actual reported failure before changing code. If it passes, that is diagnostic evidence only: approval must still go through the existing release controller and fresh immutable remote/main checks. No direct push to main is authorized by this audit.

## Other current acceptance evidence

- Installed AU/HKJC/NBA/Tennis launchd paths and loaded state were aligned to `/Users/imac/wongchoi-scheduler`. Central durability was aligned; `com.antigravity.central-wong-choi.research-review` was missing. No installer was run.
- Production power applicability recomputation verified **0/4** profiles, all `power_profile_missing`; report content hash `072d1b455e322d2ceab6378f9a1083f38b9e00631f372386f4681569a07e8f2f`. NBA remains descriptive-only. No numeric profile or promotion authority was fabricated.
- Tennis card's installed plist identifies live SQLite `/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`. A `mode=ro`, `query_only=ON` metadata inspection found 1,747,382,272 bytes and existing source/prediction/feature/odds tables. This was schema inspection only, not integrity, PIT, coverage, outcome or pilot acceptance. No archive DB was substituted.
- Prior Central observation: AU/Tennis latest runs succeeded, HKJC lineup was running, NBA health dormant; AU/NBA 30-day SLO remained below target. D1 local restore and WARM backup were verified; COLD backlog remained. HOT about 22 GiB free; mounted WARM about 819 GiB. These observations are time-bound, not exit acceptance.

## Next requirements

1. Finish the live diagnostic, retain complete result and hash the log.
2. Resolve the demonstrated gate failure without relaxing bounds or bypassing controls; refresh immutable release if code changes.
3. Revalidate the original standing-approval scope and use the existing controller for any approval/merge/activation; verify all configured production domains afterward.
4. Keep Tasks 6–10 open: reviewed power design, live review scheduler/Telegram/Dashboard acceptance, real Tennis and racing pilots, NBA forward evidence, operational/fault/resource checks and final exit audit.

This audit is preservation on a non-main branch, not another release or a deployment instruction.
