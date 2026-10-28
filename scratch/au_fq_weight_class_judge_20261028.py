#!/usr/bin/env python3
"""EXP-20261028-11／-12／-13 v3 fixed_rule 全紀錄判決 + 預先聲明分層。

    python3 au_fq_weight_class_judge_20261028.py BASE.json CAND.json OUT.json --extra runs|proxy|group:G5

由 `au_tier_fix_eval_20261016.py` 衍生：同一個判決器、同一套馬群大細／首選 SP 分層，
另加 protocol 寫明嘅分層：
  runs       baseline 首選嘅近績質素計分場數（fallback／2／3／4／5／6）           —— EXP-11
  proxy      今場有冇馬用代理分（baseline）                                    —— EXP-12
  group:Gx   該組規則觸發馬佔場內比例 ≥ 全語料中位數 → high，否則 low            —— EXP-13
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402


def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def sp(x):
    try:
        return float(str(x).replace("$", ""))
    except (TypeError, ValueError):
        return None


def top(r):
    return min(range(len(r["rows"])), key=lambda i: (-r["rows"][i]["ability"], r["rows"][i]["n"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("cand"); ap.add_argument("out")
    ap.add_argument("--extra", action="append", default=[])
    args = ap.parse_args()
    base, cand = load(args.base), load(args.cand)
    assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in base]
    rb, rc = _stage4_metric_rows(base, score), _stage4_metric_rows(cand, score)
    v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=rb, candidate_rows=rc,
                             leakage_audit_passed=True,
                             ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    out = {"races": len(base), "verdict": v["verdict"], "reason": v["reason"],
           "primary": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["primary"].items()},
           "ranking": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["ranking"].items()},
           "counts_base": _counts(base, score), "counts_cand": _counts(cand, score)}

    def fbucket(r):
        n = len(r["rows"]); return "<=8" if n <= 8 else "9-10" if n <= 10 else "11-12" if n <= 12 else "13+"

    def spbucket(r):
        s = sp(r["rows"][top(r)].get("sp"))
        return "unknown" if s is None else "$1-3" if s < 3 else "$3-5" if s < 5 else "$5-8" if s < 8 else "$8-15" if s < 15 else "$15+"

    fns = [("field", fbucket), ("top_pick_sp", spbucket)]
    for extra in args.extra:
        if extra == "runs":
            fns.append(("top_pick_fq_runs", lambda r: str(r["tags"]["fq_runs"][top(r)])))
        elif extra == "proxy":
            fns.append(("proxy_race", lambda r: str(r["tags"]["proxy_race"])))
        elif extra.startswith("group:"):
            g = extra.split(":", 1)[1]
            share = lambda r, g=g: sum(g in cg for cg in r["tags"]["class_groups"]) / len(r["rows"])  # noqa: E731
            vals = sorted(share(r) for r in base)
            med = vals[len(vals) // 2]
            fns.append((f"{g}_share", lambda r, s=share, m=med: "high" if s(r) >= m and s(r) > 0 else "low"))
        else:
            raise SystemExit(f"unknown --extra {extra}")

    cohorts = {}
    for name, fn in fns:
        for key in sorted({fn(r) for r in base}):
            idx = [i for i, r in enumerate(base) if fn(r) == key]
            for metric in ("gold", "good_positional"):
                deltas = {}
                for i in idx:
                    deltas.setdefault(dates[i], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                days = sorted(deltas); rng = random.Random(7); samples = []
                for _ in range(2000):
                    pick = [days[rng.randrange(len(days))] for _ in days]
                    flat = [d for day in pick for d in deltas[day]]
                    samples.append(sum(flat) / len(flat))
                samples.sort()
                flat = [d for day in days for d in deltas[day]]
                cohorts[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": round(100 * sum(flat) / len(flat), 2),
                                                    "ci_pp": [round(100 * samples[50], 2), round(100 * samples[1949], 2)]}
    out["cohorts"] = cohorts
    out["cohort_ci_all_negative"] = [k for k, c in cohorts.items() if c["ci_pp"][1] < 0]
    out["changed_races"] = sum(1 for a, b in zip(base, cand)
                               if [x["ability"] for x in a["rows"]] != [x["ability"] for x in b["rows"]])
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("races", "changed_races", "verdict", "reason", "primary", "ranking",
                                          "cohort_ci_all_negative")}, indent=1))
    for k in ("gold", "good_positional", "pass"):
        print(k, round(out["counts_base"][k], 2), "→", round(out["counts_cand"][k], 2))


if __name__ == "__main__":
    main()
