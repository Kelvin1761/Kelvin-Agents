# Mac storage offload — 2026-10-14 Sydney

User authorized keeping necessary items on the Mac and moving bulk storage to
the mounted external disk. Auto-release remains enabled; no further Telegram
approval is needed after a scoped release passes its immutable gates.

## Completed bulk relocation

Source and destination SHA-256s were compared, original source rehashed before
removal, and open-file checks completed. Per-item file hashes and exact rollback
locations are preserved alongside each destination as `*.migration.json`.

External root: `/Volumes/Kelvin Hardisk 1/Mac-Offload/2026-10-14/`.

| Original Mac item | External relative path | Verified bytes |
|---|---|---:|
| Downloads/Day 1-20261011T072448Z-1-001.zip | Downloads/Day 1-20261011T072448Z-1-001.zip | 2122932716 |
| Downloads/Day 1-20261011T072448Z-1-002.zip | Downloads/Day 1-20261011T072448Z-1-002.zip | 2030415775 |
| Downloads/Antigravity.dmg | Downloads/Antigravity.dmg | 206573240 |
| Antigravity-repo/mahjong_edit | Projects/mahjong_edit | 1957356148 |

First batch relocated: 6317277879 bytes (5.88 GiB). Source Mac copies removed only
following verification. This is relocation, not independent disaster backup;
the external disk must remain available to open these items. Restore by copying
the exact item back to its original absent path and checking the recorded hashes.
The mahjong project includes its Python pipeline and subtitle editor. A tiny
original-path symlink was restored after verification so existing commands can
continue using `mahjong_edit/` while its bulk bytes stay on the external disk.

Observed Mac available space increased from about 19 GiB to about 25 GiB;
external space decreased from about 828 GiB to about 823 GiB. Concurrent writes
mean observed filesystem change is not exact attribution. HOT is above the
20 GiB critical threshold but below the 30 GiB target.

## Daily analysis is not automatically offloaded next day

AU `archive_meeting` moves eligible finished meetings into the **local**
`AU_Racing/Archive`. That is not an external relocation. Central's installed
nightly durability job runs D1 backups (03:20 and 05:20), not general analysis
retention. Central `archive-copy` is copy-only and leaves the HOT source present.
No automatic next-day external retention job was found.

Production at `93a0a193e395` has a concrete blocker: shared AU `logic_files()`
only enumerates native HOT/root and Archive folders. `meeting_dirs()` has a
catalog fallback, but this does not cover consumers that use `logic_files()`.
The primary checkout has an unsaved storage-reader correction and focused tests;
it is not part of the separate 34-path Stage 5 history-reader candidate.
Moving native historic meetings now would silently narrow some evaluation
corpora. HKJC consumer coverage and launchd external-disk access also require
proof; foreground access does not establish unattended access.

Required before historical HOT removal: release native storage readers;
verify same full-history identities and counts with WARM; establish settled,
immutable per-meeting source hashes, restore and independent COLD copy;
prove background access and fail-closed offline handling. Only then activate a
settlement-aware residency job. Calendar age alone does not establish settlement.
Current user direction authorizes relocation; repeated permission requests are
not a substitute for completing these technical proofs.

## Necessary HOT items retained

Active code/checkouts/interpreters, live Tennis SQLite and WAL/SHM, current models,
control manifests/locks, current or unsettled meetings, login/browser profiles
and runtime source caches. AU/HKJC history and Sportsbet live source cache remain
intact until the reader/background/durability requirements are satisfied.

## Release review

The 34-file Stage 5 reader candidate was aligned to `93a0a193e395`, with every
candidate file SHA-256 unchanged and no upstream scope overlaps. New-base quick
gate passed; meeting data contracts were skipped in the isolated checkout.
Exact 34-path release dry-run confirmed code/full gate and automatic
push/merge/activation, without unrelated files or installers. Full scoped save
is in progress; do not treat this checkpoint as a completed commit or activation.

## Completed media relocation

LoL generated output directory (54 files, 990058598 bytes) and the Desktop
`今晚十點 ｜ LOL 之夜 10.11.mp4` (924008991 bytes) were also copied,
source/destination/source rehashed, and checked for open file handles before
removing the Mac bulk copies. External root:
`/Volumes/Kelvin Hardisk 1/Mac-Offload/2026-10-14-media/`.

Tiny symlinks preserve the original LoL output and Desktop-video paths. These
are finished personal media paths, not live racing/database/browser roots.
They require the mounted external disk; there is no local bulk fallback.
Adjacent `*.migration.json` files record every hash and exact source path.
Total verified bulk relocated across both batches: **8231345468 bytes
(7.67 GiB)**. Mac free-space measurements are recorded separately from byte totals.

Operational health check completed, exit 1: Central 30-day SLO fails for NBA
(64.9% coverage, 185 slots). AU/HKJC/Tennis slot metrics pass; 644 decisions
have 100% production provenance. Three newer D1 backups lack independent COLD
proof (14/17 verified). Schedule last-exit warnings and the old NBA legacy
status remain visible; no traceback/permission/stage failure was found in the
last three days of logs. This does not certify every scheduler or model.

## New-base reader gate failure

The guarded full-save gate on `93a0a193e395` produced a required failure in
`test_large_monitoring_corpus_above_legacy_reference_limit_keeps_one_real_fixture_label[Domain.HKJC]`.
The 1300-prediction/>5000-reference/13-page fixture and separate 600-second
deadlines were unchanged. HKJC's corpus completion and phase outcome both
report `timed_out / phase_timeout`, publication
`unconfirmed_reconcile_before_retry`; executor return code 0 does not make this
a successful phase. Executor wall time was 599.993511291 seconds.

AU corpus and actual review outcomes reported succeeded/receipt_verified
(519.025996542 and 354.516019042 seconds respectively). These are fixture
engineering observations, not live corpus or model-performance evidence.
The new-base full gate remains red; the earlier c962 full pass cannot substitute
for this new-base result. No timeout, fixture, scoring, model or ruler was changed.
All 34 candidate file SHA-256s still match the pre-alignment capture; no
commit/push/merge/activation has occurred. Cause of the timing failure remains
unconfirmed and needs a reproducible diagnosis before a new green full gate.

Retained native failure evidence:
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-apyui7y4/pytest-of-imac/pytest-7/test_large_monitoring_corpus_a1/warm/research-phases/hkjc/racing-monitoring-corpus-cx910pvy/phase-outcome.json`.
Exact requested release scope and original hashes:
`/tmp/wc-reader-scope-20261014.json`. Save command log:
`/tmp/wc-reader-release-20261014.log`.

Full scoped save reached terminal exit **1**. Central returned `blocked`:
`full gate failed; no files were staged`. Candidate is uncommitted/unpushed;
merge and activation were not started. This is a gate failure, not a missing
automatic-approval setting or a pending human approval.
