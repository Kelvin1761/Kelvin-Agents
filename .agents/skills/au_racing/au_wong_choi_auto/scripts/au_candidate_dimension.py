#!/usr/bin/env python3
"""把候選特徵當作**新維度**放入矩陣度試（唔係當加數項）。

點解要分開試：`au_feature_ab.py` 試嘅係 `ability + k·z(feature)` —— 個特徵係
**額外加**上去，其他維度嘅權重冇動。真正加一個維度係**攤薄**其他維度：
新維度攞 w，其餘按比例縮到 (1−w)。兩者數學上唔同，結論可以唔同。

歷史 scan 只准用賽前逐行往績重建嘅候選，例如 `dist_place_rate` 同
`jh_pre_place_rate`。Sportsbet career overview 會賽後刷新，唔准用嚟驗證。
呢度用新維度形式測真正嘅 incremental value。

紀律同 refit 一樣：dev 85% / holdout 15% 依時間切，dev 內 5 fold 閘，
holdout 唔參與揀 w。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(AU_RACING.parent / "shared_racing"))

from au_leaf_power import norm, results_for  # noqa: E402
from au_unused_field_power import (RE_HDR_DIST, RE_RUNNER,  # noqa: E402
                                   runner_features)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")


def build(scored_root, feature, min_depth=4.0):
    from sb_backfill_archive import load_meeting_ids, scored_meeting_index

    meeting_dirs = scored_meeting_index(scored_root)
    cj = Path(scored_root).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})
    out = []
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        md = meeting_dirs.get(name)
        if md is None:
            continue
        if min_depth and depth.get(name, 0) < min_depth:
            continue
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(md / "Meeting_Auto_Scoring.csv", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), {})[
                    norm(row["horse_name"])] = row
        for fg in sorted(md.glob("*Formguide.md")):
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
                blk = text[m.start():end]
                jm = re.search(r"\|\s*J:\s*([^(\n|]+)", blk)
                f = runner_features(blk, dist, m.group(2),
                                    jm.group(1).strip() if jm else "")
                feats = {k: float(row[k]) for k in row
                         if k.endswith("_score") and row[k] not in (None, "")}
                runners.append({"name": key, "pos": pos, "features": feats,
                                "wet": float(row.get("wet_form_feature") or 0.0),
                                "x": f.get(feature)})
            if len(runners) >= 4:
                out.append(runners)
    return out


def _dim_score(vals):
    """候選特徵 → 60-centred 維度分（同其他維度同一把尺）。

    場內 z × 12 + 60：12 係令佢嘅場內散佈大致同現有維度同級。冇值 → 60（中性），
    唔可以當最細值 —— 「唔知」唔係「差」。
    """
    have = [v for v in vals if v is not None]
    if len(have) < 2:
        return [60.0] * len(vals)
    m, sd = statistics.mean(have), statistics.pstdev(have)
    if sd <= 0:
        return [60.0] * len(vals)
    return [60.0 if v is None else 60.0 + 12.0 * (v - m) / sd for v in vals]


def evaluate(races, w_new):
    base = {k: v * (1.0 - w_new) for k, v in MATRIX_WEIGHTS.items()}
    rows = []
    for runners in races:
        dim = _dim_score([r["x"] for r in runners])
        scored = []
        for r, d in zip(runners, dim):
            m = map_features_to_matrix_scores(r["features"])
            a = sum(m.get(k, 60.0) * v for k, v in base.items()) + d * w_new + r["wet"]
            scored.append((a, r["name"], r["pos"]))
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
    o = {k: 100.0 * c[k] / n for k in KEYS}
    o["t3prec"] = 100.0 * hits / slots
    return o


def main():
    ap = argparse.ArgumentParser(description="候選特徵當新維度試")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--feature", required=True)
    ap.add_argument("--ws", default="0.03,0.05,0.08,0.12,0.18")
    ap.add_argument("--min-depth", type=float, default=4.0)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    races = build(args.scored, args.feature, args.min_depth)
    cut = int(len(races) * (1 - args.holdout))
    dev, hold = races[:cut], races[cut:]
    have = sum(1 for r in races for x in r if x["x"] is not None)
    tot = sum(len(r) for r in races)
    print(f"{len(races)} 場（dev {len(dev)} / holdout {len(hold)}）· "
          f"特徵 `{args.feature}` 有值 {have}/{tot} = {have/tot:.0%}\n")

    bd = evaluate(dev, 0.0)
    fold = len(dev) // args.folds
    best = None
    print(f"{'新維度權重':>10}{'dev t3prec':>12}{'dev winT3':>11}{'dev champ':>11}{'過閘':>8}")
    for w in [float(x) for x in args.ws.split(",")]:
        c = evaluate(dev, w)
        d = {k: c[k] - bd[k] for k in list(KEYS) + ["t3prec"]}
        passed = 0
        for i in range(args.folds):
            seg = dev[i*fold:(i+1)*fold] if i < args.folds-1 else dev[i*fold:]
            b, cc = evaluate(seg, 0.0), evaluate(seg, w)
            if b and cc and cc["t3prec"] - b["t3prec"] >= -0.01 \
                    and cc["winner_in_top3"] - b["winner_in_top3"] >= -0.01:
                passed += 1
        print(f"{w:>10.2f}{d['t3prec']:>+12.2f}{d['winner_in_top3']:>+11.2f}"
              f"{d['champion']:>+11.2f}{passed:>6}/{args.folds}")
        if passed >= args.folds - 1 and d["t3prec"] > 0 and (
                best is None or d["t3prec"] > best[1]["t3prec"]):
            best = (w, d)

    if not best:
        print("\n❌ 冇一個權重過到 fold 閘 —— 唔好加。")
        return 0
    w = best[0]
    bh = evaluate(hold, 0.0)
    ch = evaluate(hold, w)
    hd = {k: ch[k] - bh[k] for k in list(KEYS) + ["t3prec"]}
    print(f"\n✅ 揀 w={w}。而家先碰 holdout：")
    for k in list(KEYS) + ["t3prec"]:
        print(f"   {k:20}{hd[k]:>+9.2f}")
    up = sum(1 for k in ("t3prec", "winner_in_top3", "champion") if hd[k] > 0)
    dd = best[1]
    if hd["winner_in_top3"] > dd["winner_in_top3"] * 1.5 and dd["winner_in_top3"] > 0:
        print("\n⚠️ holdout 升幅大過 dev —— 查清楚個欄位係咪賽後先有值。")
    print(f"\n{'✅ holdout 支持' if up >= 2 else '❌ holdout 唔支持 —— 唔好加'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
