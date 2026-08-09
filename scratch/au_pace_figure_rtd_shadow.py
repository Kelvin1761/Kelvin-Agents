#!/usr/bin/env python3
"""P1 — `pace_figure_score` 用全程時間差 (`race_time_diff`) 校正嘅 isolated A/B。

用戶 2026-07-31 問：Benbulben 拿高段速分合理嗎？

答案係唔合理，而且判斷所需數據本來就喺 bundle：

    l600_delta      −1.71   末段 600m 快過基準 1.71s  → 段速實速分 73.7
    race_time_diff  +8.95   **全程時間慢過基準 8.95 秒**   ← 冇入分
    tempo_qrank      0.99   賽事節奏慢到 99 百分位         ← 冇入分
    early_race_pace  V Slow                              ← 冇入分
    pf_run_count        1   單場

即係「爬行賽事嘅快尾段」被當成速度證據。`_pace_figure_score`
（有效權重 0.1430，第三高）只讀 `l600_delta_avg`。

覆蓋率剛好對得上：`race_time_diff_avg` 33.1% vs `pace_figure` state=ok 33.0%
—— **凡係 pace_figure 有分嘅，race_time_diff 都有值**，所以呢個 A/B 係滿力嘅
（對比 tempo_qrank 只 1.1%，用唔到）。

做法：同 l600 一樣做場內 z-score，然後兩者混合
    z = (1−a)·z_l600 + a·z_rtd          a 係 sweep 參數
    score = clip(60 − z·20)
a=0 完全等於現行。唯讀，本地 cache。同一把尺 eval_metrics.py。
"""
from __future__ import annotations

import json
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
MIN_FIELD_WITH_DATA = 3        # 同 _pace_figure_score 嘅 count < 3 → 中性 一致


def load():
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    pf = json.loads((HERE / "au_pf_cache.json").read_text(encoding="utf-8"))
    for race in leaf["races"]:
        rtds = []
        for h in race["rows"]:
            rec = pf.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}
            h["_rtd"] = rec.get("race_time_diff_avg")
            h["_pf_runs"] = rec.get("pf_run_count")
            if h["_rtd"] is not None and h["pace_state"] == "ok":
                rtds.append(float(h["_rtd"]))
        # 場內 z-score 統計，同 l600 嘅做法一致
        if len(rtds) >= MIN_FIELD_WITH_DATA:
            mean = statistics.mean(rtds)
            sd = statistics.pstdev(rtds)
            race["_rtd_stats"] = (mean, sd) if sd > 0 else None
        else:
            race["_rtd_stats"] = None
    return leaf["races"]


def adjusted_pace_figure(race, h, alpha):
    """混合 l600 z 同 race_time_diff z；冇 rtd 或場內冇分散就完全唔改。"""
    if h["pace_state"] != "ok" or h["pace_z"] is None:
        return None
    stats = race.get("_rtd_stats")
    if not stats or h["_rtd"] is None:
        return None
    mean, sd = stats
    z_rtd = (float(h["_rtd"]) - mean) / sd
    z = (1.0 - alpha) * float(h["pace_z"]) + alpha * z_rtd
    return clip_score(60.0 - z * 20.0)


def score_races(races, alpha):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if alpha:
                new = adjusted_pace_figure(race, h, alpha)
                if new is not None:
                    feats["pace_figure_score"] = new
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
    # footprint
    n = touched = 0
    deltas = []
    for race in races:
        for h in race["rows"]:
            n += 1
            new = adjusted_pace_figure(race, h, 0.5)
            if new is not None:
                touched += 1
                deltas.append(new - h["features"]["pace_figure_score"])
    print(f"horses {n}  a=0.5 受影響 {touched} ({100*touched/max(1,n):.1f}%)")
    if deltas:
        print(f"  pace_figure 變動: 平均 {statistics.mean(deltas):+.2f}"
              f" / 中位 {statistics.median(deltas):+.2f}"
              f" / 最低 {min(deltas):+.2f} / 最高 {max(deltas):+.2f}")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold, 0.0))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'config':14}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':14}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for a in (0.2, 0.35, 0.5, 0.7, 1.0):
            d = digest(score_races(fold, a))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'a={a}':14}" + cells)


if __name__ == "__main__":
    main()
