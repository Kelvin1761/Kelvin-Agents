# Wong Choi — external-first storage recovery

## Status and evidence (2026-10-10, Sydney)

- Mac free space was approximately 13.24 GiB. After official npm package-cache
  cleanup and pip cache purge (679 files, 589.2 MB reported), `df -k` measured
  15,214,192 KiB available, approximately 14.51 GiB. Other live writes mean this
  is an observed before/after change, not an exact attribution of every byte.
- A subsequent official `uv cache clean --cache-dir /Users/imac/.cache/uv`
  removed 28,058 regenerable cache files (684.6 MiB reported). Final `df -k`
  measured 15,681,524 KiB available, about 14.96 GiB, an observed total gain
  of about 1.72 GiB versus the original 13.24 GiB. Concurrent production writes
  continue, so do not equate reported cache sizes with the exact free-space gain.
- Only regenerable package-download caches were removed. Installed packages,
  virtual environments, browser/login profiles, live SQLite databases, scoring,
  predictions, evidence, historical results and personal files were untouched.
  Cache bytes cannot be restored as the exact old cache; packages can be fetched
  again from their providers. A future uncached install needs network access.
- External disk `/Volumes/Kelvin Hardisk 1` was mounted with approximately
  877 GiB free. AU Archive allocated size was 5,729,844 KiB (about 5.46 GiB).
  AU Sportsbet cache allocated size was 1,380,672 KiB (about 1.32 GiB).
- This is partial recovery only: Mac remains below the 20 GiB critical threshold.
  Target: keep at least 30 GiB free; never claim this target achieved yet.

## Storage ownership

| Mac HOT — only latency/availability-sensitive | External WARM — primary bulk bytes | Drive COLD — independent recovery |
|---|---|---|
| Active code/interpreters and current model | Settled historical meeting artifacts | Second verified copy of unique history |
| Live Tennis DB, WAL/SHM and current jobs | Frozen SQLite backups, not live DB | Verified backup exports, not live SQLite |
| Control manifests, recent evidence and locks | Research scratch and test temporary data | Disaster recovery; never silent live fallback |
| Recent analysis needed for unattended runs | Old experiment outputs and reconstructible download caches | Remote proof must verify full bytes |

Recent HOT age policy (initial proposal: 30 days) must be reviewed against every
consumer before activation. This is a storage residency policy, not a changed
evaluation window: full-history readers must continue to see identical corpus.

## Implemented opt-in command routing

```bash
python3 .agents/scripts/wongchoi_external_run.py --check
python3 .agents/scripts/wongchoi_external_run.py -- ./檢查.sh
```

The helper checks a real mounted `/Volumes` disk, readable WARM root and 10 GiB
free-space reserve before creating private scratch. It redirects `TMPDIR`,
`PIP_CACHE_DIR`, `UV_CACHE_DIR`, `npm_config_cache` and disables bytecode writes.
Arguments are passed without a shell and child exit status is preserved.
Symlinked storage paths are rejected. Scratch is retained, not broadly deleted.

Nine focused tests passed. Actual mounted-disk `--check` and a child environment
smoke probe passed; child `tempfile.gettempdir()` pointed to external scratch.
Quick repository gate passed with an existing AU stale-baseline/new-field warning.
The AU `logic_files` WARM-reader candidate now passes catalog cutover,
no-duplicate and offline fail-closed tests. Together with command routing,
19 focused tests pass. On the current real AU root, all 3,550 native logic
paths and their ordering are exactly unchanged. Quick gate passed again.
This source change is not yet deployed to the production runtime.
Full repository gate has not run for this scope; AU production is active and
heavy acceptance remains deferred. No commit, push, installer or activation.

This is NOT yet wired into existing launchd jobs, releases or every researcher.
It is a startup guard, not a replacement for research supervision: a child that
ignores these environment variables can still write locally, and mid-run disk
loss needs the child's own resource checks. Do not globally repoint all app
caches or symlink live roots to an external disk; that can create Mac directories
under an unmounted volume or break unattended jobs through macOS TCC.

## Remaining migration sequence — do not skip gates

1. Inventory settled immutable meetings and frozen backups, excluding live days,
   live databases, active processes, unpublished work and incomplete evidence.
2. Check all native consumers. `meeting_dirs` supports catalog-backed WARM;
   the `logic_files` gap is corrected in the undeployed candidate, with focused
   tests and native corpus parity evidence. Full gate and production release,
   plus remaining consumer checks, must precede any source removal. No symlink
   or smaller-corpus workaround.
3. Copy each approved artifact using Central `archive-copy` with its native
   `settled-meeting`/`settled-day` class, preserve logical names, publish hashes.
   Recheck original bytes after copy. Do not catalog one entire Archive tree as
   if it were one race meeting.
4. Restore to a new external path and verify hashes, file/race/meeting coverage,
   sample identity and native-reader access. Verify launchd-context external
   access separately; Terminal access is not evidence of launchd TCC access.
5. Create an independent Drive/second-device copy and verify full bytes. Another
   folder on the same external disk is not independent disaster protection.
   Avoid making a downloaded Drive mirror consume the Mac space just released.
