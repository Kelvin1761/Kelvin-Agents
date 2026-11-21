#!/usr/bin/env python3
"""EXP-20261121-33：生涯同程（D1）／同場同程（D2）收縮上名率，walk-forward β，新尺判。

    arms.py BASE.json FEATURES.json OUTDIR
"""
import collections, copy, json, math, re, statistics, sys
from pathlib import Path
W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from au_eval import RANKING_METRICS, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402

P0, K, WARMUP, LO, HI = 0.30, 4.0, 20, 0.0, 40.0
REC = re.compile(r"\s*(\d+)\s*:\s*(\d+)-(\d+)-(\d+)\s*$")


def x_of(text, wins_twice=False):
    m = REC.match(text or "")
    if not m:
        return 0.0
    starts, w, s, t = map(int, m.groups())
    if starts == 0:
        return 0.0
    if wins_twice:                                   # D3（補登記）：頭馬當兩次計
        return (w + s + t + w + K * 0.40) / (starts + K) - 0.40
    return (w + s + t + K * P0) / (starts + K) - P0


def fit(samples):
    a = b = c = 0.0
    for _ in range(50):
        g = [0.0] * 3; H = [[0.0] * 3 for _ in range(3)]
        for x, f, y in samples:
            v = (1.0, x, f); z = a + b * x + c * f
            p = 1 / (1 + math.exp(-max(-30, min(30, z)))); w = p * (1 - p)
            for i in range(3):
                g[i] += (y - p) * v[i]
                for j in range(3):
                    H[i][j] += w * v[i] * v[j]
        step = solve(H, g)
        a, b, c = a + step[0], b + step[1], c + step[2]
        if max(abs(s) for s in step) < 1e-8:
            break
    return (max(LO, min(HI, c / b)) if b > 0 else 0.0), (a, b, c)


def solve(M, v):
    n = len(v); A = [row[:] + [v[i]] for i, row in enumerate(M)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[piv] = A[piv], A[i]
        for r in range(n):
            if r != i:
                k = A[r][i] / A[i][i]
                A[r] = [x - k * y for x, y in zip(A[r], A[i])]
    return [A[i][n] / A[i][i] for i in range(n)]


def load(data):
    races = [r for r in data["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def arm(base, feats, field, wins_twice=False):
    by_day = collections.defaultdict(list)
    for r in base:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    samples, betas, cand = [], [], []
    for i, d in enumerate(days):
        beta, coef = (0.0, None) if i < WARMUP else fit(samples)
        betas.append({"date": d, "beta": round(beta, 3), "n": len(samples),
                      "coef": [round(v, 5) for v in coef] if coef else None})
        for r in by_day[d]:
            xs = [x_of((feats.get(f'{r["meeting"]}|{r["race"]}|{row["n"]}') or {}).get(field), wins_twice) for row in r["rows"]]
            c = copy.deepcopy(r)
            for row, x in zip(c["rows"], xs):
                row["ability"] = row["ability"] + beta * x
            cand.append(c)
        for r in by_day[d]:                      # 當日賽果之後先入訓練
            m = statistics.mean(row["ability"] for row in r["rows"])
            for row in r["rows"]:
                x = x_of((feats.get(f'{r["meeting"]}|{r["race"]}|{row["n"]}') or {}).get(field), wins_twice)
                samples.append((row["ability"] - m, x, 1 if row["pos"] <= 3 else 0))
    return cand, betas


def judge(base, cand):
    score = lambda r: r["ability"]  # noqa: E731
    return evaluate_full_record(domain="au", mode="walk_forward_oos", dates=[r["date"] for r in base],
                                baseline_rows=_stage4_metric_rows(base, score),
                                candidate_rows=_stage4_metric_rows(cand, score),
                                leakage_audit_passed=True, ranking_metrics=RANKING_METRICS)


def main():
    base = load(json.loads(Path(sys.argv[1]).read_text()))
    feats = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, field, wt in (("D1", "dist", False), ("D2", "vdist", False), ("D3", "dist", True)):
        cand, betas = arm(base, feats, field, wt)
        v = judge(base, cand)
        (out / f"{name}.betas.json").write_text(json.dumps(betas))
        (out / f"{name}.verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=1, default=str))
        det = v.get("detail") or {}
        results[name] = {"verdict": v["verdict"], "reason": v["reason"],
                         "median_beta": statistics.median(b["beta"] for b in betas[WARMUP:]),
                         "final_beta": betas[-1]["beta"],
                         "primary": {k: [round(x["delta"] * 100, 3), round(x["ci_low"] * 100, 3), round(x["ci_high"] * 100, 3),
                                         x.get("p_value")] for k, x in det.get("primary", {}).items()},
                         "ranking": {k: [round(x["delta"] * 100, 3), round(x["ci_low"] * 100, 3), round(x["ci_high"] * 100, 3)]
                                     for k, x in det.get("ranking", {}).items()}}
    pv = {f"{n}:{k}": v["primary"][k][3] for n, v in results.items() for k in v["primary"]}
    results["holm"] = holm_adjust(pv)
    print(json.dumps(results, ensure_ascii=False, indent=1))
    (out / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
