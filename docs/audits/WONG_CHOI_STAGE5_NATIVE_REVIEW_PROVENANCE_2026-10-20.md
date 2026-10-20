# Stage 5 native review: settlement artifact provenance

## Result

Reader release `ea95996493ed58187bf6f219f63a0c4c02ac14ab` is merged and
activated; this does not prove native research acceptance. The subsequent
record-only pass on production `a99710261120d10bf4b76e9c81bcd79916b214e8`
is terminal failed. No matching review/supervision process remained at inspection.
The old shell handle 64823 is unavailable; it must not be restarted blindly.

Authoritative receipt:
`/Users/imac/WongChoiData/WongChoiControl/runs/central/2026-10-19/research-review/101046.862278Z-d1f982ff898f.json`,
content hash `01cd6269d001bcd1695cd4b550d317f19227a033ca46f82b70a4f54d8b66a619`.
AU failed without advancing generation 0. HKJC was preempted by production,
also without advancement; Tennis/NBA deferred for production activity. No model
promotion or Telegram delivery authority was granted. These are not four
independent domain failures and not four successful pilot runs.

AU phase outcome:
`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/research-phases/au/racing-monitoring-corpus-i454lyai/phase-outcome.json`,
SHA256 `a15bab4f99e30dd192bceb4cc6e5127749da9e080523bdd33acc9600e8064aa5`.
The supervised child exited 1 after 47.329357834 seconds, with
`AU settlement artifact provenance mismatch` in
`research_au_settlement_source._inspect_au_settlement_records`.
Publication is `unconfirmed_reconcile_before_retry`; no complete receipt/sample
may be inferred from intermediate prediction pages.

## Isolated cause

A bounded read-only diagnostic of AU settlement metadata at the original
cutoff `2026-10-19T10:10:46.862278+00:00` found 273 records. Metadata source and
capture clocks match their settlement contracts. Reading their 436 referenced
artifacts consumed 3,299,729 bytes under a 32 MiB diagnostic cap and 1 MiB/file
cap. Ten references in ten settlements do not match their pinned artifact hash:

| Event | Settlement suffix | Artifact |
| --- | --- | --- |
| 2026-10-12 Tamworth Race 1-8 | `0975f99f9e7c5d67b82cf16a` | meeting reflector report |
| 2026-10-03 Randwick Race 1-10 | `1d55189956a222d280391744` | Race_Results_Reflector.md |
| 2026-10-10 Hamilton Race 1-8 | `1e908ad60d85af18eaa79451` | Race_Results_Reflector.md |
| 2026-10-02 Rockhampton Race 1-7 | `3073f86c51806da3ea8e66c1` | Race_Results_Reflector.md |
| 2026-10-06 Newcastle Race 1-7 | `768e86c21da80a2c84621939` | Race_Results_Reflector.md |
| 2026-10-02 Dubbo Race 1-8 | `9e642c1582c53503cf51ace4` | Race_Results_Reflector.md |
| 2026-09-27 Port Macquarie Race 1-8 | `b25b6ee72b38e2595e95da5d` | Race_Results_Reflector.md |
| 2026-10-11 Seymour Race 1-10 | `e531c3f8e8df45c81b26cebf` | meeting reflector report |
| 2026-10-03 Flemington Race 1-10 | `e557d2008d1ee79a68763188` | Race_Results_Reflector.md |
| 2026-09-26 Toowoomba Race 1-10 | `ee401c6afe26f47c1e4b2070` | Race_Results_Reflector.md |

For Tamworth, the October 12 record pins
`65fe5bdb6cfbb19baf7c3b81cfe4fe1c96485fbcd4dbfae4893d895868354bb7`;
the current report hashes to
`7939c975cb9a19365746496c8fb44776fedd05b860af26ff99d697c8260b9052`.
A second immutable settlement, `wc:au:settlement:85c1981101930f3c419599c3`,
created October 13, references the same report path and decision, but pins the
current hash. Therefore immutable records reference mutable source locations.
This proves content drift, not which user or process performed the rewrite.
The exact configured Drive mirror path for this report does not exist; no
exhaustive search of all backups or provider version history is claimed.

