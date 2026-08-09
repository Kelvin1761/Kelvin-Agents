# AU Wong Choi — Head-to-Head Ordering Features Plan (2026-07-17)

> **Status 2026-07-17 — executed same day; hypothesis RETIRED with a clean
> negative result.** Phase 0 passed (賽績線 coverage 94.7%; H2H pairs in 38.9%
> of ordering-opportunity races). Phase 1 killed F3/F4 (no stable OOS delta)
> and F1 (pairwise direction accuracy 51.3% valid — coin flip); F2 (last-start
> margin quality) showed a real, stable retrodictive delta (+0.24/+0.23).
> Phase 2 walk-forward gate on F2(+F1): **FAIL** — positional Good +0.55pp,
> Miss +6, Top1 −1.93pp, 3/5 folds. Scripts: `scratch/au_ordering_phase0.py`,
> `au_ordering_phase1.py`, `au_ordering_phase2_gate.py`; evidence:
> `scratch/au_ordering_features_raw.json`. Conclusion: the current archive's
> information content cannot order the front of the field better than
> ability_score already does — engine build (tasks 3–6) correctly NOT started.

## Goal

Lift **positional Good**(頭兩揀齊入三甲) from 19.2% toward the 25%+ range by
attacking the measured ordering deficit: 40.1% of races already have ≥2
placegetters inside the model top-4 but not as picks 1+2. Every arithmetic
re-weighting of existing features has failed the OOS gate — the unlock is
**new pairwise information between shortlist horses**, which the current
per-horse matrix cannot express.

## Starting position (all measured on the refreshed post-adoption archive)

- Baseline: 710 races, positional Good 19.2%, any-2 Good 40.8%, Miss 85;
  OOS window 363R: gp 20.7%, Miss 43. AU ≈ HKJC parity on the canonical ruler.
- Ordering opportunity: 285 races (40.1%). Within top-4, placegetters win on
  class_weight/race_shape/jockey_trainer, lose on stability (−1.83) — but a
  matrix-delta rerank FAILS OOS (gp −1.10pp): no reliable ordering signal in
  the existing seven dimensions.
- Missed placing favourites (133 races) profile: trial +4.2 / jockey +3.4 vs
  consistency −11 / stability −9.9 — lightly-raced horses punished for missing
  history. Maiden trial-compensation also FAILED (−1.38pp gp): trial evidence
  needs a **comparative frame**, not a bonus.
- Dormant plumbing found: the engine already parses 賽績線 rows (rival names,
  finish positions, margins like `2 (-2.78L)`, 對手後續成績 franking) via
  `_formline_rows`, and the orchestrator already injects
  `race_context["field_horse_names"]` — **but the engine never consumes it**,
  and the `form_line` matrix dimension has live weight **0.0** (a clean,
  empty slot to promote into without disturbing any tuned dimension).

## Feature specifications (deterministic, from facts_section only — no odds)

- **F1 Head-to-head rematch score** (pairwise): for each horse, scan its
  賽績線 rows for rival names matched (via `normalize_horse_name`) against
  today's `field_horse_names`. Net H2H = Σ over matched encounters of
  sign(beat/lost) × recency decay × margin magnitude × class-context weight.
  Output both a per-horse net score and per-pair evidence for the verdict.
- **F2 Last-start beaten-margin quality**: latest formal run's margin
  normalized (winner = +cap; beaten margin decayed), adjusted by the run's
  franking (對手後續成績 — rivals winning next start upgrades the line).
- **F3 Sectional differential**: recent/best L400 from the record table vs the
  **shortlist median** (not the field median) — a comparative sectional edge.
- **F4 Formline strength score**: formalize the existing 綜合評估 level +
  franking counts (`_formline_followup_counts`) into a 0–100 score.

All four computed inside `RacingEngine` as derived scores persisted into
`python_auto.feature_scores` (so future cached replays keep them), with
explicit "no evidence → 60.0 default" semantics and per-feature coverage
counters logged per meeting.

## Integration candidates (test both, promote at most one)

