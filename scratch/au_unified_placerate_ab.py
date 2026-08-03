#!/usr/bin/env python3
"""統一上名率：Racenet 生涯 place% 優先，冇就用 LY 推導 —— 取代 jockey/trainer 分。

用戶 2026-08-01 兩個指示：
  1. 用新數據就應該**取代**舊嘅，唔好加喺上面（兩者同源，會 double count）
  2. 練馬師就算弱都要用，因為佢反映真實實力；先攞啱數據同計分，再調

問題：淨用 Racenet profile 只覆蓋 64%/57%，而**部分覆蓋會主動有害** ——
同一場入面部分馬用新標尺、部分用舊，場內比較就唔一致。實測要 1,041 個 profile
（≈3,100 請求）先做到全覆蓋，唔值得。

解法：`*_ly`（`252:29-31-32` = 場數/冠/亞/季）本身就係上名率嘅原材料，
同 `placePercentage` 量緊同一樣嘢。所以砌一個統一特徵：
    有 profile → 生涯上名率（樣本大、穩）
    冇 profile → LY 上名率
兩者用**同一個 prior 同同一條收縮公式**映射 → 同一把標尺、100% 覆蓋、零額外請求。

dev 85% / 未碰過 holdout 15%，同一把尺。唯讀。
"""
from __future__ import annotations

import csv
import json
import re
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
SHRINK_K = 20.0
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
    ly = json.loads((HERE / "au_ly_cache.json").read_text(encoding="utf-8"))

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
    src = defaultdict(lambda: defaultdict(int))
    # 池化 prior：用所有可得樣本（profile 生涯 + LY）一齊計，兩邊共用同一個基準
    pool = defaultdict(lambda: [0.0, 0.0])
    for race in races:
        m = VENUE.match(race["meeting"])
        tslug = normalize_track_name(m.group(1) if m else race["meeting"])
        for h in race["rows"]:
            key = (race["date"], tslug, race["race"], normalize_horse_name(h["name"] or ""))
            jk, tr = people.get(key, (None, None))
            lyrec = ly.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}
            for kind, slug in (("jockey", jk), ("trainer", tr)):
                st = table[kind].get(slug) if slug else None
                if st and st.get("totalRuns") and st.get("placePercentage") is not None:
                    runs = float(st["totalRuns"])
                    places = float(st["placePercentage"]) / 100.0 * runs
                    src[kind]["profile"] += 1
                else:
                    rec = lyrec.get(f"{kind}_ly") or {}
                    runs = float(rec.get("rides") or 0)
                    places = float(rec.get("places") or 0)
                    if runs <= 0:
                        h[f"_{kind}_rate"] = None
                        src[kind]["none"] += 1
                        continue
                    src[kind]["ly"] += 1
                h[f"_{kind}_rate"] = (places, runs)
                pool[kind][0] += places
                pool[kind][1] += runs
    priors = {k: (v[0] / v[1] if v[1] else 0.3) for k, v in pool.items()}
    total = sum(len(r["rows"]) for r in races)
    print(f"runners {total}")
    for kind in ("jockey", "trainer"):
        d = src[kind]
        print(f"  {kind:8} profile {d['profile']:>5} · LY {d['ly']:>5} · 冇 {d['none']:>5}"
              f"  → 覆蓋 {100*(d['profile']+d['ly'])/total:.0f}%  prior {priors[kind]:.4f}")
    return races, priors


def rate_score(pair, prior, spread):
    if not pair:
        return None
    places, runs = pair
    shrunk = (places + SHRINK_K * prior) / (runs + SHRINK_K)
    return clip_score(60.0 + (shrunk - prior) * spread)


def score_fold(races, priors, *, do_jockey=False, do_trainer=False, spread=100.0):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if do_jockey:
                new = rate_score(h.get("_jockey_rate"), priors["jockey"], spread)
                if new is not None:
                    feats["jockey_score"] = new
            if do_trainer:
                new = rate_score(h.get("_trainer_rate"), priors["trainer"], spread)
                if new is not None:
                    feats["trainer_score"] = new
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


def main():
    races, priors = load()
    split = int(len(races) * (1 - HOLDOUT))
    variants = []
    for spread in (60.0, 100.0, 140.0):
        variants.append((f"統一騎師 s={spread:g}", dict(do_jockey=True, spread=spread)))
    for spread in (60.0, 100.0, 140.0):
        variants.append((f"統一練馬師 s={spread:g}", dict(do_trainer=True, spread=spread)))
    for spread in (60.0, 100.0, 140.0):
        variants.append((f"兩邊統一 s={spread:g}",
                         dict(do_jockey=True, do_trainer=True, spread=spread)))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_fold(fold, priors))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'variant':22}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE (現行)':22}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, kw in variants:
            d = digest(score_fold(fold, priors, **kw))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:22}" + cells)


if __name__ == "__main__":
    main()
