#!/usr/bin/env python3
"""把一個 leaf 換成另一個算法，量最終排名指標。

點解需要：`au_leaf_power.py` 量到一個**簡單收縮上名率**好過引擎個
`trainer_score`。但「單獨 AUC 高」唔等於「換咗之後排名會好」—— 個 leaf 喺
矩陣入面同其他 leaf 混，可能重疊。所以要真真正正換咗佢再量排名。

⚠️ **AUC 差距係 1.0pp，唔係 4.4pp。** 呢個 docstring 以前寫住
「簡單公式 0.615 vs 引擎 0.571」，而嗰個係**跨語料比較** —— 0.571 喺 LY 只填
81% 嘅語料量，0.615 喺 96.8% 嘅語料量。同一語料量返：trainer 0.605 vs 0.615
（1.0pp）、jockey 0.600 vs 0.599（0.001）。所以呢個測試問嘅係一個**邊際**改善，
唔係修一個壞掉嘅 leaf。

紀律：dev 85% / holdout 15% 依時間切、dev 內 5 fold 閘、**加 walk-forward 5 窗**。
walk-forward 係後來加嘅，因為同日 `au_inner_weights.py` 出現過一個
dev 升 + holdout 升 + SD 對照過 + AUC 支持嘅候選，逐窗一睇就散（3/5）——
喺同一批數據上切出嚟嘅幾個檢查會一齊錯。

`--cache` 把 build 結果寫落 JSON。build 要 parse 全部 cached 賽事頁（~15 分鐘），
而調閘門唔應該每次都等嗰十五分鐘。
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

KEYS = ("gold", "good_positional", "pass", "champion", "winner_in_top3")


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
    from sb_backfill_archive import load_meeting_ids, scored_meeting_index
    import sb_people_stats

    cache = sb_people_stats.load_cache()
    cj = Path(scored_root).parent / "source_compare.json"
    depth = ({d["meeting"]: d.get("form_depth", 0)
              for d in json.loads(cj.read_text())} if cj.exists() else {})
    f = SportsbetFormFetcher(delay=0.0, verbose=False)
    meeting_dirs = scored_meeting_index(scored_root)
    out = []
    for name, meta in sorted(load_meeting_ids().items(), key=lambda kv: kv[1]["date"]):
        meeting_dir = meeting_dirs.get(name)
        if meeting_dir is None or (min_depth and depth.get(name, 0) < min_depth):
            continue
        p = meeting_dir / "Meeting_Auto_Scoring.csv"
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
    ap.add_argument("--cache", help="build 結果嘅 JSON；有就讀，冇就寫")
    args = ap.parse_args()

    cache = Path(args.cache) if args.cache else None
    if cache and cache.exists():
        races = [[(n, f, w, p, s) for n, f, w, p, s in r]
                 for r in json.loads(cache.read_text())]
        print(f"（由 {cache.name} 讀返 {len(races)} 場）")
    else:
        races = build(args.scored)
        if cache:
            cache.write_text(json.dumps(races))
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
        print(f"{'':20}{'gold':>8}{'good':>10}{'pass':>8}{'champ':>8}{'winT3':>8}{'t3prec':>9}{'過閘':>8}")
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
                for k in ('gold','good_positional','pass','champion','winner_in_top3','t3prec'))
                + f"{passed:>9}")
        print()

    # ── walk-forward：5 個依時間嘅窗，逐窗都唔准退步 ─────────────────────
    # dev/holdout 同 5-fold 都係喺同一次切割上做，所以佢哋會一齊被同一個
    # 時期特性騙倒。walk-forward 換一個切法再問一次。
    print("===== walk-forward（5 窗，依時間）=====")
    wn = len(races) // 5
    print(f"{'':20}" + "".join(f"{i + 1:>10}" for i in range(5)) + f"{'過閘':>8}")
    for label, swap in variants:
        cells, ok = [], 0
        for i in range(5):
            seg = races[i * wn:(i + 1) * wn] if i < 4 else races[i * wn:]
            b, c = evaluate(seg), evaluate(seg, swap)
            if not b or not c:
                cells.append("     n/a")
                continue
            good = (c["t3prec"] - b["t3prec"] >= -0.01
                    and c["winner_in_top3"] - b["winner_in_top3"] >= -0.01)
            ok += good
            cells.append(f"{c['t3prec'] - b['t3prec']:>+9.2f}" + ("✅" if good else "❌"))
        print(f"{label:20}" + "".join(f"{c:>10}" for c in cells) + f"{ok:>6}/5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
