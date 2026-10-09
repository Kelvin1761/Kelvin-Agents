# Tennis Stage 5 adapter recovery — 2026-10-09

Base: `1c77d21f6ab0786500e0ad6d689b7d5ca4cd838d` in isolated
`.codex/worktrees/wc-stage5-tennis-adapter-recovery-20261009`.

## Prediction source connection

- Daily pricing observes the exact in-memory feature/pricing objects, deep-copies them before agent review, and binds them to the stored prediction's `created_at`. No scores or features are recomputed from later database state.
- The adapter selects only raw API rows referenced by those memory inputs, in bounded SQL batches. Existing immutable raw metadata and timestamps are validated by the unchanged evidence producer; absent/future/unverified source does not become valid evidence.
- Every prediction in the card must have exactly one memory observation. Partial coverage, missing memory or source validation failure records an explicit blocked research artifact while preserving the ordinary report/card. Research-only failure is not hidden as source coverage success and does not promote the model.
- Feature/raw artifacts use the existing create-only snapshot's `additional_files`, with the same aware cutoff as the snapshot manifest. Model scoring, selection, betting ledger, settlement logic, providers, release policy, Telegram, Dashboard and production runtime are not changed.

## Tests and limits

- Focused CLI/evidence tests: 16 passed. Fixtures demonstrate memory mutation isolation, complete feature/raw consumer projection, exact snapshot hashes/sizes, unchanged database row counts, missing raw-source refusal and incomplete observation coverage refusal.
- Quick gate exited 0; AU/HKJC goldens 120/120 unchanged. Isolated checkout lacks race corpus, so data-contract corpus checks skip and cannot establish live data health.
- Full gate `env PATH="/Users/imac/.nvm/versions/node/v20.20.2/bin:$PATH" ./檢查.sh` (session `16303`) exited 0: all 15 suites passed, including Shared 1,213, Tennis 573 and Node 16 + 62. This first recovery portion does not complete the Tennis adapter or prove live acceptance.
- Remaining: results-backed immutable settlement export/callback, end-to-end store/Central integration, raw-result lineage coverage and production/live acceptance. NBA, E2 and broader Stage 5 checkpoints remain separate; no model performance improvement is claimed.

No commit, push, merge, activation, production DB write or installation performed.

## Settlement implementation constraints confirmed from current consumer

- The current producer/consumer binds `generated_at` exactly to settlement `settled_at`; assigning a fresh timestamp on every retry would produce distinct artifacts and extra logical settlements. Preserve the actual first capture clock in a create-only, hash-verified bundle indexed by the input signature (frozen prediction identity/cutoff, exact outcome rows and raw-response hashes). Reuse that capture on retries; never invent a past capture timestamp from `match_results.created_at`.
- Select the exact frozen prediction IDs linked to the event's decision, not the current latest pricing rows for all matches. Validate stored prediction time/probabilities/selection against the immutable forecast; missing/changed rows must block, never be replaced with a different forecast.
- Raw result provenance must confirm the exact participant pair and winner. Preserve raw bytes and source/provider/timestamps, including the result source chosen by the canonical settlement workflow; ambiguous/conflicting results cannot be silently treated as usable.
- Keep the canonical ledger settlement unchanged. Research callback must use a stable evidence summary rather than volatile per-run betting counters. Detect a changed latest decision before recording or otherwise bind the explicit captured parent; ambiguous linkage is not engineering acceptance.
- A create-only first-capture primitive is now implemented in `research_adapter.py`: input-addressed directory, strict artifact set/hash/size/clock/symlink checks, pure rebuild at the first clock to bind cached bytes to source inputs, and refusal to overwrite corrupted captures. Shared writer now accepts an optional expected-decision guard and rejects changed parent before writing; legacy callers remain unchanged. These primitives do not yet connect the live result query/callback.
- Focused primitive and shared writer tests: 13 passed. Quick gate passed with unchanged goldens; Node 20 full gate `51699` subsequently exited 0: all 15 suites passed, Shared 1,214, Tennis 581 and Node 16 + 62. This primitive gate predates the exact-ID result query added below; absent-corpus checks remain skipped.
- Required next source work: exact frozen-ID result query, immutable forecast/database value comparison, raw result validation and canonical settlement-source selection, stable research summary, guarded callback and end-to-end fixture. No live acceptance is claimed.

## Exact frozen-ID result query

