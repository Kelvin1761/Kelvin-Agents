#!/usr/bin/env python3
"""profile 統計加落 jockey_trainer 維度嘅 isolated A/B。

單獨 ρ 唔夠 —— 要問嘅係「**加到現有 jockey_score 之上**有冇增益」，
因為 jockey_score 本身已經用緊同源嘅 lastYear 數字，好可能重複。

做法：把 profile 統計轉成場內 z-score，加落 jockey_score / trainer_score
（喺 leaf 層加，令 matrix 權重唔變）：
    adj = K × z_場內(feature)
只喺場內有足夠覆蓋（≥4 匹有數據）時施加，其餘完全唔改。

dev 85% / 未碰過 holdout 15%，同一把尺 eval_metrics.py。唯讀。
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV, normalize_horse_name, normalize_track_name, parse_int)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT = 0.15
MIN_COVER = 4
VENUE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+(.*?)(?:\s+Race\s+\d+-\d+)?$")


def slugify(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def load():
    profiles = json.loads((HERE / "au_profile_stats.json").read_text(encoding="utf-8"))
    table = defaultdict(dict)
    for key, rec in profiles.items():
        kind, slug = key.split("|", 1)
        table[kind][slug] = rec["stats"]

    # (date, track, race, horse) -> (jockey slug, trainer slug)
    people = {}
    with HISTORICAL_RESULTS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race, pos = parse_int(row.get("Race")), parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            people[(str(row.get("Date") or "").strip(),
                    normalize_track_name(row.get("Track") or ""), race,
                    normalize_horse_name(row.get("Horse") or ""))] = (
                slugify(row.get("Jockey")), slugify(row.get("Trainer")))

    races = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))["races"]
    matched = 0
    for race in races:
        m = VENUE.match(race["meeting"])
        tslug = normalize_track_name(m.group(1) if m else race["meeting"])
        for h in race["rows"]:
            key = (race["date"], tslug, race["race"], normalize_horse_name(h["name"] or ""))
            jk, tr = people.get(key, (None, None))
            h["_jockey"] = table["jockey"].get(jk) if jk else None
            h["_trainer"] = table["trainer"].get(tr) if tr else None
            matched += 1 if (h["_jockey"] or h["_trainer"]) else 0
    total = sum(len(r["rows"]) for r in races)
    print(f"races {len(races)}  runners {total}  有 profile {matched} ({100*matched/total:.0f}%)")
    return races


def zmap(race, side, stat):
    vals = [(i, float(h[side][stat])) for i, h in enumerate(race["rows"])
            if h.get(side) and h[side].get(stat) is not None]
    if len(vals) < MIN_COVER:
        return {}
    xs = [v for _, v in vals]
    mean = statistics.mean(xs)
    sd = statistics.pstdev(xs)
    if sd <= 0:
        return {}
    return {i: (v - mean) / sd for i, v in vals}


def score_fold(races, specs, k):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        adjust = defaultdict(float)
        if k:
            for side, stat, leaf in specs:
                for i, z in zmap(race, side, stat).items():
                    adjust[(i, leaf)] += k * z
        scored = []
        for i, h in enumerate(race["rows"]):
            feats = dict(h["features"])
            for leaf in ("jockey_score", "trainer_score"):
                delta = adjust.get((i, leaf))
                if delta:
                    feats[leaf] = clip_score(feats[leaf] + delta)
            mx = map_features_to_matrix_scores(feats)
            pure = 60.0 + sum((mx[key] - 60.0) * w for key, w in MATRIX_WEIGHTS.items())
            scored.append((pure + float(h["wet"] or 0.0), h["n"]))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        out.append(race_metrics(picks, top3, winner=winners[0] if winners else None,
                               actual_pos=actual_pos, field_size=race["field"]))
    return summarize_races(out)


def digest(s):
    r, c = s["rates"], s["competitiveness"]
    return {"gold": s["counts"]["gold"], "good_pos": round(100 * r["good_positional"], 2),
            "good_any2": round(100 * r["good_any2"], 2),
            "champ": round(100 * r["champion"], 2),
            "winT3": round(100 * r["winner_in_top3"], 2),
            "t3prec": round(100 * s["top3_precision"], 2), "mrr": round(s["mrr"], 4),
            "blowout": round(100 * c["top_pick_blowout"]["rate"], 2),
            "compet": round(100 * c["top_pick_competitive"]["rate"], 2),
            "ndcg5": round(c["mean_ndcg_at5"], 4)}


KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5")

# KPI 係包位（Gold/Good/Pass = 蓋住實際前三），所以理應用 place% 而唔係 win%。
# 前一輪只測咗 win% / ROI（兩個都係搵頭馬導向），結果買到 winT3 但蝕 good_any2 ——
# 特徵導向同目標唔夾。呢輪加返 place%。
VARIANTS = {
    "騎師 place%": [("_jockey", "placePercentage", "jockey_score")],
    "練馬師 place%": [("_trainer", "placePercentage", "trainer_score")],
    "兩邊 place%": [("_jockey", "placePercentage", "jockey_score"),
                    ("_trainer", "placePercentage", "trainer_score")],
    "兩邊 place%+ROI": [("_jockey", "placePercentage", "jockey_score"),
                        ("_jockey", "roi", "jockey_score"),
                        ("_trainer", "placePercentage", "trainer_score"),
                        ("_trainer", "roi", "trainer_score")],
    "騎師 win%（對照）": [("_jockey", "winPercentage", "jockey_score")],
    "兩邊 win%（對照）": [("_jockey", "winPercentage", "jockey_score"),
                        ("_trainer", "winPercentage", "trainer_score")],
}


def main():
    races = load()
    split = int(len(races) * (1 - HOLDOUT))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_fold(fold, [], 0.0))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'variant':22}" + "".join(f"{x:>13}" for x in KEYS))
        print(f"{'BASE':22}" + "".join(f"{base[x]:>13}" for x in KEYS))
        for label, specs in VARIANTS.items():
            for k in (2.0, 4.0, 6.0):
                d = digest(score_fold(fold, specs, k))
                cells = ""
                for x in KEYS:
                    delta = d[x] - base[x]
                    cells += (f"{d[x]:>7}({delta:+d})".rjust(13) if x == "gold"
                              else f"{d[x]:>7}{delta:+.2f}".rjust(13))
                print(f"{f'{label} K={k:g}':22}" + cells)


if __name__ == "__main__":
    main()
