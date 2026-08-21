#!/usr/bin/env python3
"""F2 — 輸距入 `form_score` 嘅 isolated A/B（用戶 2026-07-31 提出）。

問題：`_form_score` 逐場只睇絕對名次（place≤5 → base 60、else 40），
完全唔睇輸幾多，亦唔睇馬群大細。Benbulben「6 匹跑第 4、輸 12 個馬位」
拿到 base 60（中性）。

呢度只改一樣嘢：逐場 base 按**距離正規化輸距**扣分。
    mpk = margin / (distance_m / 1000)        # 每公里輸幾多個馬位
    pen = −min(CAP, SCALE × max(0, mpk − FREE))
    base' = clip(base + pen)
其餘（class mult、decay、新馬試閘補充、劣績中性回歸）完全照原樣 replay。

馬群大細唔喺呢輪 —— 走位軌跡最大位置做 proxy 已驗證不可用（低估中位數 −3~−4，
而且同跑法相關，會系統性罰前領馬）。真實馬群大細要加 extractor，另議。

可測範圍：輸距只由 2026-05 起有（scraper 當時才抽），即 251 場。
唯讀。同一把尺 eval_metrics.py。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

HERE = Path(__file__).resolve().parent
MARGIN_ERA = "2026-05-01"
HOLDOUT_FRACTION = 0.2
DIST = re.compile(r"(\d+)")
REGRESS = "劣績中性回歸"


def load():
    leaf = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))
    stab = json.loads((HERE / "au_stability_cache.json").read_text(encoding="utf-8"))
    stab_index = {}
    for race in stab["races"]:
        for h in race["rows"]:
            stab_index[(race["meeting"], race["race"], h["n"])] = h["runs"]
    races = []
    for race in leaf["races"]:
        if race["date"] < MARGIN_ERA:
            continue
        for h in race["rows"]:
            h["_runs"] = stab_index.get((race["meeting"], race["race"], h["n"]), [])
        races.append(race)
    return races


def form_from_rows(rows, extra_bonus, margin_cfg, runs):
    """Faithfully replay _form_score, optionally applying a margin penalty to base."""
    if not rows:
        return None
    num = den = 0.0
    for i, row in enumerate(rows):
        base = float(row["base"])
        if margin_cfg is not None and i < len(runs):
            run = runs[i]
            # 只喺名次對得上（同一場）而且有輸距時才施加
            if run.get("place") == row.get("place") and run.get("margin") is not None:
                dm = DIST.search(str(run.get("distance") or ""))
                dist_km = (int(dm.group(1)) / 1000.0) if dm else None
                if dist_km and dist_km > 0:
                    mpk = abs(float(run["margin"])) / dist_km
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


def score_races(races, margin_cfg):
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
                new = form_from_rows(rows, h["_extra_bonus"], margin_cfg, h["_runs"])
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
    races = load()
    # form_rows_detail / extra bonus 要由 leaf cache 嘅 stability_detail 拎，
    # 但 leaf cache 只存咗 form_rows 個數。重新由 stability cache 唔夠 →
    # 呢個 script 需要 leaf cache v2（見 au_leaf_cache_build.py 加 form rows）。
    missing = sum(1 for r in races for h in r["rows"] if not h.get("form_rows_detail"))
    total = sum(len(r["rows"]) for r in races)
    print(f"races {len(races)}  runners {total}  缺 form_rows_detail {missing}")
    if missing == total:
        print("⚠️  leaf cache 未存 form rows 明細，先跑 au_leaf_cache_build.py（已加欄位）再回來。")
        return

    # 保真度：margin_cfg=None 應該完全重現存檔 form_score
    drift = []
    for race in races:
        for h in race["rows"]:
            rows = h.get("form_rows_detail") or []
            if not rows:
                continue
            replay = form_from_rows(rows, h["_extra_bonus"], None, h["_runs"])
            stored = h["features"]["form_score"]
            if replay is not None and abs(replay - stored) > 0.05:
                drift.append((h["name"], stored, round(replay, 2)))
    print(f"form_score faithful replay drift: {len(drift)} / {total}"
          f" = {100*len(drift)/max(1,total):.2f}%")
    for d in drift[:8]:
        print("   ", d)

    # 缺陷量化：place≤5（base 60）嘅場次，實際輸幾多
    band = Counter()
    for race in races:
        for h in race["rows"]:
            for row, run in zip(h.get("form_rows_detail") or [], h["_runs"]):
                if run.get("place") != row.get("place") or run.get("margin") is None:
                    continue
                if int(row["base"]) != 60:
                    continue
                m = abs(float(run["margin"]))
                band["≤2L" if m <= 2 else "2-5L" if m <= 5 else "5-10L" if m <= 10 else ">10L"] += 1
    tot_b = sum(band.values())
    print(f"\n「base 60」(place 4-5) 嘅場次共 {tot_b} 場，實際輸距分佈：")
    for k in ("≤2L", "2-5L", "5-10L", ">10L"):
        print(f"   {k:>6}: {band[k]:>5}  ({100*band[k]/max(1,tot_b):.1f}%)")

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    folds = {"dev": races[:split], "holdout": races[split:]}
    configs = []
    for scale in (4.0, 8.0, 12.0):
        for cap in (15.0, 25.0, 40.0):
            configs.append((f"free.5 s{scale:g} cap{cap:g}", (0.5, scale, cap)))

    for name, fold in folds.items():
        base = digest(score_races(fold, None))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'config':22}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':22}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for label, cfg in configs:
            d = digest(score_races(fold, cfg))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{label:22}" + cells)


if __name__ == "__main__":
    main()
