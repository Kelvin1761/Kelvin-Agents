#!/usr/bin/env python3
"""S1 — PI（位置增益）只計「有競爭力」嘅場次。

問題：`_sectional_breakdown` 逐場收 PI（定位→終點位置增益）然後平均，
完全唔理嗰場跑成點。Benbulben 拿 +20「位置增益優秀」，而嗰個 +5 係
**定位第 11、終點第 6、輸 9.05L**、賽事節奏 V Slow 嘅一場 ——
Racenet 自己嘅評語係 "Passed a few plodders late."。

「喺一場爬行賽事由最後追過幾隻慢馬」唔係後勁證據。

修正：PI 只由**有競爭力**嘅場次計。有競爭力定義為
    （知道馬群大細 → 場內百分位 ≤ 0.5）**且**（知道輸距 → 輸距 ≤ MAX_L）
兩個條件都唔知 → 保留（唔因為缺數據而丟訊號）。
冇合格 PI → 走同「完全冇 PI」一樣嘅分支（只有基礎分）。

PI 由 `legs` 自己算（定位 − 終點），已對 Benbulben 兩場驗證正確。
唯讀，本地 cache。同一把尺 eval_metrics.py。
"""
from __future__ import annotations

import csv
import json
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
    HISTORICAL_RESULTS_CSV,
    normalize_horse_name,
    normalize_track_name,
    parse_int,
)
from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, SECTIONAL_MICRO_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
HOLDOUT_FRACTION = 0.15
DIST = re.compile(r"(\d+)")
MARGIN_L = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*L")
W = SECTIONAL_MICRO_WEIGHTS


def load_results():
    field, margin = {}, {}
    counts = {}
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            race = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race or not pos:
                continue
            k3 = (str(row.get("Date") or "").strip(),
                  normalize_track_name(row.get("Track") or ""), race)
            counts[k3] = counts.get(k3, 0) + 1
            m = MARGIN_L.search(str(row.get("Margin") or ""))
            margin[k3 + (normalize_horse_name(row.get("Horse") or ""),)] = (
                abs(float(m.group(1))) if m else (0.0 if pos == 1 else None))
    field.update(counts)
    return field, margin


def load():
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    lastfin = json.loads((HERE / "au_lastfinish_cache.json").read_text(encoding="utf-8"))
    field_truth, margin_truth = load_results()
    index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            lf = lastfin.get(f"{race['meeting']}|{race['race']}|{h['n']}")
            hslug = normalize_horse_name(h["name"] or "")
            for run in h["runs"]:
                place = run.get("place")
                legs = run.get("legs") or {}
                # PI = 定位 − 終點（同 inject_fact_anchors 嘅定義一致）
                run["_pi"] = (legs["settled"] - legs["finish"]
                              if "settled" in legs and "finish" in legs else None)
                run["_field"] = run["_margin"] = None
                if not place:
                    continue
                vslug = normalize_track_name(run.get("venue") or "")
                k3 = (run["date"], vslug, run.get("race_no"))
                f = field_truth.get(k3)
                if f and f >= 2 and place <= f:
                    run["_field"] = f
                elif lf:
                    dm = DIST.search(str(run.get("distance") or ""))
                    dist = int(dm.group(1)) if dm else None
                    if (lf["place"] == place and dist == lf["distance"]
                            and normalize_track_name(lf["venue"]) == vslug
                            and lf["field"] >= 2 and place <= lf["field"]):
                        run["_field"] = lf["field"]
                run["_margin"] = (run.get("margin") if run.get("margin") is not None
                                  else margin_truth.get(k3 + (hslug,)))
            index[(race["meeting"], race["race"], h["n"])] = h["runs"]
    for race in leaf["races"]:
        for h in race["rows"]:
            h["_runs"] = index.get((race["meeting"], race["race"], h["n"]), [])
    return leaf["races"]


def competitive(run, max_len):
    """百分位 ≤ .5 且 輸距 ≤ max_len；缺數據嗰項唔判佢死。"""
    f, place, mg = run.get("_field"), run.get("place"), run.get("_margin")
    if f and f >= 2 and place:
        if (place - 1) / (f - 1) > 0.5:
            return False
    if mg is not None and abs(mg) > max_len:
        return False
    return True


