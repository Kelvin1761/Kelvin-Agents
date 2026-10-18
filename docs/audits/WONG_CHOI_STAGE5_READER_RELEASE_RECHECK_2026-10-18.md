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

## Terminal diagnostic result and isolated cause

Handle `79783` is terminal, exit 1; do not restart or poll it as live. The unchanged clean-clone gate reproduced exactly one failure: `NoStaleEngineConstantCopies.test_allowlist_has_no_dead_entries` in `.agents/skills/au_racing/au_wong_choi_auto/tests/test_no_stale_engine_constant_copies.py`. Fourteen suites passed; only AU failed (1 failed / 1,246 passed). Shared Wong Choi passed all 1,609 tests in 3,113.78 seconds, with every original large case included. Overall Python: 5,100 passed, one failed, two expected failures and 16 Dashboard skips; Node: 89 passed. AU/HKJC goldens and generated model explanations passed. Clean clone lacked untracked local data-root markers, so both meeting data-contract checks skipped; the initial controller gate had checked actual local corpora.

Retained complete diagnostic log SHA256: `b7e81414d63f77354150fc95b83b679bce254b8725d2e8dd79b851b7eb6a7b36` at the path above. Its final marker is `UNCHANGED_APPROVAL_GATE_EXIT=1`. This does not replace either failed approval with a green result.

The scanner tests every component of `path.parts` against `scratch`, `archive` and `__pycache__`. The mandated external TMPDIR is below `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/`; therefore the scanner excludes **all** repository Python files in the clean clone. All ten legitimate allowlist entries appear dead, and the literal-copy test passes vacuously. This is an upstream test-discovery defect, not a reader failure or evidence of model degradation. The same scanner file is unchanged between the reader commit and the subsequently fetched main.

The independent fix branch `codex-au-scan-root-fix-20261018` is based on newer main `1528d16e`; its single-file commit is `435996dfc3ff49b18075b1250a695d30dfd5e190`. It changes exclusion matching to `path.relative_to(root).parts`, keeping true in-repository scratch/archive/cache and defining-file exclusions. A regression exercises checkouts beneath each excluded ancestor while requiring `live.py` to remain discoverable. The new regression first failed (1 failed / 2 passed, `wc-run-0uizeg_0`), then all three tests passed after the minimal fix (`wc-run-4bdaaf8c`); repo quick gate passed with actual AU/HKJC corpus checks and unchanged goldens (`wc-run-9hlsnacc`). No original assertion or allowlist entry was removed; no model, ruler or timeout changed.

The new AU test path is **outside** the standing Stage 5 automatic-approval scope. Preserve the one-file fix on a non-main branch and request a separate human scoped release/merge decision. Do not fold it into the reader release or approve other pending releases. The full AU suite in a true external scratch clean clone completed under handle `76734`, scratch `wc-run-ibg88nel`: **1,250 passed** in 28.63 seconds, one existing deprecation warning, terminal exit 0. The clone checked out exact fix commit `435996dfc3ff49b18075b1250a695d30dfd5e190`; no test was selected out or skipped. This proves the isolated fix in the failing path environment, not a successful full reader approval gate or current production activation.

## Large-case diagnostic receipts observed before pytest cleanup

All four publications were `receipt_verified`, with unchanged separate 600-second limits and `model_promotion_allowed=false`. These are fixture evidence, not real pilot/sample-growth or model-quality evidence.

| Domain / phase | Wall seconds | Content hash |
|---|---:|---|
| AU corpus | 565.285152250 | `9accbb5e42b048890a3733c3be6442869c342168ee961d1bbe3fbd4c5cca271e` |
| AU review | 342.004631917 | `8973e50eaed962a91d1bb4a3b311c9df0df5d556174a712149539cef52adc4f2` |
| HKJC corpus | 539.001894250 | `552faeb3af170ec199f79b047527bfb984a97268fb9086b99301e00a2d4f788c` |
| HKJC review | 342.390871583 | `f5e57068fcd323bc190b5c8b812782f3e8fd42a13deb00c9fc7addafe857f0a8` |

Pytest later performs its ordinary old-temporary-directory cleanup. Receipt values above were read directly while available; no agent source deletion or archive migration was performed. The retained gate log remains the terminal suite evidence.

## Concurrent-main expiry

While diagnosis ran, remote main advanced first to `a55f5c6bb0d43afbc63a88844db3459b1c198e56` (AU display-only report changes, six non-overlapping paths), then to `1528d16e` (HKJC prior-distance normalization). The immutable reader branch remained `92004edd5bba`; its rollback target remains `f852b3d51497`. Thus it cannot now pass immutable-main approval even after the isolated test fix. Keep it pending, preserve its failed evidence, and prepare a newly aligned scoped reader release only after the separate fix decision. Telegram notification of the main-expiry condition succeeded (`ok=true`, one part, one target).

Tasks 6–10 remain open. This audit is preservation on a non-main branch, not another release or a deployment instruction.