`domain_evidence.record_settlement_for_event` hashes the current supplied paths
and puts those same paths in immutable records. A new hash creates a new record
ID; it does not preserve the old source bytes. The AU scheduler supplies meeting
artifacts through `resolve_settlement_evidence`. The shared reflector writes its
default report path directly. Future capture needs durable immutable source
bytes, not weaker verification or selection of only the latest matching record.

## Decision and repair boundaries

The reader is correctly fail-closed. Do not skip ten records, retimestamp old
content, replace old hashes, select only matching settlements, or manually
advance cursors. Preserve all historical failures and both Tamworth records.

See `stage5-settlement-provenance-repair.md` for the staged repair plan.
Future production capture and any historical source restoration/mapping require
separate scope authorization: they are not covered by the narrow shared-research
auto-approval delegation. Source-only implementation has been requested from
Kelvin initially; the subsequent explicit source-only approval is recorded below.
No producer code, data, model, ruler, scheduler, ledger, retention policy or
promotion state was changed by the diagnosis itself.
Tasks 6–10 and Stage 5 exit remain incomplete.

## Source-only implementation checkpoint

Kelvin approved source-only implementation and testing, explicitly prohibiting
commit/push/activation and any old-evidence rewrite or deletion. The preceding
diagnostic documents were already preserved on non-main `ff99a992` before that
reply; no implementation has been committed or pushed.

Implementation is isolated on `codex-stage5-settlement-provenance-20261020`:
new `shared_wong_choi/immutable_settlement_artifacts.py` creates bounded,
content-addressed AU bundles on the caller-verified WARM filesystem. Canonical
filenames and the event basename are preserved. `au_research_evidence` guards
mount availability throughout capture; the AU scheduler passes only captured
artifact paths to the existing evidence append function. Other domains and
`domain_evidence` remain unchanged. The native AU reader requires no relaxation
or new acceptance flag; existing legacy mutation rejection remains tested.

Trade-off: content-addressed bundles add durable result/report copies (not full
corpus copies); external storage being unavailable now prevents new settlement
evidence append rather than falling back to HOT. This makes the storage dependency
explicit. A mutable mirror or latest-record selection was rejected because it
does not preserve earlier pinned bytes. Existing ten historical mismatches are
not repaired by future capture; restoration remains separately authorized work.

TDD evidence: initial helper collection failed because the module was absent;
the adapter rewrite test then failed because evidence still pointed at originals.
The final focused selection passed **204 tests in 9.42 seconds** under external
scratch `wc-run-ghqah1yw`: helper, native AU settlement reader, AU production
adapter, feature/settlement evidence and daily scheduler tests. It covers source
rewrites, idempotent reuse, corrupt-capture rejection, file/ancestor/root symlinks,
file/total bounds, partial copy failure, source mutation during publication,
storage loss before publication, unmounted WARM preventing evidence append,
native reader compatibility and rejection of a corrupted immutable result.
Quick gate passed in `wc-run-pnkbwef3`; AU/HKJC scoring goldens are unchanged.
AU neutral track/trial coverage and new trial-speed baseline remain warnings.
A missing old resolver import was caught by an earlier quick gate and repaired;
that earlier run is not a passing gate. Full gate is still required before any
claim of repository-wide verification. No model-quality improvement is claimed.

## Durability follow-up before full-gate completion

The first source-only full gate, session 88138 / `wc-run-axv3_uqa`, was explicitly
stopped at terminal 143 after an independent fixture-only diagnostic reproduced
missing fsync calls for the new `settlement-artifacts` and `au` directory entries
in their parents. The diagnostic RED is `wc-run-03zkop5l`; it did not modify the
frozen source. Before stopping, cwd and parentage were checked; only owned PIDs
34860, 34864, 34905, 35429, 35430 and 42121 were signalled. Another agent's test
and all production processes were left untouched. The interrupted gate is not
a complete pass, even though its earlier AU/HKJC/shared-racing suites passed.

