#!/usr/bin/env python3
"""把一個候選特徵混入排名分，用 dev / fold 閘 / 未碰 holdout 量。

點解可以離線做：排名只睇**場內次序**，而 `ability + k·z(feature)` 對 feature
係線性嘅，所以一份評好分嘅語料就評估得到任何 k，唔使重跑引擎。同
`au_matrix_refit.py` 同一個道理。

紀律（呢個檔案存在嘅唯一理由就係強制執行佢）：
  * **時間排序** dev 85% / holdout 15%，holdout 由頭到尾唔參與揀 k
  * dev 內部再切 5 個時間 fold，一個 k 要**唔輸**先算過閘
  * z-score 係**場內**做 —— 全池標準化會把「呢場獎金高」當成「呢匹馬好」
  * 冇值嘅馬 z = 0（即係唔郁佢），唔可以當成最細值

⚠️ 「AUC 高」唔等於「加咗會贏」。一個同 `form_score` 高度重疊嘅特徵，AUC 靚
但加落去只係放大同一個訊號。所以呢度量嘅係**最終排名指標**，唔係 AUC。
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(AU_RACING.parent / "shared_racing"))

from au_leaf_power import norm, results_for  # noqa: E402
from au_unused_field_power import (RE_HDR_DIST, RE_RUNNER,  # noqa: E402
                                   runner_features)
from eval_metrics import race_metrics, summarize_races  # noqa: E402

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")


def build_races(scored_root, min_depth=4.0):
    """→ [(date, [(name, base_score, feats, placed, pos)], field_size)]，按日期排。"""
    from sb_backfill_archive import load_meeting_ids, scored_meeting_index

    meeting_dirs = scored_meeting_index(scored_root)
    cj = Path(scored_root).parent / "source_compare.json"
    # ⚠️ 2026-08-26：`source_compare.json` 唔存在嗰陣，`depth` 係空 dict，於是
    # 下面 `depth.get(name, 0) = 0 < min_depth(預設 4.0)` 對**每一個**場次都成立
    # —— 成份語料被靜靜隔走，輸出「0 場」，然後喺 `delta()` 度爆一個
    # 意義不明嘅 `TypeError: 'NoneType' object is not subscriptable`。
    # 表面睇落似「呢個特徵冇數據」，實情係個閘門掃走晒所有嘢。
    # 攞唔到深度資料就唔應該當「深度 = 0」，應該當「唔知」→ 唔篩。
    if cj.exists():
        depth = {d["meeting"]: d.get("form_depth", 0) for d in json.loads(cj.read_text())}
    else:
        depth = None
        if min_depth:
            print(f"⚠️  搵唔到 {cj.name}，冇 form depth 資料 → 唔做 --min-depth 篩選。",
                  file=sys.stderr)
    out = []
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        mdir = meeting_dirs.get(name)
        if mdir is None:
            continue
        if min_depth and depth is not None and depth.get(name, 0) < min_depth:
            continue
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(mdir / "Meeting_Auto_Scoring.csv", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), {})[
                    norm(row["horse_name"])] = row
        for fg in sorted(mdir.glob("*Formguide.md")):
            text = fg.read_text(encoding="utf-8", errors="replace")
            hm = RE_HDR_DIST.search(text)
            if not hm:
                continue
            rno, dist = int(hm.group(1)), int(hm.group(2))
            actual, rows = res.get(rno), by_race.get(rno)
            if not actual or not rows:
                continue
            starts = [m.start() for m in RE_RUNNER.finditer(text)]
            runners = []
            for i, m in enumerate(RE_RUNNER.finditer(text)):
                end = starts[i + 1] if i + 1 < len(starts) else len(text)
                key = norm(m.group(2))
                row, pos = rows.get(key), actual.get(key)
                if not row or pos is None:
                    continue
                runners.append((key, float(row["final_rank_score"]),
                                runner_features(text[m.start():end], dist, m.group(2)), pos))
            if len(runners) >= 4:
                out.append((meta["date"], runners))
    return out


def _zs(vals):
    """場內 z。全場一樣（或得一個）就全部 0 —— 冇分別即係冇資訊。"""
    have = [v for v in vals if v is not None]
    if len(have) < 2:
        return [0.0] * len(vals)
    m = statistics.mean(have)
    sd = statistics.pstdev(have)
    if sd <= 0:
        return [0.0] * len(vals)
    return [0.0 if v is None else (v - m) / sd for v in vals]


def evaluate(races, feats, k):
    rows = []
    for _, runners in races:
        adj = [0.0] * len(runners)
        for fname in feats:
            for i, z in enumerate(_zs([r[2].get(fname) for r in runners])):
                adj[i] += z
        scored = sorted(((base + k * a, key, pos)
                         for (key, base, _f, pos), a in zip(runners, adj)),
                        key=lambda x: -x[0])
        picks = [s[1] for s in scored]
        pos_map = {s[1]: s[2] for s in scored}
        top3 = {h for h, p in pos_map.items() if p <= 3}
        winner = next((h for h, p in pos_map.items() if p == 1), None)
        if not top3 or winner is None:
            continue
        rows.append(race_metrics(picks, top3, winner=winner, actual_pos=pos_map,
                                 field_size=max(pos_map.values())))
    if not rows:
        return None
    c = summarize_races(rows)["counts"]
    n = len(rows)
    hits = sum(r["hits"] for r in rows)
    slots = sum(min(3, len(r["picks"])) for r in rows)
    out = {key: 100.0 * c[key] / n for key in KEYS}
    out["t3prec"] = 100.0 * hits / slots
    out["races"] = n
    return out


def delta(a, b):
    return {key: a[key] - b[key] for key in list(KEYS) + ["t3prec"]}


def main():
    ap = argparse.ArgumentParser(description="候選特徵混入排名分嘅 isolated A/B")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--features", required=True,
                    help="逗號分隔，例如 dist_place_rate,jh_pre_place_rate")
    ap.add_argument("--min-depth", type=float, default=4.0)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--ks", default="0.25,0.5,1,1.5,2,3")
    args = ap.parse_args()

    feats = [f.strip() for f in args.features.split(",") if f.strip()]
    races = build_races(args.scored, args.min_depth)
    if not races:
        raise SystemExit(
            f"❌ 語料係空嘅（--scored {args.scored}，--min-depth {args.min_depth}）。\n"
            "   常見成因：--min-depth 篩得太緊，或者 scored root 指錯。\n"
            "   行落去只會喺 delta() 度爆一個意義不明嘅 TypeError，所以喺呢度停。")
    cut = int(len(races) * (1 - args.holdout))
    dev, hold = races[:cut], races[cut:]
    print(f"{len(races)} 場：dev {len(dev)} · holdout {len(hold)}（依時間排序）")
    print(f"特徵：{', '.join(feats)}\n")

    base_dev, base_hold = evaluate(dev, feats, 0.0), evaluate(hold, feats, 0.0)
    fold = len(dev) // args.folds
    best = None
    print(f"{'k':>6}{'dev t3prec':>12}{'dev winT3':>11}{'dev champ':>11}{'過閘 fold':>10}")
    for k in [float(x) for x in args.ks.split(",")]:
        d = delta(evaluate(dev, feats, k), base_dev)
        passed = 0
        for i in range(args.folds):
            seg = dev[i * fold:(i + 1) * fold] if i < args.folds - 1 else dev[i * fold:]
            b, c = evaluate(seg, feats, 0.0), evaluate(seg, feats, k)
            # 一個 fold 要「唔輸」先算過 —— 兩個主指標都唔可以跌
            if b and c and delta(c, b)["t3prec"] >= -0.01 \
                    and delta(c, b)["winner_in_top3"] >= -0.01:
                passed += 1
        print(f"{k:>6}{d['t3prec']:>+12.2f}{d['winner_in_top3']:>+11.2f}"
              f"{d['champion']:>+11.2f}{passed:>8}/{args.folds}")
        if passed >= args.folds - 1 and d["t3prec"] > 0 and (
                best is None or d["t3prec"] > best[1]["t3prec"]):
            best = (k, d)

    if not best:
        print("\n❌ 冇一個 k 過到 fold 閘 —— 唔好加。")
        return 0
    k = best[0]
    print(f"\n✅ 揀 k={k}（dev 最好 + 過閘）。而家先至碰 holdout：")
    hd = delta(evaluate(hold, feats, k), base_hold)
    print(f"{'指標':22}{'holdout Δ（百分點）':>20}")
    for key in list(KEYS) + ["t3prec"]:
        print(f"   {key:20}{hd[key]:>+18.2f}")
    # ⚠️ holdout 升幅大過 dev 係**洩漏**嘅典型訊號，唔係好消息。真特徵喺
    # 未見過嘅數據上通常收窄；一個含住答案嘅特徵喺邊度都一樣勁。實測
    # `in_win_range` 就係咁露餡：dev winT3 +6.63，holdout +17.58，而佢個
    # `WinRange` 欄位包含今日贏嗰仗。呢個閘攔唔到洩漏，只可以嘈。
    dd = delta(evaluate(dev, feats, k), base_dev)
    if hd["winner_in_top3"] > dd["winner_in_top3"] * 1.5 and dd["winner_in_top3"] > 0:
        print(f"\n⚠️ holdout 升幅（{hd['winner_in_top3']:+.2f}）大過 dev "
              f"（{dd['winner_in_top3']:+.2f}）好多 —— 查清楚個欄位係咪賽後先有值，"
              f"再信呢個結果。")
    good = sum(1 for key in ("t3prec", "winner_in_top3", "champion") if hd[key] > 0)
    print(f"\n{'✅ holdout 三個主指標 ' + str(good) + '/3 向上' if good >= 2 else '❌ holdout 唔支持 —— 唔好加'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
