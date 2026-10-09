# EXP-20261008-07 — HKJC history alignment correctness (not a refit)

Follow-up: [identity reconciliation audit](../audits/hkjc-history-identity-followup-20261008.md).
The five previously failing tests are now fixed in the candidate. Racecard/brand
lookup resolves more historical profiles; the original 2,227 figure below is
superseded by that audit, not evidence of 2,227 genuinely missing histories.

- Date: 2026-10-08; platform: HKJC.
- Baseline: `60c951acd672a811515a2ff0e66112c53b919946`.
- Hypothesis: positional joins between formguide and profile history shift rows
  when one source includes a non-numeric placing. Correcting this is required
  independently of predictive performance.
- Prior records: EXP-20261007-03 full-history distance records;
  EXP-20261008-03 holistic shape robustness; `docs/audits/hkjc-hv-20261007-feedback.md`.
- Working checkout: `/private/tmp/wc-dashboard-all-scores-20261008`.
- Durable candidate diff: `patches/hkjc_history_alignment_candidate_20261008.patch`.
- Decision (2026-10-08): NEEDS MORE TESTING; not committed, pushed or activated.
- **Decision (2026-10-09, Claude takeover): CORRECTNESS PROMOTE under contract §7.**
  This did not pass the performance gate and is not a proven improvement. See the last section.

## Independent correctness changes

1. Join profile enrichment by horse-local race date, not row index. No fallback
   to a different date; duplicate dates abstain and are reported. Apply to recent
   and older tables, finish-time trends and reference-sectional class lookup.
2. Numeric zero cannot count as top three, recovery or a 4th/5th-place form score.
   Unknown/non-numeric placings are excluded from numeric finish summaries with
   an exclusion record. This is **not** an inferred last-place result. Recency
   in this candidate means last valid completed finish, not necessarily last
   physical start; DNF/withdrawal semantics still require source status review.
3. Preserve `placing_raw` on future profile extraction. Existing caches lost this
   information and cannot distinguish all withdrawals, DNF and missing values.
4. Reject undated/same-day/future rows from the numeric summary; add fixtures for
   cutoff, duplicate date, zero, named DNF and an offset historical table.
5. Read effective sample size for the target surface, not the first surface
   mentioned in the transport string. The numeric surface score is unchanged.

No weights, draw cap, opponent-strength formula or complete-strength overlay
were changed. No new scoring policy was promoted. Separate ablations/refit have
**not** been run: source/provenance checks must be cleared first.

## Replay

The offline harness regenerates baseline and candidate horse Facts from identical
cached formguide/profile inputs, then transfers only changed deterministic fields
to copies of the same supplied Logic artifacts. It verifies horse identity,
date-filters profiles and disables profile network enrichment and deployment.
Legacy LLM scaffold fields are not copied. Results never enter feature generation.

- Meeting: `2026-10-07_HappyValley`, 9 races / 108 runners.
- Input cache: meeting `.hkjc_cache/profile_cache.json` (pre-meeting cache).
- Baseline replay: `/tmp/hkjc-hv-feedback.j5VUdJ` (explicit canonical HK data root).
- Candidate first replay: `/tmp/hkjc-history-candidate-20261008`.
- Final replay (without legacy scaffold fields): `/tmp/hkjc-history-candidate-final-20261008`;
  9/9 races completed, identical scores/ranks to first replay.
- 7/108 runners have changed generated scoring inputs.
- 佳登: `0-6-7-3-1-8` → `6-7-3-1-8-2`; 140 → 175 days since valid finish;
  March 4 positions end 3, January 28 end 1, December 23 end 8 after date join.
