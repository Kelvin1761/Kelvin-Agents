# Stage 5 reader recovery — 2026-10-18

## Scope and provenance

This is engineering recovery, not model acceptance, release approval or production activation.

- Fetched base: `efebdb06c62b9e09b2fb7b1f6f0e8228876f7f16`.
- Isolated branch: `codex-stage5-reader-recovery-20261018`.
- Worktree: `/private/tmp/wc-stage5-reader-recovery-20261018`.
- Backup: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-worktree-cleanup-20261014/worktrees/06-stage5-history-reader-Antigravity-repo`.
- Original backup HEAD: `126b6747da1524d8796dbf3f2728493f7318aebe`.
- Patch SHA256 verified: `946fd8a591ac25f92fe530ad28519dcd43b523aa1a24c2209b911d4e5eb94280`.
- All 22 previously untracked backup files restored byte-for-byte and hash-checked. Thirteen tracked changes recovered; no backup data deleted or modified.
- Data-root markers copied from main as required by AGENTS.md. Main and scheduler checkouts were not edited.

## Upstream reconciliation

`git apply --check` rejected the original cursor-test hunk: main raised its timeout from 20 to 120 seconds. Recovery preserves 120 seconds, adds the genuine old-schema producer fixture, verifies migration to the paged coverage schema, and expects a source-verification child failure without advancing either cursor. No test was removed or skipped to resolve this conflict.

The preserved `research_index.py` change uses `lstat` to check symlinks, with pathlib fallback. It requires fresh regression coverage; it must not inherit the earlier 34-path gate result.

## Fresh verification

`env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents/skills python3 .agents/scripts/wongchoi_external_run.py -- nice -n 10 ./檢查.sh --quick`

- Exit 0; external scratch `wc-run-h5pkfziz`.
- Ruff passed; AU and HKJC 120-horse golden snapshots unchanged.
- Generated model descriptions match scoring code.
- Actual data-contract checks ran over AU 60 meetings / 563 horses and HKJC 60 meetings / 747 horses. HKJC passed without warnings. AU warned about neutral track/trial coverage and the new trial-speed field missing from the calibration baseline; these were not hidden or recalibrated here.
- Unit tests were not part of this quick check. Fresh full gate is required before delivery/release. Earlier gate results in the recovered audit remain historical only.

Targeted recheck: `python3 -m pytest -q -p no:cacheprovider` over `test_research_native_evidence_snapshot.py`, `test_research_index.py`, `test_research_review_cursor.py` and `test_research_paged_monitoring_consumer.py` (all under `.agents/skills/shared_wong_choi/tests/`), using the same external wrapper and environment. Exit 0: **166 passed in 53.07 seconds**; external scratch `wc-run-ni1dje9l`. `git diff --check` also passed. This includes the reconciled cursor tests and index symlink rejection, but is not full-gate or live-pilot acceptance.

## Full gate on the recovered payload — failed, not release-ready

Command: `env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents/skills /usr/bin/caffeinate -i python3 .agents/scripts/wongchoi_external_run.py -- nice -n 10 ./檢查.sh`.

- Immutable tested HEAD: `bed38b257e1cf8446173c70bc3fab8ab60d23645`; the worktree was clean before and after execution.
- Terminal session `36401` exited **1**. External scratch: `wc-run-iv_krlzd`.
- **14/15 suites passed; Agent scripts failed.** Across Python suites: 5,114 passed, one failed, two expected failures and two Dashboard skips. Node: 89 passed. Ruff, unchanged scoring goldens, generated descriptions and both actual meeting data-contract checks passed (AU warnings above remain).
- Shared Wong Choi: **1,609 passed in 2,727.55 seconds**. All original large cases were included, with no selection filter, reduced history, altered labels or relaxed timeout. Tennis: 709 passed in 177.40 seconds.
- AU 1,300-prediction/>5,000-reference/13-page case: corpus 559.265149458 seconds, review 334.233480042 seconds, both `receipt_verified` and within their unchanged separate 600-second limits. Corpus hash `329691b3388789d3fc9e09d0b4ad2338c03ed75457ecd95c261e830a641d8afc`; review hash `daec1531a0d8624a40518f43bba2c8134281e3a00176073ff842d33a2a5edefb`.
- HKJC counterpart: corpus 528.172195750 seconds, review 257.809622458 seconds, both `receipt_verified` within unchanged separate limits. Corpus hash `57f9b4b41e060d7e1d271efc86fa6edc3d402c50e0ccebcd63403bfd6908d981`; review hash `05ba3e51f245f35691ae4928bed07262aa45649e77cead39259b1a17d778f25e`.
- Each case retains one real fixture label only, no sample growth or promotion authority, and unchanged companion bytes after review. These are engineering fixtures, not real domain pilots or model-performance evidence.

### Isolated upstream test failure

`test_local_storage_is_not_an_external_volume` passes pytest's `tmp_path` to the external storage inspector and expects a non-`/Volumes` rejection. When the wrapper deliberately routes `TMPDIR` to the mounted external disk, that fixture is a valid external path: the expected exception must not occur. Agent scripts reported one failed, 101 passed and two expected failures.

The failure was independently reproduced on clean `origin/main` base `efebdb06c62b9e09b2fb7b1f6f0e8228876f7f16` without any reader changes: one failed in 0.05 seconds, external scratch `wc-run-1uqq1wgx`.

A separate one-file WIP branch `codex-external-scratch-test-20261018`, commit `6985b534300ef6f3066a9534545d5c10ad94cf07`, uses a lexical non-`/Volumes` path anchored at the filesystem root and asserts rejection before any disk-capacity probe. It does not change the production guard, allowed storage paths or timeouts. External-wrapper recheck: all 11 tests passed in 0.11 seconds (`wc-run-j0318v6x`); its repo quick gate also passed (`wc-run-h8uie5z4`). Commit and push were preservation only, not release/merge/activation.

The test path `.agents/scripts/tests/test_wongchoi_external_run.py` is outside the heartbeat's Stage 5 approval allowlist. It has not been folded into the reader scope or automatically merged. A separate human scope/release decision is required; then align the reader and rerun the full gate. The passing isolated recheck cannot retroactively turn the failed full gate green.

Read-only policy inspection of the reader's 36 paths yields risk `code`, gate `full`, four-domain code sync, no installer, no Dashboard deploy and no manual reason. This does not satisfy the missing successful full gate, immutable remote/rollback checks or other approval conditions. No release manifest or approval was created.

## Integration-only full gate — passed, not release approval

The separate reader and one-file test correction were combined on non-main branch `codex-stage5-integration-20261018`, based on the same fetched main. Tested immutable HEAD: `a0448bbb8d54081242c774e298ffd7bfa79cd342`; worktree clean before and after. The 37-path integration is not the reader's 36-path release scope and is not eligible for automatic heartbeat approval because it includes `.agents/scripts/tests/test_wongchoi_external_run.py`.

The original complete gate was rerun with the external wrapper and `nice -n 10`, piping output through `tee "$TMPDIR/full-gate.log"` under `bash -c 'set -o pipefail; ...'`. Session `29041` terminated with **exit 0**, all **15/15 suites passed**: Python 5,115 passed, two expected failures, two Dashboard skips; Node 89 passed. Shared Wong Choi: 1,609 passed in 2,503.76 seconds; Agent scripts: 102 passed / two expected failures; Tennis: 709 passed. All original large cases and limits remained intact. Goldens and actual AU/HKJC data-contract checks passed with the previously recorded AU warnings.

Log: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-w8y_v6js/full-gate.log`; SHA256 `efbade10a451523075edcce82a031796d34364c7894236c73e88f150efdb7882`.

