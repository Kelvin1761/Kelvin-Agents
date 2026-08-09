# AU Wong Choi — Round 5: ML Retest / Pace-Role / Results Backfill (2026-07-17)

> Directions genuinely untried before this round, all on the refreshed
> (post-adoption) archive. Canonical metrics, expanding-date walk-forward,
> pre-registered gate throughout.

## 1. ML retest on refreshed features — FAIL (both variants)

All prior ML work (2026-06-06 cached walk-forward, ML weight/residual gates)
predates the evidence refresh, when form/trial/health were ~100% default —
so it had to be redone:

- Matrix-input ML (ability + 7 mx): Top3 43.8% vs baseline 45.1%, Miss 54
  vs 43 — still loses to the hand-calibrated linear formula.
- **Raw-feature ML** (ability + all 17 feature scores, now real): pure ML
  rank gp −3.31pp / miss +7 (1/5 folds); blend rank (ability + α·logit,
  α per fold) gp −0.28pp / neutral (2/5 folds) — FAIL
  (`scratch/au_raw_feature_ml_test.py`).

At 710 races the hand formula remains unbeaten by logistic ML even with the
recovered features.

## 2. Pace-role × predicted-pace — the strongest near-miss yet (WATCH LIST)

Audit vs speed_map roles: in races predicted 快 (fast) pace, **leaders are
underrated by +12.6pp** (actual top-3 35.2% vs model-picked 22.6%, n=159)
and **closers overrated by −7.8pp** (n=257) — the engine's
fast-pace-favours-closers tilt runs backwards in this sample.

Candidate `ability ± δ` for fast-pace leaders/closers
(`scratch/au_pace_role_adjust_test.py`):

- Per-fold selection extremely stable (δL=0.5, δC≈2 chosen in all 5 folds,
  effect saturates across grid extensions);
- OOS: any-2 Good **+1.38pp** (149→154), Top3 +0.4pp, 5/5 fold stability —
  but gp flat, **Miss +1**, and +1.38 < +1.5 gate → **FAIL / HOLD**.

**Watch-list disposition**: this is a causally-audited, parameter-stable
effect that just misses the gate. Re-run the script when the archive grows
by ~100–150 races; if real, it clears the gate on its own.

## 3. Racenet results backfill — pipeline built and validated (Tier 1)

- Connection probe + one historical meeting (Randwick 2026-07-11) extracted
  cleanly: full fields with Pos/Jockey/Trainer/Weight/Margin/SP/Time,
  going, rail, in-running positions.
- **Zero-request meeting discovery**: mined 4,244 real (date, venue) pairs
  from our own horses' 賽績線/record tables → **2,669 missing meetings**
  queued, ranked by how many of our horse population ran there (top entries
  270–444 runs — same jockey/trainer colony, maximal J/T value)
  (`scratch/au_backfill_queue.json`).
- **Gentle daily driver** (`scratch/au_results_backfill_driver.py`):
  default 8 meetings/run, 25–45s random gaps, hard-stops on any block
  signal, resumable done-list on Drive, appends to a separate
  `AU_Backfill_Race_Results.csv` (canonical CSV untouched).
- Payoff path: at ~8 meetings/day the results DB roughly doubles in a
  month → re-run `scratch/au_jt_empirical_fill_test.py` (J/T empirical
  ratings failed only for thin data) and the franking/probability
  calibration improves with it.

## Standing watch-list (re-run monthly or at +100 races)

| Candidate | Script | Last result | Trigger to retest |
|---|---|---|---|
| Fast-pace leader/closer adjust | `au_pace_role_adjust_test.py` | +1.38pp any-2, 5/5 folds | +100 races |
| J/T empirical fill | `au_jt_empirical_fill_test.py` | −0.83pp (data-thin) | backfill DB ≥ 2× |
| Phase-5 arithmetic suite | `au_phase5_candidates.py` | all HOLD | +150 races |
| Ordering F2 rerank | `au_ordering_phase2_gate.py` | +0.55pp gp | new features only |