- First replay changed ranks only in R7 (#1 10→11 / #6 11→10) and
  R8 (#4 4→3 / #1 3→4). R3 佳登 remains first, 卓越蒨鋒 remains third.
- For the user's R1–R8, Good=0, Gold=0, Capture@5=13/24 remain unchanged.
- This is a **retrospective correctness diagnostic**, not out-of-sample evidence:
  the user-matching Logic version is evening/post-start for earlier races.
- No dev/terminal fitting or bootstrap claim. No performance improvement proven.

## Historical corpus readiness

Read-only scan of 35 top-level meeting folders: 351 races / 4,408 runner records.
Only 851 records resolved by stored horse ID plus matching name to that meeting's
profile cache. A further 1,330 resolve through a unique name-only cache candidate
(not treated as proven identity). 2,227 remain unresolved even with that fallback.
Across matched histories there are 173 distinct horse/date non-finish records.
The old cache schema did not retain their raw placing status. These are counts
of archived records, not distinct current horses or proof of live extraction failure.

Therefore a full corrected historical paired corpus is **not yet ready**. Do not
silently drop unresolved rows and reuse the old holdout split; do not substitute
newly scraped current profiles and call them frozen pre-off evidence. Next work
must resolve identities from the archived racecard and establish the source/status
contract, then replay the same locked evaluation cohort.

## Tests and limitations

- Baseline `./檢查.sh --quick`: pass, but both corpus contracts skipped because
  isolated checkout lacks data-root configuration (not a data-health PASS).
- Correctness tests + Agent scripts tests: 60 passed, 2 existing expected failures.
- HKJC and AU golden: unchanged (120 sampled runners each); no snapshots overwritten.
- One old surface-normalization fixture had undated rows; supplied explicit
  historical dates so it still tests normalization without bypassing the cutoff.
- Five **pre-existing** standalone `test_hkjc_fact_source_alignment.py` tests fail
  on both HEAD and the candidate: standby identity, withdrawn runner filtering,
  missing-profile-ID alignment, empty CLI ID slot, and profile-only history adapter.
  The normal suite does not discover these five tests. They are not hidden or
  converted to expected failures by this candidate. New regression cases have a
  discovery wrapper in `.agents/scripts/tests/test_hkjc_history_date_join.py`.
- Final `./檢查.sh`: all discovered suites passed, exit 0. Corpus data contracts
  were skipped, not passed. The five separately run pre-existing tests above
  remain failures outside default discovery; therefore this is not release-ready.
- No recalibration/promotion: candidate is unaccepted, existing golden and data
  contract baselines retained. No Dashboard or production files touched.

## Leakage decision and next gates

**FLAG** for performance promotion: source identity and actual pre-off artifact
selection are unresolved across the historical cohort. The numerical-date fixes
have local correctness evidence, not complete PIT provenance.

The data-quality/leakage skills require pausing refit at this point. Next gates:
resolve archived identities and raw non-finish status; reconcile the five existing
source-alignment test failures; rerun correctness-only paired corpus; then conduct
separate contextual-draw, rider/trainer reliability and opponent-strength ablations
on the unchanged development split. Terminal remains untouched by selection.

## Reproduce

Apply the durable diff only to the stated clean baseline, not the user's dirty
root checkout. From the candidate checkout, choose a fresh output directory:

```sh
WONGCHOI_HK_DATA_ROOT='/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing' PYTHONDONTWRITEBYTECODE=1 python3 scratch/hkjc_history_alignment_replay.py '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing/2026-10-07_HappyValley' /tmp/hkjc-history-alignment-fresh-output
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q .agents/scripts/tests .agents/skills/hkjc_racing/hkjc_wong_choi_auto/tests/test_invalid_history_status.py
./檢查.sh --quick
./檢查.sh
```


## 2026-10-09 — Claude takeover: review fixes, corpus replay, §7 decision

Kelvin handed this line over after Codex stopped. Baseline `60c951ac` (= `origin/main`,
unchanged since the patch was cut). Applied `hkjc_history_identity_candidate_20261008.patch`
(superset of the alignment patch) and `hkjc_profile_recovery_validator_20261009.patch`
cleanly; the five standalone alignment tests listed above now pass and are discovered.

### Review fixes on top of the candidate

1. **One runner no longer aborts the race.** `require_reconciled_profiles()` raised, so
   a single replacement runner whose profile fetch failed killed that race's Facts and
   the publish gate then blocked the whole race. Replaced by
   `mark_unverified_reconciled_runners()`: the runner renders `HISTORY_UNVERIFIED`
   (never `(無往績記錄)`), the Logic builder keeps that tag (`is_debut=False`,
   stage label `歷史未核實`), and `racing_data_health` raises a per-horse
   `HISTORY_UNVERIFIED` **warning** (does not block deploy). Genuine identity
   conflicts in `_reconcile_racecard()` still fail the race closed; the pipeline
   already records that race as FAILED with stderr naming the horse.
2. **`--horse-ids` no longer maps by position.** Takes `num:ID` pairs; a positional
   list is accepted only with exactly one slot per declared runner, and an ID that
   contradicts the formguide brand is rejected. (No production caller passes it.)
3. **No silent future leakage without a race date.** `compute_stats()` and the season
   anchor used `datetime.now()`, and `filter_profile_as_of()` returned the unfiltered
   profile when `race_date` was empty. Both now raise. `main()` infers the date from a
   `YYYY-MM-DD_` meeting folder (the legacy LangGraph caller never passed
   `--race-date`) and otherwise exits 2.
4. **DNF ends a layoff; withdrawal does not.** `classify_finish_status()` uses the
   newly preserved `placing_raw`: finished / started_no_finish (PU, UR, FE, DNF,
   DISQ…) / withdrawn (WV, WX, TNP…) / unknown. 休後復出 counts from the last
   *start*; recent form counts only finishes. Old caches without raw status stay
   `unknown`: excluded and reported, not guessed.
5. **Dead heats.** The profile scraper parsed placing with `isdigit()`, so `"3 DH"`
   became 0, the same value as a withdrawal. Now uses the leading integer.

Tests: 6 new cases (plus wrappers for discovery), skeleton and data-health cases.
`./檢查.sh` exit 0, all suites pass, AU and HKJC golden unchanged.

### 10-07 Happy Valley replay (isolated from code drift)

Baseline = current main engine on the untouched root Logic; candidate = this fix.
(Comparing against the 21:05 root CSV instead mixes in later commits and moves
ranks in races where no input changed.) Reproduces Codex: 7/108 runners change
inputs. Only R7 (#1 10→11, #6 11→10) and R8 (#1 3→4, #4 4→3) move. R1–R8
capture@5 13/24 in both arms. **R3 佳登 stays first.** This fix does not address
most of the 10-07 feedback.

### Corpus replay: paired, frozen inputs

`scratch/hkjc_history_alignment_corpus.py <baseline_checkout> <out>`: 35 meetings,
2026-04-12 → 2026-10-07. Each meeting's own Logic + pre-meeting profile cache; the
candidate arm receives only Facts fields that the candidate generator produces
differently. Results are read only after both arms are scored.

| Item | Count |
|---|---:|
| Races compared | 333 |
| Runners | 4,408 |
| Runners with changed inputs | 236 |
| Abstained: profile identity not provable from the meeting cache | 1,108 |
| Abstained: formguide/Logic name mismatch | 6 |
| Races with any rank change | 33 |
| Races refused by the engine in **both** arms (`SCORE-004`, pre-existing) | 18 |
| Transferred fields containing a date on/after race day | 0 |

Abstained runners keep identical Logic in both arms. The 803 earlier-cache
recovery candidates were not used because `/tmp/hkjc-recovered-profiles-20261009`
and the manifest had been cleaned up. So this replay covers the fix where identity
is provable from each meeting's own cache, and nothing else.

Stage 4 v2 (`build_evaluation_input`, locked 15% terminal = 09-16 → 10-07):

| Metric | Dev Δ | Terminal Δ | Terminal CI |
|---|---:|---:|---|
| gold | 0.000 | 0.000 | [0, 0] |
| good_positional | 0.000 | 0.000 | [0, 0] |
| top3_capture_at5 | +0.0012 | 0.000 | [0, 0] |
| ndcg_at5 | +0.0012 | 0.000 | [0, 0] |
| competitive_recall_at5 | +0.0015 | 0.000 | [0, 0] |
| mean_top3_model_rank (lower better) | +0.0024 | 0.000 | [0, 0] |

Cohorts (HV 119 / ST 214 / field ≤10: 29 / ≥11: 304): Gold and Good identical in
every cohort; capture@5 equal or marginally higher. As a candidate the decision
engine returns **REJECT `ranking_evidence_too_weak`**, as expected for a change with
no performance claim.

### §7 decision

1. Error is independently provable: profile placing 0 counted as a top-3 finish;
   history joined by row offset so finish and running positions came from
   different races; scratched runners shifted profile IDs; surface sample regex
   read the wrong surface; DH parsed as 0. No performance number is needed.
2. Zero significant regression: primary deltas exactly 0 on dev and terminal; no
   cohort CI fully negative.
3. Leakage audit: date cutoffs fail closed (tests); no transferred field carries a
   race-day-or-later date; results enter only after scoring.
4. **This did not pass the performance gate and is not a proven improvement.**

Would we change it if the numbers had gone the other way? Yes: a 0 counted as a
place is wrong regardless of what it does to Gold.

### Still open

- 1,108 runners (25%) have no provable profile identity in their meeting's own cache.
  Rebuild the 803-candidate recovery manifest before using this corpus for refits.
- 18 archived races (11 meetings, including terminal-window 10-01) are refused by
  current main with `SCORE-004 ability formula mismatch` (~0.44 points). Every replay
  silently evaluates 333 rather than 351 races.
- Rankings were re-scored mid-meeting on 10-07 (snapshots 20:48 and 21:05 HKT, after
  R1–R4 had run), and the feedback judged the 21:05 version. Nothing prevents a race's
  ranking from being overwritten after it starts.
- Structural hypotheses from the feedback audit (draw prior, rider/trainer vs horse
  evidence, form-line opponent credit) remain untested; they need ≥400 races.

Reproduce (from the candidate checkout, baseline checkout at `60c951ac`):

```sh
WONGCHOI_HK_DATA_ROOT='/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing' PYTHONDONTWRITEBYTECODE=1 python3 scratch/hkjc_history_alignment_corpus.py <baseline_checkout> <fresh_output_dir>
```
