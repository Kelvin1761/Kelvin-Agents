# HKJC Historical Integrity Audit

| check | status | evidence |
|---|---|---|
| Duplicate races | PASS | Race keys are unique at race metadata level. |
| Duplicate runners | PASS | 0 duplicate date/meeting/race/horse-number keys after cleaning. |
| Incorrect race/result joins | LIMITATION | 3 non-contiguous/incomplete joins hard-excluded. |
| Horse identity | LIMITATION | 107 runner rows lack canonical horse_id; horse names missing: 0. |
| Jockey identity | LIMITATION | Canonical jockey IDs unavailable; name missing rows: 0. |
| Trainer identity | LIMITATION | Canonical trainer IDs unavailable; name missing rows: 14. |
| Renamed entities | NOT AUDITABLE | No effective-dated canonical entity registry is present. |
| Finish/date/venue/race number | PASS | One winner, unique contiguous finish positions, parseable dates, and authoritative meeting venue enforced. |
| Surface/course/distance/class | LIMITATION | AWT separated from venue; unknown distance rows 10; unknown class rows 32. |
| Going/rail | NOT AVAILABLE | No aligned point-in-time going or rail field exists in this archive. |
| Scratching/reserves | LIMITATION | Actual matched starters are used, but a complete timestamped scratch/reserve lifecycle table is absent. |
| Abandoned/DQ/dead heat/settlement | NOT AUDITABLE | No complete event-status/settlement ledger; affected or non-contiguous labels are excluded rather than inferred. |

## Invalid races excluded

| date | meeting_name | race_number | starters | winners | top3 | finish_max |
|---|---|---|---|---|---|---|
| 2026-06-03 | 2026-06-03_HappyValley | 9 | 10 | 1 | 3 | 12 |
| 2026-06-07 | 2026-06-07_ShaTin | 1 | 10 | 1 | 1 | 12 |
| 2026-06-07 | 2026-06-07_ShaTin | 8 | 12 | 1 | 3 | 14 |

Unresolved identity and event-lifecycle limitations are not silently imputed and are not used to claim production readiness.
