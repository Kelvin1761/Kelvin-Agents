# AU publication failure — 2026-10-24

## Evidence and cause

Production SHA at incident: e7e1d28e. The overnight run and
`run-morning-20261024T091506.json` stopped before Cloudflare deployment.
The latter merged 15 local meetings, then blocked on Armidale's
`preparation_score` (within-race SD 0.00; baseline 1.2844).

Armidale's six Logic files contain 44 runners, all scoring 60 on preparation.
22 runners have no trials; the remaining 22 have parsed trial evidence.
Recounting `fg_trials` with the live top-40%-finish rule gives **zero** runners
with at least two qualifying trials, the preparation bonus trigger. Raw
Formguide trial rows retain finish positions and starter counts. This is
legitimate neutral evidence, not a lost field. The calibrated preparation
neutral rate is 0.6503. The neutral-rate gate already treats that as sparse,
but the spread gate incorrectly promoted it to a blocking dead field.

The healthcheck then truncated the control-result JSON to its final 400
characters, concealing the domain's structured errors. Gold Coast Poly is genuinely missing: its meeting ID 453966 and race IDs
3456686–3456693 differ from Gold Coast 453932. These must never be aliased
in healthchecks. Discovery cannot match `aquis_park_gold_coast_poly` to the
API's `Gold Coast Poly` because of the sponsor prefix.

## Changes

- Constant scores at the neutral point warn when the calibrated neutral rate
  exceeds the existing 20% normally-populated threshold. Normally populated
  fields, constant non-neutral scores, and unknown baseline rates still block.
- Failed healing reads `detail.source_payload.errors` before falling back to
  adapter errors/stderr. The notification retains the beginning of that error.
- Discovery strips the known Aquis Park sponsor prefix and requires an exact
  Gold Coast Poly surface match; it cannot fall back to the turf card.
- No scoring functions, weights, ranks, calibration data or evaluation
  verdict rules changed.

## Validation

- Targeted AU daily-auto suite plus sparse-contract tests: 423 passed.
- `./檢查.sh --quick`: passed.
- All 15 local 2026-10-24 meetings pass `data_contract.py --platform au
  --meeting <folder> --gate` after repair; Armidale retains sparse warnings.
- Full repository checks and controlled release are required before activation.

## Recovery and rollback

After controlled release activation, run the normal AU wrapper with a distinct
repair slot and `--skip-refresh --skip-review` to rebuild/publish existing
analyses under all normal contract/snapshot/deployment verification gates.
Do not bypass gates, rewrite model outputs or occupy the 10:00 scheduled slot.
Independently recheck public meeting presence after deployment. The release
manifest captures the previous production SHA for rollback.
