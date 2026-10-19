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

Each prediction bundle uses its own `_Blobs` reader with half the native byte
budget reserved for final source recheck, including all direct/relocation
attempts in the initial half. Default legacy readers remain unchanged. One oversized bundle
still fails; it is never split to bypass the cap. Across bundles, conflicting
digests/sizes are rejected. Before returning a page, every unique source blob
is reread once with a bounded native reader and compared with its pinned digest
and size, then all metadata is rechecked. For every bundle, these final unique
bytes cannot exceed its initial bytes, so the reserved half suffices. Source
growth or digest changes fail closed rather than expanding a page budget.
The outer deterministic page list and complete-source reconstruction remain
mandatory. These subpages grant no authority independently of the complete proof.

The cost is additional bounded readers and source traversal.
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

## First full-gate attempt: rejected on runtime

Final quick gate `wc-run-2a5y2xjn` passed. Exact-scope dry-run classified all
eight paths as code/full, with no installer, Dashboard deploy or manual reason;
remote main was still `ffc9111118a0`. Source checkpoint `0fe7e1a4` and complete
gate-input snapshot `0be74c832e80baee1ae9307fb5d1d8a1b21c7887` were pushed only
to private non-main branches. No formal candidate release was created.

Controller session `14598`, PID `38548`, ran the full gate with external scratch
`wc-run-g4dsr_ya`. Both inventory-only feature-corpus fixture phases succeeded
with verified receipts: AU 95.239624959 s, HKJC 120.8603745 s. These do not
establish monitoring/pilot acceptance.

The mandatory large AU monitoring-corpus fixture then **timed out** under the
unchanged 600-second limit. Its preserved outcome is:

```text
/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-g4dsr_ya/pytest-of-imac/pytest-8/test_large_monitoring_corpus_a0/warm/research-phases/au/racing-monitoring-corpus-l0u_6vq_/phase-outcome.json
SHA256 f9ed40e0b2120a16fb38f2378bacec038ea5645345b752bd419a0abdded08366
disposition/status/execution.state: timed_out
execution.wall_seconds: 598.052643334
execution.returncode: -15
publication: unconfirmed_reconcile_before_retry
result: null
```

All 13 intermediate monitoring pages existed, but **no acknowledged complete
receipt** was obtained. The test requires `ResearchDisposition.SUCCEEDED`, so
the full gate was conclusively red. Only the verified six-PID controller
subtree `[38548, 38570, 38606, 39089, 39090, 46341]` was stopped; session 14598
terminated 143. Production jobs and original failure evidence were not changed.
No gate success, full-suite totals, immutable approval, merge or activation is
claimed for this candidate. Do not resume or duplicate that terminated gate.

The next engineering iteration must reduce duplicate work without dropping
source rechecks or resetting/increasing native limits. Read-only inspection
identifies repeated outer/physical metadata path guards and both per-bundle
plus final per-blob double reads as hypotheses. First measure exact reader-call
counts with a regression test, then optimize while preserving complete final
source/directory/mutation checks. Re-run focused tests and the original full
gate; do not extend the deadline or relabel intermediate pages as success.

## Second iteration: measured duplicate work

The first full gate is terminal, not a live handle. A clean working tree at
checkpoint `111278423ecbc6da8798819b7dc07f988f585dee` was used to reproduce two
exact call-count failures before changing code (`wc-run-sl11kd91`, two failed):
metadata initial/final reads invoked the native path guard four times instead
of twice; four valid bundles sharing three source files made 30 blob reads
instead of 12 reference visits plus three final unique-source reads.

The next candidate removes only the outer duplicate metadata guard/checkpoint:
each physical `_Reader.read` still performs the original checkpoint, full
non-symlink path guard, no-follow open, type/size/byte limits and chunk checks.
Early graph-count/budget rejection still calls the supervisor checkpoint.
No source-path cache or check-frequency throttling is introduced.

Bundle initial reads now reserve half the unchanged native cap. One final
full-page digest/size reconstruction replaces the first iteration's redundant
per-bundle and extra per-file rechecks. No physical counter resets; failed
readers retain their cumulative byte counts. Default `_Blobs` callers retain
their original cap, including their existing recheck behavior. A mutation
after the last bundle but before final proof remains explicitly tested; the
fault injection targets that actual boundary, not a removed inner method call.

