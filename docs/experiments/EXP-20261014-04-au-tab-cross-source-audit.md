# EXP-20261014-04 — AU TAB cross-source audit and field reconnaissance

- Date: 2026-10-14, Australia/Sydney.
- Status: small cross-source audit COMPLETE; API integration UNVERIFIED; no model candidate or performance claim.
- User authorized a small TAB results comparison and investigation of additional model information.
- Baseline commit: `0116c740330db7f02f9d04d2884e211b1d494517`; shared checkout is dirty with other ongoing work. No scoring, scheduler, canonical results or release files changed.
- Prior research checked: model evaluation contract; AU ML dataset/program; EXP-20261014-01 people recent form (four dev rejections); current Sportsbet parser and Eagle Farm formguide. Existing trial times, in-running positions, speed maps and apprentice claims must not be presented as new concepts.

## Method and evidence

Selected 2026-10-10 Rosehill, Caulfield and Eagle Farm, races 1–2 at each venue. Before comparison, local CSV contained complete position sets 1–11, 1–13, 1–10, 1–9, 1–7 and 1–8 respectively. Selection is a convenience sample of recent complete meetings, not a random nationwide validation sample.

The project's documented historical-results endpoint did not return a payload here: HTTP/2 stream error, HTTP/1.1 25-second timeout, and direct Chrome navigation reported `ERR_BLOCKED_BY_CLIENT`. The public TAB site **did** load historical meetings and individual races through its calendar. No credentials, third-party proxy, fingerprint rotation or repeated API polling used. This validates browser access, not API usability.

Read-only rendered DOM capture collected all entrant rows, scratching status, horse names, barriers, apprentice claims, and visible results. The browser results table exposes only first–fourth, although the entrant list is complete. Compact CSV is a transcription of captured DOM values, not a downloaded historical API payload. TAB's displayed runner number is preserved, but local CSV has no runner-number column; names are matched within date/venue/race. Explicit venue alias `ROSEHILL -> Rosehill Gardens`; horse matching trims, collapses spaces and uppercases only. Ambiguous keys are reported and excluded; there is no fuzzy matching or fabricated fifth-and-later finish.

Evidence: `evidence/tab-crosscheck-20261014/` contains TAB capture, local baseline sample, comparison JSON and provenance with URLs, SHA256 hashes, code SHA and dirty status. The two sources may share upstream racing data; independence is not established.

Reproduce offline from repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/tab_crosscheck.py \
  --date 2026-10-10 \
  --tab-sample docs/experiments/evidence/tab-crosscheck-20261014/tab_visible_sample.csv \
  --baseline docs/experiments/evidence/tab-crosscheck-20261014/sportsbet_baseline_sample.csv \
  --out scratch/tab-crosscheck-20261014/reproduced.json
