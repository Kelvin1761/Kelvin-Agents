#!/usr/bin/env python3
"""合併估算：S1（PI 競爭力封頂）＋ F3（獎金班次調整）一齊落，713 場，同一把尺。

點解要呢個：archive 重跑只量到 S1+S2（舊 Facts 冇馬群/獎金欄），
但 F3 先係唯一 shadow A/B 兩邊 fold 都正嘅修正。呢度用本地 cache
（獎金由 Formguide 抽返，PI 由走位軌跡算）估算兩者一齊落嘅效果。

⚠️ 呢個係 shadow 估算，唔係真引擎重跑：S2（L600 口徑）冇包括喺內，
而且 F1（馬群大細）只有 33% 覆蓋。真實效果要等新 meeting 累積先量得準。

唯讀。
"""
from __future__ import annotations

import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV, normalize_horse_name, normalize_track_name, parse_int)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, SECTIONAL_MICRO_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT = 0.15
DIST = re.compile(r"(\d+)")
ML = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*L")
W = SECTIONAL_MICRO_WEIGHTS
K = 10.0
MAX_L = 3.0
DECAY = (1.0, 0.8, 0.6, 0.4)


def load_results():
    field, margin = {}, {}
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race, pos = parse_int(row.get("Race")), parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            k3 = (str(row.get("Date") or "").strip(),
                  normalize_track_name(row.get("Track") or ""), race)
            field[k3] = field.get(k3, 0) + 1
            m = ML.search(str(row.get("Margin") or ""))
            margin[k3 + (normalize_horse_name(row.get("Horse") or ""),)] = (
                abs(float(m.group(1))) if m else (0.0 if pos == 1 else None))
    return field, margin


def prize_level(runs):
    official = [r for r in runs if not r.get("is_trial") and r.get("prize")]
    if not official:
        return None
    num = den = 0.0
    for run, w in zip(official[:4], DECAY):
        num += math.log10(max(1000.0, float(run["prize"]))) * w
        den += w
    return num / den if den else None


def load():
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    prize = json.loads((HERE / "au_prize_cache.json").read_text(encoding="utf-8"))
    lastfin = json.loads((HERE / "au_lastfinish_cache.json").read_text(encoding="utf-8"))
    field_truth, margin_truth = load_results()
    runs_index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            lf = lastfin.get(f"{race['meeting']}|{race['race']}|{h['n']}")
            hslug = normalize_horse_name(h["name"] or "")
            for run in h["runs"]:
                legs = run.get("legs") or {}
                run["_pi"] = (legs["settled"] - legs["finish"]
                              if "settled" in legs and "finish" in legs else None)
                run["_field"] = None
                run["_margin"] = run.get("margin")
                place = run.get("place")
                if not place:
                    continue
                vslug = normalize_track_name(run.get("venue") or "")
                k3 = (run["date"], vslug, run.get("race_no"))
                f = field_truth.get(k3)
                if f and f >= 2 and place <= f:
                    run["_field"] = f
                elif lf:
                    dm = DIST.search(str(run.get("distance") or ""))
                    if (lf["place"] == place and dm and int(dm.group(1)) == lf["distance"]
                            and normalize_track_name(lf["venue"]) == vslug
                            and lf["field"] >= 2 and place <= lf["field"]):
                        run["_field"] = lf["field"]
                if run["_margin"] is None:
                    run["_margin"] = margin_truth.get(k3 + (hslug,))
            runs_index[(race["meeting"], race["race"], h["n"])] = h["runs"]
    for race in leaf["races"]:
        levels = []
        for h in race["rows"]:
            h["_runs"] = runs_index.get((race["meeting"], race["race"], h["n"]), [])
            rec = prize.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}
            h["_prize"] = prize_level(rec.get("runs") or [])
            if h["_prize"] is not None:
                levels.append(h["_prize"])
        race["_median"] = statistics.median(levels) if len(levels) >= 4 else None
    return leaf["races"]


def competitive(run):
    f, place, mg = run.get("_field"), run.get("place"), run.get("_margin")
    if f and f >= 2 and place and (place - 1) / (f - 1) > 0.5:
        return False
    if mg is not None and abs(mg) > MAX_L:
        return False
    return True


def sectional_s1(h):
    if not h.get("sec_has_pi") or h.get("sec_base") is None:
        return None
    runs = [r for r in h["_runs"] if r.get("_pi") is not None]
    if not runs:
        return None
    pis = [float(r["_pi"]) if competitive(r) else min(float(r["_pi"]), 0.0) for r in runs]
    l600 = sum(float(i["d"] or 0.0) for i in (h.get("sec_items") or [])
               if "末段" in str(i.get("f") or ""))
    forgive = any("寬恕" in str(i.get("f") or "") for i in (h.get("sec_items") or []))
    avg = statistics.mean(pis)
    tier = (W["pi_extreme_bonus"] if avg >= 4 else W["pi_excellent_bonus"] if avg >= 2
            else W["pi_pass_bonus"] if avg >= 0 else 0.0)
    score = float(h["sec_base"]) + tier + l600
    top4 = sum(1 for r in h["_runs"][:3] if (r.get("place") or 99) <= 4)
    if avg > 0 and top4 > 0:
        score += W["realization_bonus"]
    elif avg > 2.0 and forgive:
        score += W["forgiveness_bonus"]
    return clip_score(score)


def score_fold(races, *, s1=False, f3=False):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if s1:
                new = sectional_s1(h)
                if new is not None:
                    feats["sectional_score"] = new
            if f3 and race["_median"] is not None and h["_prize"] is not None:
                feats["form_score"] = clip_score(
                    feats["form_score"] + K * (h["_prize"] - race["_median"]))
            mx = map_features_to_matrix_scores(feats)
            pure = 60.0 + sum((mx[k] - 60.0) * w for k, w in MATRIX_WEIGHTS.items())
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

if __name__ == "__main__":
    races = load()
    split = int(len(races) * (1 - HOLDOUT))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:]),
                       ("全部", races)):
        base = digest(score_fold(fold))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'config':14}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':14}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, kw in (("S1 只封頂", {"s1": True}),
                          ("F3 只班次", {"f3": True}),
                          ("S1+F3", {"s1": True, "f3": True})):
            d = digest(score_fold(fold, **kw))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:14}" + cells)
