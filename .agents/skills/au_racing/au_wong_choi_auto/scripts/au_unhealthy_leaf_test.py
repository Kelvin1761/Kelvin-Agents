#!/usr/bin/env python3
"""喺 0.5 以下嘅 leaf，剷咗會唔會贏？—— 用量嘅，唔用估。

背景：`au_leaf_power.py` 量到三個 leaf 場內 AUC 喺 0.5 以下，即係佢哋把上名馬
排喺落榜馬下面嘅次數多過上面。但**線性組合入面負相關唔一定係淨噪音**，所以
唔可以見到 <0.5 就剷 —— 要真係量。

三個嘅實際處境唔同（睇 `MATRIX_FORMULAS`）：

    weight_score    0.463  ← **根本唔喺矩陣入面**，剷唔剷都冇分別
    track_score     0.487  ← **就係成個 `track` 維度**（9.4% 權重）
    sectional_score 0.469  ← 喺 `pace_perf` 入面佔 0.194（≈2.8% 總權重）

所以真正要測嘅係 track 同 sectional。

紀律同 refit 一樣：dev 85% / holdout 15% 依時間切，holdout 唔參與任何選擇。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

import matrix_mapper  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

KEYS = ("gold", "good_positional", "good_any2", "pass_any1", "champion",
        "winner_in_top3")


def renorm(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()} if s else d


def evaluate(races, weights, formulas=None):
    saved = matrix_mapper.MATRIX_FORMULAS
    if formulas is not None:
        matrix_mapper.MATRIX_FORMULAS = formulas
    try:
        rows = []
        for r in races:
            scored = []
            for row in r["rows"]:
                m = matrix_mapper.map_features_to_matrix_scores(row["features"])
                ability = sum(m.get(k, 60.0) * w for k, w in weights.items()) + row["wet"]
                scored.append((ability, row["name"], row["pos"]))
            scored.sort(key=lambda x: -x[0])
            picks = [s[1] for s in scored]
            pos = {s[1]: s[2] for s in scored}
            top3 = {h for h, p in pos.items() if p <= 3}
            win = next((h for h, p in pos.items() if p == 1), None)
            if not top3 or win is None:
                continue
            rows.append(race_metrics(picks, top3, winner=win, actual_pos=pos,
                                     field_size=max(pos.values())))
    finally:
        matrix_mapper.MATRIX_FORMULAS = saved
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
                                  ("gold", "good_positional", "good_any2",
                                   "champion", "winner_in_top3", "t3prec"))
          + f"   主指標 {up}↑/{dn}↓")


def main():
    ap = argparse.ArgumentParser(description="測試剷走 <0.5 leaf 嘅效果")
    ap.add_argument("--data", required=True)
    ap.add_argument("--holdout", type=float, default=0.15)
    args = ap.parse_args()

    races = json.loads(Path(args.data).read_text())["races"]
    cut = int(len(races) * (1 - args.holdout))
    dev, hold = races[:cut], races[cut:]

    F = matrix_mapper.MATRIX_FORMULAS
    # sectional 由 pace_perf 剷走，其餘兩個 leaf 按比例補返
    pp = [(k, w) for k, w in F["pace_perf"] if k != "sectional_score"]
    tot = sum(w for _, w in pp)
    no_sect = dict(F)
    no_sect["pace_perf"] = tuple((k, w / tot) for k, w in pp)

    no_track = renorm({k: v for k, v in MATRIX_WEIGHTS.items() if k != "track"})
    no_both_w = no_track

    variants = [
        ("剷 sectional（留 track）", MATRIX_WEIGHTS, no_sect),
        ("剷 track 維度（留 sectional）", no_track, None),
        ("兩個都剷", no_both_w, no_sect),
    ]
    hdr = f"{'':34}{'gold':>9}{'good_pos':>9}{'any2':>9}{'champ':>9}{'winT3':>9}{'t3prec':>9}"
    for name, sub in (("dev", dev), ("holdout（未碰）", hold)):
        base = evaluate(sub, MATRIX_WEIGHTS)
        print(f"\n===== {name}（{len(sub)} 場）=====")
        print(hdr)
        for label, w, f in variants:
            show(label, evaluate(sub, w, f), base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
