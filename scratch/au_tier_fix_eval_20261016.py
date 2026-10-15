#!/usr/bin/env python3
"""EXP-20261016-05 §7 判決：tier parser 修正前後（v3 fixed_rule 全紀錄 + 預先聲明分層）。"""
import json, random, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import _counts, _stage4_metric_rows
from model_evaluation_decision import evaluate_full_record

def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))

base, cand = load(sys.argv[1]), load(sys.argv[2])
assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
score = lambda r: r["ability"]
dates = [r["date"] for r in base]
rb, rc = _stage4_metric_rows(base, score), _stage4_metric_rows(cand, score)
v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=rb, candidate_rows=rc,
                         leakage_audit_passed=True, ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
out = {"races": len(base), "verdict": v["verdict"], "reason": v["reason"],
       "primary": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["primary"].items()},
       "ranking": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["ranking"].items()},
       "counts_base": _counts(base, score), "counts_cand": _counts(cand, score)}

def sp(x):
    try: return float(str(x).replace("$", ""))
    except (TypeError, ValueError): return None
def fbucket(r):
    n = len(r["rows"]); return "<=8" if n <= 8 else "9-10" if n <= 10 else "11-12" if n <= 12 else "13+"
def spbucket(r):
    top = min(r["rows"], key=lambda x: (-x["ability"], x["n"])); s = sp(top.get("sp"))
    return "unknown" if s is None else "$1-3" if s < 3 else "$3-5" if s < 5 else "$5-8" if s < 8 else "$8-15" if s < 15 else "$15+"
cohorts = {}
for name, fn in (("field", fbucket), ("top_pick_sp", spbucket)):
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
Path(sys.argv[3]).write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(json.dumps({k: out[k] for k in ("races", "verdict", "reason", "primary", "ranking", "cohort_ci_all_negative")}, indent=1))
for k in ("gold", "good_positional", "pass"): print(k, round(out["counts_base"][k], 2), "→", round(out["counts_cand"][k], 2))
