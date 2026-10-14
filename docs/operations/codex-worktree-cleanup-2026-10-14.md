# Codex worktree cleanup — 2026-10-14 Sydney

This cleanup preserves unfinished work and publishes completed tooling and research records. It does not adopt rejected model candidates or claim a measured prediction improvement.

## Recovery copy

Before deleting any completed checkout, the cleanup copied and SHA-256 verified 3,101 loose files from the primary checkout and captured binary patches, HEADs and non-ignored untracked files for 37 Codex worktrees.

Recovery root: `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/codex-worktree-cleanup-20261014/`.

`manifest.json` records source paths, backup paths, hashes and original commit IDs. `primary-untracked/` contains original loose files. Each `worktrees/` entry contains `changes.patch`, `status.txt` and an `untracked/` directory. These are recovery copies, not model promotion evidence or an independently replicated disaster backup.

To recover an old pending checkout, create a new worktree at its manifest HEAD, apply its binary patch with `git apply`, then copy its untracked files to the same relative paths. Do not apply an old patch directly over a current checkout without reviewing the diff.

## Completed source and records

- Preserve the LoL highlight editor, review interface, subtitles workflow, tests and evaluation notes. Media, models and runtime environments stay outside Git.
- Preserve external scratch/cache routing and its tests. The command refuses an absent external volume and never silently falls back to the internal disk.
- Restore the research CLIs' existing `WC_SB_CACHE` precedence, including empty-value fallback and explicit CLI override.
- Restore HKJC AWT identity in form-guide parsing, displayed history and standard-time lookup. Main already contains the separate target-surface effective-sample fix; it is not replaced with an old engine copy.
- Preserve the completed AU/HKJC experiment reports, audits, evidence samples, borrowing reviews and operational notes. Their original rejection and uncertainty decisions remain in the records.
- Preserve NBA decimal-safe padding detection and Tennis forward integrity fixes: pre-match tracker admission, honest research-paper labels and recommendation blocking when data integrity cannot be verified. Existing historical rows and model thresholds remain unchanged.
- Ignore nested `.codex/worktrees/` checkouts as local workspace infrastructure.

## Worktree cleanup

Removed 14 clean Codex worktrees only after rechecking their HEADs were ancestors of `origin/main` and their complete Git status was empty. No force-removal was used. Branch commits remain in Git.

Pending reader, scheduler, deployment-lock and older research worktrees remain recoverable. The reviewed NBA/Tennis integrity files are included in this release. The reader and integrity candidates' earlier save logs reported `full gate failed; no files were staged`; targeted passes do not override that result. Rejected AU reranker code and local Punters/browser configuration are preserved in the recovery copy and are not promoted by this cleanup.

The primary checkout was moved to `main` by a concurrent session during the inventory. This cleanup does not claim that concurrent action as its own and does not reset concurrent tracked edits.

## Verification

- Restored source and routing regressions: 26 passed.
- LoL editor: 13 passed in the existing video runtime, including actual FFmpeg analysis/render and authenticated loopback review.
- NBA/Tennis integrity regressions: 5 NBA and 216 Tennis tests passed.
- The initial full run passed 14 suites and failed one external-runner test because its assumed local `tmp_path` was actually on the external disk. The test now explicitly checks `/private/tmp`; all 11 runner tests pass under external TMPDIR. The final save must rerun the full gate.
- Quick repository gate: passed, with unchanged scoring goldens and generated model descriptions.
- Full repository gate and final exact-scope release results are recorded in the release output; a failed gate must block commit and push.