- `read_settlement_sources` executes only SELECTs, in bounded ID batches, with raw response bytes joined in the same query as the canonical result. It checks exact frozen ID coverage, event date, aware prediction time, stored probabilities/selection/match and participant IDs. Missing or mutated forecasts are refused, never replaced by a newer prediction.
- Canonical source ordering mirrors the native ledger: complete aces first, then `tennismylife`, then latest result ID. Missing result/raw provenance blocks research; pure producer still validates provider, participant pair, winner and chronology.
- Focused adapter tests: 19 passed. Includes SQLite query-only mode and unchanged total changes, native source ordering, mutations/missing sources, duplicate forecasts and query → pure producer → first-capture retry → frozen Central outcome validation. A winner unsupported by raw bytes is refused. Synthetic fixture is not live acceptance.
- Query-payload Node 20 full gate `11202` exited 0: all 15 suites passed, including Shared 1,214, Tennis 592 and Node 16 + 62. Existing expected failures/skips remain; isolated checkout has no AU/HKJC corpus. This gate predates the frozen-parent loader below.
- Entry-path inspection confirms manual `settle-bets`, CLI `settle-backlog`, run-daily's direct backlog sweep, and native `review_date` call settlement. A CLI-only callback would leave automatic paths uncovered. Connect the observation layer across these paths without changing the native ledger decisions/counters; independently retry research days whose business ledger no longer has pending rows.

## Frozen parent loader

- `load_forecast_context` validates canonical decision/prediction/model-release records using the existing Central record reader, then verifies the full direct frozen bundle, manifest file set/hash/sizes, artifact cutoff/source and pure feature/raw provenance. No database access, source repair or basename relocation search.
- A tied latest decision timestamp or future parent is refused; missing matching decision returns no context. Missing/changed snapshot bytes or provenance block rather than falling back to older forecasts. Reader/blob recheck detects changes during inspection.
- Focused adapter suite: 22 passed; actual model registry → prediction/decision writer → immutable snapshot fixture resolves exact features without evidence writes. Tampered bytes and same-time contradictory decisions are refused. Quick gate passes, goldens unchanged. These are source fixtures, not live acceptance.
- Frozen-parent loader full gate `62213` exited 0: all 15 suites passed, Shared 1,214, Tennis 595 and Node 16 + 62; goldens unchanged, AU/HKJC corpus checks skipped. This evidence predates the callback below. No commit/push/activation performed.

## Guarded settlement observer

- `record_research_settlement` observes exact frozen forecast/result/raw inputs without changing the DB/ledger, freezes source-bound artifacts and appends through the existing writer with expected-decision guard. Stable summaries use input signature/count, not volatile native betting counters; repeated callbacks retain the actual first-capture time and same settlement ID.
- Missing/invalid result sources under a verified parent append an explicit `unverified` status artifact/settlement, not a successful outcome. Invalid parent provenance returns blocked. Capture/storage/writer failures remain failures; the observer does not relabel them missing source.
- Public Central consumer integration caught an incompatible hash-only capture parent directory: consumer requires an event-date prefix. Fixed the source layout to `EVENT_INPUTHASH`, with strict canonical-date validation; consumer/ruler unchanged. Existing generic primitive callers retain their original layout.
- Focused adapter tests: 25 passed. Includes actual query-only DB → immutable capture → real guarded writer → public Central settlement inventory, one verified outcome, duplicate callback idempotency, unverified missing-result recording and publication-error propagation. Synthetic fixtures cannot prove live acceptance.
- Callback full gate `67955` exited 0: all 15 suites passed, Shared 1,214, Tennis 598, Node 16 + 62. Corpus checks remain skipped. This gate predates CLI wiring below; broader fault/concurrency and live acceptance remain pending.

## CLI and automatic entry wiring

- Manual `settle-bets`, scheduler-facing `review-date`, explicit `settle-backlog` and run-daily's backlog now observe research after unchanged native settlement calls. Native counters/report paths are preserved. Observer errors are exposed separately as `failed`, never labeled evidence success or erased by an otherwise successful business settlement.
- Observer DB connections enforce `PRAGMA query_only=ON` and close in `finally`. Capture/evidence writes remain separate from the betting database.
- Bounded canonical prediction inventory feeds an independent calendar-rotating retry batch (default 10 dates, allowed 0..30). It does not depend on native PENDING rows or qualify corpus/samples. Eligible/deferred counts remain explicit, and future event dates are not retried. Native attempted dates also observe once via set union, without repeating business settlement.
- Focused adapter/CLI suites: 35 passed, including empty native backlog research catch-up, rotation over eligible dates, excluded future days, unchanged native counters, visible inventory failure and read-only connection closure. Quick gate and diff check pass; source fixtures are not live production acceptance.
- Wiring full gate `94151` exited 0: all 15 suites passed, Shared 1,214, Tennis 603 and Node 16 + 62; corpus checks skipped. This predates latest-main integration and the fault tests below. No release/install/activation performed.

## Read-only operational recheck — 2026-10-09T07:11Z