Capture now fsyncs both new-directory parents as well as the event directory,
temporary bundle, copied files and final rename parent. Regression verifies
directory device/inode identities across rename, not literal temporary paths.
An initial version of that regression incorrectly compared final path strings
to paths observed before rename; its failure is retained in `wc-run-ru9ip8ok`
(205 pass, 1 fail), then corrected without removing any durability assertion.
Final focused run `wc-run-fswn9kx3` passed **206 tests in 6.55 seconds** (205 repo
cases plus the independent diagnostic); quick gate `wc-run-lvrstk84` passed.
These checks verify the fsync protocol, not a physical power-loss experiment.
Fresh full-repository verification on the corrected source remains required.

Read-only recovery discovery additionally inspected the canonical storage
catalog and Google Drive metadata. The sole registered AU settled-meeting
artifact covers 2026-07-15 Warwick Farm, not the ten affected meetings. Drive
folder `1IeAaSHvXMiWc2bASltsz-z5L94u4tELj` is the exact October 12 Tamworth
folder, but its listed children are pre-race inputs/snapshots; no result or
reflector report was returned. Exact target report-name searches, including one
without the trashed filter, found no target. Revision tools exist, but there is
no grounded report file ID to inspect. No file content was fetched, no bytes
were restored, and no exhaustive historical-backup absence is claimed.

## Corrected source: terminal full-gate verification

The fresh source-only full gate, session **43157**, is terminal **exit 0**.
Command: `PYTHONDONTWRITEBYTECODE=1 python3 .agents/scripts/wongchoi_external_run.py -- ./檢查.sh`
in this isolated worktree, external scratch `wc-run-d_sg3l8q`.
`run_tests.sh` and the final gate summary both confirm all 15 suites passed:

| Suite | Passed | Other outcomes |
| --- | ---: | --- |
| AU Wong Choi | 1250 | existing warning |
| AU daily auto | 398 | |
| AU racing | 26 | |
| HKJC Wong Choi | 208 | |
| HKJC daily auto | 110 | |
| HKJC extractor | 89 | |
| HKJC reflector | 60 | |
| Shared racing | 183 | |
| Shared Wong Choi | 1637 | 2885.15 seconds |
| Race compliance QA | 26 | |
| NBA Wong Choi | 187 | |
| Agent scripts | 102 | 2 expected failures |
| Dashboard Python | 191 | 2 skipped; 6 existing return-value warnings |
| Tennis Wong Choi | 709 | |
| Dashboard Node | 89 | 17 function + 72 template tests; zero failures |

Totals: **5176 Python passed, 2 expected failures, 2 skips; 89 Node passed**.
Scoring goldens and generated explanations matched. AU neutral track/trial
coverage and trial-speed calibration warnings were not hidden or changed.
No skipped case is treated as verified runtime/production acceptance.

All four original large monitoring fixture phases retain `succeeded`,
`receipt_verified`, zero return codes and unchanged 600-second per-phase limits:

| Domain / phase | Wall seconds | Outcome SHA256 |
| --- | ---: | --- |
| AU corpus | 549.876991167 | `721e76ca66ea56a641bca8c38d424deee290d2daf8d3142921e8a02aa1f55aa0` |
| AU review | 323.61675549999995 | `c61e80c6783f98a0f349065a97389a21646bea33502dac6351f023f19c34897a` |
| HKJC corpus | 566.4808523330003 | `35b82230408a0da4c1bd279e3697301c7fe10cb417a7da4314f1f0fc647d3b0b` |
| HKJC review | 314.68327691600007 | `8e25246639ea483a918bfe5c82f10572755198b94e3e16302a8b844b563ea62f` |