def pi_tier_bonus(avg_pi, n):
    if avg_pi >= 4.0:
        return W.get("pi_extreme_bonus", 25.0)
    if avg_pi >= 2.0:
        return W.get("pi_excellent_bonus", 15.0)
    if avg_pi >= 0.0:
        return W.get("pi_pass_bonus", 5.0)
    return 0.0


def rebuild_sectional(h, max_len):
    """重算 sectional_score，PI 只由有競爭力場次計。max_len=None → 原樣（保真度檢查）。"""
    if not h.get("sec_has_pi") or h.get("sec_base") is None:
        return None
    runs = [r for r in h["_runs"] if r.get("_pi") is not None]
    if not runs:
        return None
    # 封頂而唔係剔除：非競爭場次唔可以賺 PI credit（正值封到 0），但仍然計入
    # 分母，所以失位（負 PI）呢種弱勢證據唔會被一併抹走。
    # 早期版本直接剔走整場，結果有啲馬平均 PI 反而升（剔走咗負 PI）—— 係設計錯誤。
    if max_len is None:
        pi_values = [float(r["_pi"]) for r in runs]
    else:
        pi_values = [float(r["_pi"]) if competitive(r, max_len)
                     else min(float(r["_pi"]), 0.0) for r in runs]
    qualifying = pi_values

    # 原本嘅 L600 項照留（唔關 PI 事）
    l600_delta = sum(float(i["d"] or 0.0) for i in (h.get("sec_items") or [])
                     if "末段極速" in str(i.get("f") or ""))
    had_forgiveness = any("寬恕" in str(i.get("f") or "")
                          for i in (h.get("sec_items") or []))

    base = float(h["sec_base"])
    if not qualifying:
        # 同「完全冇 PI 數據」一樣：三項全部 0
        return clip_score(base)

    avg_pi = statistics.mean(qualifying)
    score = base + pi_tier_bonus(avg_pi, len(qualifying)) + l600_delta
    # 增益兌現 / 寬恕：沿用原本嘅分支條件，只係 avg_pi 換成新值
    recent_top4 = sum(1 for r in h["_runs"][:3]
                      if (r.get("place") or 99) <= 4)
    if avg_pi > 0 and recent_top4 > 0:
        score += W.get("realization_bonus", 10.0)
    elif avg_pi > 2.0 and had_forgiveness:
        score += W.get("forgiveness_bonus", 5.0)
    return clip_score(score)


def score_races(races, max_len):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if max_len is not None:
                new = rebuild_sectional(h, max_len)
                if new is not None:
                    feats["sectional_score"] = new
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
    races = load()

    # 保真度：max_len=None 必須重現存檔 sectional_score
    drift = big = 0
    horses = 0
    for race in races:
        for h in race["rows"]:
            horses += 1
            rep = rebuild_sectional(h, None)
            if rep is None:
                continue
            big += 1
            if abs(rep - h["features"]["sectional_score"]) > 0.05:
                drift += 1
    print(f"horses {horses}  可重算 {big}  replay drift {drift}"
          f" ({100*drift/max(1,big):.2f}%)")

    for max_len in (3.0, 5.0, 8.0):
        touched = deltas = 0
        vals = []
        for race in races:
            for h in race["rows"]:
                new = rebuild_sectional(h, max_len)
                if new is None:
                    continue
                d = new - h["features"]["sectional_score"]
                if abs(d) > 1e-9:
                    touched += 1
                    vals.append(d)
        print(f"  max_len={max_len}: 受影響 {touched} ({100*touched/max(1,horses):.1f}%)"
              f"  平均變動 {statistics.mean(vals):+.2f}" if vals else "")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold, None))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'config':16}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':16}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for max_len in (3.0, 5.0, 8.0):
            d = digest(score_races(fold, max_len))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'≤{max_len:g}L':16}" + cells)


if __name__ == "__main__":
    main()
