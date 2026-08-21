#!/usr/bin/env python3
"""F1+F2 合併 A/B —— 馬群大細正規化 **同** 輸距扣分一齊做。

用戶 2026-07-31 指正：之前將兩者當成獨立 toggle 分開測係錯嘅，佢們互補 ——

  Benbulben Casterton  4/6  輸 12.0L → 百分位 0.60 → base 60→40  ✓ 兩者同向
  Benbulben Swan Hill  6/12 輸 9.05L → 百分位 0.45 → base 40→**60** ✗ 馬群令佢升，
                                       但輸 9L 係災難 → 要靠輸距扣返落去

即係「位置」同「距離」量度兩件唔同嘅嘢：位置講你喺場內排第幾，
輸距講你同頭馬差幾遠。9L 落後嘅中游位置唔應該當成中性。

數據：`AU_Historical_Raw_Race_Results.csv` 有 `Margin` 欄，
而馬群大細由同一個 CSV 逐 (date, track, race) 數行數得出 —— 同一批 run
兩個欄位都齊，零 scraping。另補 Facts 表輸距（2026-05+）同
`last_finish_line` 馬群大細（88.4%）。

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
    normalize_horse_name,
    normalize_track_name,
    parse_int,
)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT_FRACTION = 0.15
DIST = re.compile(r"(\d+)")
MARGIN_L = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*L")

PCT_LADDER = ((0.0, 100), (0.12, 85), (0.25, 75), (0.50, 60), (1.01, 40))


def pct_base(pct):
    for edge, points in PCT_LADDER:
        if pct <= edge:
            return points
    return 40


def load_results():
    """(field size, per-horse margin) off the shared results CSV."""
    field = Counter()
    margin = {}
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            key3 = (str(row.get("Date") or "").strip(),
                    normalize_track_name(row.get("Track") or ""), race)
            field[key3] += 1
            m = MARGIN_L.search(str(row.get("Margin") or ""))
            margin[key3 + (normalize_horse_name(row.get("Horse") or ""),)] = (
                abs(float(m.group(1))) if m else (0.0 if pos == 1 else None)
            )
    return field, margin


def load(field_truth, margin_truth):
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    lastfin = (json.loads((HERE / "au_lastfinish_cache.json").read_text(encoding="utf-8"))
               if (HERE / "au_lastfinish_cache.json").exists() else {})
    src = Counter()
    index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            lf = lastfin.get(f"{race['meeting']}|{race['race']}|{h['n']}")
            hslug = normalize_horse_name(h["name"] or "")
            for run in h["runs"]:
                run["_field"] = None
                run["_margin"] = run.get("margin")
                place = run.get("place")
                if not place:
                    continue
                vslug = normalize_track_name(run.get("venue") or "")
                key3 = (run["date"], vslug, run.get("race_no"))
                f = field_truth.get(key3)
                if f and f >= 2 and place <= f:
                    run["_field"] = f
                    src["field:results_csv"] += 1
                elif lf:
                    dm = DIST.search(str(run.get("distance") or ""))
                    dist = int(dm.group(1)) if dm else None
                    if (lf["place"] == place and dist == lf["distance"]
                            and normalize_track_name(lf["venue"]) == vslug
                            and lf["field"] >= 2 and place <= lf["field"]):
                        run["_field"] = lf["field"]
                        src["field:last_finish"] += 1
                if run["_margin"] is None:
                    mv = margin_truth.get(key3 + (hslug,))
                    if mv is not None:
                        run["_margin"] = mv
                        src["margin:results_csv"] += 1
                elif run["_margin"] is not None:
                    src["margin:facts"] += 1
            index[(race["meeting"], race["race"], h["n"])] = h["runs"]
    for race in leaf["races"]:
        for h in race["rows"]:
            h["_runs"] = index.get((race["meeting"], race["race"], h["n"]), [])
    print("來源:", dict(src))
    return leaf["races"]


def form_replay(rows, extra_bonus, runs, *, use_pct, margin_cfg):
    if not rows:
        return None
    num = den = 0.0
    for i, row in enumerate(rows):
        base = float(row["base"])
        run = runs[i] if i < len(runs) else None
        matched = run is not None and run.get("place") == row.get("place")
        if matched and use_pct and run.get("_field"):
            pct = (run["place"] - 1) / (run["_field"] - 1)
            base = float(pct_base(pct))
        if matched and margin_cfg and run.get("_margin") is not None:
            dm = DIST.search(str(run.get("distance") or ""))
            dist_km = (int(dm.group(1)) / 1000.0) if dm else None
            if dist_km and dist_km > 0:
                mpk = abs(float(run["_margin"])) / dist_km
                free, scale, cap = margin_cfg
                base = clip_score(base - min(cap, scale * max(0.0, mpk - free)))
        num += base * float(row["mult"]) * float(row["decay"])
        den += float(row["decay"])
    score = clip_score(num / den) if den else 60.0
    score = clip_score(score + extra_bonus)
    n = len(rows)
    if n and score < 60.0:
        score = 60.0 + (score - 60.0) * (n / (n + 2.0))
    return clip_score(score)


def score_races(races, *, use_pct=False, margin_cfg=None):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            rows = h.get("form_rows_detail") or []
            if rows and (use_pct or margin_cfg):
                new = form_replay(rows, h["_extra_bonus"], h["_runs"],
                                 use_pct=use_pct, margin_cfg=margin_cfg)
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
    return {"gold": s["counts"]["gold"],
            "good_pos": round(100 * r["good_positional"], 2),
            "good_any2": round(100 * r["good_any2"], 2),
            "champ": round(100 * r["champion"], 2),
            "winT3": round(100 * r["winner_in_top3"], 2),
            "t3prec": round(100 * s["top3_precision"], 2),
            "mrr": round(s["mrr"], 4),
            "blowout": round(100 * c["top_pick_blowout"]["rate"], 2),
            "compet": round(100 * c["top_pick_competitive"]["rate"], 2),
            "ndcg5": round(c["mean_ndcg_at5"], 4)}


KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")


def main():
    field_truth, margin_truth = load_results()
    races = load(field_truth, margin_truth)

    runs = fcov = mcov = both = 0
    for race in races:
        for h in race["rows"]:
            for i, row in enumerate(h.get("form_rows_detail") or []):
                runs += 1
                if i >= len(h["_runs"]):
                    continue
                r = h["_runs"][i]
                if r.get("place") != row.get("place"):
                    continue
                f = bool(r.get("_field"))
                m = r.get("_margin") is not None
                fcov += f
                mcov += m
                both += (f and m)
    print(f"計分 runs {runs}：有馬群 {fcov} ({100*fcov/max(1,runs):.1f}%)、"
          f"有輸距 {mcov} ({100*mcov/max(1,runs):.1f}%)、兩者齊 {both} "
          f"({100*both/max(1,runs):.1f}%)\n")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    configs = [
        ("F1 只馬群", {"use_pct": True}),
        ("F2 只輸距 s8c15", {"margin_cfg": (0.5, 8.0, 15.0)}),
        ("F1+F2 s4c15", {"use_pct": True, "margin_cfg": (0.5, 4.0, 15.0)}),
        ("F1+F2 s8c15", {"use_pct": True, "margin_cfg": (0.5, 8.0, 15.0)}),
        ("F1+F2 s8c25", {"use_pct": True, "margin_cfg": (0.5, 8.0, 25.0)}),
        ("F1+F2 s12c25", {"use_pct": True, "margin_cfg": (0.5, 12.0, 25.0)}),
    ]
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold))
        print(f"===== {name} ({len(fold)} races) =====")
        print(f"{'config':18}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':18}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, kw in configs:
            d = digest(score_races(fold, **kw))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:18}" + cells)
        print()


if __name__ == "__main__":
    main()