These live beneath the scratch `pytest-of-imac/pytest-8/` fixtures
`test_large_monitoring_corpus_a0` and `test_large_monitoring_corpus_a1`.
Each corpus still reports only **one fixture** sample and no promotion authority;
neither review confirms Telegram delivery. This is engineering evidence, not a
real pilot, power profile, profitability result or model-promotion approval.

Post-gate byte checks confirmed all seven source/test files unchanged from the
frozen input. Sorted canonical JSON path-to-SHA256 map digest:
`c810666412443e16ff3d2cb4ea73025d911f09771d8dc29dce132db003ec8684`.
Helper digest: `6521b7330ec9ae2486944d9cbf195d06551f6f8212bafdf79cc4199baf0fd804`;
helper-test digest: `b711c34fc00e8efe9e7a0355ad789803e6febbe301cc488c78d135457aa64667`.
The worktree HEAD remains `ff99a99295c37031e8e3cd466a5700ce6d5a1456`, containing
only the earlier diagnostic checkpoint, not the uncommitted implementation.
Seven source/test paths and these two audit/plan paths remain local and
uncommitted under Kelvin's explicit source-only restriction. No release
controller, commit, push, merge or activation was run for this implementation.

Next boundary: obtain exact-scope save/release authorization; any later release
must recheck fresh main, immutable scope, full gate and production rollback.
Historical restoration/mapping still requires separate approval, and the ten
old mismatches remain unresolved. Stage 5 Tasks 6–10 are not complete.

Exact local implementation scope awaiting a separate save/release decision:

```text
.agents/skills/shared_wong_choi/immutable_settlement_artifacts.py
.agents/skills/shared_wong_choi/tests/test_immutable_settlement_artifacts.py
.agents/skills/shared_wong_choi/tests/test_research_au_settlement_source.py
.agents/skills/au_racing/au_daily_auto/au_daily_schedule.py
.agents/skills/au_racing/au_daily_auto/au_research_evidence.py
.agents/skills/au_racing/au_daily_auto/tests/test_au_daily_schedule.py
.agents/skills/au_racing/au_daily_auto/tests/test_stage5_production_adapter.py
docs/audits/WONG_CHOI_STAGE5_NATIVE_REVIEW_PROVENANCE_2026-10-20.md
stage5-settlement-provenance-repair.md
```

## Read-only release-boundary recheck

Remote main remains `a99710261120d10bf4b76e9c81bcd79916b214e8`; the remote
source branch remains the earlier documentation-only `ff99a992` checkpoint.
Directly releasing this branch would union its committed history with the nine
local paths and unintentionally include a tenth path, `wong-choi-stage-5-plan.md`.
After explicit authorization, use a fresh-main release worktree containing only
the nine approved final files; do not silently broaden scope or reset this tree.
No release has been prepared or executed.

Production status at `2026-10-19T15:30:43.783026Z`: four domain runtime mappings
aligned; AU/HKJC model stages production, Tennis/NBA shadow. Latest runs were
AU partial, HKJC dormant, Tennis succeeded and NBA dormant. AU evening attempt 3
(`2026-10-19/evening/22%3A00/attempt-3.json`, SHA256
`3f110d33ad2986de7c2914e7e734c8a124b79735c82096a1eda714c9e6820b1f`)
reports seven Mt Isa races with missing Dashboard win/place odds and exit 75 /
`odds-degraded`. Settlement evidence and full-field result ingestion were `ok`.
This is not caused by the unactivated source patch, and no odds repair or fetch
was performed. D1 backup, local restore and WARM copy were verified; latest COLD
copy was not. Existing catalog has 14/21 verified COLD artifacts (7 backlog),
including provider-backed Drive proofs. HOT free 26.37 GiB, WARM free 817.69 GiB;
the central research-review label remains missing. No global all-green health
or Stage 5 completion is claimed. Source-only restriction still prohibits
commit/push/merge/activation without a new explicit decision.
