#!/usr/bin/env python3
"""EXP-20261102-10 判決：v3 fixed_rule 全紀錄（08-05 起）+ 預先聲明分層（加今場地況）。  judge.py BASE CAND OUT"""
import glob, json, os, random, re, sys
from pathlib import Path
W = Path(__file__).resolve().parents[1]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402

ROOT = open(W / ".wongchoi_au_data_root").read().strip()
DIRS = {os.path.basename(d): d for d in glob.glob(ROOT + "/20*") + glob.glob(ROOT + "/Archive/**/20*", recursive=True)}
HCP = re.compile(r"\b(?:handicap|hcp|hcap|benchmark|bm\s*\d+)\b|\b\d{1,2}\s*-\s*\d{2,3}\b", re.I)
_card = {}

def card(meeting, race):
    k = (meeting, race)
    if k not in _card:
        hcp, rated, n = None, 0, 0
        d = DIRS.get(meeting)
        fs = glob.glob(f"{d}/* Race {race} Racecard.md") if d else []
        if fs:
            txt = open(fs[0], encoding="utf-8").read().splitlines()
            hcp = bool(HCP.search(txt[0])) if txt else None
            for line in txt:
                if "| Rating:" in line:
                    n += 1; rated += bool(re.search(r"Rating:\s*\d", line))
        _card[k] = (hcp, rated, n)
    return _card[k]

def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))

def sp(x):
    try: return float(str(x).replace("$", ""))
    except (TypeError, ValueError): return None

def top(r): return min(range(len(r["rows"])), key=lambda i: (-r["rows"][i]["ability"], r["rows"][i]["n"]))

def going_state(r):
    g = str(r["rows"][0].get("going") or "")
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", g, re.I)
    if not m:
        return "good/other"
    return "heavy" if m.group(1).lower() == "heavy" else ("soft7+" if int(m.group(2)) >= 7 else "soft5-6")


def main():
    base, cand = load(sys.argv[1]), load(sys.argv[2])
    assert [(r["meeting"], r["race"]) for r in base] == [(r["meeting"], r["race"]) for r in cand]
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in base]
    rb, rc = _stage4_metric_rows(base, score), _stage4_metric_rows(cand, score)
    v = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=rb, candidate_rows=rc,
                             leakage_audit_passed=True,
                             ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    out = {"races": len(base), "verdict": v["verdict"], "reason": v["reason"],
           "primary": {k: {kk: e.get(kk) for kk in ("delta", "ci_low", "ci_high", "p_value", "block_deltas")} for k, e in v["detail"]["primary"].items()},
           "ranking": {k: {kk: e.get(kk) for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["ranking"].items()},
           "counts_base": _counts(base, score), "counts_cand": _counts(cand, score)}
    def dist(r):
        try: d = float(str(r["rows"][0].get("distance")).rstrip("m"))
        except (TypeError, ValueError): return "?"
        return "<=1200" if d <= 1200 else "1201-1600" if d <= 1600 else ">1600"
    def rmix(r):
        hcp, rated, n = card(r["meeting"], r["race"])
        if not n: return "?"
        return "all_rated" if rated == n else "majority_unrated" if rated < n / 2 else "mixed"
    fns = [("field", lambda r: "<=8" if len(r["rows"]) <= 8 else "9-12" if len(r["rows"]) <= 12 else "13+"),
           ("going", going_state),
           ("top_pick_sp", lambda r: (lambda s: "unknown" if s is None else "$1-3" if s < 3 else "$3-6" if s < 6 else "$6+")(sp(r["rows"][top(r)].get("sp")))),
           ("distance", dist),
           ("top_style", lambda r: str(r["rows"][top(r)].get("style") or "")[:2] or "?"),
           ]
    cohorts = {}
    for name, fn in fns:
        keys = [fn(r) for r in base]
        for key in sorted(set(keys)):
            idx = [i for i, k in enumerate(keys) if k == key]
            for metric in ("gold", "good_positional"):
                deltas = {}
                for i in idx:
                    deltas.setdefault(dates[i], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                days = sorted(deltas); rng = random.Random(7); samples = []
                for _ in range(2000):
                    flat = [d for day in (days[rng.randrange(len(days))] for _ in days) for d in deltas[day]]
                    samples.append(sum(flat) / len(flat))
                samples.sort(); flat = [d for day in days for d in deltas[day]]
                cohorts[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": round(100 * sum(flat) / len(flat), 2),
                                                    "ci_pp": [round(100 * samples[50], 2), round(100 * samples[1949], 2)]}
    out["cohorts"] = cohorts
    out["cohort_ci_all_negative"] = [k for k, c in cohorts.items() if c["ci_pp"][1] < 0]
    out["changed_races"] = sum(1 for a, b in zip(base, cand) if [x["ability"] for x in a["rows"]] != [x["ability"] for x in b["rows"]])
    Path(sys.argv[3]).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    p = out["primary"]; rk = out["ranking"]
    print(f"{Path(sys.argv[2]).stem:5s} races {out['races']} changed {out['changed_races']}  {out['verdict']}/{out['reason']}")
    for k, e in {**p, **rk}.items():
        print(f"   {k:20s} {100*e['delta']:+.3f}  [{100*e['ci_low']:+.3f},{100*e['ci_high']:+.3f}] p={e['p_value']}" + (f" blocks≥0={sum(d >= 0 for d in e['block_deltas'])}/6" if k in p else ""))
    print("   cohort CI all<0:", out["cohort_ci_all_negative"])

if __name__ == "__main__":
    main()
