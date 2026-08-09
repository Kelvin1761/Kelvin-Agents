#!/usr/bin/env python3
"""Round-5 test: logistic ML on RAW feature scores (post-refresh) vs ability.

All prior ML work fed only the 7 matrix aggregates (+ability). After the
facts-refresh adoption the 17 raw feature scores are real for the first time
(form/trial/health were ~100% default before). Tests:
  A) pure ML rank on ability + raw features;
  B) blend rank: ability + α·standardized(ML logit), α per fold on train.
Expanding-date walk-forward, canonical metrics, standard gate.
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean, pstdev

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

from au_archive_calibrator import FEATURE_SCORE_KEYS  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
    predict,
    train_logistic,
)

FEATURES = ("ability_score",) + tuple(FEATURE_SCORE_KEYS)
ALPHAS = (0.0, 0.5, 1.0, 2.0)


def flat(races):
    return [row for race in races for row in race]


def scored_ability(races):
    return [[{**r, "_score": as_float(r["ability_score"], 60.0)} for r in race] for race in races]


def scored_ml(races, model):
    return [[{**r, "_score": predict(model, r, FEATURES)} for r in race] for race in races]


def scored_blend(races, model, alpha, mu, sd):
    out = []
    for race in races:
        rows = []
        for r in race:
            z = (predict(model, r, FEATURES) - mu) / (sd or 1.0)
            rows.append({**r, "_score": as_float(r["ability_score"], 60.0) + alpha * z})
        out.append(rows)
    return out


def main() -> int:
    races = group_races(materialize_dataset())
    folds = date_folds(races)
    agg = {"base": [], "ml": [], "blend": []}
    non_worse = {"ml": 0, "blend": 0}
    for idx, (train, valid) in enumerate(folds, 1):
        model = train_logistic(flat(train), FEATURES, epochs=6, lr=0.05, l2=1e-4, seed=20260717 + idx)
        train_preds = [predict(model, r, FEATURES) for r in flat(train)]
        mu, sd = mean(train_preds), pstdev(train_preds)
        # α selected on train positional-Good
        best_alpha, best_gp = 0.0, -1.0
        for alpha in ALPHAS:
            m = metrics_for_races(scored_blend(train, model, alpha, mu, sd))
            gp = m["good_positional"] / max(1, m["races"])
            if gp > best_gp:
                best_gp, best_alpha = gp, alpha
        vb = metrics_for_races(scored_ability(valid))
        vm = metrics_for_races(scored_ml(valid, model))
        vbl = metrics_for_races(scored_blend(valid, model, best_alpha, mu, sd))
        non_worse["ml"] += vm["top3_precision"] >= vb["top3_precision"]
        non_worse["blend"] += vbl["top3_precision"] >= vb["top3_precision"]
        print(f"fold {idx}: α={best_alpha} | gp base {vb['good_positional']} ml {vm['good_positional']} "
              f"blend {vbl['good_positional']} | miss {vb['miss']}/{vm['miss']}/{vbl['miss']}")
        agg["base"].extend(scored_ability(valid))
        agg["ml"].extend(scored_ml(valid, model))
        agg["blend"].extend(scored_blend(valid, model, best_alpha, mu, sd))

    base = metrics_for_races(agg["base"])

    def fmt(m):
        return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")

    print(f"baseline: {fmt(base)}")
    for name in ("ml", "blend"):
        cand = metrics_for_races(agg[name])
        gp = (cand["good_positional"] - base["good_positional"]) / base["races"] * 100
        g2 = (cand["good"] - base["good"]) / base["races"] * 100
        passed = (max(gp, g2) >= 1.5 and min(gp, g2) >= -0.5 and cand["miss"] <= base["miss"]
                  and non_worse[name] >= 4
                  and (base["top1_win"] - cand["top1_win"]) * 100 <= 0.5
                  and (base["winner_in_top3"] - cand["winner_in_top3"]) * 100 <= 0.5
                  and (base["gold"] - cand["gold"]) / base["races"] * 100 <= 0.5)
        print(f"{name:<6}: {fmt(cand)}")
        print(f"        gp {gp:+.2f}pp g2 {g2:+.2f}pp miss Δ {cand['miss']-base['miss']:+d} "
              f"folds {non_worse[name]}/{len(folds)} → {'PASS' if passed else 'FAIL / HOLD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
