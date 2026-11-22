#!/usr/bin/env python3
"""Forward shadow：表現評分 PR1（輸距＋負磅）疊喺 live 之上（EXP-20261122-05，Kelvin 2026-11-22）。

Kelvin：「如果明顯改善 Good 同埋 1 hit 都可以諗」—— 研究入面 PR1 疊 live：Good +0.53（下界 −0.03）、頭二選有中 +0.13、
Gold −0.70，未達標，所以用新賽事驗證。**唔郁排名**。

  live      = 儲存綜合分（`au_age_upnil_forward.collect`，exact_score 重建）
  candidate = live + 0.148 ×（PR1 − 場均）　（β = 研究 walk-forward 中位，凍結；冇往績 = 場均）

預先登記判法：START_DATE 起夠 TARGET_RACES 場，逐場 Δ Good、Δ 頭二選有中，賽日 bootstrap 2,000；
**兩個 95% CI 下界都 > 0 = PASS**。另報 Gold、log-loss（唔係門檻）。未夠數只報數量（盲測）。判一次就凍結。

    python3 au_pr1_shadow_forward.py --output STATUS.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

import au_perf_rating as PR  # noqa: E402

EXPERIMENT_ID = "EXP-20261122-05"
START_DATE = "2026-11-23"
TARGET_RACES = 1000
BETA = 0.148


def attach_pr1(races, root):
    from corpus_paths import meeting_dirs
    dirs = {d.name: d for d in meeting_dirs(root)}
    cache = {}
    for r in races:
        if r["date"] < START_DATE:
            continue
        key = (r["meeting"], r["race"])
        if key not in cache:
            d = dirs.get(r["meeting"])
            files = sorted(d.glob(f"* Race {r['race']} Formguide.md")) if d else []
            cache[key] = PR.formguide_sections(files[0].read_text(encoding="utf-8", errors="replace")) if files else {}
        for x in r["rows"]:
            x["pr1"] = PR.pr1(cache[key].get(x["n"], ""), r["date"])
    return races


def candidate(races):
    out = []
    for r in races:
        vals = [x.get("pr1") for x in r["rows"]] if r["date"] >= START_DATE else []
        known = [v for v in vals if v is not None]
        if not known:
            out.append(r)
            continue
        mean = sum(known) / len(known)
        out.append(dict(r, rows=[dict(x, ability=x["ability"] + BETA * ((x.get("pr1") if x.get("pr1") is not None else mean) - mean))
                                 for x in r["rows"]]))
    return out


def evaluate(races):
    import numpy as np
    from au_logloss_ruler import _metrics, eligible, evaluate as ll_evaluate
    live = eligible(races); cand = eligible(candidate(races))
    rows = [(b["date"], np.array(_metrics(c)) - np.array(_metrics(b))) for b, c in zip(live, cand) if b["date"] >= START_DATE]
    by = defaultdict(list)
    for i, (d, _m) in enumerate(rows):
        by[d].append(i)
    days = sorted(by); M = np.array([m for _d, m in rows]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))]); bs.append(M[ii].mean(0))
    bs = np.array(bs); lo, hi = np.percentile(bs, 2.5, 0) * 100, np.percentile(bs, 97.5, 0) * 100
    names = ("gold", "good", "capture5", "top2_any_hit")
    point = {n: round(float(M[:, i].mean() * 100), 3) for i, n in enumerate(names)}
    ci = {n: [round(float(lo[i]), 3), round(float(hi[i]), 3)] for i, n in enumerate(names)}
    ll = ll_evaluate(live, cand, nnull=100, version="v1")  # 11-22 登記，照用 v1 尺
    passed = ci["good"][0] > 0 and ci["top2_any_hit"][0] > 0
    return {"verdict": "PASS" if passed else "REJECT", "rule": "Good 同頭二選有中 95% CI 下界都 > 0",
            "races": len(rows), "point_pp": point, "ci95_pp": ci,
            "logloss": {k: ll[k] for k in ("verdict", "reason", "dlogloss")}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    from au_archive_calibrator import ARCHIVE_ROOT
    from au_age_upnil_forward import collect

    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} PR1 shadow 已判（凍結）：{previous['evaluation']['verdict']}")
        return
    root = Path(args.data_root) if args.data_root else ARCHIVE_ROOT
    races = attach_pr1(collect(root), root)
    forward = [r for r in races if r["date"] >= START_DATE]
    status = {"experiment": EXPERIMENT_ID, "arm": "PR1 shadow", "beta": BETA, "start_date": START_DATE,
              "target_races": TARGET_RACES, "races_collected": len(forward),
              "interim": {"horses_with_pr1": sum(1 for r in forward for x in r["rows"] if x.get("pr1") is not None),
                          "note": "盲測：未夠數只報數量"},
              "outcomes_visible": len(forward) >= TARGET_RACES,
              "state": "evaluated" if len(forward) >= TARGET_RACES else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if status["outcomes_visible"]:
        cutoff = sorted(r["date"] for r in forward)[TARGET_RACES - 1]
        status["evaluation"] = evaluate([r for r in races if r["date"] <= cutoff])
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
