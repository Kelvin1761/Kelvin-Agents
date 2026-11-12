#!/usr/bin/env python3
"""EXP-20261113-21 顯示 leaf：場內 AUC（前三 vs 落榜，剔走 = 60 嘅馬），賽日 bootstrap 95% CI。

    au_noise_display_auc_20261113.py DUMP.json [leaf ...]
"""
import json
import random
import sys
from collections import defaultdict

LEAVES = ("confidence_score", "health_score", "weight_score", "pace_map_score", "distance_score",
          "formline_score", "track_score", "class_score", "preparation_score", "trial_speed_score")


def race_pairs(race, leaf, excl):
    vals = [(r["features"][leaf], r["pos"] <= 3) for r in race["rows"]]
    if excl:
        vals = [(v, p) for v, p in vals if abs(v - 60.0) > 1e-9]
    pl = [v for v, p in vals if p]
    un = [v for v, p in vals if not p]
    w = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pl for b in un)
    return w, len(pl) * len(un)


def main():
    races = [r for r in json.load(open(sys.argv[1]))["races"] if r["date"] >= "2026-08-05"]
    leaves = sys.argv[2:] or LEAVES
    n_runners = sum(len(r["rows"]) for r in races)
    print(f"races {len(races)} runners {n_runners}")
    for leaf in leaves:
        for excl in (True, False):
            by_day = defaultdict(lambda: [0.0, 0])
            for race in races:
                w, n = race_pairs(race, leaf, excl)
                by_day[race["date"]][0] += w
                by_day[race["date"]][1] += n
            days = sorted(by_day)
            W = sum(by_day[d][0] for d in days)
            N = sum(by_day[d][1] for d in days)
            rng = random.Random(7)
            samples = []
            for _ in range(2000):
                pick = [days[rng.randrange(len(days))] for _ in days]
                ww = sum(by_day[d][0] for d in pick)
                nn = sum(by_day[d][1] for d in pick)
                samples.append(ww / nn if nn else 0.5)
            samples.sort()
            neutral = sum(abs(x["features"][leaf] - 60) < 1e-9 for r in races for x in r["rows"]) / n_runners
            tag = "剔中性" if excl else "全部 "
            print(f"{leaf:22s} {tag} AUC {W / N if N else float('nan'):.4f} "
                  f"[{samples[50]:.4f}, {samples[1949]:.4f}]  pairs {N}  中性 {neutral:.1%}")


if __name__ == "__main__":
    main()
