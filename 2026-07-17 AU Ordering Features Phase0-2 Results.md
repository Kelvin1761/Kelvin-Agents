# AU Ordering Features — Phase 0–2 Results (2026-07-17, round 4)

> Execution of `au-wong-choi-ordering-features-plan.md`. Outcome: the pairwise
> ordering hypothesis is **retired with a clean negative result** before any
> engine code was written — exactly what the phase gates were designed to do.

## Phase 0 — coverage audit: PASSED

- 賽績線 rows: **94.7%** of 7,530 horses (the facts-refresh adoption paid off).
- Top-4 H2H pairs (rival named in my 賽績線 AND in today's top-4): present in
  40.3% of all races; **38.9% of the 285 ordering-opportunity races** (gate ≥25%).
- L400 from record-table text: 0% (format drift — real sectional source is the
  merged `timing_600m_*` fields, coverage **90.6%**).
- F4 franking data present but sparse in usable form.

## Phase 1 — retrodictive signal check (train = first half of dates)

| Feature | train Δ (placegetter − non) | valid Δ | verdict |
|---|---:|---:|---|
| F2 last-start margin quality | +0.242 | +0.228 | **KEEP — real, stable** |
| F1 H2H net score | +0.047 | +0.037 | weak (pairwise direction accuracy valid 51.3% ≈ coin flip) |
| F3 sectional differential | +0.036 | +0.006 | KILL — decays OOS |
| F4 franking rate | −0.002 | +0.000 | KILL — dead |

## Phase 2 — walk-forward gate on F2 (+ optional F1): FAIL / HOLD

Stage-2 rerank of the ability top-4 by `ability + λ·(F2 + β·F1)`, (λ, β)
selected per fold on train positional-Good only (λ stabilized at 0.5):

- OOS aggregate (363R): positional Good **+0.55pp** (75→77), any-2 +0.55pp,
  **Miss +6** (43→49), **Top1 −1.93pp**, Top3 fold stability 3/5.
- Gate requires gp ≥ +1.5pp with Miss/Top1 non-regression → **FAIL**.

## Conclusion and standing recommendation

Fifteen candidates have now been honestly killed by the same pre-registered
gate; the one intervention that passed (facts-refresh evidence recovery)
delivered +3.6pp positional Good and HKJC parity. The remaining ordering gap
is not extractable from the archive's current information content.

What actually moves the number from here:

1. **Time / data accumulation** — pace_figure (PF sectionals) is still ~72%
   default even in 2026-07 and will densify organically; J/T empirical ratings
   need a results database several times larger. Re-run the standing harnesses
   (`au_phase5_candidates.py`, `au_ordering_phase2_gate.py`,
   `au_jt_empirical_fill_test.py`) monthly as data grows.
2. **Extraction-side new information** (not scoring-side): richer trial
   sectionals, gear changes, official ratings movements — new inputs, captured
   at extraction time going forward.
3. **Practice layer already shipped**: `--going` refresh + confidence-tiered
   radar (tight races → Top-5 圍捕) are the operational wins to exercise in
   live meetings now.
