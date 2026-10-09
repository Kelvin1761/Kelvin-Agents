# NBA Stage 5 production adapter recovery — 2026-10-09

Base: `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d` in isolated worktree
`.codex/worktrees/wc-stage5-nba-adapter-recovery-20261009`.

## Source changes and boundaries

- New snapshots publish canonical `domain`, `event_id`, cutoff and a typed file list with exact hashes/sizes. Existing snapshots are not rewritten or backfilled.
- The scheduler calls the existing feature producer on already-copied snapshot bytes. Each game must match its official scheduled start, canonical team tag and Sydney analysis date, and the capture cutoff must precede tipoff. The legacy fallback's synthetic `now + 1 day` schedule is not accepted as research evidence.
- Missing/inconsistent research sources explicitly block research qualification without inventing feature values or changing the ordinary prediction output. Source I/O/publishing failures are not silently hidden.
- Recommendation evidence observes the existing reflector's native report parser, preserving player/stat/line identities. Identical props repeated in multiple combos form one monitoring identity; inconsistent identities fail closed. It does not change selections, odds, scoring, bankroll or betting delivery.
- Successful pregame source projections remain `settlement_pending`, not live model acceptance or profitability evidence. A source snapshot without official schedule remains blocked. No model promotion, evaluation ruler, installer, Telegram or Dashboard change is included.
- Postgame captures only the three validated native result-chain files under content-addressed `_research_settlements`; it revalidates captured bytes before publication and refuses symlink/tampered/conflicting existing bytes. Retry reuses exact paths; changed valid native bytes append a distinct capture rather than overwrite history. Missing/inconsistent research provenance is explicitly blocked, without undoing the ordinary archive/deploy. Capture I/O and evidence-writer failures remain failures.
- An already-archived day retries this callback without redoing archive/deploy; multiple archive candidates block research rather than select one silently.

## Evidence

- Final focused producer and scheduler tests: 52 passed (`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q .../test_stage5_research_evidence.py .../test_nba_daily_schedule.py`). Includes frozen source mutation, schedule mismatch/missing/naive time, cutoff at tipoff, hash/size coverage, native recommendation consumer, repeated-combo identity, real evidence writer/public bundle and feature-provenance readers, immutable settlement mutation/idempotency/tamper, capture-time source change, archived retry and ambiguous archive refusal.
- Quick gate and `git diff --check` passed. AU/HKJC goldens 120/120 unchanged. Corpus checks skipped because this isolated checkout has no meeting data; this does not verify live data health.
- Pregame-source full gate `env PATH="/Users/imac/.nvm/versions/node/v20.20.2/bin:$PATH" ./檢查.sh` (session `2029`) exited 0: all 15 suites passed, including Shared 1,213, NBA 69, Tennis 570, and Node 16 + 62 tests. This evidence predates the settlement callback changes; a new full gate is required before claiming final source readiness.
- Final callback full gate with the same Node 20 command (session `84163`) exited 0: all 15 suites passed, including Shared 1,213, NBA 74, Tennis 570 and Node 16 + 62. Quick steps and unchanged goldens passed; absent-corpus data-contract checks remain skipped. This establishes source regression readiness, not live acceptance.
- After adding public settlement/monitoring end-to-end and duplicate-key assertions: focused 52 tests and quick gate passed. Refreshed full gate launched with the same Node 20 command, live terminal session `65835`; terminal completion remains unobserved and must be checked on this same handle.
- After the heartbeat/context handoff, polling `65835` returned `Unknown process id`; no terminal success could be recovered from that handle. Its latest observed progress is not a full-gate pass. The unchanged-source rerun `90642` subsequently exited 0: all 15 suites passed, including NBA 74, Shared 1,213, Tennis 570 and Node 16 + 62. This includes the later end-to-end assertions; absent-corpus checks remain skipped and live acceptance remains pending.

## Remaining requirements

- End-to-end producer → store → frozen settlement → public Central monitoring fixture is now included: one valid synthetic monitoring identity, duplicate callback idempotency, archive mutation isolation and unchanged model-promotion prohibition. Native duplicate result keys are explicitly tested as blocked, never normalized into acceptance. Focused and full refresh pass. No synthetic result is live acceptance.
- Native result verification may repeat a prop across combos; the frozen monitoring consumer rejects duplicate result keys. Do not change the ruler or rewrite native results to manufacture acceptance. An independently reviewed provenance/normalization decision is still needed for such days.
- Verify producer-to-evidence-store-to-Central consumer integration and complete fresh forward, results-backed live acceptance. Synthetic fixtures cannot replace it.
- D-Tennis recovery, E2 release/production acceptance, F Telegram, C private Dashboard, reviewed numeric power applicability, pilots and Stage 5 exit remain open.

No commit, push, merge, activation or production-state write performed. E2 is separate in its own worktree; no changes to the primary dirty checkout were staged.

## Latest-main integration

- Another approved/merged/activated release advanced verified remote main and production to `2b692cff1ef3eff253b8dc4b65206b82e4d8e9ef`. Recovery branch fast-forwarded only to that existing commit, preserving all five uncommitted paths; no new commit/push/main merge/activation performed by this task. Incoming NBA pipeline/model files do not overlap the adapter recovery files.
- Focused producer/scheduler suite on updated base: 52 passed. Previous full gate `90642` remains evidence for the prior base, not a full latest-main integration pass. Updated full gate, live acceptance and native duplicate-key policy remain pending.
- Latest-main full gate `47839`, using Node 20, reached terminal exit 0: all 15 suites passed, including Shared 1,213, NBA 102, Tennis 570 and Node 16 + 62. Goldens and code checks passed; absent AU/HKJC corpus checks remain skipped. This is source regression evidence only: live acceptance and native duplicate-key policy remain pending. No commit, push or activation was performed.
