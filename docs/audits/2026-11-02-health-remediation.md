# Remaining health-check remediation — 2026-11-02

Base: `6f6092e3`. This follows the earlier health triage. No scoring code,
weights, model evaluation rules, prediction snapshots or run outcomes are edited.

## Dashboard size recovery

The 2026-10-31 failure was measured before the current meeting-level horse
packing and Tennis tracking packing. The inspected current production snapshot
is 3,979,500 bytes, four meetings, already in the current packed format.

The scheduler now losslessly re-encodes an oversized legacy snapshot using the
existing dashboard decoder/transport encoder **before** considering removal of
past AU meetings. Every current/future meeting, horse, score, price, analysis
field and tracking record is retained; the original input file is unchanged.
Repacking an already compact snapshot is idempotent. No sports feed is rebuilt
while repacking.

The 24 MiB buffer is a warning, distinct from the 25 MiB upload ceiling. With
no eligible past meetings, a 24.9 MiB file no longer marks an otherwise healthy
run failed solely for entering the warning margin. At or above 25 MiB, the
scheduler stops before validation/upload. The existing generator also enforces
its per-asset ceiling, including HTML and analysis bundles.

Validation before release: AU automation suite 483 passed; after adding the
explicit hard-limit deployment guard case, targeted tests 178 passed.
`./檢查.sh --quick` passed. The exact candidate's full gate and activation
outcome are recorded by the Central release manifest.

## AU contract baseline

Refreshed with the existing command/rules:

```
PYTHONDONTWRITEBYTECODE=1 python3 .agents/skills/shared_racing/scripts/data_contract.py \
  --platform au --calibrate --since 2026-09-18 --limit 2000
```

The rolling corpus now contains 2,000 races / 19,553 horses, 2026-09-19
Bowraville through 2026-11-02 Corowa. Engine fingerprint is `0a72a970f00b`.
The previous baseline remains recoverable in Git. Thresholds are unchanged;
explicitly disabled/sparse trial evidence remains visible as a warning. This
refresh is an operational field-health calibration, not a model performance
evaluation or a claim of prediction improvement.

## COLD second copy completed

The missing 86,016-byte NBA reflector recovery snapshot was uploaded to the
existing shared WongChoi-Archive folder, then downloaded in full and checked
with the repository's `artifact_digest` function against its WARM manifest:

- Artifact: `wc-artifact:2ad4a78e0bff222ab80ce88e`
- Verified digest: `9bad595328f6e7d02573dcb336e46e855ec33fc3e59261c0854c7c11ecaad565`
- Remote: https://drive.google.com/file/d/15-Eomt4mJztUmO44xohEdB7urjiVdoah/view
- Append-only proof: `wc-artifact-remote-mirror:5c581fc3597e3f46dc40e778`

Neither the original nor WARM copy was removed.

## Stale work preserved without release

Verified no processes referenced the three stale worktree paths. All dirty
paths and their SHA-256 hashes were captured before saving. Exactly those
files were committed, and their bytes were verified unchanged afterwards.
Each original worktree is now clean. Dedicated remote rescue branches hold
the WIP commits; these changes are **not evaluated, merged or activated**:

| Worktree | Files | Commit | Remote branch |
| --- | ---: | --- | --- |
| stage5-weekly-review-cadence | 4 | `2a7a5926` | `rescue/health-20261102-stage5-weekly-review-cadence` |
| claude-nba-injury-20261023 | 5 | `f869caf7` | `rescue/health-20261102-claude-nba-injury-20261023` |
| claude-nba-layerA-20261023 | 11 | `8361e77a` | `rescue/health-20261102-claude-nba-layerA-20261023` |

The scheduler's automatically updated tracked data and another active
session's new primary-checkout scratch file were not changed by this work.

## Storage and remaining external access

Deep verification of all 274 externally offloaded AU snapshot meetings passed.
Offload dry-run reports zero eligible local meetings, so rerunning it cannot
reclaim additional space. The internal disk initially had about 21 GiB free.

AU/HKJC Drive mirror backfill was retried with ordinary filesystem access;
macOS still denied both File Provider roots. No mirror files were overwritten.
The user has been asked to enable Codex's macOS filesystem access; backfill
and its verification remain dependent on that access. Connector-backed COLD
proof above is independent of the inaccessible local Drive mount.

The 30-day SLO retains its historical failures. Recent successful runs do not
justify altering old manifests or redefining failed/blocked slots as healthy.
NBA startup's recorded failure remains a 2026-10-28 event, not today's state.
