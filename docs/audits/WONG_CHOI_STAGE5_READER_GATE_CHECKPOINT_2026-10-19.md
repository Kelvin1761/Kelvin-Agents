# Stage 5 reader release checkpoint — 2026-10-19

## Proven milestone, not completed activation

The first complete `./檢查.sh` gate on the aligned reader tree returned exit
0. The existing scoped release controller committed and pushed
`ffc9111118a08eab801f64ef5c3c3d11e92882eb` and created immutable release
`wc-release:ffc9111118a0:2026-10-18T230330.439459_0000`.

Manifest:
`/Users/imac/WongChoiData/WongChoiControl/releases/wc-release%3Affc9111118a0%3A2026-10-18T230330.439459_0000.json`.

The controller then started its unchanged clean-checkout full-gate approval
recheck. At this checkpoint it is still running; approval, merge, activation
and four-domain post-activation verification are **not** claimed complete.
The controller stores the first gate exit code, not its full stdout in this
manifest, so no new exact pytest/Node pass totals are invented here.

## Scope and immutable-state observations

- Branch: `codex-stage5-reader-release-20261018`.
- Scope remains exactly 36 reader research-library/test/audit/plan paths;
  selected dirty scope was only `wong-choi-stage-5-plan.md`.
- Risk `code`, check `full`, `check_exit_code: 0`.
- Rollback target and observed remote main:
  `660b0952d952cf57ca9e35f55dd8a96f005a4c9e`.
- Observed remote branch equals the manifest's full commit.
- Prior reader `92004edd5bbae6d240477cc95f40bda5d2417c03` is now
  `superseded`, unapproved and unactivated; its failed recheck remains
  historical evidence. The Stage-5-named pending inventory contains the new
  release only. No unrelated pending release was approved.
- Activation plan: sync AU, HKJC, NBA and Tennis; installers empty;
  Dashboard deploy false; manual-required false and manual reasons empty.
- No ruler, model/scoring/feature-calculation/weight/domain-engine,
  release-policy, scheduler/installer, Dashboard, credential, data-retention,
  external-ledger, bankroll or model-promotion delta was added.
- The separate Tennis diagnostic WIP `8663249c` and cadence WIP
  `244ac67a` are not included or authorized by this reader manifest.

All 35 original reader files other than the updated plan have identical Git
blobs to the original reader payload `92004edd5bba`. The plan matches the
saved remote checkpoint `ae620cd9bdf1f9e0648de9fda30ad970d76d86b1`,
SHA256 `efaa05b5153fd04be5d377b7e7a856586be507f9b4b0cfb57924c4a6326e95cb`.
That saved checkpoint and the committed candidate have the identical complete
Git tree `e58c055e243fba1e68592204a28755045f19e104`.

The approved upstream executor fix is already in rollback target main;
it is not part of this reader release delta. No old-base or interrupted gate
has been substituted for the fresh successful gate.

## Large-case engineering evidence

The original unchanged AU/HKJC large-case tests retain 1,300 prediction
records, more than 5,000 artifact references, 13 monitoring pages and one real
**fixture** settlement label. The actual review children replay the pages;
they are not replaced by a report-only stub. All four corpus/review phases
below report `succeeded / receipt_verified`, under their separate unchanged
600-second limits. Their durations are approximately AU corpus 503.57s,
AU review 234.02s, HKJC corpus 486.41s and HKJC review 269.11s.

These receipts are synthetic engineering-test evidence, not live-domain
samples, a pilot, power applicability or model-performance improvement.
Metadata clones do not create new labels; no sample-growth or promotion
authority is inferred. The extra feature-corpus inventory receipt below
likewise grants neither normalized-source nor sample authority.

The transient test artifacts were read without modifying them. Recorded
receipt byte hashes preserve the observation if normal pytest scratch cleanup
later removes those fixtures. Full controller recheck and current-state
approval checks are still required.

