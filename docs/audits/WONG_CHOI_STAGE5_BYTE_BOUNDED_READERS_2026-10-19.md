# Stage 5 byte-bounded native readers — candidate

Base: `ffc9111118a08eab801f64ef5c3c3d11e92882eb`. Engineering-only change;
no scoring, ruler, holdout, model promotion, scheduler/installer, deployment
policy, ledger or data deletion change. Native acceptance remains unproven.

## Reproduced production boundary

The approved reader's first native review receipt is
`runs/central/2026-10-18/research-review/235811.249477Z-4b7d7ed68c85.json`
under the Central control root, SHA256
`426f692981b7ca3bd984e7f759e6bd8b4b2f895ecba856e46394156a42288e59`.
AU failed during complete metadata recheck; HKJC failed during blob reading.
Both retained cursor generation 0. Review bookkeeping success in Tennis/NBA
does not constitute a pilot or qualified samples.

AU metadata sizing observed 1,620 files/22,298,211 bytes; a double read exceeds
the native flat 32 MiB budget. HKJC's actual first page contains 67 whole
predictions/4,942 refs totaling 954,633,579 artifact bytes per visit, above the
native 512 MiB blob budget. Ref counts alone do not bound byte volume.

## Decision and trade-offs

Keep canonical inventory/page/proof schemas, whole-bundle integrity, complete
source coverage and every native flat-reader limit. Do not increase constants,
reset physical-reader counters, drop records or accept partial history.

Metadata uses explicit single-record pages with unchanged per-file limits.
Each physical read has half the native byte allowance, reserving the other
half for the final complete graph recheck. The outer graph retains the global
record cap, every digest and directory witness; cumulative bytes remain
telemetry, not a disguised counter reset. Existing flat index readers retain
their original aggregate budget. Snapshot and both all-history inventories use
this traversal; prediction-page metadata uses it as well.

Each prediction bundle uses its own native `_Blobs` reader, including all
direct/relocation attempts and its byte-for-byte recheck. One oversized bundle
still fails; it is never split to bypass the cap. Across bundles, conflicting
digests/sizes are rejected. Before returning a page, every unique source blob
is revisited with a bounded reader and rechecked, then all metadata is rechecked.
The outer deterministic page list and complete-source reconstruction remain
mandatory. These subpages grant no authority independently of the complete proof.

The cost is additional bounded readers/I/O, especially for bundle rechecks.
The existing supervisor's deadline, resource checks, production-lock/preemption
and create-only publication remain unchanged. Full runtime tests must still
prove the candidate fits them. No native runtime improvement is claimed from
small fixtures; no model-performance improvement is claimed at all.

## Evidence so far

- RED: `wc-run-z_6aanss`: seven failures; both native-domain large-metadata
  tests reproduce `evidence byte budget exceeded` during snapshot recheck.
  Earlier collection without `PYTHONPATH=.agents/skills` was an invocation
  error, not the RED evidence.
- First metadata iteration: 126 passed/three failed. Two failures were new
  tests expecting the wrong exception class; source-byte mutation correctly
  raised the existing snapshot `ValueError`. The concurrent-append hook needed
  to target the complete metadata traversal, not an inner physical page.
  Its directory-change rejection assertion is retained.
- Metadata-focused intermediate run: 129 passed, 60.30 s.
- Blob RED: `wc-run-n1zwoltt`: large-byte multi-bundle page fails, single
  oversized bundle rejection passes. Only fixture budgets are scaled.
- Latest combined focused run: `wc-run-z7ec7mtu`, 132 passed, 53.77 s. This
  includes native AU/HKJC full metadata, inventory, source mutation, directory
  mutation, page tampering, whole-bundle budget rejection, large byte volume
  and mutation after the last bundle but before final page proof.
- Quick gates passed on intermediate iterations. Whole-repository gates and
  clean immutable-SHA recheck are still required before formal activation.

## Remaining verification

Run final quick and full gates without loosening timeouts or excluding heavy
corpus/review tests. Use the existing exact-scope release controller, immutable
SHA/main checks and four-domain runtime verification. Only after verified
activation, append a fresh native review receipt through the existing wrapper;
preserve all old failures and never advance a cursor by hand. A later blocker
must be diagnosed, not hidden by these pagination changes.

Stage 5 Tasks 6–10, real pilots, reviewed power profiles, Central research
scheduler/Telegram/private Dashboard acceptance and exit health remain open.