6. Obtain separate exact-source removal approval only after those proofs exist.
   Record retention/cutover evidence; never delete a root, glob or unresolved
   directory. Re-prove identical corpus via WARM and fail closed when offline.
7. Route future research/test temporary data through the external guard and
   integrate unattended archive-copy with dedup, volume/production checks and
   Telegram meaningful failures. Deletion remains separately controlled.
8. Re-measure free space and operational health; resume heavy Stage 5 acceptance
   only when production/resource gates permit. Keep Stage 5 Tasks 6–10 open.

## Not in automatic cleanup scope

Personal browser/app profiles, logins, Games, Codex runtimes/session history,
active worktrees, current models and database compression/vacuum are not approved
cleanup targets. Root size scans do not authorize deleting those files. Historical
data migration, cache routing and backup verification never change model scoring,
the ruler, holdout, bankroll or the external betting ledger.

## Continuation checkpoint — 2026-10-11 Sydney

- Fresh Mac measurement was 14,422,260 KiB available (~13.75 GiB); Central
  shortly afterwards measured 13.78 GiB. Space has fallen since the previous
  14.96 GiB measurement. Cleanup alone has not controlled ongoing growth.
- The same AU PID 68933 was independently observed alive at elapsed 02:15:27;
  Central records it within its 11-hour timeout. No restart, interruption,
  runtime switch or heavy full gate was performed.
- Added regressions for an empty/corrupt native AU meeting folder masking the
  verified WARM copy. Catalog-registered meetings now use the verified resolved
  location in both `logic_files` and `meeting_dirs`; unregistered enumeration
  remains unchanged. Fixed the duplicate test's catalog fixture to use the real
  `control/storage/catalog` layout rather than accidentally exercising no catalog.
- Added a RED/GREEN command-routing regression for `..` escaping the mounted
  volume: canonical archive-root containment is now checked before any writes.
  All 22 focused storage/reader tests pass. Mounted-disk read-only `--check`
  passes. Quick gate passed (unchanged existing AU calibration warnings); full
  gate and scoped release remain outstanding. The source changes are uncommitted,
  unpushed and not activated.
- Per Central copy-only policy, copied one settled native meeting:
  `2026-07-15 Warwick Farm Race 1-7`, 50 files / 4,022,800 bytes.
  Artifact ID: `wc-artifact:3cbc406c486ebeeec387f420`.
  SHA256: `b5f034fee18e5a30af8953a1c872a222858ef64bb433dc99f9df7aae662453d0`.
  WARM destination:
  `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/au/settled-meeting/b5f034fee18e/2026-07-15 Warwick Farm Race 1-7`.
- Restored it to a new external path under
  `restore-drills/storage-20261011-warwick-farm/`; restore returned `pass` with
  the identical digest and append-only event
  `wc-artifact-restore:72342354e786193ba4d97f90`. This is recovery proof, NOT an
  independent second-device copy. Original source digest remains unchanged.
- After registration, all 3,558 current native AU logic paths and their ordering
  exactly match the catalog-aware reader. Count growth since 3,550 reflects
  concurrent production output; only same-instant parity is asserted.
- No historical source was removed. This copy-only pilot frees zero Mac bytes.
  COLD coverage for this artifact and launchd-context external-disk permission
  remain unverified. The prior COLD backlog must not be silently counted as fixed.
- Fresh Central run records: AU running, HKJC watch succeeded, Tennis daily
  succeeded, NBA postgame partial. Registry reports AU/HKJC production and
  Tennis/NBA shadow; registry labels do not certify current model performance.
  Dashboard configured; D1 backup status okay with verified restore/WARM but
  unverified COLD for its latest snapshot. Stage 5 Tasks 6–10 remain open.

Next: finish full gate/release when production resource checks allow; verify
independent COLD recovery and background disk access, then plan a pinned batch of
old immutable meetings. Exact source-removal authority is still required after
proofs; never approve deletion merely because this copy-only pilot passed.

## Independent COLD pilot verified — 2026-10-11 Sydney

- Grounded the existing Google Drive `WongChoi-Archive` folder through connector
  search and metadata (`1QXtbUhD4dJxYl37zksTatzK6xrEJxcMi`). No new sharing
  permissions or folder moves were applied.
- Packed the native Warwick Farm meeting into a new external-only tar.gz,
  uploaded it as `AU-2026-07-15-Warwick-Farm-b5f034fee18e.tar.gz`, and read its
  completed Drive metadata back. Remote file ID:
  `157qAmrYEJOPqFfMRq1SDmPGYpz4cUMCW`; stored compressed size 744,065 bytes.
  Canonical link:
  https://drive.google.com/file/d/157qAmrYEJOPqFfMRq1SDmPGYpz4cUMCW
- Downloaded the COMPLETE remote raw file using the connector-returned
  authenticated file reference, directly to a new external path. Compared
  compressed bytes exactly against the upload artifact before extracting into
  the fresh `cold-restored-content` directory. No bearer URL is stored here.