```json
[
  {
    "gateScratch": "wc-run-jdj3ye9p",
    "phasePath": "test_supervised_feature_corpus2/warm/research-phases/au/racing-feature-corpus-fwp9me6n",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 66.239612583,
    "phaseOutcomeSha256": "8191a9eadb417416e8d4b63f19af7f59aab5ab51538835f8ccfbc8f88475be9a",
    "completedSha256": "b60d3640a2cde6896004a0cff87134d9190c3d7566c61c3185ee872b18499184",
    "content_hash": "daed0fde0e1a30557d5b8f55b01aa828cf21821202d4166d9d67d5b2ef5d8137",
    "model_promotion_allowed": false,
    "verified_monitoring_samples": null
  },
  {
    "gateScratch": "wc-run-jdj3ye9p",
    "phasePath": "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jdj3ye9p/pytest-of-imac/pytest-8/test_large_monitoring_corpus_a0/warm/research-phases/au/racing-monitoring-corpus-ak8btada",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 503.573415542,
    "phaseOutcomeSha256": "4943ac4b290480c8fd2d7460c9fdda6977e75427601794a1f1f6585f172865fa",
    "completedSha256": "30bee36f81910c41a8e63209da2951c324f7ef9e20007f41e3e4150ef55728c4",
    "content_hash": "898f9a315936af81ff6c0ed55f295c7fccbf504948b3b76f8eedb839a61e1dd1",
    "model_promotion_allowed": false,
    "verified_monitoring_samples": 1
  },
  {
    "gateScratch": "wc-run-jdj3ye9p",
    "phasePath": "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jdj3ye9p/pytest-of-imac/pytest-8/test_large_monitoring_corpus_a0/warm/research-phases/au/review-9t3vuja2",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 234.02406070899997,
    "phaseOutcomeSha256": "6e0a8debd0e4de6365db2688f6ae07104876648e117f34f63d8ef03f4fa7131f",
    "completedSha256": "e80e2138aabfe7ee5352db74adfdfbc263438022a47a226e1a28049ed9a2b8c9",
    "content_hash": "34e3dbb17e7fd6584b10783ca7fff098f0f43c4a507938a98d79ac0953d5529a",
    "model_promotion_allowed": false,
    "verified_monitoring_samples": null
  },
  {
    "gateScratch": "wc-run-jdj3ye9p",
    "phasePath": "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jdj3ye9p/pytest-of-imac/pytest-8/test_large_monitoring_corpus_a1/warm/research-phases/hkjc/racing-monitoring-corpus-xzfvm3s2",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 486.40570649999995,
    "phaseOutcomeSha256": "0132da09a74ba3614358df630e10936b267a621822414b2869876be965bbfe0b",
    "completedSha256": "db6a20994bd5a1e63db58d137e01d3eb56100339dc3c831e2d1d8ddba9a30836",
    "content_hash": "a01d4ca8ee8fafe9785de75aeda2a6214a148731819e21c94c3dab040ea363a8",
    "model_promotion_allowed": false,
    "verified_monitoring_samples": 1
  },
  {
    "gateScratch": "wc-run-jdj3ye9p",
    "phasePath": "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/command-runs/wc-run-jdj3ye9p/pytest-of-imac/pytest-8/test_large_monitoring_corpus_a1/warm/research-phases/hkjc/review-lcz36rxk",
    "disposition": "succeeded",
    "publication": "receipt_verified",
    "wall_seconds": 269.1088385830003,
    "phaseOutcomeSha256": "12d64739ecd0bfc4c95f7409d50dcf01695eacfb4ce97e5957b17fe31e9c638e",
    "completedSha256": "18367a341f5eb9fa966252cced38babcec46af7df1e45e5f7947a3cc0d02ae93",
    "content_hash": "9990f9bdaa91596f085ab7cdd09730dc551f28ec01c83e4121c7cadf0a2259b8",
    "model_promotion_allowed": false,
    "verified_monitoring_samples": null
  }
]
```

## Next safe action

Continue the existing controller exec session `15756` / controller PID
`6888`; do not start a duplicate approval. After its terminal result, inspect
append-only release events, recheck remote branch/main and verify all configured
production domains. Any changed or absent delegation condition remains blocking;
do not bypass, broaden scope or approve another release to force completion.

Tasks 6–10, reviewed power profiles, real Tennis/racing pilots, research
scheduler/Telegram/private-Dashboard acceptance and Stage 5 exit remain open.

## Task 7 read-only production preflight

While the clean-checkout gate continued, the approved production wrapper was
invoked with **only** `--status --receipt` (no initialize, review pass, scheduler
installation, notification or model action). The selected receipt was the
newest one in the inspected Central research-review receipt inventory:

```text
/Users/imac/WongChoiData/WongChoiControl/runs/central/2026-10-15/research-review/144755.927250Z-a713bdb7fff3.json
```

Its byte SHA256 is
`1b0e833c7db0a4067e163109afb6a96ea9e073daac819d345d9f226d35f37632`;
the existing status verifier accepted its content hash
`3597e6ca2e1d724302b62f0946995e44a6928793c13a4a40c1a2434fc1fe145c`.
All four existing cursor structures/configurations verified, but overall status
was correctly **blocked**: the receipt is `partial`, over its 36-hour freshness
limit (289,443.64 seconds at inspection). That historical receipt reports AU
and HKJC failed without advancing (generation 0), Tennis succeeded with
`reviews_recorded` and NBA succeeded with `reviewed_freeze_required`
(generation 2 each). These are receipt observations, not a new claim about
current cursor generations or completed production acceptance. Promotion and
Telegram-delivery flags remain false.

Reading the original production phase outcomes, separately from current pytest
scratch, confirms both race failures end in
`ValueError: prediction artifact reference limit exceeded`:

- AU: `research-phases/au/racing-monitoring-samples-zkc13unv/phase-outcome.json`,
  SHA256 `22906014e5c3635d3accc4c4ef51a513edf85fc7dbe0be0ffa4f3665c92ed730`.
