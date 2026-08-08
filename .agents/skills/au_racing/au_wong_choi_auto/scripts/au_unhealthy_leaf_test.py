#!/usr/bin/env python3
"""量度弱 standalone matrix 維度有冇真正 marginal value。

單一維度 AUC 接近 0.5 唔代表放入多維線性組合後冇價值，所以唔可以見弱就剷。
現役 ranking 已經移除 `sectional_score` 同 `weight_score`；呢個工具只測仍在排名嘅
`track`／`race_shape`，並使用 canonical runtime loader 同完整賽日 holdout。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

import matrix_mapper  # noqa: E402
from au_eval import date_partitions, load_races  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")


def renorm(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s else d


def evaluate(races, weights):
    rows = []
    for r in races:
        scored = []
        for row_index, row in enumerate(r["rows"]):
            m = matrix_mapper.map_features_to_matrix_scores(row["features"])
            ability = sum(m.get(k, 60.0) * w for k, w in weights.items()) + row["wet"]
            identity = row.get("name") or row.get("horse_name") or row_index
            scored.append((ability, identity, row["pos"]))
        scored.sort(key=lambda x: -x[0])
        picks = [s[1] for s in scored]
        pos = {s[1]: s[2] for s in scored}
        top3 = {h for h, p in pos.items() if p <= 3}
        win = next((h for h, p in pos.items() if p == 1), None)
        if not top3 or win is None:
            continue
        rows.append(race_metrics(picks, top3, winner=win, actual_pos=pos,
                                 field_size=max(pos.values())))
    if not rows:
        return None
    c = summarize_races(rows)["counts"]
    n = len(rows)
    hits = sum(x["hits"] for x in rows)
    slots = sum(min(3, len(x["picks"])) for x in rows)
    out = {k: 100.0 * c[k] / n for k in KEYS}
    out["t3prec"] = 100.0 * hits / slots
    return out


def show(label, cand, base):
    if not cand or not base:
        print(f"{label}: 冇資料")
        return
    d = {k: cand[k] - base[k] for k in list(KEYS) + ["t3prec"]}
    up = sum(1 for k in ("t3prec", "winner_in_top3", "champion") if d[k] > 0.001)
    dn = sum(1 for k in ("t3prec", "winner_in_top3", "champion") if d[k] < -0.001)
    print(f"{label:34}" + "".join(f"{d[k]:>+9.2f}" for k in
                                  ("gold", "good_positional", "pass",
                                   "champion", "winner_in_top3", "t3prec"))
          + f"   主指標 {up}↑/{dn}↓")


def main():
    ap = argparse.ArgumentParser(description="測試剷走 <0.5 leaf 嘅效果")
    ap.add_argument("--data", required=True)
    ap.add_argument("--holdout", type=float, default=0.15)
    args = ap.parse_args()

    races = load_races(args.data)
    dev_indices, hold_indices = date_partitions(races, args.holdout)
    dev = [races[index] for index in dev_indices]
    hold = [races[index] for index in hold_indices]

    no_track = renorm({k: v for k, v in MATRIX_WEIGHTS.items() if k != "track"})
    no_shape = renorm({k: v for k, v in MATRIX_WEIGHTS.items() if k != "race_shape"})
    no_both = renorm({
        k: v
        for k, v in MATRIX_WEIGHTS.items()
        if k not in {"track", "race_shape"}
    })

    variants = [
        ("剷 track 維度", no_track),
        ("剷 race_shape 維度", no_shape),
        ("兩個弱維度都剷", no_both),
    ]
    hdr = f"{'':34}{'gold':>9}{'good_pos':>9}{'pass':>9}{'champ':>9}{'winT3':>9}{'t3prec':>9}"
    for name, sub in (("dev", dev), ("holdout（未碰）", hold)):
        base = evaluate(sub, MATRIX_WEIGHTS)
        print(f"\n===== {name}（{len(sub)} 場）=====")
        print(hdr)
        for label, weights in variants:
            show(label, evaluate(sub, weights), base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
