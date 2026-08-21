#!/usr/bin/env python3
"""F1 — 馬群大細正規化入 `form_score` 嘅 isolated A/B（用戶 2026-07-31 提出）。

`_form_score` 現時用絕對名次定 base（1→100, 2→85, 3→75, ≤5→60, else→40），
唔理馬群幾大。量化：21.5% 嘅 run 拿錯 base、11.0% 錯 ≥20 分。

改法：有真實馬群大細嘅場次，改用場內百分位定 base
    pct = (place − 1) / (field − 1)        0.0 = 頭馬，1.0 = 最後
（同 eval_metrics.py 嘅 top_pick_pct 同一條公式，repo 內已有先例。）
冇馬群大細嘅場次完全唔改 —— 即係同 rollout 初期嘅實際行為一致。

真實馬群大細源自 AU_Historical_Raw_Race_Results.csv 逐 (date, track, race) 數行數，
覆蓋率約 11%（只有我哋抽過嘅 meeting）。Formguide 原文冇馬群大細，
要 extractor 補（Racenet results view 有「4th of 6」）。

其餘（class mult、decay、新馬試閘補充、劣績中性回歸）完全照原樣 replay。
唯讀。同一把尺 eval_metrics.py。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV,
    normalize_track_name,
    parse_int,
)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT_FRACTION = 0.15
DIST = re.compile(r"(\d+)")

# 百分位 → base 階梯。用同一組數值（100/85/75/60/40），只係改用百分位而唔係
# 絕對名次做入口，令「唔同馬群大細嘅同一名次」唔再拿同一個分。
# 邊界由現行階梯反推 12 匹標準場：2/12→0.09、3/12→0.18、5/12→0.36。
PCT_LADDER = ((0.0, 100), (0.12, 85), (0.25, 75), (0.50, 60), (1.01, 40))


def pct_base(pct):
    for edge, points in PCT_LADDER:
        if pct <= edge:
            return points
    return 40


def field_size_truth():
    counts = Counter()
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if race and pos:
                counts[(str(row.get("Date") or "").strip(),
                        normalize_track_name(row.get("Track") or ""), race)] += 1
    return counts


def load_scraped():
    """{(horse_slug, date, venue_slug): field} 由 au_starters_backfill.py 抽到嘅場次。"""
    path = HERE / "au_starters_backfill.json"
    if not path.exists():
        return {}
    store = json.loads(path.read_text(encoding="utf-8")).get("races", {})
    out = {}
    for rows in store.values():
        for r in rows:
            if r.get("starters") and r.get("horse") and r.get("date"):
                key = (str(r["horse"]).strip().lower(), r["date"],
                       normalize_track_name(r.get("venue") or ""))
                out[key] = int(r["starters"])
    return out


def load_lastfinish():
    path = HERE / "au_lastfinish_cache.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load(truth):
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    scraped = load_scraped()
    lastfin = load_lastfinish()
    src = Counter()
    index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            lf = lastfin.get(f"{race['meeting']}|{race['race']}|{h['n']}")
            for run in h["runs"]:
                run["_field"] = None
                place, venue = run.get("place"), run.get("venue") or ""
                if not place:
                    continue
                vslug = normalize_track_name(venue)
                # 1) 我哋自己嘅結果庫（最可靠，逐 (date, track, race) 數行數）
                if run.get("race_no"):
                    f = truth.get((run["date"], vslug, run["race_no"]))
                    if f and f >= 2 and place <= f:
                        run["_field"] = f
                        src["results_csv"] += 1
                        continue
                # 2) 直接由 Racenet 抽到嘅 eventStarters
                f = scraped.get((str(h["name"]).strip().lower(), run["date"], vslug))
                if f and f >= 2 and place <= f:
                    run["_field"] = f
                    src["scraped"] += 1
                    continue
                # 3) last_finish_line —— 只覆蓋最近一仗，而且可能指向試閘，
                #    所以一定要 場地 + 路程 + 名次 三者都對得上先用。
                if lf:
                    dm = DIST.search(str(run.get("distance") or ""))
                    dist = int(dm.group(1)) if dm else None
                    if (lf["place"] == place and dist == lf["distance"]
                            and normalize_track_name(lf["venue"]) == vslug
                            and lf["field"] >= 2 and place <= lf["field"]):
                        run["_field"] = lf["field"]
                        src["last_finish"] += 1
            index[(race["meeting"], race["race"], h["n"])] = h["runs"]
    for race in leaf["races"]:
        for h in race["rows"]:
            h["_runs"] = index.get((race["meeting"], race["race"], h["n"]), [])
    print("馬群大細來源:", dict(src))
    return leaf["races"]


def form_replay(rows, extra_bonus, runs, *, use_pct, blend=1.0):
    if not rows:
        return None
    num = den = 0.0
    for i, row in enumerate(rows):
        base = float(row["base"])
        if use_pct and i < len(runs):
            run = runs[i]
            if (run.get("place") == row.get("place") and run.get("_field")):
                pct = (run["place"] - 1) / (run["_field"] - 1)
                new = float(pct_base(pct))
                base = base + blend * (new - base)
        num += base * float(row["mult"]) * float(row["decay"])
        den += float(row["decay"])
    score = clip_score(num / den) if den else 60.0
    score = clip_score(score + extra_bonus)
    n = len(rows)
    if n and score < 60.0:
        score = 60.0 + (score - 60.0) * (n / (n + 2.0))
    return clip_score(score)


def score_races(races, *, use_pct, blend=1.0):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            rows = h.get("form_rows_detail") or []
            if rows:
                new = form_replay(rows, h["_extra_bonus"], h["_runs"],
                                  use_pct=use_pct, blend=blend)
                if new is not None:
                    feats["form_score"] = new
            matrix = map_features_to_matrix_scores(feats)
            pure = 60.0 + sum((matrix[k] - 60.0) * w for k, w in MATRIX_WEIGHTS.items())
            scored.append((pure + float(h["wet"] or 0.0), h["n"]))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        out.append(race_metrics(picks, actual_top3,
                               winner=winners[0] if winners else None,
                               actual_pos=actual_pos, field_size=race["field"]))
    return summarize_races(out)


def digest(s):
    r, c = s["rates"], s["competitiveness"]
    return {
        "gold": s["counts"]["gold"],
        "good_pos": round(100 * r["good_positional"], 2),
        "good_any2": round(100 * r["good_any2"], 2),
        "champ": round(100 * r["champion"], 2),
        "winT3": round(100 * r["winner_in_top3"], 2),
        "t3prec": round(100 * s["top3_precision"], 2),
        "mrr": round(s["mrr"], 4),
        "blowout": round(100 * c["top_pick_blowout"]["rate"], 2),
        "compet": round(100 * c["top_pick_competitive"]["rate"], 2),
        "ndcg5": round(c["mean_ndcg_at5"], 4),
    }


KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def main():
    races = load(field_size_truth())

    total_runs = changed = horses = horses_changed = 0
    for race in races:
        for h in race["rows"]:
            horses += 1
            rows = h.get("form_rows_detail") or []
            hit = False
            for i, row in enumerate(rows):
                total_runs += 1
                if i < len(h["_runs"]):
                    run = h["_runs"][i]
                    if run.get("place") == row.get("place") and run.get("_field"):
                        pct = (run["place"] - 1) / (run["_field"] - 1)
                        if pct_base(pct) != int(row["base"]):
                            changed += 1
                            hit = True
            horses_changed += 1 if hit else 0
    print(f"races {len(races)}  horses {horses}  計分 runs {total_runs}")
    print(f"base 有改動嘅 runs: {changed} ({100*changed/max(1,total_runs):.1f}%)"
          f"；受影響馬匹: {horses_changed} ({100*horses_changed/max(1,horses):.1f}%)")

    # 保真度：use_pct=False 必須完全重現存檔 form_score
    drift = sum(
        1 for race in races for h in race["rows"]
        if (h.get("form_rows_detail")
            and abs(form_replay(h["form_rows_detail"], h["_extra_bonus"], h["_runs"],
                                use_pct=False) - h["features"]["form_score"]) > 0.05)
    )
    print(f"form_score faithful replay drift: {drift}/{horses}"
          f" = {100*drift/max(1,horses):.2f}%\n")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold, use_pct=False))
        print(f"===== {name} ({len(fold)} races) =====")
        print(f"{'config':20}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':20}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for blend in (0.5, 1.0):
            d = digest(score_races(fold, use_pct=True, blend=blend))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'pct blend={blend}':20}" + cells)
        print()


if __name__ == "__main__":
    main()