- After the extraction process completed, the restored native folder digest
  matched the manifest: 50 files, 4,022,800 bytes,
  `b5f034fee18e5a30af8953a1c872a222858ef64bb433dc99f9df7aae662453d0`.
  An early probe while extraction was still running returned an empty digest;
  it was NOT used as evidence or submitted as a proof. The terminal successful
  extraction and subsequent full matching digest are the acceptance evidence.
- Central `archive-remote-proof` accepted the real full-download digest and
  appended `wc-artifact-remote-mirror:e730b9424db5f072cefab654`, status `verified`.
  The pilot now has WARM copy, restore, and independently verified Drive COLD
  proof. This resolves this pilot's COLD gap only, not the older three-item backlog.
- Packing, download and restoration intermediates were retained on the external
  disk. No source removal occurred and no historical Mac bytes were freed.
  This is storage-durability evidence, not model-performance or Stage 5 exit proof.
- AU PID 68933 remained live at elapsed 02:19:47 before these small copy probes;
  no new scheduler, installer, launchd job, full gate, release or activation was
  initiated. Background external-disk access and consumer release remain open.

## D1 COLD backlog cleared — 2026-10-11 Sydney

Three sealed WARM snapshots were independently rehashed before packing; all
matched their existing immutable catalog manifests. Grounded the existing Drive
`WongChoi-Archive/central/d1-ledger-backup` folder through search, parent metadata
and folder listing (ID `1Hf5EjmlL_gee8EkO6rppLfJNO8oCd8u9`). Existing organization
and sharing were preserved; no live D1 query/write, ledger settlement, source
removal, scheduler change or deployment was performed.

