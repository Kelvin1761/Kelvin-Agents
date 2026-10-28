#!/usr/bin/env python3
"""EXP-20261028-15 出賽經驗校準：walk-forward 逐組綜合分加減 + v3 判決。規格見 protocol —— 唔准喺度改。

    python3 au_starts_offset_wf_20261028.py --dump dump_new.json --arm S1 --out S1.json
    python3 au_starts_offset_wf_20261028.py --dump dump_new.json --arm AA --out AA.json   # A/A：必須 REJECT

候選 = 最終綜合分（ability）+ offset[生涯出賽組]。offset 逐窗只用測試窗之前嘅乾淨賽日 fit：
  logit P(入前三) = α[馬群組] + β·(ability − 場內平均) + γ[出賽組]
  offset = 收縮(γ) / β，收縮 = n/(n+KAPPA)，再按匹數加權置中。
S1 九組全部估；S2 只估「3 仗」同「20+ 仗」（發現時揀出嘅兩組，其餘 0）；AA 全部 0。
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record  # noqa: E402

BUCKETS = ("0", "1", "2", "3", "4", "5", "6-9", "10-19", "20+")
ARMS = {"S1": BUCKETS, "S2": ("3", "20+"), "AA": ()}
FIELDS = ("<=8", "9-12", "13+")
WARMUP, WINDOW, KAPPA, RIDGE = 30, 7, 500.0, 1e-3
SCORE = lambda r: r["ability"]  # noqa: E731


def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def bucket(x):
    c = int((x.get("cls") or {}).get("career_starts") or 0)
    return str(c) if c <= 5 else "6-9" if c <= 9 else "10-19" if c <= 19 else "20+"


def field(r):
    n = len(r["rows"])
    return "<=8" if n <= 8 else "9-12" if n <= 12 else "13+"


def fit(train, active):
    """→ {出賽組: offset（綜合分點）}；唔喺 active 嘅組 = 0。"""
    if not active:
        return {b: 0.0 for b in BUCKETS}
    X, y, counts = [], [], dict.fromkeys(active, 0)
    for r in train:
        mean = sum(x["ability"] for x in r["rows"]) / len(r["rows"])
        f = field(r)
        for x in r["rows"]:
            b = bucket(x)
            X.append([float(f == k) for k in FIELDS] + [x["ability"] - mean] + [float(b == k) for k in active])
            y.append(float(x["pos"] <= 3))
            if b in counts:
                counts[b] += 1
    X, y = np.array(X), np.array(y)
    w = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], RIDGE)
    pen[:len(FIELDS) + 1] = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (y - p) - pen * w
        H = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen)
        step = np.linalg.solve(H, g)
        w += step
        if np.max(np.abs(step)) < 1e-8:
            break
    beta = w[len(FIELDS)]
    raw = {b: w[len(FIELDS) + 1 + i] / beta for i, b in enumerate(active)}
    shrunk = {b: raw[b] * counts[b] / (counts[b] + KAPPA) for b in active}
    total = sum(counts.values())
    centre = sum(shrunk[b] * counts[b] for b in active) / total if total else 0.0
    # 只喺 S1（全部組都 active）置中；S2 其餘組係 0，唔置中（否則會郁晒其他馬）
    if len(active) == len(BUCKETS):
        shrunk = {b: v - centre for b, v in shrunk.items()}
    return {b: round(float(shrunk.get(b, 0.0)), 4) for b in BUCKETS}


def apply(race, off):
    rows = [{**x, "ability": round(x["ability"] + off[bucket(x)], 6)} for x in race["rows"]]
    return {**race, "rows": rows}


def day_bootstrap(per):
    ds = sorted(per); rng = random.Random(7); samples = []
    for _ in range(2000):
        pk = [ds[rng.randrange(len(ds))] for _ in ds]
        flat = [d for day in pk for d in per[day]]
        samples.append(sum(flat) / len(flat))
    samples.sort()
    flat = [d for day in ds for d in per[day]]
    return round(100 * sum(flat) / len(flat), 2), [round(100 * samples[50], 2), round(100 * samples[1949], 2)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True); ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    races = load(args.dump)
    active = ARMS[args.arm]
    days = sorted({r["date"] for r in races})
    windows, base, cand = [], [], []
    for start in range(WARMUP, len(days), WINDOW):
        test_days = set(days[start:start + WINDOW])
        off = fit([r for r in races if r["date"] < days[start]], active)
        windows.append({"test": [min(test_days), max(test_days)], "offsets": off})
        for r in races:
            if r["date"] in test_days:
                base.append(r); cand.append(apply(r, off))
    dates = [r["date"] for r in base]
    rb, rc = _stage4_metric_rows(base, SCORE), _stage4_metric_rows(cand, SCORE)
    v = evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates, baseline_rows=rb, candidate_rows=rc,
                             leakage_audit_passed=True,
                             ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))

    def sp(x):
        try:
            return float(str(x).replace("$", ""))
        except (TypeError, ValueError):
            return None

    def top(r):
        return min(r["rows"], key=lambda x: (-x["ability"], x["n"]))
    fns = {"field": lambda r: "<=8" if len(r["rows"]) <= 8 else "9-10" if len(r["rows"]) <= 10 else "11-12" if len(r["rows"]) <= 12 else "13+",
           "top_pick_sp": lambda r: (lambda s: "unknown" if s is None else "$1-3" if s < 3 else "$3-5" if s < 5 else "$5-8" if s < 8 else "$8-15" if s < 15 else "$15+")(sp(top(r).get("sp"))),
           "top_pick_starts": lambda r: bucket(top(r))}
    cohorts = {}
    for name, fn in fns.items():
        for key in sorted({fn(r) for r in base}):
            idx = [i for i, r in enumerate(base) if fn(r) == key]
            for metric in ("gold", "good_positional"):
                per = {}
                for i in idx:
                    per.setdefault(dates[i], []).append(float(rc[i][metric]) - float(rb[i][metric]))
                d, ci = day_bootstrap(per)
                cohorts[f"{name}:{key}:{metric}"] = {"n": len(idx), "delta_pp": d, "ci_pp": ci}
    changed = sum(sorted(range(len(a["rows"])), key=lambda i: -a["rows"][i]["ability"])
                  != sorted(range(len(b["rows"])), key=lambda i: -b["rows"][i]["ability"]) for a, b in zip(base, cand))
    out = {"arm": args.arm, "test_races": len(base), "test_days": len(set(dates)), "changed_races": changed,
           "windows": windows, "verdict": v["verdict"], "reason": v["reason"],
           "primary": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["primary"].items()},
           "ranking": {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in v["detail"]["ranking"].items()},
           "counts_base": _counts(base, SCORE), "counts_cand": _counts(cand, SCORE),
           "full_record_offsets": fit(races, active),
           "cohorts": cohorts, "cohort_ci_all_negative": [k for k, c in cohorts.items() if c["ci_pp"][1] < 0]}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("arm", "test_races", "test_days", "changed_races", "verdict", "reason",
                                          "primary", "ranking", "cohort_ci_all_negative")}, indent=1, ensure_ascii=False))
    for k in ("gold", "good_positional", "pass"):
        print(k, round(out["counts_base"][k], 2), "→", round(out["counts_cand"][k], 2))
    print("offsets last window:", windows[-1]["offsets"])
    print("full record offsets:", out["full_record_offsets"])


if __name__ == "__main__":
    main()
