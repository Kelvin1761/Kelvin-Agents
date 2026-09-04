# AU matrix feedback — release handoff (2026-09-02)

## Production alignment completed — latest status

User explicitly approved shared four-domain production alignment. At Sydney 2026-09-03
13:45:54, Central recorded activation succeeded for the already approved
`6b97eea1808cbdfff9be16403a957ef952006c74`. Remote main and all four production roots
now match that SHA. Production branch `codex-production-main-20260903` tracks origin/main
with 0/0 divergence. Old au-production branch/history and all five original working files
are preserved. Only allowed runtime mapping remains dirty.

Full ten-suite gate passed, production quick gate passed, allowlisted runtime installer
and actual loaded-label verification passed, four dispatch dry-runs passed, 455 source /
configuration hashes match approved source, and all four engine imports resolve to the
production checkout. See `docs/handoff/production-alignment-20260903.md` for proof and
backup/rollback details. No additional approval is pending for this exact release.

## Telegram approval processed — current status

Authenticated Telegram approval was granted at `2026-09-02T23:53:26.761711+00:00`.
Commit `6b97eea1808cbdfff9be16403a957ef952006c74` merged to main at
`23:53:28.863850+00:00`; remote main independently verified at this exact SHA.
Activation then failed at `23:53:31.650926+00:00` on four dirty production paths.
Rollback reports `already_rolled_back`: production stayed at
`dae33573ef18e1671f0a6d7c1bed11ceb9c902ba`, with all working files preserved.
Do not ask the user to repeat this approval; it is recorded and valid for this release.

Further inspection establishes all four hotfixes are already included in the approved
tree. Three files pass reverse-patch check; the complete production test file is a
byte-for-byte prefix of the approved test file (the latter appends Speedmap tests).
This does NOT resolve divergent ancestry or authorize resetting production: 115 committed
paths differ from the approved release, including 43 Tennis paths and live modelling /
bet filtering behaviour. Reconciliation is a separate cross-domain deployment decision.
See `docs/handoff/au-production-activation-blockers-20260903.md` and the hashed inventory
`docs/handoff/au-production-reconciliation-20260903.json`.

Latest runtime inspection: all installed four-domain labels loaded/aligned to the old
production checkout. AU evening and Tennis card succeeded; HKJC recovery and NBA pregame
dormant. No new-model production activation is proven. Original root work in progress is
untouched. This update only records evidence; no production source/plist/ledger mutation.

## Published candidate — previous status, superseded above

Commit `6b97eea1808cbdfff9be16403a957ef952006c74` pushed successfully to `codex-au-feedback-ready-20260903`; exact 27-file scope, full gate exit 0 and push exit 0. Remote main verified still `165f923a1aa43a34f9ae0c1e2a1df0e328b6090e`. No merge or activation yet. Central requires authenticated Telegram `/approve 6b97eea1808c`; no fabricated Telegram actor permitted. Public-publication authorization is fully resolved.

Production preflight blockers and preservation are documented in `docs/handoff/au-production-activation-blockers-20260903.md`. Source checkout clean after commit. Original root work-in-progress belongs to prior refactor and other tasks, do not reset it.


## 2026-09-03 explicit publication authorization

User explicitly replied: "Yes go ahead and commit push and merge to main and push it to automation". Prior public-publication blocker is resolved. Exact 26-file payload hashes were verified unchanged.

Release full gate initially failed because isolated runtime-installer test calls host pgrep and sees the live Tennis card run. Added fixture pgrep and parametrized active/idle cases (3 tests pass); production installer/guard unchanged. Necessary test-only fix adds one path; final scope `/tmp/au-feedback-release-final-scope.json` has 27 paths. Save retry running, log `/tmp/au-feedback-public-release-20260903.log`.

Production at `/Users/imac/wongchoi-scheduler` is NOT fast-forwardable from main: HEAD `dae33573ef18e1671f0a6d7c1bed11ceb9c902ba`, legacy cherry-pick lineage; 96 committed files differ from main. Four uncommitted extractor/scheduler files plus allowed runtime mapping exist. Preserve them; do not reset/copy around Central activation guards. All installed runtime labels are loaded/aligned when actual production roots are configured. Tennis card run 09:00 was active at preflight.


## 2026-09-03 consolidated release, supersedes the 14-file save target below

LATEST TARGET: `/tmp/au-feedback-ready-20260903`, branch `codex-au-feedback-ready-20260903`,
parent `165f923a1aa43a34f9ae0c1e2a1df0e328b6090e`. Origin gained two Dashboard commits while
verifying; engine/scoring/mapper byte contents did not change. Same 26-file scope copied
onto fresh main; fresh Central dry-run succeeded (model/full, no auto-merge/activate).
Use `/tmp/au-feedback-release-20260903-scope.json` with the LATEST worktree. Do not save
the old 926eac54-based consolidated branch. Current full log:
`/tmp/au-feedback-ready-20260903-full.log` — PASSED, all ten suites including 598 AU tests.


Latest user said `continue`. A concise async question explicitly asking authorization to
publish model/test/experiment payload to PUBLIC `Kelvin1761/Kelvin-Agents` was sent again;
no affirmative public-publication response has arrived. Do not mistake `continue` for
resolved review authorization or bypass the earlier automatic approval rejection.

Preferred release worktree: `/tmp/au-feedback-release-20260903`, branch
`codex-au-feedback-release-20260903`, parent `926eac54de7f67f78a8f6f7a5c3632a7d95b0cce`.
26-file exact scope `/tmp/au-feedback-release-20260903-scope.json`; reviewable manifest
`docs/handoff/au-feedback-20260903-scope.json`. This combines EXP-06 C, EXP-08 set-weight
condition correctness, and EXP-09 preparation chronology/explanation. It does NOT include
the full no-gain refactor or evaluation adapter. Original experiment worktrees remain intact.

