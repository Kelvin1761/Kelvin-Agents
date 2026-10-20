# AU settlement artifact recovery, 2026-10-21

The wider recovery found ten immutable settlement references whose mutable
report paths had subsequently been rendered again. Changing the recorded hashes
or accepting the newest settlement would discard historical evidence.

All ten original versions were reproduced and matched the existing recorded
SHA256 exactly. Eight result files used the cached Sportsbet responses and the
renderer from `2b3a8e1a^`, with network access disabled. Tamworth's meeting report
used `c9620bd0`; Seymour's used `1dc706a1`, the production commits recorded in
their respective original evening-run logs. Existing frozen prediction inputs
and result files were read without modification.

The recovery inventory and exact hashes are retained at
`/Users/imac/WongChoiData/WongChoiControl/recovery_reports/2026-10-21-exact-artifact-recovery.json`.
Ten create-only recovered versions and identity manifests were written under
the local evidence root and the mounted external WARM archive. Original
canonical evidence JSON and today's report files remained byte-identical.

The reader falls back only to a version keyed by the original absolute path,
recorded SHA256 and event. It verifies the manifest, file hash, bounded reads,
event identity, source and original capture clock; both manifest and bytes are
rechecked. Missing or corrupt recovery fails closed. It neither searches for
adjacent files nor omits conflicting records. Old and new versions of one path
can both remain valid. Recovery confers no feature-availability, qualified-sample
or model-promotion authority.

New AU settlements capture bounded, content-addressed report bundles before
appending evidence. This reuses the previously preserved implementation at
`3362b35e5898aba7e993716d0dbc0568a68541fe`, with the macOS temporary-path fixture
resolved to its real path rather than weakening the symlink rejection.

Focused validation covers immutable capture, native label readers, scheduler
adapters, duplicate versions, wrong hashes/events, corrupt manifests, missing
files and symlinks. Required repository quick/full gates apply to delivery.

The Drive canonical results CSV was separately restored after preserving both
FileProvider-blocked files under dated names. Its SHA256 is
`d83489b702f6b31e2043afe68187477db983361792529970641a6df4ca307a76`;
the normal production mirror step then reported `ok`, zero failures and no
fallback. No model or NBA prediction changes are included in this repair.

Additional operational verification during the wider recovery:

- All 276 settled AU records resolve 444 hash-pinned artifacts: 434 directly
  and ten through exact recovered versions. This is an artifact audit, not a
  feature-availability or model-promotion grant.
- A full hash audit matched 771 current AU mirror files (159,492,824 bytes).
  The older `AU_Backfill_Race_Results.csv` cloud placeholder remains stalled;
  its intact 77,795-byte source is mirrored through the existing supported
  `.latest.csv` path. No original was deleted or security permission weakened.
- The user explicitly approved restoring eight missing secondary D1 backup
  copies and the nightly destination. All copies were verified, and the
  machine-local `.wongchoi_cold_mirror_root` now identifies the existing Drive
  archive. The installed durability job initially received Cloudflare 7403;
  after the pinned CLI session was refreshed and a read-only probe succeeded,
  its launchd retry completed with exit 0 and verified local restore, WARM and
  COLD copies. A subsequent installed run correctly skipped the duplicate
  export (`today_already_verified`, exit 0). Coverage became 23/23 artifacts.
- The existing control-state restore drill passed into a new external-disk
  directory: source stable, all four tree hashes equal, and evidence audit
  clean (4 model releases, 949 predictions, 949 decisions, 292 settlements).
- WTA statistics collection is current, but switching the serve readers is
  still unevaluated. The existing serve-pricing replay since October 16 has
  nine props, seven WTA props from three matches; none of those three fixtures
  had the new feed available before prediction. A read-only connection-local
  candidate therefore scored identically, which proves neither improvement
  nor no regression. Live model code and its stale-input warning remain intact.
  The precise assessment is retained in the local recovery reports directory.
- Historical 30-day AU/NBA reliability failures and old failed attempts remain
  in their records. Today's HKJC refresh succeeded automatically; current
  distance evidence exists for every one of its 102 runners. AU's trial-score
  trend concerns a field already removed from ranking.

