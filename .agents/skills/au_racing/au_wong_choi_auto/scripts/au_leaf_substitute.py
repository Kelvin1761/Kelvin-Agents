#!/usr/bin/env python3
"""把一個 leaf 換成另一個算法，量最終排名指標。

點解需要：`au_leaf_power.py` 量到一個**簡單收縮上名率**（0.615）好過引擎個
`trainer_score`（0.571），濕地更加係 0.629 vs 0.571。但「單獨 AUC 高」唔等於
「換咗之後排名會好」—— 個 leaf 喺矩陣入面同其他 leaf 混，可能重疊。所以要
真真正正換咗佢再量排名。

引擎個 `_trainer_score` 係 base（統一上名率）+ 一層 micro adjustment
（場館成績、Waller 首戰…）。呢個測試等於問：**淨用 base、剷走 adjustment，
會唔會更好？**

紀律同其他測試一樣：dev 85% / holdout 15% 依時間切，dev 內 5 fold 閘。
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
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(AU_RACING.parent / "shared_racing"))

from au_leaf_power import norm, results_for  # noqa: E402
from au_people_going_power import place_rate  # noqa: E402
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

KEYS = ("gold", "good_positional", "good_any2", "pass_any1", "champion",
        "winner_in_top3")


def to_leaf(rate, lo=0.20, hi=0.50):
    """上名率 → 60-centred leaf 分。

    ⚠️ 尺一定要同其他 leaf 同級（散佈相近），否則換咗個 leaf 等於偷偷改咗
    佢喺矩陣入面嘅實際影響力，就唔再係一個乾淨嘅 A/B。0.20–0.50 係實測
    上名率嘅主體範圍，映去 40–80。
    """
    if rate is None:
        return 60.0
    x = max(lo, min(hi, rate))
    return 40.0 + (x - lo) / (hi - lo) * 40.0


def build(scored_root, min_depth=4.0):
    """每場 → [(name, features, wet, pos, sub_scores)]。"""
    from claw_sportsbet_form import (BASE, SportsbetFormFetcher, _match_person,
                                     parse_race)
    from sb_backfill_archive import load_meeting_ids
    import sb_people_stats

    cache = sb_people_stats.load_cache()
    cj = Path(scored_root).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    out = []
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        p = Path(scored_root) / name / "Meeting_Auto_Scoring.csv"
        if not p.exists() or (min_depth and depth.get(name, 0) < min_depth):
            continue
        res = results_for(meta)
        if not res:
            continue
        by_race = {}
        with open(p, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                by_race.setdefault(int(row["race_number"]), []).append(row)
        for rid in meta["races"]:
            url = f"{BASE}/{meta['meetingId']}/{rid}/"
            if not f._cache_path(url).exists():
                continue
            pr = parse_race(f.get(url))
            rno = pr["meta"].get("race_number")
            actual, rows = res.get(rno), by_race.get(rno)
            if not actual or not rows:
                continue
            people = pr["meta"].get("people_by_name") or {}
            ov = {v.get("name", "").lower(): v for v in pr["overview"].values()}
            runners = []
            for r in rows:
                pos = actual.get(norm(r["horse_name"]))
                if pos is None:
                    continue
                feats = {k: float(v) for k, v in r.items()
                         if k.endswith("_score") and v not in (None, "")}
                o = ov.get(r["horse_name"].lower(), {})
                sub = {}
                for kind, leaf in (("Trainer", "trainer_score"),
                                   ("Jockey", "jockey_score")):
                    pid = _match_person(people, kind, o.get(kind.lower()) or "")
                    st = (cache.get(f"{kind.lower()}|{pid}") or {}).get("stats") if pid else None
                    sub[leaf] = to_leaf(place_rate(st, "12 Months") if st else None)
                runners.append((r["horse_name"], feats, float(r.get("wet_form_feature") or 0.0),
                                pos, sub))
            if len(runners) >= 4:
                out.append(runners)
    return out


def evaluate(races, swap=()):
    rows = []
    for runners in races:
        scored = []
        for nm, feats, wet, pos, sub in runners:
            ff = dict(feats)
            for leaf in swap:
                if leaf in sub:
                    ff[leaf] = sub[leaf]
            m = map_features_to_matrix_scores(ff)
            a = sum(m.get(k, 60.0) * w for k, w in MATRIX_WEIGHTS.items()) + wet
            scored.append((a, nm, pos))
        scored.sort(key=lambda x: -x[0])
        picks = [s[1] for s in scored]
        pm = {s[1]: s[2] for s in scored}
        top3 = {h for h, p in pm.items() if p <= 3}
        win = next((h for h, p in pm.items() if p == 1), None)
        if not top3 or win is None:
            continue
        rows.append(race_metrics(picks, top3, winner=win, actual_pos=pm,
                                 field_size=max(pm.values())))
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
    ap = argparse.ArgumentParser(description="換 leaf 算法，量排名")
    ap.add_argument("--scored", required=True)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    races = build(args.scored)
    cut = int(len(races) * (1 - args.holdout))
    dev, hold = races[:cut], races[cut:]
    print(f"{len(races)} 場（dev {len(dev)} / holdout {len(hold)}）\n")

    variants = [("換 trainer_score", ("trainer_score",)),
                ("換 jockey_score", ("jockey_score",)),
                ("兩個都換", ("trainer_score", "jockey_score"))]
    fold = len(dev) // args.folds
    for nm, sub in (("dev", dev), ("holdout（未碰）", hold)):
        base = evaluate(sub)
        print(f"===== {nm} =====")
        print(f"{'':20}{'gold':>8}{'good_pos':>10}{'any2':>8}{'champ':>8}{'winT3':>8}{'t3prec':>9}{'過閘':>8}")
        for label, swap in variants:
            c = evaluate(sub, swap)
            d = {k: c[k] - base[k] for k in list(KEYS) + ["t3prec"]}
            passed = ""
            if nm == "dev":
                ok = 0
                for i in range(args.folds):
                    seg = dev[i*fold:(i+1)*fold] if i < args.folds-1 else dev[i*fold:]
                    b, cc = evaluate(seg), evaluate(seg, swap)
                    if b and cc and cc["t3prec"] - b["t3prec"] >= -0.01 \
                            and cc["winner_in_top3"] - b["winner_in_top3"] >= -0.01:
                        ok += 1
                passed = f"{ok}/{args.folds}"
            print(f"{label:20}" + "".join(
                f"{d[k]:>+8.2f}" if k != 'good_positional' else f"{d[k]:>+10.2f}"
                for k in ('gold','good_positional','good_any2','champion','winner_in_top3','t3prec'))
                + f"{passed:>9}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