- **Option A — revive `form_line`**: form_line = w1·F1 + w2·F2 + w3·F4
  (F3 stays in sectional territory). Grid-search the dimension weight upward
  from 0.0 (0.03–0.10) with the other six renormalized, expanding-date
  walk-forward only.
- **Option B — stage-2 ordering inside the shortlist**: keep stage-1 ability
  ranking; re-rank top-4/5 by ability + λ·(F1 + F3 pairwise edges). Unlike the
  failed rerank this uses genuinely new pairwise info; λ selected per fold on
  train only.

## Tasks

- [ ] **1. Phase-0 coverage audit.** Measure across the refreshed archive: %
  of horses with ≥1 賽績線 row; % of shortlist pairs with ≥1 H2H encounter;
  L400 row coverage; franking coverage — by era, going, class, field size.
  → **Verify:** a coverage table proving enough pairwise support in the
  ordering-opportunity cohort (target: H2H evidence in ≥25% of opportunity
  races; else descope F1 to a tiebreak-only role before building).
- [ ] **2. Retrodictive signal check (before any engine code).** Compute
  F1–F4 offline from stored facts_sections; test each feature's standalone
  ordering power within top-4s (does the placegetter side win on the
  feature?) with train/valid split. → **Verify:** at least one feature shows
  a stable positive OOS ordering delta; kill features that don't.
- [ ] **3. Engine implementation.** Add derived scores to `RacingEngine`
  (consuming the dormant `field_horse_names`), persist to feature_scores,
  coverage counters in meeting logs, unit tests with fixture facts_sections
  (incl. margin parsing `2 (-2.78L)`, rival-name normalization, dead-heat
  rows). → **Verify:** tests green; modern-meeting replay (Warwick 07-15)
  byte-identical except the new persisted scores.
- [ ] **4. Archive re-score in sandbox** (existing driver pattern,
  `scratch/au_full_rescore_driver.py`) to materialize F1–F4 archive-wide;
  rebuild a sandbox cache. → **Verify:** manifest + race count match the
  adopted archive exactly; no production files touched.
- [ ] **5. Walk-forward gate on Options A and B.** Expanding-date folds,
  params selected on train only. Gate: **positional Good ≥ +1.5pp OOS**,
  any-2 Good ≥ −0.5pp, Miss non-regression, Gold/Top1/W-in-T3 ≥ −0.5pp,
  Top3-precision fold stability ≥ 4/5. Cohort checks: ordering-opportunity
  races, missed-favourite slice, maiden slice, fields 12+.
  → **Verify:** full gate report per option; if both fail, document and stop
  (the negative result still retires the hypothesis cleanly).
- [ ] **6. Shadow + promote.** Winner runs shadow beside production for ≥5
  meetings / 40 races (dual verdict blocks in reports, no ranking change),
  then promote behind a versioned flag; dashboard shows the H2H evidence
  lines so 圍捕 radar picks are explainable. → **Verify:** live shadow KPIs
  non-regressive; rollback threshold defined before flip.

## Explicitly out of scope

- Odds/SP as model input (diagnostic only, as before).
- Racenet scraping — bottleneck is feature content; extraction risk budget
  stays reserved (site blocks aggressively per Kelvin).
- Any re-tuning of the seven existing dimension weights (exhausted; only the
  vacant form_line slot may gain weight via Option A).

## Risks

- **Pairwise sparsity**: H2H encounters may be rare outside NSW/VIC metro
  circuits → Phase-0 gate before any build.
- **Era variance**: 賽績線 blocks exist only in post-realignment facts (the
  adopted refresh maximized coverage; Phase-0 quantifies what remains).
- **Overfit**: pre-registered gates, per-fold train-only selection, one
  candidate promoted at most, shadow before flip — same regime that has now
  correctly killed 13 weak candidates in a row.

## Done when

- Ordering features are measured, built, and gated — with either a promoted
  candidate lifting positional Good ≥ +1.5pp OOS, or a documented negative
  result that retires the pairwise hypothesis and redirects effort (e.g.
  toward sectional-data accumulation).
