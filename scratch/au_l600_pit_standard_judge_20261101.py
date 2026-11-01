#!/usr/bin/env python3
"""EXP-20261101-31 v3 walk_forward_oos 全紀錄判決 + protocol 預先聲明嘅分層。

    python3 au_l600_pit_standard_judge_20261101.py BASE.json CAND.json OUT.json

由 `au_fq_weight_class_judge_20261028.py` 衍生：同一個判決器；分層換成 protocol 寫嘅
馬匹數（≤8／9–12／13+）、首選 SP（$1–3／$3–6／$6+）、今仗路程、首選 PF 仗數。
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
    args = ap.parse_args()
    base, cand = load(args.base), load(args.cand)
    assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in base]
    rb, rc = _stage4_metric_rows(base, score), _stage4_metric_rows(cand, score)
    v = evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates, baseline_rows=rb, candidate_rows=rc,
                             leakage_audit_passed=True,
                             ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    out = {"races": len(base), "verdict": v["verdict"], "reason": v["reason"],
           "primary": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["primary"].items()},
           "ranking": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["ranking"].items()},
           "counts_base": _counts(base, score), "counts_cand": _counts(cand, score)}

    def fbucket(r):
        n = len(r["rows"]); return "<=8" if n <= 8 else "9-12" if n <= 12 else "13+"

    def spbucket(r):
        s = sp(r["rows"][top(r)].get("sp"))
        return "unknown" if s is None else "$1-3" if s < 3 else "$3-6" if s < 6 else "$6+"

    fns = [("field", fbucket), ("top_pick_sp", spbucket)]
    fns.append(("distance", lambda r: str(r["tags"]["distance"])))
    shares = sorted(r["tags"]["fallback_share"] for r in base)
    med = shares[len(shares) // 2]
    fns.append(("fallback_share", lambda r, m=med: "high" if r["tags"]["fallback_share"] >= m else "low"))

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
