#!/usr/bin/env python3
"""「冇證據」嘅馬被放喺 leaf 尺嘅邊度，同佢哋實際跑成點？

呢個 repo 已經有**兩次**同一個 bug：一個 leaf 把「查唔到數據」放喺尺嘅底部，
於是報告讀成「呢匹馬差」，而嗰批馬實際上跑得同平均一樣或者更好。

    段速分     base 35.8 → 冇 PI 數據嘅 1,391 匹 top-3 率 30.1%（高過平均）→ 改 60
    檔位形勢   base 55.7 + cap +4.05 → 60 係天花板唔係中性 → 改 60

兩次都係人手讀參數表捉到，唔係 A/B 捉到 —— A/B 會話你「郁佢會蝕」，
但唔會話你「你把尺嘅零點放錯位」。所以呢個工具做同一件事，但係系統化：
逐個 leaf 搵出「聚集喺某一個值」嘅 cohort（＝某條 no-evidence 分支嘅產物），
再量嗰批馬**修正馬群大細之後**嘅實際前三率。

⚠️ **一定要修正馬群大細。** 8 匹馬嘅場次前三率天然係 37.5%，18 匹係 16.7%。
如果某個 cohort 集中喺大場（例如新馬多嘅維持賽），未修正嘅 pooled 數字會
話你佢哋差，而嗰個「差」係場數造成嘅。呢個 repo 已經因為漏咗呢一步而得出過
「差檔位跑得好」嘅假結論。

用法：
    python3 au_no_evidence_cohorts.py --data <sb_leaves_v2.json>
    python3 au_no_evidence_cohorts.py --data ... --leaf jockey_horse_fit_score
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

# 每個 leaf 嘅「冇證據」值 —— 由 scoring.py 嘅 *_MICRO_WEIGHTS 讀返嚟嘅
# base / career0_base。呢度寫死係為咗令輸出講得出「呢個值代表咩」。
NO_EVIDENCE = {
    "consistency_score": [(52.4, "career0_base：初出馬，冇往績可言"),
                          (64.6, "base：有往績但冇任何加減觸發")],
    "class_score": [(57.7, "career0_base：初出馬")],
    "sectional_score": [(60.0, "base：冇 PI／段速數據（2026-08-01 已由 35.8 修上嚟）")],
    "track_score": [(62.9, "base：呢個場地／going 冇往績")],
    "pace_map_score": [(60.0, "base（2026-08-01 已由 55.7 修上嚟）")],
    "jockey_horse_fit_score": [(60.0, "base：今場騎師從未策過呢匹馬")],
    "formline_score": [(60.0, "冇對手強度證據")],
    "trial_score": [(60.0, "冇試閘紀錄")],
}
TOL = 0.05


def main():
    ap = argparse.ArgumentParser(description="no-evidence cohort 實際表現")
    ap.add_argument("--data", required=True)
    ap.add_argument("--leaf", action="append")
    ap.add_argument("--min-n", type=int, default=60)
    args = ap.parse_args()

    races = json.loads(Path(args.data).read_text())["races"]

    # 期望前三率：逐個馬群大細算，即係嗰批場次真實觀察到嘅比率。
    # 唔用 3/n 理論值 —— 退賽同並頭馬令實際同理論唔同。
    by_size = defaultdict(lambda: [0, 0])
    rows = []
    for r in races:
        n = len(r["rows"])
        for row in r["rows"]:
            placed = row["pos"] <= 3
            by_size[n][0] += placed
            by_size[n][1] += 1
            rows.append((n, placed, row["features"]))
    expected = {n: (a / b if b else 0.0) for n, (a, b) in by_size.items()}

    leaves = args.leaf or list(NO_EVIDENCE)
    print(f"{len(races)} 場 / {len(rows)} 匹\n")
    print(f"{'leaf':26}{'值':>7}{'匹數':>7}{'佔比':>7}"
          f"{'實際前三':>9}{'同場數期望':>11}{'超額':>8}")
    print("─" * 76)

    for leaf in leaves:
        vals = [f.get(leaf) for _, _, f in rows if f.get(leaf) is not None]
        if not vals:
            print(f"{leaf:26}  —— 語料冇呢個 leaf")
            continue
        # 先報整體集中度：一個 leaf 有幾多匹卡喺同一個值，就係佢冇幾多 gradient
        top = Counter(round(v, 2) for v in vals).most_common(3)
        stuck = sum(c for _, c in top) / len(vals)
        print(f"{leaf:26}" + f"  最密三個值佔 {stuck:.1%}"
              f"（{', '.join(f'{v}×{c}' for v, c in top)}）")

        for target, why in NO_EVIDENCE.get(leaf, []):
            sel = [(n, p) for n, p, f in rows
                   if f.get(leaf) is not None and abs(f[leaf] - target) < TOL]
            if len(sel) < args.min_n:
                print(f"{'':26}{target:>7.1f}{len(sel):>7}"
                      f"     樣本太細（<{args.min_n}），唔報")
                continue
            hits = sum(p for _, p in sel)
            act = hits / len(sel)
            exp = sum(expected[n] for n, _ in sel) / len(sel)
            d = (act - exp) * 100
            flag = ""
            if d > 1.5:
                flag = "  ⚠️ 跑得好過期望，但被放喺低位" if target < 60 else "  ✅ 跑得好過期望"
            elif d < -1.5:
                flag = "  ⚠️ 跑得差過期望，但被放喺 60 或以上" if target >= 60 else "  ✅ 位置啱"
            print(f"{'':26}{target:>7.1f}{len(sel):>7}{len(sel) / len(vals):>7.1%}"
                  f"{act:>9.1%}{exp:>11.1%}{d:>+8.1f}{flag}")
            print(f"{'':33}↳ {why}")
        print()

    print("讀法：「超額」＝實際前三率減去同馬群大細嘅期望前三率，單位 pp。")
    print("      正數＝呢批馬跑得好過同場數嘅平均。如果佢哋同時被放喺 60 以下，")
    print("      就係把尺嘅零點放錯位 —— 同 2026-08-01 段速分嗰個 bug 一樣。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
