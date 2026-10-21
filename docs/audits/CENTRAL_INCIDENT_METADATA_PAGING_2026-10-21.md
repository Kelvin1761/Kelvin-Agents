# Central production-incident metadata paging

The orchestration/lock-observer recovery was merged and activated as
`02c7f5035219b86ddc3fed7e708350755a4d5294`, after its source gate and both
replayed preparation and immutable approval gates passed. All four production
domains aligned. The strict research installer then verified the existing
cursor configurations and ran its native first pass.

AU's complete monitoring corpus succeeded in 544.509 seconds. Its subsequent
review failed in 1.286 seconds at `collect_production_incidents`' final source
recheck: `ResearchIndexError: evidence byte budget exceeded`. This collector
still used a flat `_Reader` for the complete production evidence graph. Its
32 MiB physical-read budget counted both the initial read and final recheck.
The actual graph therefore exceeded that budget despite every individual
record remaining within the native file bound. The installer correctly refused
installation. Once AU was terminal, only the remaining owned HKJC worker was
canceled, so the controller could retain the failed canonical receipt without
spending the rest of the pass on futile retries. Tennis and NBA's successful
outcomes were retained; NBA reported `reviewed_freeze_required`.

The collector now uses the existing `_MetadataPages` implementation already
used by complete native evidence graphs. Each record is read through a physical
single-record reader with the original 1 MiB file cap and half of the original
32 MiB read allocation reserved for the final recheck. The graph-wide 10,000
record limit remains unchanged. Cumulative I/O telemetry can span multiple
pages; no physical reader counter is reset. Every source file and directory is
still rechecked. No record is omitted to fit a flat budget.

Incident criteria, canonical source validation, parent closure, timestamps,
report schema and its 32 KiB output bound are unchanged. Metadata still grants
neither verified samples nor model-promotion authority. The 900-second domain
and 3,600-second pass budgets are unchanged.

Validation before release:

- Required quick checks pass.
- 48 focused incident, paging and metadata-reader tests pass.
- New regressions read 24-record AU/HKJC graphs whose initial read fits 32 MiB
  but whose full recheck crosses it. All 48 physical reads retain native page
  bounds; every source is revisited.
- Global record limits, equal-size/restored-mtime mutation, newly appended
  files, deleted unselected future records and symlinked parents remain guarded.
- A supervised diagnostic against the complete real AU graph succeeds:
  1,680 source files, 46,493,900 cumulative bytes read, zero incident findings,
  original 1 MiB file / 10,000 record caps. It ran under the real production,
  WARM-capacity and shared research-worker guards, taking 2.361 seconds.

Diagnostic receipt:
`/Users/imac/WongChoiData/WongChoiControl/recovery_reports/2026-10-21-au-paged-incident-scan.json`.
The failed installer and intentional sibling cancellation are separately
preserved in the same recovery-report directory.

No research safety latch is cleared. `research_guard.py` deliberately provides
no automatic unfreeze API; existing AU/NBA incident latches remain visible for
independent evidence review. A clean scan does not erase a historical latch.
This change restores the complete metadata scan and does not bypass those
guards. Full release gates and a successful real four-domain installer pass
remain required before declaring the scheduler installed.
