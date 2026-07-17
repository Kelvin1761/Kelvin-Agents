# AU Wong Choi Evidence Enrichment Review (2026-07-17)

> Follow-up to the 2026-07-17 canonical gap / cohort / Phase-5 reports. Those
> established that AU misses are **evidence problems, not weighting problems**.
> This review localizes the missing evidence and tests recovery paths.
> Research artifacts in `scratch/`; production changes are noted explicitly.

## 1. Schema drift: the archive mixes engine eras

Per-month default-60 rates in the cached 710-race archive (stored production scores):

| Month | form | trial | pace_figure | health |
|---|---:|---:|---:|---:|
| 2025-08 → 2026-03 | ~100% | 95–100% | 100% | 77–89% |
| 2026-04 | 86% | 82% | 100% | 80% |
| 2026-05 | 15% | 44% | 100% | 91% |
| 2026-06 | 6% | 38% | 100% | 46% |
| 2026-07 | 4% | 43% | 72% | 27% |

Roughly two-thirds of the archive was scored before the modern form/trial/
health/PF features existed. **The archive benchmark understates the current
engine**, and any calibration fit on the full archive mixes eras.

## 2. Root cause found and fixed: stale `facts_section` + Facts filename mismatch

- Old Logic files embed a pre-realignment `facts_section` blob that the modern
  parsers (賽績線 / 試閘 / L400) cannot read; `enrich_logic_from_facts` merged
  fill-if-missing, so the stale blob **permanently blinded** form/trial/health.
- `_facts_path_for_logic` only matched `Race_N_Facts.md` (underscores); archive
  Facts files are named `MM-DD Race N Facts.md` (spaces), so re-enrichment never
  ran on archive dirs at all.

**Both fixed in commit `f47f9e4`** (orchestrator glob + facts_section override,
with tests). Sandbox re-score recovery on stale meetings:

| Feature | stored default | rescored default |
|---|---:|---:|
| form_score | 100% | 1–6% |
| trial_score | 95–100% | 10–26% |
| health_score | 74–88% | 6–21% |

Modern meetings are unaffected (Warwick Farm 2026-07-15 replay byte-identical).
A full 87-meeting sandbox re-score + canonical old-vs-new benchmark is the
promotion experiment (results section below).

## 3. Maiden plates and small courses (requested audit)

710 races matched to Racecard headers (`scratch/au_racecard_headers.json`).
Canonical KPIs + per-feature default-60 rates:

| Cohort | Races | Avg field | Good-pos | W-in-T3 | form dflt | trial dflt | jockey dflt | trainer dflt | rating dflt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Maiden × metro** | 58 | 9.9 | **12.1%** | 43.1% | 77% | 72% | 22% | 30% | 48% |
| **Maiden × small** | 48 | 8.4 | **37.5%** | 60.4% | 55% | 44% | 78% | 80% | 100% |
| Benchmark × metro | 269 | 10.8 | 15.6% | 46.8% | 63% | 78% | 29% | 41% | 22% |
| Benchmark × small | 45 | 10.1 | 13.3% | 44.4% | 43% | 73% | 75% | 80% | 19% |
| Stakes/Listed | 101 | 11.5 | 15.8% | 53.5% | 71% | 77% | 12% | 21% | 13% |
| Class N *(n<30)* | 28 | 13.1 | 3.6% | 32.1% | 56% | 75% | 34% | **80%** | 22% |
| Open Handicap | 50 | 9.6 | 22.0% | 54.0% | 61% | 53% | 46% | 45% | 29% |

Findings:

1. **Metro maidens are a genuine weak cohort** (12.1% Good-pos) and are
   evidence-poor exactly where it matters for debutants: form 77% / trial 72%
   default. Much of that is the recoverable schema-drift gap (§2) — metro
   maidens are concentrated in the stale era.
2. **Small-course maidens are the model's best cohort** (37.5% Good-pos)
   despite 78–100% J/T and rating defaults — small fields (avg 8.4) dominate.
   J/T coverage gaps at small tracks are real but currently not costing labels.
3. `class_weight` leans 70% on `rating_score`, which is 48–100% default in
   maidens (unraced horses are unrated) — that dimension is near-dead weight
   in maidens. A maiden-specific class_weight fallback is a future candidate,
   test only after the facts-refresh rescore lands.
4. Class N races (big fields 13.1 + trainer 80% default) are the single worst
   slice but underpowered (n=28) — watch, don't tune.

## 4. Jockey/trainer empirical fill — tested, FAIL / HOLD

Leak-free as-of-date strike-rate ratings from `AU_Historical_Raw_Race_Results.csv`
(7,916 rows), filling only default-60 J/T scores (1,322 jockey + 1,104 trainer
OOS fills): good any-2 **−0.83pp**, fold stability 2/5 → **FAIL / HOLD**
(`scratch/au_jt_empirical_fill_test.py`). The curated ratings stay. Revisit when
the results database is several times larger.

## 5. Full-archive facts-refresh re-score benchmark — **GATE: PASS**

85 meetings re-scored in a sandbox through the current engine with the §2
fixes (Drive archives untouched; scripts: `scratch/au_full_rescore_driver.py`,
`scratch/au_rescore_benchmark.py`). All 710 races matched 1:1 to stored
production scores. No result leakage: Facts files are pre-race documents and
the engine is deterministic — this measures what the live engine would have
scored with its own evidence pipeline actually working.

| Sample | KPI | stored prod | facts-refresh rescore | Δ |
|---|---|---:|---:|---:|
| OOS 363R | Good any-2 | 37.2% | 41.0% | **+3.86pp** |
| OOS 363R | Good positional | 17.1% | 20.7% | **+3.58pp** |
| OOS 363R | Miss | 65 | 43 | **−22** |
| OOS 363R | Top3 precision | 41.7% | 45.1% | +3.40pp |
| OOS 363R | Winner in Top3 | 47.1% | 52.9% | +5.79pp |
| OOS 363R | Top1 win | 17.6% | 22.6% | +5.0pp |
| Full 710R | Good positional | 17.6% | 19.2% | +1.55pp |

Fold stability 4/5. The weak cohorts gain most: Heavy good-any2 +6.03pp /
miss −11; Soft winner-in-Top3 +7.92pp; field 12+ good-positional +3.20pp /
miss −10. Good/Firm is ~flat (+0.94pp, miss +3) — the recovered evidence
matters precisely where the model was blind.

**The rescored AU positional Good (20.7% OOS) essentially closes the measured
gap to HKJC (21.0%).**

### Production actions

1. The code fixes are already live (commit `f47f9e4`) — new meetings are
   unaffected (byte-identical replay) because their Logic carries modern
   facts_sections.
2. The **stored archive scores and the ML cache are stale** relative to the
   live engine. Until the archive is refreshed, every archive benchmark and
   calibration underestimates the engine and mixes eras. Recommended (needs
   approval, it rewrites archived `python_auto` blocks): supervised re-run of
   the sandbox driver against the Drive archive, or adopt the sandbox output
   as the canonical benchmark dataset.
3. Future weight calibrations must run on refreshed scores — the Phase-5
   candidate FAILs above were measured on stale evidence and should be
   re-tested after adoption.
