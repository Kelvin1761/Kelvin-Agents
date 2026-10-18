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

## Remaining acceptance

1. Fresh targeted snapshot/index/cursor/paged-consumer tests, including preserved upstream timeout behavior.
2. Full repository gate, including both original large AU/HKJC reader cases without reduced history, relaxed limits or changed labels.
3. Scoped preservation on a non-main branch; then separate release eligibility and current immutable SHA checks. A recovery branch is not a release and must not deploy.
4. Task 6 real reviewed power applicability, Task 7 live acceptance and Tasks 8–10 pilots/checkpoints remain unproven. Reader engineering success cannot stand in for these requirements.

No scoring, feature, weight, ruler, holdout, scheduler, installer, Dashboard, credential, retention, ledger, bankroll or promotion change is part of this recovery.
