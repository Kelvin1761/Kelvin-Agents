#!/usr/bin/env python3
"""C3 — `consistency_score` 已核實證據深度收縮嘅 isolated A/B。

問題（機制）：`stability` 維度 = 0.60×form_score + 0.40×consistency_score，
但兩個 leaf 讀**唔同嘅證據窗**：

  form_score        ← 已核實賽績表 `_official_entries()[:4]`
                      有班次係數、有 index decay、有薄樣本向中性收縮
  consistency_score ← 原始 last-10 字串 `recent_form[:6]`
                      冇班次加權、冇 decay、冇 cap、冇收縮

所以 form 嘅薄數據防護會俾 consistency 抵銷。Benbulben：form 只見 2 場 → 55.56
（已收縮），consistency 用 7 場 last-10 → 「近6仗3次前三」+23.58 → 88.18。
嗰批 1-3-3 係 2024-08 之前嘅鄉下 Maiden。

修正：將 consistency 由 last-10 衍生嘅 adjustment（近績前三獎勵 / 大敗懲罰）
按已核實深度縮：factor = 1 − S·(1 − form_rows/window)。S 係 sweep 參數。
其餘 adjustment（輸距趨勢、重複交代、跑法穩定…）完全不變。

唯讀，用本地 cache，唔讀 Drive、唔碰 Racenet。同一把尺 eval_metrics.py。
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
HOLDOUT_FRACTION = 0.15
WINDOW = re.compile(r"近(\d+)仗")
RECENT_FORM_FACTORS = ("近績前三獎勵", "大敗懲罰")


def shrink_consistency(row, strength):
    if row.get("cons_base") is None or not row.get("cons_adj"):
        return None
    form_rows = row.get("form_rows") or 0
    total = float(row["cons_base"])
    touched = False
    for adj in row["cons_adj"]:
        delta = float(adj.get("d") or 0.0)
        if adj.get("f") in RECENT_FORM_FACTORS:
            m = WINDOW.search(str(adj.get("e") or ""))
            window = int(m.group(1)) if m else 0
            if window > 0:
                ratio = min(1.0, form_rows / window)
                factor = 1.0 - strength * (1.0 - ratio)
                if abs(factor - 1.0) > 1e-9:
                    touched = True
                delta *= factor
        total += delta
    return clip_score(total) if touched else None


def score_races(races, strength):
    out = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if strength is not None:
                new = shrink_consistency(h, strength)
                if new is not None:
                    feats["consistency_score"] = new
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
    races = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))["races"]

    # footprint：有幾多匹馬會受影響、幅度幾大
    deltas = []
    gap = Counter()
    for race in races:
        for h in race["rows"]:
            new = shrink_consistency(h, 1.0)
            if new is not None:
                d = new - h["features"]["consistency_score"]
                if abs(d) > 1e-9:
                    deltas.append(d)
                w = 0
                for adj in h["cons_adj"]:
                    m = WINDOW.search(str(adj.get("e") or ""))
                    if adj.get("f") in RECENT_FORM_FACTORS and m:
                        w = max(w, int(m.group(1)))
                if w:
                    gap[f"form{min(h.get('form_rows') or 0, 5)}/win{w}"] += 1
    horses = sum(len(r["rows"]) for r in races)
    print(f"races {len(races)}  horses {horses}")
    print(f"S=1.0 受影響馬匹: {len(deltas)} ({100*len(deltas)/max(1,horses):.1f}%)")
    if deltas:
        import statistics
        print(f"  consistency 變動: 平均 {statistics.mean(deltas):+.2f}"
              f" / 中位 {statistics.median(deltas):+.2f} / 最大 {min(deltas):+.2f}")
    print("  最常見 (form 場數 / consistency 窗):",
          dict(sorted(gap.items(), key=lambda kv: -kv[1])[:6]))

    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    for name, fold in (("dev", races[:split]), ("holdout", races[split:])):
        base = digest(score_races(fold, None))
        print(f"\n===== {name} ({len(fold)} races) =====")
        print(f"{'config':16}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':16}" + "".join(f"{base[k]:>13}" for k in KEYS))
        for s in (0.25, 0.5, 0.75, 1.0):
            d = digest(score_races(fold, s))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += (f"{d[k]:>7}({delta:+d})".rjust(13) if k == "gold"
                          else f"{d[k]:>7}{delta:+.2f}".rjust(13))
            print(f"{f'S={s}':16}" + cells)


if __name__ == "__main__":
    main()