- Another release has advanced production and verified remote `origin/main` to `2b692cff1ef3eff253b8dc4b65206b82e4d8e9ef`; this task performed no activation. Diff from recovery base `1c77d21f6ab0` is NBA pipeline/model files and its audit, with no Tennis/shared adapter overlap. Recovery work remains uncommitted on its original base; integration/full gate against the latest approved main is still required before release.
- Current baseline checker reports all four installed/loaded domain mappings and Central durability aligned to `/Users/imac/wongchoi-scheduler`. E2 preview checker additionally expects new HKJC intraday/research-review labels which are not installed; that is pending E2 activation, not evidence that the current baseline's scheduled labels stopped.
- AU latest run succeeded (production model); HKJC dormant (production); Tennis running within timeout (shadow); NBA partial (shadow). A run record is not independently confirmed OS process liveness, and no live acceptance is granted by these states.
- Dashboard configured. D1 snapshot restore was verified, but age about 36.9h exceeds 36h threshold; WARM copy pending. HOT available with warning, approximately 23.39 GiB free; WARM mounted with approximately 877 GiB free. Catalog COLD evidence covers 10/11 known artifacts, including provider-backed copies; do not misreport an unconfigured local COLD root as zero backup coverage.
- Production checkout retains existing `hkjc_draw_stats.json` and AU archive-ID runtime changes; untouched. No backup copy/deletion, schedule repair, credential change or external ledger operation performed.

## Latest-main integration and actual fault tests

- Release event state confirms `2b692cff1ef3` approved, merged and activation succeeded. Remote main SHA independently verified with `git ls-remote`. Only isolated Tennis recovery branch fast-forwarded to that existing commit; no new commit, remote write, main mutation or production activation. All uncommitted recovery paths preserved. Earlier gates are historical, not latest-main integration proof.
- Focused adapter/CLI suites: 38 passed on this base. Actual race fixture appends a new canonical decision after capture and before real publication; expected-parent guard refuses settlement, while immutable captured source bytes remain recoverable. Injected rename/disk-full failure appends no settlement. Changing native winner without supporting raw bytes appends unverified evidence without touching the original verified capture.
- Latest-base full gate `86306` exited 0: all 15 suites passed, Shared 1,214, Tennis 606, NBA 88 and Node 16 + 62; corpus checks remain skipped. This predates resource guards below. Source readiness is not production activation/live acceptance; no-bet/missing-source day coverage and deployment acceptance remain separate checks before broad Stage 5 completion.

## Capture resource boundaries

- Parent symlinks/path traversal are refused before root creation. Cached capture reads use no-follow/nonblocking descriptors, require regular files and are bounded even if a file grows after stat. Manifest maximum 1 MiB; artifact count/file/bundle limits mirror existing frozen consumer budgets (5,000 / 32 MiB / 512 MiB). Generated payloads exceeding budgets cannot be published, and invalid existing captures are not overwritten or deleted.
- Focused adapter/CLI suites: 43 passed, including parent symlink target remaining untouched, generated file/count/total-byte refusal and bounded cached manifest/artifact refusal. Quick source gate passed; goldens unchanged. These guards bound capture publication/read-back, not allocations already made by the native feature builder or SQLite raw-query inputs. Wider preallocation/runtime-timeout budget review remains open; no claim of complete resource isolation.
- NBA and E2 recovery branches also fast-forwarded independently to already approved `2b692cff1ef3`, preserving uncommitted scopes; focused 52 NBA and 32 E2 tests passed. Their prior-base full gates do not prove latest-base full readiness.
- Capture-guard full gate `40970` exited 0: all 15 suites passed, Shared 1,214, Tennis 611, NBA 88 and Node 16 + 62; corpus checks remain skipped. This predates exact hash binding/no-bet tests below. No save, release approval, production install, model promotion or ledger mutation performed.

## Exact publication hash binding and no-bet coverage

- Inspection identified a capture-to-publication race: a writer that hashes current files without an expected source hash could pin changed bytes after capture validation. Added optional exact `expected_artifact_hashes` guard: complete unique path set, valid SHA256 and exact bytes required before duplicate/publication checks. Writer now uses one observed hash for both stable identity and artifact refs; callers without pins retain their ordinary signature/behavior. Later mutation remains detectable by pinned consumer hashes, not accepted as repaired evidence.
- Tennis derives these pins from the pure source-bound rebuild at the actual preserved capture clock, not by rereading potentially changed files. Actual post-capture mutation fixture reaches the real writer and appends zero settlements.
- Focused adapter/CLI/shared-writer selection: 55 passed. Includes partial/wrong-path/malformed/wrong-hash refusal and valid pin acceptance, normal verified watchlist retaining `NO_BET` and unchanged recommendations with provenance, and empty native card retaining its report/`NO_BET` while producing no verified feature/sample evidence. Missing-raw and incomplete-observation coverage remain blocked; no synthetic zero-outcome acceptance added.
- Publication/no-bet full gate `88112` exited 0 on approved `2b692cff1ef3` base: all 15 suites passed, Shared 1,218, Tennis 614, NBA 88, Node 16 + 62. Quick gate and scoring goldens unchanged; AU/HKJC corpus checks skipped. This is source regression evidence, not live corpus or production acceptance. Latest-main NBA/E2 full integration gates, broader runtime resource/preallocation review, authorized scoped save/activation and real live acceptance remain pending. Stage 5 Tasks 6/7 and pilots/exit remain incomplete.
