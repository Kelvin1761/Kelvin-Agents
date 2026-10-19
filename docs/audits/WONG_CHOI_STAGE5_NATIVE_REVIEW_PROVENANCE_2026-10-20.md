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
Kelvin; no answer has arrived. No producer code, data, model, ruler, scheduler,
ledger, retention policy or promotion state was changed by this diagnosis.
Tasks 6–10 and Stage 5 exit remain incomplete.
