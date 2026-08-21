# AU Wong Choi — "Improve, don't remove" the weak scoring (2026-07-24)

Kelvin: don't delete weak features — they were added because they gave signal;
try to improve them to reflect real signal. Result, honestly.

## Why each weak feature is weak — two distinct causes

A feature is weak for one of two reasons, and only one is fixable by better math:

1. **Mis-specified** — the logic captures the signal in the WRONG direction/form.
   Fixable by correcting the logic.
2. **Redundant** — the signal it would carry is already captured by another
   feature. NOT fixable by better math; only new information helps.

## weight_score: mis-specified AND redundant

- **Mis-specified (fixed):** the old logic rewarded LIGHT weight (score 68,
  "負輕磅有明顯優勢") and penalised topweight (56). In AU handicaps that is
  backwards — the handicapper assigns weight by ability, so topweights are the
  better horses. Data: top-3 finish by weight_score bucket — light 23.2% / mid
  29.1% / heavy **34.3%**. The narrative was teaching the human the OPPOSITE of
  the truth.
- **Redundant:** conditional on rating rank, the weight effect flattens
  (rated-top4: light 33% / mid 38% / heavy 36% — no monotonic edge). The ability
  in weight is already in rating_score.
- **Fixing the direction unlocks nothing**: flip vs neutralise vs current are
  identical on every ranking metric (Δgp/g2/miss 0, top1 +0.3, 5/5 folds),
  because weight_score is only 0.64% of ability and has no rating-orthogonal
  signal.
- **Action taken:** re-specified `_weight_score` to the correct direction —
  neutral by default (no light-weight reward), keeping only the genuinely
  orthogonal nudges (real wet-going burden on topweights; class-move weight
  relief) and a truthful topweight note. **This is a correctness / narrative-
  truth fix, validated as a ranking wash — not a performance claim.**

## The other weak features are redundant, not mis-specified

`class_score`, `sectional_score`, `trial_score` wash out CONDITIONAL on the
model (drop-one is ±0-1 on gp/g2). They already use the right raw data; their
signal is captured by rating/pace_figure/form. Re-mathing them cannot help —
there is no orthogonal signal to recover from the data we have. (Removing them
in combination hurts fold stability, so they stay as harmless support.)

## The general lesson

Weak features can't be maths-ed into strong ones. weight_score proves it:
even after fixing a genuine inversion, it stays a wash because its real signal
lives in rating_score. **Improvement comes from NEW information (market money,
richer trial data that turned out not to exist), not from better arithmetic on
the signals we already have.** The dead-weight audit is therefore best used for
*correctness/truthfulness* fixes (like this one), not performance.

## Dead-weight audit summary (leave-one-out, 363-race OOS)

| feature | drop Δgp | drop Δg2 | verdict |
|---|---:|---:|---|
| form_score | −19 | −11 | core, keep |
| pace_figure_score | −10 | −8 (miss +21) | core, keep |
| jockey_horse_fit_score | −7 | −4 | keep |
| consistency/rating/trainer | mixed (protect top1/miss) | | keep |
| sectional/class/jockey/trial | wash | | redundant, harmless keep |
| **weight_score** | 0 | 0 | **inverted → direction-fixed (wash)** |
| form_line dimension | (weight 0) | | already dead — retire in a clean-up SIP |
