#!/usr/bin/env python3
"""Post-adoption: rebuild the production ML cache from the refreshed Drive
archive and verify the canonical metrics match the sandbox benchmark."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPTS = Path("/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/shared_racing")

import au_cached_walkforward_ml as ml
from au_cached_walkforward_ml import as_float, date_folds, group_races, metrics_for_races

BACKUP_CACHE = Path("/private/tmp/au_wong_choi_ml_cache_prescore_2026-07-17")


def scored(races):
    return [[{**row, "_score": as_float(row["ability_score"], 60.0)} for row in race] for race in races]


def fmt(m):
    return (f"{m['races']}R {m['gold']}G/{m['good']}g2/{m['good_positional']}gp/{m['miss']}M "
            f"Top3 {m['top3_precision']*100:.1f}% WinT3 {m['winner_in_top3']*100:.1f}% Top1 {m['top1_win']*100:.1f}%")


def main() -> int:
    # preserve the pre-adoption cache once
    if ml.CACHE_DIR.exists() and not BACKUP_CACHE.exists():
        shutil.copytree(ml.CACHE_DIR, BACKUP_CACHE)
        print(f"pre-adoption cache backed up to {BACKUP_CACHE}")
    rows = ml.materialize_dataset(rebuild=True)
    races = group_races(rows)
    full = metrics_for_races(scored(races))
    valid = [race for _t, v in date_folds(races) for race in v]
    oos = metrics_for_races(scored(valid))
    print(f"FULL: {fmt(full)}")
    print(f"OOS : {fmt(oos)}")
    print("expect OOS ~ 363R 22G/149g2/75gp/43M Top3 45.1% WinT3 52.9% Top1 22.6% (sandbox benchmark)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
