# AU progressive publication — engineering verification

Baseline: `27397c6d8fbe216a42013dc6feaf776e54df9681`.
Scope: publication scheduling, isolation and concurrency. Scoring, weights and prediction methodology are unchanged.

The evening scheduler admits each complete meeting after immutable prediction evidence registration. A separate process publishes while analysis continues. Arrivals during a deployment coalesce; later batches include earlier admitted meetings to protect against a stale CDN base. Morning remains one batch.

The shared publication lock covers live read, merge, deploy and verification for AU, HKJC and post-success hooks. Direct dashboard deployments acquire it before touching the shared build directory. Invalid meeting inputs are quarantined with named errors; a previously live version is preserved and is not reported as refreshed. Failed deployment receipts or missing jobs cannot authorize an all-live summary. Existing field, structure, shrink and public freshness gates remain enforced.

## Reproduce the offline check

Use a saved public dashboard snapshot and local immutable prediction snapshots. This command makes no Sportsbet requests, scoring runs or Cloudflare uploads:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  .agents/skills/au_racing/au_daily_auto/benchmark_progressive_publication.py \
  --data-root '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing' \
  --base-snapshot /private/tmp/au-final-public.json --day 2026-10-24 \
  --output docs/audits/2026-10-24-au-progressive-benchmark.json
```

The adjacent JSON records source hashes, input hash, real copy/build duration, retained files and final meeting keys. The benchmark uses the current real snapshot builder with frozen inputs, then checks those inputs are unchanged. Queue behavior is tested separately with explicitly simulated analysis and upload delays. Simulated deployment count is not a forecast of tonight's Cloudflare cost.

## Cost and limits

The final offline run copied 146,416,516 bytes for 16 meetings in 0.4509 seconds and built/validated the full snapshot in 58.6966 seconds. It preserved the HKJC meeting and all 16 AU meetings, with one final JSON/HTML pair and unchanged frozen input digests. The declared 2-second upload / 0.15-second analysis simulation coalesced 16 arrivals into three publishes; this count is illustrative only. There are no additional odds requests or scoring runs. Additional cumulative snapshot builds and Cloudflare uploads consume CPU/network work in the background. Earlier production deployments took 224 and 307 seconds, so total network work must not be called negligible without an actual progressive run.

The first live evening run remains the operational confirmation. Inspect `progressive_publication` in its scheduler log: first-live delay, deployment count, foreground queue/drain time, publication time, published jobs and pending/rejected lists. A small copy cost does not establish a small total upload cost.

Each staged meeting is bounded to 64 MiB and each run's queue to 512 MiB. Only top-level publication files are copied. Intermediate full dashboard copies are deleted as merges advance, and each worker build directory is removed after its batch. Frozen queue inputs and JSON receipts remain available for diagnosis.

Rollback: set `WC_AU_PROGRESSIVE_PUBLISH=0` in the scheduler environment to restore evening batch publication with meeting isolation. The prior approved commit is the code rollback baseline. Do not set the internal inherited publication-lock marker.

## Verification

572 targeted tests passed, including real subprocess locking, coalescing, failed-upload retry on later arrivals, partial rejection, immutable evidence/digest checks, final-queue barrier race, parent receipt completeness, process-group cancellation, orphan prevention, morning single batch and evening rollback selection. Full repository checks and exact-scope release are required before activation.
