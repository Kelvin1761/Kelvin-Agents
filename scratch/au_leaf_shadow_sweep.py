#!/usr/bin/env python3
"""C2′ / C3 leaf-level isolated A/B — 全部喺本地 cache 上跑，唔讀 Drive。

三個獨立 toggle，各自 sweep，再測組合：

  A  pace_figure sample shrinkage   z' = z · n/(n+k)         n = pf_run_count
  B  sectional  sample shrinkage    bonus' = bonus · n/(n+k) n = PI run count
  C  consistency 已核實深度收縮      近績衍生 adjustment × factor
                                     factor = 1 − S·(1 − form_rows/window)

A / B 係同一個原則（薄樣本唔應該出全力）擺喺兩個唔同權重嘅 leaf：
`pace_figure_score` 有效權重 0.1430，`sectional_score` 只有 0.0365。
C 針對 `form_score` 同 `consistency_score` 用兩個唔同證據窗嘅問題。

時間切分：dev 85% / 未碰過 holdout 15%。同一把尺 eval_metrics.py。唯讀。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402

CACHE = Path(__file__).resolve().parent / "au_leaf_cache.json"
HOLDOUT_FRACTION = 0.15
WINDOW = re.compile(r"近(\d+)仗")
# The two consistency adjustments that are derived from the raw last-10 string
# rather than from the verified record table.
RECENT_FORM_FACTORS = ("近績前三獎勵", "大敗懲罰")


def shrink_pace_figure(row, k):
    z, n = row["pace_z"], row["pace_runs"]
    if row["pace_state"] != "ok" or z is None or not n:
        return None
    return clip_score(60.0 - (z * n / (n + k)) * 20.0)


def shrink_sectional(row, k):
    if not row["sec_has_pi"] or row["sec_base"] is None:
        return None
    n = row["pi_runs"]
    if not n:
        return None
    bonus = sum(float(i["d"] or 0.0) for i in row["sec_items"])
    return clip_score(float(row["sec_base"]) + bonus * n / (n + k))


def shrink_consistency(row, strength):
    if row["cons_base"] is None or not row["cons_adj"]:
        return None
    form_rows = row["form_rows"]
    total = float(row["cons_base"])
    changed = False
    for adj in row["cons_adj"]:
        delta = float(adj["d"] or 0.0)
        if adj["f"] in RECENT_FORM_FACTORS:
            m = WINDOW.search(str(adj.get("e") or ""))
            window = int(m.group(1)) if m else 0
            if window > 0 and form_rows >= 0:
                ratio = min(1.0, form_rows / window)
                factor = 1.0 - strength * (1.0 - ratio)
                if abs(factor - 1.0) > 1e-9:
                    changed = True
                delta *= factor
        total += delta
    return clip_score(total) if changed else None


def apply_and_score(races, *, pf_k=None, sec_k=None, cons_s=None):
    rows = []
    for race in races:
        actual_pos = {h["n"]: h["pos"] for h in race["rows"]}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for h in race["rows"]:
            feats = dict(h["features"])
            if pf_k is not None:
                new = shrink_pace_figure(h, pf_k)
                if new is not None:
                    feats["pace_figure_score"] = new
            if sec_k is not None:
                new = shrink_sectional(h, sec_k)
                if new is not None:
                    feats["sectional_score"] = new
            if cons_s is not None:
                new = shrink_consistency(h, cons_s)
                if new is not None:
                    feats["consistency_score"] = new
            matrix = map_features_to_matrix_scores(feats)
            pure = 60.0 + sum((matrix[k] - 60.0) * w for k, w in MATRIX_WEIGHTS.items())
            scored.append((pure + float(h["wet"] or 0.0), h["n"]))
        picks = [n for _, n in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        rows.append(race_metrics(picks, actual_top3,
                                 winner=winners[0] if winners else None,
                                 actual_pos=actual_pos, field_size=race["field"]))
    return summarize_races(rows)


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
        "crec5": round(c["mean_competitive_recall_at5"], 4),
    }


KEYS = ("gold", "good_pos", "good_any2", "champ", "winT3", "t3prec", "mrr",
        "blowout", "compet", "ndcg5", "crec5")
BIGGER_IS_BETTER = {k: True for k in KEYS}
BIGGER_IS_BETTER["blowout"] = False


def table(title, folds, configs):
    print(f"\n########## {title} ##########")
    for fold_name, races in folds.items():
        base = digest(apply_and_score(races, ))
        print(f"\n--- {fold_name} ({len(races)} races) ---")
        print(f"{'config':22}" + "".join(f"{k:>13}" for k in KEYS))
        print(f"{'BASE':22}" + "".join(
            f"{base[k]:>13}" for k in KEYS))
        for label, kwargs in configs:
            d = digest(apply_and_score(races, **kwargs))
            cells = ""
            for k in KEYS:
                delta = d[k] - base[k]
                cells += f"{d[k]:>7}{delta:+.2f}".rjust(13) if k != "gold" else f"{d[k]:>8}({delta:+d})".rjust(13)
            print(f"{label:22}" + cells)


def main():
    payload = json.loads(CACHE.read_text(encoding="utf-8"))
    races = payload["races"]
    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    folds = {"dev": races[:split], "holdout": races[split:]}

    table("A — pace_figure shrinkage only (權重 0.1430)", folds,
          [(f"A k={k}", {"pf_k": k}) for k in (0.5, 1.0, 2.0, 3.0, 5.0)])
    table("B — sectional shrinkage only (權重 0.0365)", folds,
          [(f"B k={k}", {"sec_k": k}) for k in (1.0, 2.0, 4.0)])
    table("C — consistency 已核實深度收縮 (權重 0.1197)", folds,
          [(f"C S={s}", {"cons_s": s}) for s in (0.25, 0.5, 0.75, 1.0)])
    table("A+B / A+C / A+B+C 組合", folds, [
        ("A k=2 + B k=2", {"pf_k": 2.0, "sec_k": 2.0}),
        ("A k=2 + C S=0.5", {"pf_k": 2.0, "cons_s": 0.5}),
        ("A k=2 + C S=1.0", {"pf_k": 2.0, "cons_s": 1.0}),
        ("A2 + B2 + C0.5", {"pf_k": 2.0, "sec_k": 2.0, "cons_s": 0.5}),
        ("A2 + B2 + C1.0", {"pf_k": 2.0, "sec_k": 2.0, "cons_s": 1.0}),
    ])


if __name__ == "__main__":
    main()
