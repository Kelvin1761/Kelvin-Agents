#!/usr/bin/env python3
"""C1b — tail-gated 久休扣分。

第一輪（`au_layoff_shadow_test.py`）用連續 piecewise-linear 扣分覆蓋全個久休範圍，
結果 FAIL：只有 `top_pick_blowout` 單調改善，但 Gold 由 33 跌到 25（dev），
champion / mrr / ndcg 全部平或差。

診斷：量到嘅訊號只喺尾部決定性（>365d 前三率 19.4%，n=31），
而 0–180d 三格（28.6 / 27.5 / 26.5%）幾乎冇 gradient 但佔 6,939 / 7,226 匹。
喺呢個密集區施加扣分＝純噪音重排，就係 Gold 流失嘅來源。

所以呢輪只喺 threshold 以上施加扣分，threshold 以下完全零改動。
Sweep threshold × magnitude。唯讀。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from au_layoff_shadow_test import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    digest,
    iter_logic_rows,
    load_historical_results,
    race_metrics,
    spell_days,
    summarize_races,
)

HOLDOUT_FRACTION = 0.15
THRESHOLDS = (180, 270, 365)
PENALTIES = (0.0, 3.0, 6.0, 10.0, 15.0)


def evaluate(races, threshold, penalty):
    rows = []
    for race_rows in races:
        actual_pos = {r["horse_number"]: r["actual_pos"] for r in race_rows}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for r in race_rows:
            days = r["_spell"]
            # Ramp from 0 at the threshold to full penalty one year later, so the
            # gate is not a cliff that a single day either side flips.
            if penalty and days is not None and days > threshold:
                ramp = min(1.0, (days - threshold) / 365.0)
                adj = -penalty * ramp
            else:
                adj = 0.0
            scored.append((r["model_score"] + adj, r["horse_number"]))
        picks = [num for _, num in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        rows.append(race_metrics(
            picks, actual_top3,
            winner=winners[0] if winners else None,
            actual_pos=actual_pos,
            field_size=len(race_rows),
        ))
    return summarize_races(rows)


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            r["_spell"] = spell_days(r)
        races.append(race_rows)
    races.sort(key=lambda rr: (rr[0]["date"], rr[0]["meeting"], rr[0]["race"]))
    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    folds = {"dev": races[:split], "holdout": races[split:], "all": races}

    # How many races does each gate actually touch?  A gate that moves nothing is
    # unmeasurable on this sample, and that has to be stated, not hidden.
    touched = {}
    for th in THRESHOLDS:
        n_runners = sum(1 for rr in races for r in rr
                        if r["_spell"] is not None and r["_spell"] > th)
        n_races = sum(1 for rr in races
                      if any(r["_spell"] is not None and r["_spell"] > th for r in rr))
        n_toppick = sum(1 for rr in races
                        if (sorted(rr, key=lambda r: (-r["model_score"], r["horse_number"]))[0]["_spell"] or 0) > th)
        touched[f">{th}d"] = {"runners": n_runners, "races_with_one": n_races,
                             "races_where_top_pick": n_toppick}

    out = {"races": len(races), "gate_footprint": touched, "sweep": {}}
    for th in THRESHOLDS:
        for p in PENALTIES:
            key = f"th={th},P={p:g}"
            out["sweep"][key] = {name: digest(evaluate(fold, th, p))
                                 for name, fold in folds.items()}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("gate footprint (of %d races):" % len(races))
    for k, v in touched.items():
        print(f"  {k:>7}  runners {v['runners']:>4}  races touched {v['races_with_one']:>4}"
              f"  races where it is the TOP PICK {v['races_where_top_pick']:>3}")
    print()

    keys = ["good_pos_pct", "good_any2_pct", "champion_pct", "winner_in_top3_pct",
            "top3_precision_pct", "mrr", "top_pick_blowout_pct",
            "top_pick_competitive_pct", "mean_ndcg_at5"]
    for fold in ("dev", "holdout"):
        print(f"===== {fold} =====")
        base = out["sweep"][f"th={THRESHOLDS[0]},P=0"][fold]
        cols = [k for k in out["sweep"] if not k.endswith("P=0")]
        print(f"{'metric':28}{'base':>8}" + "".join(f"{c.replace('th=',''):>16}" for c in cols))
        for k in keys:
            line = f"{k:28}{base[k] if base[k] is not None else '-':>8}"
            for c in cols:
                v = out["sweep"][c][fold][k]
                line += (f"{v:>9} ({v - base[k]:+.2f})".rjust(16)) if v is not None else f"{'-':>16}"
            print(line)
        line = f"{'gold':28}{base['gold']:>8}"
        for c in cols:
            v = out["sweep"][c][fold]["gold"]
            line += f"{v:>9} ({v - base['gold']:+d})".rjust(16)
        print(line + "\n")


if __name__ == "__main__":
    main()