The first full release gate failed and staged nothing. Isolated reruns passed
every other suite and 1,641 shared tests excluding the two largest monitoring
cases. The isolated AU large case then passed with the unchanged 1,300-record,
13-page fixture: corpus phase 597.609 seconds and review phase 309.957 seconds,
each against its original 600-second limit. The corpus phase had only 2.4
seconds of headroom.

The metadata reader now avoids reconstructing parent `Path` objects while
still calling `lstat` on every ancestor on every physical read. A 5,000-call,
three-run benchmark measured median path-check time 0.502 versus 0.423 seconds.
Rechecks still reread and hash every byte under the original physical bounds;
only a second JSON parse is skipped when that exact digest successfully parsed
earlier in the same reader. Failed initial parsing never gains this status.
There is no mtime cache, checkpoint throttling, larger deadline, smaller corpus,
or persisted validation authority. Tests additionally check equal-size changes
with restored mtimes, parent replacement by a symlink to identical bytes, and
all sixteen physical reads in an eight-file initial/recheck pair. The focused
reader/snapshot/source/index tests pass (121); end-to-end and immutable release
gates remain mandatory.


HKJC recovery found twelve settlements with twenty-four recorded artifacts.
Seventeen files still match directly; seven exact historical versions are now
preserved locally and on WARM storage. All twelve records and twenty-four
references pass the read/recheck hash audit. No evidence record was rewritten.
Five ledgers were reconstructed by filtering the existing historical entries
and running the original deterministic summary/serializer; the October 7
weight ledger required the original `51dd52bf` summary implementation. The
reverse-bias ledgers additionally matched their original second-resolution
update timestamps. The October 7 report matched an exact byte prefix of the
current report, before the subsequently appended diagnostic section. Every
reconstruction was accepted only after matching its already-recorded SHA256.

The historical HKJC writer also referenced two global shadow ledgers outside
the meeting directory. The reader now verifies those exact two state-path
roles as auxiliaries; they never supply labels. Original meeting paths still
must agree with the event, and unrelated files with the same basenames remain
rejected. Exact recovery identities include domain, event, original absolute
path and digest. The AU identities remain unchanged. Future HKJC settlements
capture the report, canonical full-day results and materialized shadow ledgers
in one immutable event bundle on mounted WARM storage before writing evidence.
Missing results or unavailable WARM storage fail closed. Tests cover exact
recovery, corrupt copies, foreign event/state paths, auxiliary hash drift and
preservation of copied bytes after the next ledger update. The focused AU/HKJC
source/capture/scheduler group passed 45 tests.

The second release attempt was stopped before staging or committing when
these additional HKJC issues were discovered. A fresh full gate and immutable
recheck are required for the combined AU/HKJC repair; no earlier partial gate
is represented as a completed release.


After sync, FileProvider denied local listing of the latest COLD backup folder.
The files exist in Drive. The connected Drive readback downloaded both files
for that snapshot and all sixteen files in the eight approved restored backup
folders. All nine complete directory digests exactly matched their WARM
catalog digests. Append-only `full_download_content_digest` provider proofs
now preserve that independent verification; Central reports the latest D1
backup `restore_verified`, `warm_verified`, and `cold_verified` all true.
Local FileProvider accessibility is not asserted by a cloud proof. The nightly
job retains its configured destination and existing deferred behavior if
macOS denies a future background copy.

While this work was in progress, main advanced to `b7849740` with separately
released NBA/HKJC changes and scaled large-test fixtures. This worktree was
fast-forwarded and its exact owned changes reapplied. The original large-test
source from `87d89fe5` was retained outside the repo and both 1,300-record cases
are additionally required before this recovery release. No upstream work was
reverted. The latest observed NBA pregame retry succeeded; no NBA model or
prediction source is part of this recovery scope.


The third release gate used the external disk for all pytest fixtures. Its
notification warm-loss test timed out before the fake helper wrote its marker:
2.831 seconds wall time with only 0.180 seconds CPU against the original
2-second child deadline. The unchanged isolated test passed on the local disk
in 1.18 seconds. The entire external gate temporary tree measured 127.5 MiB,
below the repository's 1 GiB external-temp threshold. That failed gate was
stopped before staging/commit; the next complete gate uses a dedicated local
temporary directory. No test, deadline, guard, corpus, or assertion was changed.
The external failure receipt remains preserved for diagnosis.