```

## Results

| Meeting / race | Actual starters, both sources | Matched | Visible positions agreeing | Raw barrier differences |
|---|---:|---:|---:|---:|
| Rosehill 1 | 11 | 11 | 4/4 | 0 |
| Rosehill 2 | 13 | 13 | 4/4 | 0 |
| Caulfield 1 | 10 | 10 | 4/4 | 0 |
| Caulfield 2 | 9 | 9 | 4/4 | 0 |
| Eagle Farm 1 | 7 | 7 | 4/4 | 0 |
| Eagle Farm 2 | 8 | 8 | 4/4 | 2 |

- 72 entrants, 14 scratchings, **58 actual starters**. Both-direction starter matching **58/58 = 100%**.
- Missing starters: **0** both ways. Duplicate starter keys: **0** both sources. Ambiguous matches: **0**. Scratched entrants leaking into local results: **0**.
- Observed first-four positions: **24/24 agree**, zero disagreement. TAB visible finishing-position coverage is **24/58 = 41.38%**; remaining 34 positions are unobserved, not validated. Whole-field ordering agreement cannot be claimed.
- Raw barriers: **56/58 agree**. Eagle Farm R2 LITTLE BEGINNINGS is TAB 9/local 8; CHIEF IN CHARGE is TAB 8/local 7. Scratched METAPHORICALLY occupies raw barrier 7. Sorting the eight unique starter barriers and compressing to 1–8 removes both discrepancies. This matches the local results ingestion's documented densification. Keep raw draw and effective post-scratching gate distinct; no data was overwritten.
- **No missing local result rows were recovered in this sample.** TAB is promising for verification but demonstrated incremental result coverage here is zero.

## Additional pre-race information: verified reconnaissance

Observed live Eagle Farm R1, 2026-10-14, around the displayed 29-minute countdown before scheduled 14:58. Expanded Speed Map and Dragon Link form. This is one race/one detailed horse; it does not establish nationwide coverage or historical availability.

| Field | Evidence / novelty | Timing and decision |
|---|---|---|
| Speed Map categories | 9 active runners: 5 On Pace, 2 Mid Field, 2 First Start. Categories extractable from rendered colours and visible legend. Sportsbet already supplies `SpeedPos`. | Verified pre-race availability for this race. Best next **shadow comparison**, especially disagreement and missing Sportsbet map coverage; do not add two correlated map scores blindly. Archive snapshots now before future evaluation. |
| Class-specific horse record | Dragon Link TAB `2: 0 - 2`; local Sportsbet Class `-`. | A concrete coverage lead. Class definition and place counting need validation across horses, class changes and field sizes before scoring. |
| Detailed history `IN RUN` | Dragon Link 2026-02-07 `2-2-4`, versus Sportsbet 800m=2, 400m=4. | Potential additional early checkpoint. Checkpoint labels absent on the displayed TAB form; **FLAG**, cannot map the first value to settled/1200m without documentation. |
| Historical `TIME` | Dragon Link 2026-01-16 TAB 58.18s, local WinningTime 57.750s; beaten 2.5/2.52 lengths. | **FLAG**: likely individual elapsed time versus winner time, but this audit does not prove the definition. Candidate source for individual speed only after semantic validation. Never overwrite WinningTime. |
| Apprentice claim | Explicit `a(1.5)`, `a(2)`, `a(3)` in historical and live runner rows. | Useful source cross-check. Already studied locally; earlier dev experiment rejected scoring candidates. Availability does not demonstrate performance uplift. |
| Trial dates/times, spell, pedigree, career/going/distance records | Visible detailed form; largely already in Sportsbet. | Prior dates can be useful for gap filling, after identity and timing checks. Existing functionality, not a new model architecture. |
| TAB narrative trouble comments | Dragon Link comment mentions awkward start and covering ground. The same comment also evaluates odds-on defeats. | Possible trip-context lead; **FLAG** structured provenance and independent extraction required. Entire prose imports would introduce market proxies. Prefer original stewards evidence. |
| Sky Rating / expert tips | Numerical Sky Rating appears in live rows. | Public before this race, but methodology and market dependencies unverified. **Do not import into independent model** until resolved. |
| Exotic dividends / scratchings and deduction timestamps | Historical R1/R2 tables expose these. | Results/settlement QA only; final payouts and post-race status cannot enter current-race scores. No TAB pool payout is assumed to equal Sportsbet fixed payout. |

## A source-semantic warning already found

Dragon Link's 2026-02-07 GCST run is displayed by TAB as `Good`, while Sportsbet identifies **Aquis Park Gold Coast Poly / Synthetic**. TAB's own narrative calls it Gold Coast Poly. This is a concrete discrepancy, not evidence that one whole provider is superior. Race surface identity must be cross-checked before using going aggregates. `Good` cannot be converted automatically into Good turf. TAB venue abbreviations also need an explicit surface-aware mapping.

History is known before today's race, but fetching an old race's page today does **not** prove every aggregate/comment/rating was available before that old race. Keep source snapshots with capture time; use completed previous events only and validate publication time for historical aggregates. Final odds, current-race finishes, final going and dividends stay in evaluation/settlement tables.

## Decision and next experiments

1. Retain TAB as a small verification/shadow source; **do not replace Sportsbet** on this evidence. API access remains a separate blocker; the public browser is the verified path.
2. Most promising model blind spot to measure next: TAB categorical pace versus Sportsbet SpeedPos, with source coverage, disagreements, and race-shape effects. This requires forward pre-race snapshots or validated historical snapshots; six result races cannot evaluate its model contribution.
3. Screen class-record coverage and individual historical timing separately. First resolve class definition, timing semantics, surface identity and checkpoint labels. Keep hypotheses separate for attribution.
4. Only a later scored candidate goes through the unchanged Gold/Good dev/terminal gate, leakage audit, cohort checks and ablation. This audit has **not demonstrated a ranking or financial improvement**.

TAB official feature reference: https://help.tab.com.au/article/betting-on-racing-on-the-tab-app (Speed Map types). The source project's historical extraction reference: https://github.com/lukewilde1/horse-racing-llm/blob/main/data_ingest/extract-data.py.

Validation: offline comparison reproduced byte-for-byte; focused checks verified scratch denominators, duplicate exclusion, disagreement detection and unobserved positions; quick repository checks passed. Full `./檢查.sh` passed lint, both scoring goldens, model explanation freshness and both data contracts. All unit suites passed except HKJC daily auto, where 12 tests failed writing the protected default scheduler log (`PermissionError`). Its existing `WC_HKJC_SCHED_LOG_DIR` override allows an isolated writable test log; **same-runtime retry: 70 passed**, using `.venv/bin/python3 -m pytest .agents/skills/hkjc_racing/hkjc_daily_auto/tests -q -p no:cacheprovider`. No production code changed to accommodate the environment. Logs are in `scratch/tab-crosscheck-20261014/`. No commit/push/deployment performed.
