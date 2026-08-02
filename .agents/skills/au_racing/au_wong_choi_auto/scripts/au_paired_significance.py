#!/usr/bin/env python3
"""兩個版本嘅**配對**顯著性（McNemar）—— 唔係兩個獨立比例。

點解要專登做：兩個版本跑**同一批場次、同一批賽果**，只係數據源／權重唔同。
當成兩個獨立樣本嚟比（普通兩比例檢定）會**大幅低估**檢定力：兩邊同意嘅場次
提供唔到資訊，但佢哋照樣入晒分母，把個差距溝淡。

實測差別有幾大：604 場、頭馬入前三 323 vs 294，獨立檢定門檻係 ±5.63pp，
而實際差 +4.80pp —— 判「唔顯著」。但兩個版本喺絕大部分場次係一樣嘅，真正
有資訊嘅只係唔同意嗰批。McNemar 淨係睇嗰批。

    b = 新中、舊唔中的場次數
    c = 舊中、新唔中的場次數
    兩邊都中／都唔中 → 冇資訊，剔走

⚠️ 呢個答嘅係「呢個差距係咪真」，唔係「呢個差距有幾大」。樣本細嘅時候，
   「顯著」都可以係細差距。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))

from au_leaf_power import norm, results_for  # noqa: E402

METRICS = ("winner_in_top3", "good_any2", "good_positional", "champion",
           "pass_any1", "gold")


def outcomes(picks, actual):
    top3 = {h for h, p in actual.items() if p <= 3}
    win = next((h for h, p in actual.items() if p == 1), None)
    if not top3 or win is None:
        return None
    t3 = picks[:3]
    hits = sum(1 for h in t3 if h in top3)
    return {
        "winner_in_top3": win in t3,
        "good_any2": hits >= 2,
        "good_positional": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
        "champion": bool(picks) and picks[0] == win,
        "pass_any1": hits >= 1,
        "gold": hits == 3,
        "_hits": hits,
    }


def load_picks(root, name):
    for base in (Path(root), Path(root) / "Archive"):
        p = base / name / "Meeting_Auto_Scoring.csv"
        if not p.exists():
            continue
        d = {}
        with open(p, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                d.setdefault(int(r["race_number"]), []).append(
                    (int(r["rank"]), norm(r["horse_name"])))
        return {k: [n for _, n in sorted(v)] for k, v in d.items()}
    return None


def mcnemar(b, c):
    """雙尾精確 binomial（b+c 細嘅時候比卡方準）。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def main():
    ap = argparse.ArgumentParser(description="配對顯著性（McNemar）")
    ap.add_argument("--new", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--min-depth", type=float, default=4.0)
    args = ap.parse_args()

    from sb_backfill_archive import load_meeting_ids

    cj = Path(args.new).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})

    tab = {m: [0, 0] for m in METRICS}      # [b(新贏), c(舊贏)]
    both = {m: 0 for m in METRICS}
    slots = [0, 0]
    races = 0
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        if args.min_depth and depth.get(name, 0) < args.min_depth:
            continue
        pn, po = load_picks(args.new, name), load_picks(args.old, name)
        if not pn or not po:
            continue
        res = results_for(meta)
        for rno, actual in res.items():
            if rno not in pn or rno not in po:
                continue
            on, oo = outcomes(pn[rno], actual), outcomes(po[rno], actual)
            if not on or not oo:
                continue
            races += 1
            slots[0] += on["_hits"]
            slots[1] += oo["_hits"]
            for m in METRICS:
                if on[m] and not oo[m]:
                    tab[m][0] += 1
                elif oo[m] and not on[m]:
                    tab[m][1] += 1
                elif on[m]:
                    both[m] += 1

    print(f"配對比較（{races} 場，兩邊都評到）\n")
    print(f"{'指標':18}{'新贏':>6}{'舊贏':>6}{'唔同意':>8}{'p 值':>10}  判斷")
    for m in METRICS:
        b, c = tab[m]
        p = mcnemar(b, c)
        v = ("✅ 顯著（新贏）" if p < 0.05 and b > c else
             "✅ 顯著（舊贏）" if p < 0.05 else "— 唔顯著")
        print(f"{m:18}{b:>6}{c:>6}{b+c:>8}{p:>10.4f}  {v}")
    print(f"\n前三命中格數：新 {slots[0]} · 舊 {slots[1]} · 差 {slots[0]-slots[1]:+}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
