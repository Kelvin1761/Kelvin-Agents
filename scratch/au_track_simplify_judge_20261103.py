#!/usr/bin/env python3
"""EXP-20261103-02 §7 判決：場地模組簡化（只有「截斷紀錄唔當 0 上名」會改分，全部喺 2026-08）。

    judge.py BASE.json CAND.json OUT.json

v3 fixed_rule 全紀錄（08-05 起）；§7 準則：primary（gold／good_positional）冇顯著負、預先聲明分層冇 CI 全負。
分層 helper 同 EXP-20261103-01 一樣。
"""
import json
import random
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / "scratch"))
import au_track_rebuild_judge_20261102 as old  # noqa: E402  (會順手設好 sys.path)
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402


def cohorts(base, rb, rc, dates):
    fns = [("field", lambda r: "<=8" if len(r["rows"]) <= 8 else "9-12" if len(r["rows"]) <= 12 else "13+"),
           ("going", old.going_state),
           ("top_pick_sp", lambda r: (lambda s: "unknown" if s is None else "$1-3" if s < 3 else "$3-6" if s < 6
                                      else "$6+")(old.sp(r["rows"][old.top(r)].get("sp")))),
           ("distance", lambda r: (lambda d: "?" if d is None else "<=1200" if d <= 1200 else "1201-1600"
                                   if d <= 1600 else ">1600")(_dist(r)))]
    out = {}
    for name, fn in fns:
        keys = [fn(r) for r in base]
        for key in sorted(set(keys)):
            idx = [i for i, k in enumerate(keys) if k == key]
            for metric in ("gold", "good_positional"):
                deltas = {}
                for i in idx:
                    deltas.setdefault(dates[i], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                days = sorted(deltas)
                rng = random.Random(7)
                samples = []
                for _ in range(2000):
                    flat = [d for day in (days[rng.randrange(len(days))] for _ in days) for d in deltas[day]]
                    samples.append(sum(flat) / len(flat))
                samples.sort()
                flat = [d for day in days for d in deltas[day]]
                out[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": round(100 * sum(flat) / len(flat), 2),
                                                 "ci_pp": [round(100 * samples[50], 2), round(100 * samples[1949], 2)]}
    return out


def _dist(r):
    try:
        return float(str(r["rows"][0].get("distance")).rstrip("m"))
    except (TypeError, ValueError):
        return None


def main():
    base, cand = old.load(sys.argv[1]), old.load(sys.argv[2])
    assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
    dates = [r["date"] for r in base]
    score = lambda r: r["ability"]  # noqa: E731
    rb, rc = _stage4_metric_rows(base, score), _stage4_metric_rows(cand, score)
    v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=rb, candidate_rows=rc,
                             leakage_audit_passed=True,
                             ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    coh = cohorts(base, rb, rc, dates)
    pick = lambda group: {k: {f: e.get(f) for f in ("delta", "ci_low", "ci_high", "p_value")}  # noqa: E731
                          for k, e in v["detail"][group].items()}
    primary = pick("primary")
    report = {"races": len(base), "verdict": v["verdict"], "reason": v["reason"], "primary": primary,
              "ranking": pick("ranking"), "counts_base": _counts(base, score), "counts_cand": _counts(cand, score),
              "changed_races": sum(1 for a, b in zip(base, cand)
                                   if [x["ability"] for x in a["rows"]] != [x["ability"] for x in b["rows"]]),
              "cohorts": coh, "cohort_ci_all_negative": [k for k, c in coh.items() if c["ci_pp"][1] < 0],
              "primary_significantly_negative": [k for k, e in primary.items() if e["ci_high"] < 0]}
    report["section7_pass"] = not report["cohort_ci_all_negative"] and not report["primary_significantly_negative"]
    Path(sys.argv[3]).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"races {len(base)} changed {report['changed_races']}  {v['verdict']}/{v['reason']}")
    for k, e in {**report["primary"], **report["ranking"]}.items():
        print(f"   {k:20s} {100*e['delta']:+.3f}  [{100*e['ci_low']:+.3f},{100*e['ci_high']:+.3f}] p={e['p_value']}")
    print("cohort CI all<0:", report["cohort_ci_all_negative"], " §7 pass:", report["section7_pass"])


if __name__ == "__main__":
    main()