- AU corpus: 485.533295083 seconds, hash `d2d1ec7b2368e4d62f8122dc3e51efd70b69c0259989f239a0c4025e2c772138`; review: 239.691915875 seconds, hash `58db83c4d36c1976f4c7bcbb57e830362ee4d1d76144e935717aee66601102f9`.
- HKJC corpus: 513.641649708 seconds, hash `c95e9ca91de8ac3f152bef7f7bd9dd76a1cc77a11ea3c0ec8f9d50f0f84c2b08`; review: 242.577615250 seconds, hash `8999e1b727ee3aa389ba76d3c027f4c39f586ca5f7f4aad8f970d49aed444e3d`.
- All four phase publications were `receipt_verified`, within unchanged separate 600-second limits; model promotion remained false. These timings are not a controlled performance comparison or model-quality evidence.

This green integration run does not erase the earlier failed reader-only gate. No release manifest, approval, main merge or activation was created. Separate correction authorization, release-controller gates/current SHA checks, real pilots and power evidence remain outstanding. Any subsequent documentation-only commit is not the tested immutable HEAD.

## Remaining acceptance

1. Separate scope/release decision for the independently verified upstream test correction; no automatic approval under the Stage 5 heartbeat.
2. Align to the approved base and rerun the complete repository gate; the failed run and its evidence remain historical, not replaced by a partial recheck.
3. Reader WIP preservation is complete; release eligibility and current immutable SHA checks remain open. A recovery branch is not a release and must not deploy.
4. Task 6 real reviewed power applicability, Task 7 live acceptance and Tasks 8–10 pilots/checkpoints remain unproven. Reader engineering success cannot stand in for these requirements.

No scoring, feature, weight, ruler, holdout, scheduler, installer, Dashboard, credential, retention, ledger, bankroll or promotion change is part of this recovery.