Each archive was uploaded, metadata read back, fully downloaded through its
authenticated connector file reference directly to the external disk, compared
byte-for-byte with the known upload, and extracted into a new external directory.
Restored native directory digests matched their manifests before Central accepted
the append-only full-download proofs. Working files are retained under:
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/restore-drills/d1-cold-20261011-6p8xTB`. No signed download URLs are stored here.

| Sealed snapshot | Artifact suffix | Directory bytes/files | SHA256 | Drive file | Central proof event |
|---|---|---:|---|---|---|
| 20261009T115237.072013Z | 021917b9b7ac4f3775fa82bf | 315023 / 2 | 13b4dd1e5a6827fc456b1574d198bc4da3cd6c95e36db5d8cc5dc20c820d71a7 | [verified backup](https://drive.google.com/file/d/1RxtDrkYuoO-mWdg4W8Lx1Ra6Ag1XYJ2u) | wc-artifact-remote-mirror:069cc66e1c2bad5d14471bab |
| 20260925T172001.636947Z | 5664ec8ca4d71df9252ea5fa | 239982 / 2 | 9f241d32a3f97f3bbba2ebd754cd5115ab2fe7f5bbb846755d827e399b1d529d | [verified backup](https://drive.google.com/file/d/1EdRkxb7h57A0xYU6lqm4Pd-foyU7rRG_) | wc-artifact-remote-mirror:eb33c40906911e5e2f755318 |
| 20261009T162004.125026Z | e5d43174df1fac899ae90189 | 315023 / 2 | 6e7795e3f77a5ce2be57289ec9570d329f8608f738d327c1cbcbc3422f54ab26 | [verified backup](https://drive.google.com/file/d/1TNZpsKbg7Ip2FgXYDaOMTnZ--CXqhwK3) | wc-artifact-remote-mirror:4f1fce33c9bfe249e356f521 |

These proofs cover the previously outstanding three artifacts, not every future
nightly backup. Recheck catalog coverage after the next nightly snapshot. No Mac
history was removed, so this operation does not free historical HOT bytes or
establish that the 30 GiB capacity target has been reached.

Fresh Central readback confirms 14/14 known COLD artifacts verified, backlog 0,
latest D1 `cold_verified=true` and backup status `ok`. Mac free space was 13.47
GiB and external free space 877.24 GiB: HOT pressure remains unresolved. Latest
domain run records show AU/HKJC running, Tennis succeeded, NBA partial; registry
stages remain AU/HKJC production, Tennis/NBA shadow. Candidate code remains
uncommitted/unpushed/unactivated; scoped-save authority and full gate are pending.

## Candidate save scope — separate from any source removal

### AU Sportsbet cache routing discovery — 2026-10-11 Sydney

- Allocated primary `.agents/skills/au_racing/.sportsbet_cache` size is now
  1,389,824 KiB (~1.33 GiB). Production's same relative cache path is a symlink
  to this primary cache; they are NOT two independently reclaimable copies.
- `claw_sportsbet_form.py` already reads `WC_SB_CACHE` at import time; its
  `SportsbetFormFetcher` and `sb_browser_bridge.py` use that same selected root.
  Daily `run_cmd` forces `WC_SB_CACHE_ONLY=1`, so missing cache returns `None`
  without fetching replacements. This is source data needed for live analysis,
  not an approved regenerable package cache. No cache bytes were removed.
- Constructor `mkdir(parents=True)` has no native mounted-volume guard. Merely
  pointing `WC_SB_CACHE` at an unmounted `/Volumes` path is unsafe: it can write
  locally if permissions allow. External startup/background access checks and
  mid-run disk-loss handling must precede production routing.
- At initial inspection, two research entrypoints ignored this environment variable in their CLI
  defaults: `au_sportsbet_raw_field_audit.py` and
  `au_sportsbet_performance_quality_candidate.py`, both under
  `au_wong_choi_auto/scripts/`. They require an explicit verified `--cache-dir`
  during a cutover unless their defaults are separately corrected and released.
- Added one isolated subprocess compatibility test to the existing storage
  test file. It executes the real native cache loader with an explicitly seeded
  alternate root, verifies both cached-read APIs and missing-page no-network
  behavior. Only the external HTTP API is mocked; cache read code is real.
  Combined storage/catalog tests: **23 passed in 0.74 seconds**. This fixture
  does not prove live full-cache parity, launchd permissions or activation.
- Correct cutover must quiesce all cache writers, freeze/copy/hash the source,
  validate the chosen root across browser/parser/research consumers, preserve
  PIT evidence and approved rollback, then release guarded runtime routing.
  Do not change the live symlink or delete the old cache while AU PID 68933 is
  still confirmed alive (elapsed 02:43:24 at this investigation).
- No domain engine, score, feature, scheduler, installer or cache root setting
  changed. The existing five-file candidate scope remains unchanged; this is
  additional integration evidence and migration risk documentation, not a
  completed production storage fix.
- Primary and production `claw_sportsbet_form.py` SHA256 both equal
  `1d93d887dcc2ac1c199c04556ef82e64f7982da02ce309c46c62be4e68f88726`.
  Quick gate subsequently passed; existing AU stale-baseline/new-field warnings
  remain, without any recalibration or ruler change. Full gate remains pending.

Only these five repository paths belong to this storage candidate:

- `.agents/scripts/wongchoi_external_run.py`
- `.agents/scripts/tests/test_wongchoi_external_run.py`
- `.agents/skills/shared_racing/scripts/corpus_paths.py`
- `.agents/skills/shared_wong_choi/tests/test_corpus_catalog.py`
- `docs/operations/wongchoi-storage-plan-2026-10-10.md`

### Separate AU research CLI follow-up source scope

The following three paths are a separate, unsaved follow-up, NOT silently added
to the five-path save request:

- `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_sportsbet_raw_field_audit.py`
- `.agents/skills/au_racing/au_wong_choi_auto/scripts/au_sportsbet_performance_quality_candidate.py`
- `.agents/scripts/tests/test_au_research_cache_routing.py`

Both existing entrypoints were clean at preflight. They now import the native
`claw_sportsbet_form.CACHE_DIR` for their argparse cache default. Precedence is
explicit `--cache-dir` > nonempty `WC_SB_CACHE` > unchanged native local default.
No scoring, extraction algorithm, weights, dataset, ruler, holdout or runtime
cache setting changed. The change does not create a mounted-volume guard.

TDD RED: two environment-default cases failed, six empty/unset/explicit cases
passed. GREEN: all eight native CLI subprocess probes passed; combined with
the existing storage/catalog tests, 31 passed in 1.40 seconds. Probes execute
real module import and argparse, replace only the HTTP dependency, and stop
immediately after parsing before any dataset access or evaluation. Each fixture
directory remains empty. Quick gate and diff check passed, with existing AU
stale-baseline/new-field warnings unchanged. No full gate, save, push or activation.

These source changes supersede the earlier hardcoded-cache-default finding in
the candidate only; production still has its original files/configuration.
AU PID 68933 remains live at elapsed 02:49:29. Actual seeded-cache parity,
mount/background access, offline/preemption behavior and controlled cutover
still require proof before routing production. Output/quality sidecar CLI
defaults remain under `/private/tmp`: cache-root alignment alone does not move
them. Supervised execution must supply explicit verified WARM output paths.

Expected result: manual guarded commands use external scratch/download caches;
AU catalog readers select a verified known copy instead of a corrupt/empty HOT
folder. This does not wire existing automation into the helper. Release requires
full gate, fresh exact-scope/immutable SHA rechecks and production resource gates.
Unrelated worktree changes, model scoring, rulers, installers, schedulers and
historical source deletion are excluded. Earlier Central storage readback measured
14.78 GiB HOT and 877.29 GiB WARM, with 11/14 COLD artifacts verified and three
older artifacts outstanding. Concurrent free-space change is not credited to
this copy-only work.

## Old AU batch inventory — 2026-10-11 Sydney

Read-only metadata snapshot; not a deletion approval, immutable hash manifest,
settlement proof or activated retention policy. Cutoff `2026-09-10` is only an
inventory filter, not an evaluation-window change. Every path below is beneath
`/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/Archive`. Names, file counts and logical byte sizes were observed together.

195 meetings, 1809210572 logical bytes (1.68 GiB).
8 meetings lack a result-named file; names alone cannot prove settlement.
Files still require stable before/after hashes, consumer compatibility, WARM copy,
restore, independent COLD proof, launchd access and exact-source removal approval.
Allocated/reclaimable Mac bytes may differ because of filesystem blocks/snapshots.
This old batch alone is insufficient to reach the 30 GiB HOT free-space target.

| Relative meeting source | Files | Logical bytes | Logic files | Result-named files |
|---|---:|---:|---:|---:|
| 2026-07-15 Warwick Farm Race 1-7 | 50 | 4022800 | 7 | 3 |
| 2026-07-18 Flemington Race 1-9 | 57 | 6738438 | 9 | 0 |
| 2026-07-18 Rosehill Gardens Race 1-10 | 63 | 8950912 | 10 | 0 |
| 2026-07-25 Caulfield Race 1-9 | 57 | 6215769 | 9 | 0 |
| 2026-07-25 Eagle Farm Race 1-9 | 57 | 6108456 | 9 | 0 |
| 2026-07-25 Randwick Race 1-10 | 63 | 9322348 | 10 | 0 |
| 2026-07-31 Geelong Race 1-9 | 61 | 7826190 | 9 | 3 |
| 2026-08-01 Flemington Race 1-9 | 59 | 7074365 | 9 | 1 |
| 2026-08-01 Rosehill Gardens Race 1-10 | 65 | 8506163 | 10 | 1 |
| 2026-08-05 Belmont Race 1-8 | 55 | 6815809 | 8 | 1 |
| 2026-08-05 Canterbury Race 1-7 | 47 | 3749176 | 7 | 1 |
| 2026-08-05 Cranbourne Race 1-8 | 51 | 6657858 | 8 | 0 |
| 2026-08-05 Doomben Race 1-8 | 53 | 4817440 | 8 | 1 |
| 2026-08-05 Hobart Race 1-9 | 59 | 5939048 | 9 | 1 |
| 2026-08-05 Murray Bridge Race 1-8 | 53 | 5540123 | 8 | 1 |
| 2026-08-06 Ballarat Synthetic Race 1-8 | 55 | 4954431 | 8 | 1 |
| 2026-08-06 Gosford Race 1-8 | 55 | 3590540 | 8 | 1 |
| 2026-08-06 Moree Race 1-7 | 49 | 4825892 | 7 | 1 |
| 2026-08-06 Mt Isa Race 1-7 | 49 | 3389966 | 7 | 1 |
| 2026-08-06 Northam Race 1-8 | 55 | 5055473 | 8 | 1 |
| 2026-08-07 Canberra Race 1-7 | 49 | 3383729 | 7 | 1 |
| 2026-08-07 Coffs Harbour Race 1-8 | 55 | 6016622 | 8 | 1 |
| 2026-08-07 Ipswich Race 1-7 | 49 | 4917725 | 7 | 1 |
| 2026-08-07 Mount Gambier Race 1-7 | 49 | 4104299 | 7 | 1 |
| 2026-08-07 Seymour Race 1-8 | 55 | 6275607 | 8 | 1 |
| 2026-08-08 Alice Springs Race 1-7 | 49 | 2780532 | 7 | 1 |
| 2026-08-08 Casino Race 1-8 | 55 | 6656835 | 8 | 1 |
| 2026-08-08 Caulfield Heath Race 1-9 | 61 | 6612604 | 9 | 1 |
| 2026-08-08 Eagle Farm Race 1-9 | 61 | 6952229 | 9 | 1 |
| 2026-08-08 Kembla Grange Race 1-8 | 55 | 5194834 | 8 | 1 |
| 2026-08-08 Mildura Race 1-7 | 47 | 3998473 | 7 | 1 |
| 2026-08-08 Morphettville Race 1-9 | 61 | 6382915 | 9 | 1 |
| 2026-08-08 Randwick Race 1-10 | 67 | 7264357 | 10 | 1 |
| 2026-08-08 Townsville Race 1-8 | 55 | 9411822 | 8 | 1 |
| 2026-08-09 Ballarat Synthetic Race 1-8 | 55 | 5296220 | 8 | 1 |
| 2026-08-09 Casterton Race 1-7 | 49 | 3483493 | 7 | 1 |
| 2026-08-09 Kalgoorlie Race 1-8 | 55 | 5480110 | 8 | 1 |
| 2026-08-09 Muswellbrook Race 1-7 | 49 | 3603771 | 7 | 1 |
| 2026-08-09 Sunshine Coast Race 1-8 | 55 | 4583304 | 8 | 1 |
| 2026-08-09 Wagga Race 1-7 | 47 | 4418804 | 7 | 0 |
| 2026-08-10 Dubbo Race 1-7 | 49 | 6552175 | 7 | 1 |
| 2026-08-10 Kilcoy Race 1-7 | 49 | 5082187 | 7 | 1 |
| 2026-08-10 Nowra Race 1-7 | 49 | 5629986 | 7 | 1 |
| 2026-08-10 Pakenham Synthetic Race 1-9 | 61 | 6835477 | 9 | 1 |
| 2026-08-11 Ballarat Synthetic Race 1-10 | 67 | 6453161 | 10 | 1 |
| 2026-08-11 Ballina Race 1-8 | 55 | 5346724 | 8 | 1 |
| 2026-08-11 Broome Race 1-6 | 43 | 3502135 | 6 | 1 |
| 2026-08-11 Dalby Race 1-8 | 55 | 6036408 | 8 | 1 |
| 2026-08-11 Hawkesbury Race 1-7 | 49 | 4791481 | 7 | 1 |
| 2026-08-12 Bendigo Race 1-8 | 55 | 4209662 | 8 | 1 |
| 2026-08-12 Canterbury Race 1-7 | 49 | 3918059 | 7 | 1 |
| 2026-08-12 Devonport Race 1-8 | 54 | 5363924 | 8 | 1 |
| 2026-08-12 Eagle Farm Race 1-8 | 54 | 5166248 | 8 | 1 |
| 2026-08-12 Murray Bridge Race 1-8 | 54 | 7019637 | 8 | 1 |
| 2026-08-12 Pinjarra Scarpside Race 1-8 | 54 | 5920788 | 8 | 1 |
| 2026-08-13 Bunbury Race 1-8 | 55 | 6139663 | 8 | 1 |
| 2026-08-13 Moe Race 1-8 | 55 | 6053171 | 8 | 1 |
| 2026-08-13 Newcastle Race 1-8 | 55 | 4627367 | 8 | 1 |
| 2026-08-13 Rockhampton Race 1-7 | 49 | 4293115 | 7 | 1 |
| 2026-08-13 Wellington Race 1-7 | 47 | 5021160 | 7 | 0 |
| 2026-08-14 Geelong Race 1-8 | 55 | 5348646 | 8 | 1 |
| 2026-08-14 Gunnedah Race 1-8 | 55 | 6541092 | 8 | 1 |
| 2026-08-14 Ipswich Race 1-7 | 49 | 4798444 | 7 | 1 |
| 2026-08-14 Taree Race 1-8 | 55 | 6863839 | 8 | 1 |
| 2026-08-15 Caulfield Race 1-9 | 61 | 7504244 | 9 | 1 |
| 2026-08-15 Doomben Race 1-9 | 61 | 5836626 | 9 | 1 |
| 2026-08-15 Katherine Race 1-7 | 49 | 4016983 | 7 | 1 |
| 2026-08-15 Kembla Grange Race 1-8 | 55 | 5215232 | 8 | 1 |
| 2026-08-15 Morphettville Race 1-9 | 61 | 6122180 | 9 | 1 |
| 2026-08-15 Narrandera Race 1-6 | 43 | 3953787 | 6 | 1 |
| 2026-08-15 Roma Race 1-6 | 43 | 3409302 | 6 | 1 |
| 2026-08-15 Rosehill Race 1-10 | 67 | 7433105 | 10 | 1 |
| 2026-08-15 Warracknabeal Race 1-7 | 49 | 5418531 | 7 | 1 |
| 2026-08-16 Ballarat Race 1-6 | 43 | 3056289 | 6 | 1 |
| 2026-08-16 Moruya Race 1-8 | 55 | 5896249 | 8 | 1 |
| 2026-08-16 Pakenham Synthetic Race 1-7 | 49 | 5073497 | 7 | 1 |
| 2026-08-16 Sunshine Coast Race 1-8 | 55 | 5229059 | 8 | 1 |
| 2026-08-16 Wyong Race 1-8 | 55 | 4667936 | 8 | 1 |
| 2026-08-17 Bathurst Race 1-7 | 49 | 3785454 | 7 | 1 |
| 2026-08-17 Emerald Race 1-7 | 49 | 3872840 | 7 | 1 |
| 2026-08-17 Scone Race 1-7 | 49 | 4173965 | 7 | 1 |
| 2026-08-17 Wodonga Race 1-8 | 55 | 5633352 | 8 | 1 |
| 2026-08-18 Albury Race 1-7 | 49 | 3862095 | 7 | 1 |
| 2026-08-18 Ballarat Synthetic Race 1-7 | 49 | 5218601 | 7 | 1 |
| 2026-08-18 Grafton Race 1-7 | 49 | 5426141 | 7 | 1 |
| 2026-08-18 Townsville Race 1-7 | 49 | 4621463 | 7 | 1 |
| 2026-08-19 Belmont Race 1-8 | 55 | 6240617 | 8 | 1 |
| 2026-08-19 Hobart Race 1-10 | 67 | 6370637 | 10 | 1 |
| 2026-08-19 Ipswich Race 1-7 | 49 | 4878385 | 7 | 1 |
| 2026-08-19 Sandown Race 1-8 | 55 | 6036868 | 8 | 1 |
| 2026-08-19 Strathalbyn Race 1-7 | 49 | 4747292 | 7 | 1 |
| 2026-08-19 Warwick Farm Race 1-7 | 49 | 4741735 | 7 | 1 |
| 2026-08-20 Hawkesbury Race 1-8 | 55 | 4575317 | 8 | 1 |
| 2026-08-20 Mackay Race 1-6 | 43 | 3472902 | 6 | 1 |
| 2026-08-20 Pinjarra Race 1-7 | 49 | 5305960 | 7 | 1 |
| 2026-08-20 Warrnambool Race 1-8 | 55 | 5032845 | 8 | 1 |
| 2026-08-21 Beaudesert Race 1-8 | 57 | 5593776 | 8 | 1 |
| 2026-08-21 Canberra Race 1-7 | 49 | 4631909 | 7 | 1 |
| 2026-08-21 Murtoa Race 1-8 | 55 | 4427307 | 8 | 1 |
| 2026-08-21 Murwillumbah Race 1-8 | 55 | 5141152 | 8 | 1 |
| 2026-08-21 Sale Race 1-9 | 61 | 6866755 | 9 | 1 |
| 2026-08-22 Belmont Race 1-8 | 55 | 5108191 | 8 | 1 |
| 2026-08-22 Cairns Race 1-8 | 55 | 5936740 | 8 | 1 |
| 2026-08-22 Doomben Race 1-10 | 67 | 7446108 | 10 | 1 |
| 2026-08-22 Gympie Race 1-5 | 37 | 3085584 | 5 | 1 |
| 2026-08-22 Morphettville Race 1-9 | 61 | 6911171 | 9 | 1 |
| 2026-08-22 Newcastle Race 1-8 | 55 | 4605917 | 8 | 1 |
| 2026-08-22 Port Macquarie Race 1-5 | 37 | 2916469 | 5 | 1 |
| 2026-08-22 Quirindi Race 1-6 | 43 | 4385655 | 6 | 1 |
| 2026-08-22 Randwick Race 1-10 | 67 | 8258071 | 10 | 1 |
| 2026-08-22 Sandown Race 1-9 | 61 | 5602169 | 9 | 1 |
| 2026-08-23 Goulburn Race 1-8 | 55 | 5466156 | 8 | 1 |
| 2026-08-23 Kalgoorlie Race 1-8 | 55 | 6618604 | 8 | 1 |
| 2026-08-23 Kilcoy Race 1-9 | 61 | 5881793 | 9 | 1 |
| 2026-08-23 Narromine Race 1-9 | 61 | 6445172 | 9 | 1 |
| 2026-08-23 Port Augusta Race 1-7 | 48 | 4465461 | 7 | 1 |
| 2026-08-23 Wangaratta Race 1-8 | 55 | 6034917 | 8 | 1 |
| 2026-08-24 Pakenham Synthetic Race 1-9 | 61 | 6506240 | 9 | 1 |
| 2026-08-24 Tuncurry Race 1-8 | 55 | 5342723 | 8 | 1 |
| 2026-08-25 Ballarat Synthetic Race 1-7 | 51 | 5244094 | 7 | 1 |
| 2026-08-25 Rockhampton Race 1-7 | 51 | 4402332 | 7 | 1 |
| 2026-08-25 Tamworth Race 1-7 | 51 | 5329399 | 7 | 1 |
| 2026-08-26 Belmont Race 1-8 | 57 | 6188440 | 8 | 1 |
| 2026-08-26 Bendigo Race 1-8 | 57 | 4032324 | 8 | 1 |
| 2026-08-26 Canterbury Race 1-7 | 51 | 4189476 | 7 | 1 |
| 2026-08-26 Devonport Race 1-9 | 63 | 5780723 | 9 | 1 |
| 2026-08-26 Doomben Race 1-8 | 57 | 6126995 | 8 | 1 |
| 2026-08-27 Ipswich Race 1-8 | 57 | 6133897 | 8 | 1 |
| 2026-08-27 Northam Race 1-8 | 57 | 5834702 | 8 | 1 |
| 2026-08-27 Seymour Race 1-8 | 57 | 6799532 | 8 | 1 |
| 2026-08-28 Alice Springs Race 1-5 | 39 | 2380413 | 5 | 1 |
| 2026-08-28 Cairns Race 1-8 | 57 | 6659125 | 8 | 1 |
| 2026-08-28 Geelong Race 1-9 | 63 | 8134964 | 9 | 1 |
| 2026-08-28 Gosford Race 1-8 | 57 | 6677741 | 8 | 1 |
| 2026-08-29 Cairns Race 1-8 | 57 | 6746246 | 8 | 1 |
| 2026-08-29 Caulfield Race 1-10 | 69 | 10362263 | 10 | 1 |
| 2026-08-29 Eagle Farm Race 1-10 | 69 | 8796076 | 10 | 1 |
| 2026-08-30 Carnarvon Race 1-6 | 66 | 8921888 | 6 | 1 |
| 2026-08-30 Casterton Race 1-7 | 99 | 14802884 | 7 | 1 |
| 2026-08-30 Echuca Race 1-8 | 111 | 14429775 | 8 | 1 |
| 2026-08-30 Mudgee Race 1-7 | 99 | 13661528 | 7 | 1 |
| 2026-08-30 Strathalbyn Race 1-8 | 111 | 15743096 | 8 | 1 |
| 2026-08-30 Townsville Race 1-6 | 87 | 14008316 | 6 | 1 |
| 2026-08-30 Wyong Race 1-8 | 111 | 13375758 | 8 | 1 |
| 2026-08-31 Ballarat Synthetic Race 1-9 | 123 | 20539093 | 9 | 1 |
| 2026-08-31 Corowa Race 1-7 | 99 | 14043671 | 7 | 1 |
| 2026-08-31 Taree Race 1-8 | 111 | 18291473 | 8 | 1 |
| 2026-09-01 Scone Race 1-8 | 111 | 16043650 | 8 | 1 |
| 2026-09-01 Wodonga Race 1-8 | 111 | 14732653 | 8 | 1 |
| 2026-09-02 Belmont Race 1-7 | 99 | 17481617 | 7 | 1 |
| 2026-09-02 Devonport Race 1-9 | 123 | 13933754 | 9 | 1 |
| 2026-09-02 Ipswich Race 1-8 | 111 | 17623144 | 8 | 1 |
| 2026-09-02 Murray Bridge Race 1-9 | 144 | 26602787 | 9 | 1 |
| 2026-09-02 Sandown Race 1-8 | 111 | 18536914 | 8 | 1 |
| 2026-09-02 Warwick Farm Race 1-7 | 99 | 14717749 | 7 | 1 |
| 2026-09-03 Coffs Harbour Race 1-8 | 111 | 16455203 | 8 | 1 |
| 2026-09-03 Mackay Race 1-7 | 99 | 14849014 | 7 | 1 |
| 2026-09-03 Northam Race 1-7 | 99 | 15376646 | 7 | 1 |
| 2026-09-03 Warrnambool Race 1-8 | 111 | 18347002 | 8 | 1 |
| 2026-09-04 Birdsville Race 1-6 | 87 | 9602650 | 6 | 1 |
| 2026-09-04 Canberra Race 1-8 | 111 | 21237562 | 8 | 1 |
| 2026-09-04 Mornington Race 1-9 | 123 | 24306340 | 9 | 1 |
| 2026-09-04 Wyong Race 1-8 | 111 | 17801198 | 8 | 1 |
| 2026-09-05 Birdsville Race 1-7 | 123 | 17094029 | 7 | 1 |
| 2026-09-05 Eagle Farm Race 1-10 | 168 | 33677877 | 10 | 1 |
| 2026-09-05 Gold Coast Race 1-8 | 138 | 27257844 | 8 | 1 |
| 2026-09-05 Hawkesbury Race 1-8 | 138 | 19622473 | 8 | 1 |
| 2026-09-05 Kempsey Race 1-6 | 108 | 16451735 | 6 | 1 |
| 2026-09-05 Mildura Race 1-7 | 123 | 23764425 | 7 | 1 |
| 2026-09-05 Morphettville Race 1-9 | 153 | 30401579 | 9 | 1 |
| 2026-09-05 Randwick Race 1-10 | 168 | 39797621 | 10 | 1 |
| 2026-09-05 Sandown Race 1-10 | 168 | 32223612 | 10 | 1 |
| 2026-09-06 Bendigo Race 1-10 | 135 | 24068946 | 10 | 1 |
| 2026-09-06 Gundagai Race 1-7 | 99 | 16136365 | 7 | 1 |
| 2026-09-06 Kalgoorlie Race 1-8 | 111 | 23851330 | 8 | 1 |
| 2026-09-06 Moree Race 1-8 | 111 | 23414004 | 8 | 1 |
| 2026-09-06 Sunshine Coast Race 1-8 | 111 | 20270954 | 8 | 1 |
| 2026-09-07 Dubbo Race 1-7 | 99 | 20103976 | 7 | 1 |
| 2026-09-07 Grafton Race 1-7 | 99 | 15445268 | 7 | 1 |
| 2026-09-07 Tatura Race 1-8 | 111 | 21733079 | 8 | 1 |
| 2026-09-08 Moe Race 1-7 | 75 | 15546530 | 7 | 1 |
| 2026-09-08 Muswellbrook Race 1-7 | 75 | 13903249 | 7 | 1 |
| 2026-09-08 Queanbeyan Race 1-7 | 75 | 12553711 | 7 | 1 |
| 2026-09-08 Townsville Race 1-8 | 84 | 15124658 | 8 | 1 |
| 2026-09-09 Belmont Race 1-8 | 84 | 13210070 | 8 | 1 |
| 2026-09-09 Devonport Race 1-9 | 93 | 11094934 | 9 | 1 |
| 2026-09-09 Ipswich Race 1-7 | 75 | 10382927 | 7 | 1 |
| 2026-09-09 Murray Bridge Race 1-8 | 84 | 13411642 | 8 | 1 |
| 2026-09-09 Randwick-Kensington Race 1-7 | 75 | 9346751 | 7 | 1 |
| 2026-09-09 Sandown Race 1-10 | 102 | 14944653 | 10 | 1 |
| 2026-09-10 Bunbury Race 1-7 | 99 | 20533430 | 7 | 1 |
| 2026-09-10 Hawkesbury Race 1-8 | 111 | 17234701 | 8 | 1 |
| 2026-09-10 Lismore Race 1-7 | 99 | 15763855 | 7 | 1 |
| 2026-09-10 Seymour Race 1-8 | 111 | 16595918 | 8 | 1 |
| 2026-09-10 Warwick Race 1-7 | 99 | 22022759 | 7 | 1 |
