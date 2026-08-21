#!/usr/bin/env python3
"""C1 shadow test — 久休 (layoff) 做真正 ranking feature 嘅 isolated A/B。

設計對齊現有 `wet_form_feature` 嘅做法：一個 per-horse feature 加落單一
`ability_score`（綜合戰力分），唔係 post-hoc 排名 bolt-on。

Bucket 權重係由 `scratch/au_layoff_cohort.py` 量到嘅**全體馬匹**前三率斜率折算
（n=7,226），唔係由 top-pick cell（n=3）折算 —— 呢個係刻意嘅，避免 fit 三場賽事。
唯一 sweep 嘅參數係 magnitude `P`（>400 日嘅扣分上限）。

時間切分：前 85% 場次做 development，尾 15% 做未碰過嘅 holdout，兩邊分開報。

唯讀。輸出 scratch/au_layoff_shadow_test.json。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/shared_racing"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
)
from eval_metrics import race_metrics, summarize_races  # noqa: E402

ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
FORMAL_ROW = re.compile(r"^\|\s*\d+\s*\|\s*([^|]*?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|(.*)$")

# 由量到嘅全體前三率折算嘅相對權重（1.0 = 最長久休組嘅完整扣分）。
# 量到：0-45d 28.6% / 46-90d 27.5% / 91-180d 26.5% / 181-365d 24.6% / 365d+ 19.4%
# 加權基線 28.16% → 各組差距 +0.44 / -0.66 / -1.66 / -3.56 / -8.76 pp
# 除以 8.76 正規化，用 bucket 中位日數做 piecewise-linear anchor。
LAYOFF_ANCHORS = (
    (22.0, -0.05),
    (68.0, 0.075),
    (135.0, 0.19),
    (270.0, 0.41),
    (400.0, 1.00),
)
HOLDOUT_FRACTION = 0.15


def parse_iso(text):
    m = ISO.search(str(text or ""))
    if not m:
        return None
    try:
        return date(*(int(p) for p in m.groups()))
    except ValueError:
        return None


def last_official_date(row):
    data = row["data"]
    explicit = parse_iso(data.get("latest_official_date"))
    if explicit:
        return explicit
    best = None
    for line in str(data.get("facts_section") or "").splitlines():
        m = FORMAL_ROW.match(line.strip())
        if not m:
            continue
        kind, iso, rest = m.group(1), m.group(2), m.group(3)
        if "試閘" in kind or "TRIAL" in rest.upper():
            continue
        parsed = parse_iso(iso)
        if parsed and (best is None or parsed > best):
            best = parsed
    return best


def layoff_weight(days):
    """Piecewise-linear relative penalty weight in [-0.05, 1.0]; 0 when unknown."""
    if days is None:
        return 0.0
    if days <= LAYOFF_ANCHORS[0][0]:
        return LAYOFF_ANCHORS[0][1]
    if days >= LAYOFF_ANCHORS[-1][0]:
        return LAYOFF_ANCHORS[-1][1]
    for (d0, w0), (d1, w1) in zip(LAYOFF_ANCHORS, LAYOFF_ANCHORS[1:]):
        if d0 <= days <= d1:
            return w0 + (w1 - w0) * (days - d0) / (d1 - d0)
    return 0.0


def spell_days(row):
    last = last_official_date(row)
    meeting = parse_iso(row["date"])
    if not last or not meeting:
        return None
    return max(0, (meeting - last).days)


def evaluate(races, penalty):
    """Re-rank each race with the layoff feature applied, return summarize_races."""
    rows = []
    for race_rows in races:
        actual_pos = {r["horse_number"]: r["actual_pos"] for r in race_rows}
        actual_top3 = [n for n, p in actual_pos.items() if p <= 3]
        winners = [n for n, p in actual_pos.items() if p == 1]
        scored = []
        for r in race_rows:
            adj = -penalty * layoff_weight(r["_spell"]) if penalty else 0.0
            scored.append((r["model_score"] + adj, r["horse_number"]))
        picks = [num for _, num in sorted(scored, key=lambda kv: (-kv[0], kv[1]))]
        rows.append(race_metrics(
            picks, actual_top3,
            winner=winners[0] if winners else None,
            actual_pos=actual_pos,
            field_size=len(race_rows),
        ))
    return summarize_races(rows)


def digest(summary):
    r = summary["rates"]
    c = summary["competitiveness"]
    return {
        "races": summary["races"],
        "gold": summary["counts"]["gold"],
        "good_pos_pct": round(100 * r["good_positional"], 2),
        "good_any2_pct": round(100 * r["good_any2"], 2),
        "champion_pct": round(100 * r["champion"], 2),
        "winner_in_top3_pct": round(100 * r["winner_in_top3"], 2),
        "winner_in_top5_pct": round(100 * r["winner_in_top5"], 2),
        "top3_precision_pct": round(100 * summary["top3_precision"], 2),
        "mrr": round(summary["mrr"], 4),
        "top_pick_blowout_pct": round(100 * c["top_pick_blowout"]["rate"], 2)
        if c["top_pick_blowout"]["rate"] is not None else None,
        "top_pick_competitive_pct": round(100 * c["top_pick_competitive"]["rate"], 2)
        if c["top_pick_competitive"]["rate"] is not None else None,
        "mean_ndcg_at5": round(c["mean_ndcg_at5"], 4) if c["mean_ndcg_at5"] is not None else None,
        "mean_competitive_recall_at5": round(c["mean_competitive_recall_at5"], 4)
        if c["mean_competitive_recall_at5"] is not None else None,
    }


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            r["_spell"] = spell_days(r)
        races.append(race_rows)

    races.sort(key=lambda rr: (rr[0]["date"], rr[0]["meeting"], rr[0]["race"]))
    split = int(len(races) * (1 - HOLDOUT_FRACTION))
    folds = {"dev": races[:split], "holdout": races[split:], "all": races}

    # coverage / distribution sanity
    spells = [r["_spell"] for rr in races for r in rr]
    known = [s for s in spells if s is not None]
    buckets = defaultdict(int)
    for s in known:
        buckets[">400d" if s > 400 else "181-400d" if s > 180 else
                "91-180d" if s > 90 else "46-90d" if s > 45 else "0-45d"] += 1

    out = {
        "runners": len(spells),
        "spell_known": len(known),
        "spell_unknown": len(spells) - len(known),
        "spell_buckets": dict(buckets),
        "dev_races": len(folds["dev"]),
        "holdout_races": len(folds["holdout"]),
        "dev_date_range": [folds["dev"][0][0]["date"], folds["dev"][-1][0]["date"]],
        "holdout_date_range": [folds["holdout"][0][0]["date"], folds["holdout"][-1][0]["date"]],
        "sweep": {},
    }

    for penalty in (0.0, 2.0, 4.0, 6.0, 8.0, 12.0):
        out["sweep"][f"P={penalty:g}"] = {
            name: digest(evaluate(fold, penalty)) for name, fold in folds.items()
        }

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"runners {out['runners']}  spell known {out['spell_known']}"
          f"  unknown {out['spell_unknown']}")
    print("buckets:", dict(sorted(buckets.items())))
    print(f"dev {out['dev_races']} races {out['dev_date_range']}"
          f"   holdout {out['holdout_races']} races {out['holdout_date_range']}\n")

    keys = ["good_pos_pct", "good_any2_pct", "champion_pct", "winner_in_top3_pct",
            "top3_precision_pct", "mrr", "top_pick_blowout_pct",
            "top_pick_competitive_pct", "mean_ndcg_at5", "mean_competitive_recall_at5"]
    for fold in ("dev", "holdout", "all"):
        print(f"===== {fold} =====")
        base = out["sweep"]["P=0"][fold]
        header = f"{'metric':30}" + "".join(f"{p:>12}" for p in out["sweep"])
        print(header)
        for k in keys:
            line = f"{k:30}"
            for p in out["sweep"]:
                v = out["sweep"][p][fold][k]
                b = base[k]
                if v is None:
                    line += f"{'-':>12}"
                elif p == "P=0":
                    line += f"{v:>12}"
                else:
                    line += f"{v:>7} ({v - b:+.2f})".rjust(12)
            print(line)
        print(f"{'gold':30}" + "".join(f"{out['sweep'][p][fold]['gold']:>12}" for p in out["sweep"]))
        print()


if __name__ == "__main__":
    main()