`wc-run-6xocj8eq`: 150 related metadata/snapshot/inventory/prediction/artifact
tests passed in 32.08 s. Quick gate `wc-run-5al2ov2c` passed with the existing AU
sparsity/new-field warnings unchanged. Exact call counts improved; timings from
different test selections are not a speed benchmark. The original AU/HKJC
large corpus plus real review-child tests with their unchanged 600-second
limits must still pass, followed by full release and immutable approval gates.
No native pilot acceptance or production performance improvement is claimed.

After explicit reservation/cumulative-counter coverage was added,
`wc-run-e_qzq8b2` passed all 151 selected tests in 49.82 s. Final quick gate
`wc-run-gx15cph5` also passed, with the same existing AU warnings. The next
checkpoint is still non-main WIP, not a release; the original parametrized
AU/HKJC large-corpus/review test will run unchanged before another full gate.

## Original large corpus and review-child regression: passed

At clean/pushed source commit `558e97145e6c3772dc14625e77cd6b7ee4b2949c`,
the following original test, including **both** existing domain parameters and
all existing assertions, terminated with exit 0: **2 passed in 1693.82 s**.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents/skills python3 .agents/scripts/wongchoi_external_run.py -- python3 -m pytest .agents/skills/shared_wong_choi/tests/test_research_racing_monitoring_page_runtime.py::test_large_monitoring_corpus_above_legacy_reference_limit_keeps_one_real_fixture_label -xq -p no:cacheprovider
```

`-x` stops at the first failure; it did not deselect a domain or change a
threshold. Each corpus and each real review child retained its original
600-second limit. All four phases returned `succeeded / receipt_verified`:

| Domain | Corpus seconds | Review-child seconds |
| --- | ---: | ---: |
| AU | 538.176406417 | 251.932969791 |
| HKJC | 537.957921959 | 274.019308834 |

This verifies the unchanged 1,300-prediction / above-legacy-reference-limit /
13-page fixture, one real fixture label per domain, no sample growth through
metadata cloning, original-source preservation and promotion prohibition.
The result is not a benchmark against a different harness, not native
production corpus acceptance, and not a model-performance or pilot claim.

All paths below share this retained external prefix:

```text
/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-oe86rh3v/pytest-of-imac/pytest-0/
```

- AU corpus: `test_large_monitoring_corpus_a0/warm/research-phases/au/racing-monitoring-corpus-uckjdt1n/`.
  Outcome SHA256 `f62ee755572b7f27cd10fd771e4e3ad753353bb6abc4026b782308605fd70e01`;
  completed SHA256 `4df3f63aff0d22bdf065e71734a50abb97404f4bdd6753a0ff8e413ca8118116`;
  content hash `a25105e06680894028b4ba58d0a1e0a83ddca12d8731759ee8d6ec1620d9fe4b`.
- AU review: same `a0/.../au/` parent, `review-noslurl4/`.
  Outcome SHA256 `b4ac1a8dc26f86421e1578480dc3289d5f074cf7fe8a7ccc08729f922afd3009`;
  completed SHA256 `813013504afba94dcb1118aa400de374a17e6f958223af6c7f53bcc9681a58dc`;
  content hash `de35645e73fccf355f9b071a19183cdf8e5a718c178508979e83be564c69bffe`.
- HKJC corpus: `test_large_monitoring_corpus_a1/warm/research-phases/hkjc/racing-monitoring-corpus-pkh1bvek/`.
  Outcome SHA256 `e70ac6cdf89ae96e755d823869ec01edd99c5701b6d82c4ad908625d7f5924d2`;
  completed SHA256 `a34edc3f5b774b9685688f044218e113a7b35bdd767556ae71b4b8e6889b9be8`;
  content hash `61a9c42d2d33b80d9c79779e0f5a0d0535049703ee84b48a31c3bab8c909a19f`.
- HKJC review: same `a1/.../hkjc/` parent, `review-11c150tb/`.
  Outcome SHA256 `9ebbb8638a548d7f2a72ea26095876ea0dd83a76e2f45be52a7b21c39b17e84d`;
  completed SHA256 `e3ee3bc3dd3f8657aaa9b6add0f58075e5afc89c62ab23f8852ccae72007f214`;
  content hash `b120ca3e27245e246fb8f7014712753557a4c0faac4dda94fd4bcd0de27ae13a`.

The first failed full-gate attempt and timeout above remain preserved. Its
terminated session `14598` must not be resumed. This successful targeted test
session `86079` is also terminal, not a live job to restart. Next run the
formal nine-path scoped release dry-run/full gate and clean immutable recheck;
there is still no release approval, merge, activation or native pilot result.
