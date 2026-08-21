#!/usr/bin/env python3
"""用 Racenet profile place% **取代** jockey_score / trainer_score（唔係加喺上面）。

用戶 2026-08-01 指正：之前把 profile 統計**加**落現有分數係錯 —— 兩者食同一來源，
等於 double count。應該係取代。

現行結構（讀 code 確認）：
  `_jockey_score`  優先用**自己 DB 嘅 tier**（build_comprehensive_stats，由 63 日
                   archive 推導），`jockey_ly` 只係 DB 冇名時 fallback
  `_trainer_score` 用自己 DB tier；`trainer_ly` **完全冇入分**，淨係顯示

即係主力靠一個薄 DB。Racenet profile 係全庫、實時，理應優先。

映射沿用現行 `_jockey_ly_score` 同一個形狀（收縮 + 線性映射到 60 中性）：
    rate   = placePercentage / 100
    shrunk = (rate·n + K·prior) / (n + K)          n = totalRuns
    score  = 60 + (shrunk − prior) × SPREAD
prior 由抓到嘅 profile 池化計，唔用直覺值（用錯 prior 會全體平移）。

dev 85% / 未碰過 holdout 15%，同一把尺。唯讀。
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
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV, normalize_horse_name, normalize_track_name, parse_int)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

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

    # 池化 prior：用抓到嘅 profile 按場數加權，唔用直覺值
    priors = {}
    for kind, entries in table.items():
        num = den = 0.0
        for st in entries.values():
            n, p = st.get("totalRuns"), st.get("placePercentage")
            if n and p is not None:
                num += float(p) / 100.0 * float(n)
                den += float(n)
        priors[kind] = (num / den) if den else 0.30
    print("池化 prior:", {k: round(v, 4) for k, v in priors.items()})

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
    have = {"jockey": 0, "trainer": 0}
    total = 0
    for race in races:
        m = VENUE.match(race["meeting"])
        tslug = normalize_track_name(m.group(1) if m else race["meeting"])
        for h in race["rows"]:
            total += 1
            key = (race["date"], tslug, race["race"], normalize_horse_name(h["name"] or ""))
            jk, tr = people.get(key, (None, None))
            for kind, slug in (("jockey", jk), ("trainer", tr)):
                st = table[kind].get(slug) if slug else None
                h[f"_{kind}"] = st
                have[kind] += 1 if st else 0
    print(f"runners {total}：有騎師 profile {have['jockey']} ({100*have['jockey']/total:.0f}%)、"
          f"練馬師 {have['trainer']} ({100*have['trainer']/total:.0f}%)")
    return races, priors


def replacement_score(stats, prior, spread):
    """profile place% → 同 `_jockey_ly_score` 同形狀嘅 60-中性分。"""
    if not stats:
        return None
    pct, runs = stats.get("placePercentage"), stats.get("totalRuns")
    if pct is None or not runs:
        return None
    rate = float(pct) / 100.0
    shrunk = (rate * float(runs) + SHRINK_K * prior) / (float(runs) + SHRINK_K)
    return clip_score(60.0 + (shrunk - prior) * spread)


def score_fold(races, priors, *, do_jockey=False, do_trainer=False, spread=100.0,
               min_cover=0.0):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        # 混合標尺問題：如果一場只有部分馬換咗新標尺，場內比較就唔一致。
        # min_cover 令我哋只喺覆蓋足夠嘅場次施加，用嚟分辨「數據差」定「標尺撈亂」。
        if min_cover > 0:
            n = len(race["rows"])
            jc = sum(1 for h in race["rows"] if h.get("_jockey")) / n
            tc = sum(1 for h in race["rows"] if h.get("_trainer")) / n
            need = [c for c, on in ((jc, do_jockey), (tc, do_trainer)) if on]
            if need and min(need) < min_cover:
                do_jockey_here = do_trainer_here = False
            else:
                do_jockey_here, do_trainer_here = do_jockey, do_trainer
        else:
            do_jockey_here, do_trainer_here = do_jockey, do_trainer
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if do_jockey_here:
                new = replacement_score(h.get("_jockey"), priors["jockey"], spread)
                if new is not None:
                    feats["jockey_score"] = new
            if do_trainer_here:
                new = replacement_score(h.get("_trainer"), priors["trainer"], spread)
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
    for mc in (0.0, 0.9, 1.0):
        tag = "全部場次" if mc == 0 else f"只限覆蓋≥{mc:.0%}"
        variants.append((f"取代騎師 s100 {tag}",
                         dict(do_jockey=True, spread=100.0, min_cover=mc)))
        variants.append((f"取代練馬師 s100 {tag}",
                         dict(do_trainer=True, spread=100.0, min_cover=mc)))
        variants.append((f"兩邊取代 s100 {tag}",
                         dict(do_jockey=True, do_trainer=True, spread=100.0, min_cover=mc)))

    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_fold(fold, priors))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'variant':26}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE (現行)':26}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, kw in variants:
            d = digest(score_fold(fold, priors, **kw))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:26}" + cells)


if __name__ == "__main__":
    main()