- HKJC: `research-phases/hkjc/racing-monitoring-samples-_hbs2oam/phase-outcome.json`,
  SHA256 `43eac9cdac44a554df55dcd44381a8febf0e29a1d479f0e3228901388405a0b0`.

Both paths are relative to
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/`. Matching failures also exist for
the earlier 2026-10-09 pass. No historical receipt or cursor was repaired,
deleted or reclassified as success.

The candidate `research_review_cursor.py` routes AU/HKJC through
`RacingMonitoringCorpusInspectionRunner`. This establishes that the pending
reader addresses the observed old capacity boundary; it does **not** establish
that the real production corpus is accepted or that no later blocker exists.
After successful immutable activation, the next relevant acceptance is a fresh
controlled review using the existing production-lock/resource/preemption
guards. Production work must defer research. Preserve all original history,
append new evidence and inspect the new receipt; never advance cursors by hand,
shrink the corpus or install a scheduler to hide a failing first pass.

## Terminal release result and first native acceptance

Controller session `15756` terminated with exit 0. Both full gates passed;
`ffc9111118a08eab801f64ef5c3c3d11e92882eb` was approved, fast-forwarded into
remote main and activated through the existing controller. Remote main and the
immutable release branch were independently verified at that SHA. The original
manifest remains immutable; approval, merge and activation are append-only
events at 2026-10-18T23:57:26Z, 23:57:28Z and 23:57:34Z respectively.
The controller reports one successful Telegram delivery. No installer or
Dashboard deploy ran. A subsequent configured-root status check verified all
four domains aligned, their installed labels loaded and their runtime SHA equal
to the release. Central research-review launchd remains missing; durability is
loaded/aligned. AU/Tennis latest runs succeeded, HKJC/NBA dormant; AU/HKJC
registry stages remain production and Tennis/NBA shadow.

A fresh existing-wrapper manual pass then ran from the approved production
checkout with all four production locks and external scratch
`wc-run-66xwupsw`. No cursor initialization, scheduler installation, ledger
action, notification or promotion was performed. Its terminal result is
**partial**, not Stage 5 acceptance:

```text
/Users/imac/WongChoiData/WongChoiControl/runs/central/2026-10-18/research-review/235811.249477Z-4b7d7ed68c85.json
byte SHA256: 426f692981b7ca3bd984e7f759e6bd8b4b2f895ecba856e46394156a42288e59
content_hash: 512dc468770ebe53ccedcd3c426e798ffee2e46b450f2bdeed5aa357e58bf024
```

AU/HKJC failed, did not advance and remain generation 0. Tennis recorded
reviews and NBA recorded `reviewed_freeze_required`; both advanced to generation
3. These are review bookkeeping outcomes, not qualified experiment samples or
model improvement. All promotion/delivery-authority flags remain false.

New preserved native phase failures, relative to WARM:

- `research-phases/au/racing-monitoring-corpus-g1loaiwo/phase-outcome.json`:
  SHA256 `e80d05c88ad49a75826f4961d36c11570c58925f117eedeaac1761cb5135376a`;
  `_NativeEvidenceSnapshot.__init__` -> `_Reader.recheck` fails with
  `ResearchIndexError: evidence byte budget exceeded`.
- `research-phases/hkjc/racing-monitoring-corpus-pf_wmyaf/phase-outcome.json`:
  SHA256 `c46172f0fa964bdc18c636d4be6da97dca0f1364c32879ed1a597328bc9fb38a`;
  prediction page inspection -> `_Blobs.read` fails with
  `ValueError: prediction artifact read budget exceeded`.

Read-only sizing isolates the remaining design boundary. At inspection, the
canonical AU filename set contained 1,620 files totaling 22,298,211 bytes;
two full reads would cost 44,596,422 bytes against the existing 33,554,432-byte
reader budget. The stack fails during the second read. No byte budget was reset
or enlarged. HKJC's persisted inventory contains 145 predictions. Reconstructing
the deterministic **first actual page** using both current limits (100 records,
5,000 refs) gives 67 predictions/4,942 refs, whose existing artifacts total
954,633,579 bytes per visit, already above the 536,870,912-byte blob budget.
This was metadata/stat sizing only, not blob verification. An earlier sizing
of the first 100 records was not the actual planned page and is not used as the
failure evidence.

Thus ref-count pagination is insufficient for this native corpus. The next
engineering candidate needs bounded byte-aware source traversal and artifact
pages, with deterministic complete inventory coverage, unchanged source-byte
and directory rechecks, atomic publication, mid-read mutation rejection,
production preemption and unchanged supervisor limits. Test both metadata
recheck volume and blob bytes before another formal release/native replay.
Do not fix this by resetting counters, silently increasing limits, skipping
records, accepting partial coverage or treating the passing synthetic large-ref
fixture as evidence that large-byte native history was accepted. No corrective
source change has yet been implemented or released.

At post-activation inspection HOT had about 24.6 GiB free and WARM about
818.5 GiB; external volume was mounted. D1 backup/restore/WARM proof remained
OK, but COLD backlog and the HOT warning remain. Tasks 6–10 stay open.
