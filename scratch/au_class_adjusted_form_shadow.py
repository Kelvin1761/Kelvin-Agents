#!/usr/bin/env python3
"""F3 — 用獎金做真正嘅班次調整，補上 `form_score` 缺失嘅 ability 成分。

問題：`_form_score` 個 `class_mult` 註釋自己認咗係「全場統一」——
`entry["class"]` 呢個 key 由來冇存在過，所以 `entry_tier` 永遠係空字串嘅 tier，
`delta = today_tier − const` 對全場每一匹馬每一場都一樣。
即係 form_score **完全冇**逐場班次調整：一匹馬喺 $27k 鄉下 Maiden 入前列，
同另一匹喺 $500k 都會賽入前列，同分。

賽績表個「班次」欄 85% 係 fallback "Maiden/SW"（`hc` 缺失），用唔到。
但 Formguide 每一行都有獎金，**85,010 個 run 100% 密度**，
分佈由 $0-25k (3.9%) 到 $500k+ (8.5%)，班次跨度足夠。
獎金水平單獨嘅場內 ρ = 0.105、Q1−Q5 10.1pp —— 比 sectional(0.086)、
track(0.096)、jockey_horse_fit(0.071)、pace_map(0.066) 都強。

做法（場內相對，唔需要今仗獎金）：
    prize_level_i = decay 加權平均 log10(獎金)  over 計分近仗
    class_adj_i   = K × (prize_level_i − 今場所有馬嘅 prize_level 中位數)
    form'_i       = form_i + class_adj_i
排名只喺場內比較，所以場內相對係足夠而且更穩健（唔受今仗獎金缺失影響）。

唯讀，本地 cache。同一把尺 eval_metrics.py。
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT_FRACTION = 0.15
DECAY = (1.0, 0.8, 0.6, 0.4)


def prize_level(runs):
    """decay 加權嘅 log10(獎金)，只計正式仗，同 form_score 一樣睇近 4 仗。"""
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
    prize = json.loads((HERE / "au_prize_cache.json").read_text(encoding="utf-8"))
    for race in leaf["races"]:
        levels = []
        for h in race["rows"]:
            rec = prize.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}
            h["_prize_level"] = prize_level(rec.get("runs") or [])
            if h["_prize_level"] is not None:
                levels.append(h["_prize_level"])
        race["_prize_median"] = statistics.median(levels) if len(levels) >= 4 else None
    return leaf["races"]


def score_races(races, k):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        median = race.get("_prize_median")
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if k and median is not None and h["_prize_level"] is not None:
                adj = k * (h["_prize_level"] - median)
                feats["form_score"] = clip_score(feats["form_score"] + adj)
            matrix = map_features_to_matrix_scores(feats)
            pure = 60.0 + sum((matrix[m] - 60.0) * w for m, w in MATRIX_WEIGHTS.items())
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
    races = load()
    have = sum(1 for r in races for h in r["rows"] if h["_prize_level"] is not None)
    tot = sum(len(r["rows"]) for r in races)
    usable = sum(1 for r in races if r.get("_prize_median") is not None)
    print(f"races {len(races)}（可用 {usable}）  horses {tot}"
          f"  有獎金水平 {have} ({100*have/max(1,tot):.1f}%)")
    spread = [h["_prize_level"] - r["_prize_median"]
              for r in races if r.get("_prize_median") is not None
              for h in r["rows"] if h["_prize_level"] is not None]
    if spread:
        spread.sort()
        print(f"場內 log10(獎金) 偏離中位數：P10 {spread[len(spread)//10]:+.2f}"
              f"  中位 {spread[len(spread)//2]:+.2f}"
              f"  P90 {spread[9*len(spread)//10]:+.2f}")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold, 0.0))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'K':10}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':10}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for k in (5.0, 10.0, 20.0, 30.0):
            d = digest(score_races(fold, k))
            cells = ""
            for key in KEYS:
                delta = d[key] - base[key]
                cells += (f"{d[key]:>7}({delta:+d})".rjust(13) if key == "gold"
                          else f"{d[key]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'K={k:g}':10}" + cells)


if __name__ == "__main__":
    main()
