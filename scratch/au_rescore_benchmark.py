#!/usr/bin/env python3
"""Benchmark the facts-refresh full-archive rescore against stored production.

Builds a fresh labelled cache from the sandbox rescored archive (via
WONGCHOI_DATA_ROOT redirect + patched cache dir), joins races by
(date, track, race), and compares canonical metrics old vs new on the full
common set and the expanding-date OOS window, plus per going family and
field band, with the Phase-5 promotion gate.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

SP = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad")
os.environ["WONGCHOI_DATA_ROOT"] = str(SP / "data")

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

import au_cached_walkforward_ml as ml  # noqa: E402  (module-level ARCHIVE_ROOT now points at sandbox)
from au_archive_calibrator import normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import as_float, date_folds, group_races, metrics_for_races  # noqa: E402

# keep the production cache intact — rebuild into a sandbox cache dir
ml.CACHE_DIR = SP / "rescore_cache"
ml.DATASET_CSV = ml.CACHE_DIR / "au_labelled_horse_rows.csv"
ml.MANIFEST_JSON = ml.CACHE_DIR / "manifest.json"

PROD_CACHE = Path("/private/tmp/au_wong_choi_ml_cache/au_labelled_horse_rows.csv")


def load_prod_races():
    rows = ml.load_dataset(PROD_CACHE)
    return group_races(rows)


def race_key(race):
    return (str(race[0]["date"]), str(race[0].get("track") or "").lower(), str(race[0]["race"]))


def scored(races):
    return [[{**row, "_score": as_float(row["ability_score"], 60.0)} for row in race] for race in races]


def field_band(n):
    return "<=8" if n <= 8 else ("9-11" if n <= 11 else "12+")


def main() -> int:
    new_rows = ml.materialize_dataset(rebuild=not ml.DATASET_CSV.exists())
    new_races = {race_key(r): r for r in group_races(new_rows)}
    prod_races = {race_key(r): r for r in load_prod_races()}
    common = sorted(set(new_races) & set(prod_races))
    print(f"prod races {len(prod_races)}, rescored races {len(new_races)}, common {len(common)}")

    prod = [prod_races[k] for k in common]
    cand = [new_races[k] for k in common]

    def report(name, base_set, cand_set):
        b = metrics_for_races(scored(base_set))
        c = metrics_for_races(scored(cand_set))
        def line(m):
            return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
                    f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")
        print(f"--- {name}")
        print(f"  prod    : {line(b)}")
        print(f"  rescored: {line(c)}")
        print(f"  Δ good-any2 {(c['good']-b['good'])/max(1,b['races'])*100:+.2f}pp | "
              f"Δ good-pos {(c['good_positional']-b['good_positional'])/max(1,b['races'])*100:+.2f}pp | "
              f"Δ miss {c['miss']-b['miss']:+d} | Δ Top3 {(c['top3_precision']-b['top3_precision'])*100:+.2f}pp | "
              f"Δ WinT3 {(c['winner_in_top3']-b['winner_in_top3'])*100:+.2f}pp")
        return b, c

    report("FULL common set", prod, cand)

    prod_folds = {k: True for _t, v in date_folds(prod) for k in map(race_key, v)}
    oos_prod = [prod_races[k] for k in common if k in prod_folds]
    oos_cand = [new_races[k] for k in common if k in prod_folds]
    b, c = report("OOS window (expanding-date folds)", oos_prod, oos_cand)

    fold_non_worse = 0
    folds = date_folds(prod)
    for _train, valid in folds:
        keys = [race_key(r) for r in valid if race_key(r) in new_races]
        fb = metrics_for_races(scored([prod_races[k] for k in keys]))
        fc = metrics_for_races(scored([new_races[k] for k in keys]))
        fold_non_worse += fc["top3_precision"] >= fb["top3_precision"]
    print(f"fold Top3 non-worse: {fold_non_worse}/{len(folds)}")

    for slicer, namer in (("going", lambda r: normalize_condition_bucket(str(r[0].get('condition_bucket') or ''))),
                          ("field", lambda r: field_band(len(r)))):
        groups = defaultdict(list)
        for k in common:
            groups[namer(prod_races[k])].append(k)
        for gname, keys in sorted(groups.items()):
            if len(keys) < 30:
                continue
            report(f"{slicer}={gname} (n={len(keys)})",
                   [prod_races[k] for k in keys], [new_races[k] for k in keys])

    good_lift = (c["good"] - b["good"]) / max(1, b["races"]) * 100
    losses_ok = ((b["top1_win"] - c["top1_win"]) * 100 <= 0.5
                 and (b["winner_in_top3"] - c["winner_in_top3"]) * 100 <= 0.5
                 and (b["gold"] - c["gold"]) / max(1, b["races"]) * 100 <= 0.5)
    passed = good_lift >= 1.5 and losses_ok and c["miss"] <= b["miss"] and fold_non_worse >= 4
    print(f"\nGATE: {'PASS' if passed else 'FAIL / HOLD'} "
          f"(good {good_lift:+.2f}pp, miss Δ {c['miss']-b['miss']:+d}, folds {fold_non_worse}/{len(folds)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