25 targeted tests passed; `./檢查.sh --quick` and full `./檢查.sh` passed, all ten suites
including 598 AU tests. Logs `/tmp/au-feedback-release-20260903-{quick,full}.log`.
Generated AU explanation/calibration updated. Parent original golden retained verbatim at
`docs/experiments/EXP-20260903-au-pre-feedback-golden.json`; same 120 old inputs show zero
ability/grade changes and only 115 report-only form_line changes. New record sampled newer
corpus, so its own 120-case pass must not be claimed as old-case equality.

Central dry-run uses --no-notify --allow-unrelated (five test-produced line-ending-only files:
two .codex/hooks/*.cmd and Dashboard launch/start/stop shell scripts). These five are outside
scope, confirmed with git diff --ignore-space-at-eol, never stage them. No actual commit,
push, merge, notification or activation performed. Immutable SHA approval still required
after a successful release. Do not bypass Central identity checks.

EXP-09: Gunroom 08-22 is second-up, 239-day break before 08-08 and 14 days since that start;
Bacetti 09-02 first-up after 154 days. Engine now derives dated formal-race cycle, ignores
trials/future dates, and renders it consistently. No ranking penalty adopted. Fixed F/Q/FQ
pre-spell reliability ablations all failed dev primary; terminal not opened. Failed scoring
helper moved OUT of production module into scratch only. Details and evidence in EXP-09.

Standalone cycle-only worktree `/tmp/au-preparation-release` (11 files) also passed full gate;
prefer consolidated worktree now. Root shared checkout HEAD advanced to 926eac54 by other
work during the session; protect all unrelated HKJC/Dashboard edits.

## Approval blocker

Latest user explicitly asks commit/push/main automation. Automatic approval review rejected the
latest save invocation because configured origin is PUBLIC `Kelvin1761/Kelvin-Agents` and requires
specific user permission to publish this model payload. GitHub get_repo verified admin/push.
An async question has been sent; do not retry or use another push route until the user answers.
No commit/push from this work has succeeded. High-risk merge/activation still requires authenticated
Central `/approve SHA`; do not manufacture an issuer.

## Exact release worktree (EXP-06 only)

`/tmp/au-feedback-main-final`, branch `codex-au-feedback-main-final-20260902`, parent
`926eac54de7f67f78a8f6f7a5c3632a7d95b0cce`. Parent source and candidate source verified
byte-equivalent to original EXP-06 experiment engine. Avoid earlier worktree `/tmp/au-field-main`
which is based on stale main. Scope file `/tmp/au-field-main-scope.json`; use 保存.sh exact scope,
--no-notify (no authorization to message others), --allow-unrelated. Fetch freshness is enforced.

Scope:

- .agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/engine_core.py
- .agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/matrix_mapper.py
- .agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/renderer.py
- .agents/scripts/inject_fact_anchors.py
- .agents/skills/au_racing/sb_horse_index.py
- docs/experiments/EXP-20260902-06-au-matrix-feedback.md
- scratch/au_matrix_feedback_20260902.py
- .agents/skills/au_racing/au_wong_choi_auto/tests/test_matrix_feedback.py
- docs/experiments/INDEX.md
- .agents/skills/au_racing/au_wong_choi_auto/tests/golden/scoring_golden.json
- .agents/skills/shared_racing/resources/au_data_contract.json
- Wong Choi 模型說明/AU Wong Choi 模型說明.md
- Wong Choi 模型說明/AU Wong Choi 模型說明.html
- docs/experiments/EXP-20260902-06-main-evidence.json

Quick and full gates PASSED (exit 0); `/tmp/au-feedback-final-full.log` ends 全部過 ✅.
Golden preserved same 120 vectors,
calibration/explainer regenerated. HKJC generated docs dirt is outside scope, do not stage.

## Additional prepared work not in this release

EXP-07 full refactor removes matrix gains via explicit coefficients, separates trial preparation,
exports features at six decimals, preserves dated class/surface evidence. Tested isolated copy
`/tmp/au-matrix-release` passed full gate. It cannot be released together with its au_eval/golden
adapter because Central classifies those as EVALUATION. Prepare a separate backward-compatible
adapter release before the model refactor; do not change policy or evaluation contract.

EXP-08 Bacetti: `_is_wfa_or_sw_race` correction and 11 tests in original root only. Research scripts
and evidence in docs/experiments. Fixed corpus 1822/18216; correction dev primary flat, terminal
Gold +2 races and Good flat, no significant cohort loss. Performance gate REJECT, correctness §7
passes. This source change is NOT in the 14-file release and must not be silently added after
approval of that payload. Full-root refactor+this correction not yet fully tested together; root
quick and 11 focused tests passed. Generation logs `/tmp/au-bacetti-{golden,calibrate,explain}.log` all exit 0; final root quick also passed.

Three PQ diagnostics are complete, no production scoring change to PQ. Neutral: dev Gold -1.0703pp,
Good -0.9174pp; terminal -2.34375pp/-0.9765625pp. Half: terminal -.390625/+.390625.
Consistency replacement: terminal -1.953125/+.390625. Detail in EXP-08 evidence.
Bacetti actual finish 5/9, 3.57L, SP81; pre-race snapshot34. PQ removal or fixed set-weight
classification does NOT move it out of third. Do not claim either case solved.

## Protect other work

Original root `Horse_Racing_Dashboard/static_template.html`, untracked refit JSONs and tennis_wc.db
predate this task. Do not stage/revert. Original branch `claude/au-pace-figure-rebuild`, HEAD fbf14998.
Do not squash all root changes into release. Do not overwrite evaluation contract or old golden
without retained baseline. No schedule or production state has been changed.
