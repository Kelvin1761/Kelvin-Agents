#!/usr/bin/env python3
"""EXP-20261121-30：濕地 overlay 按濕度調幅度（walk-forward）。預先登記見 docs/experiments。

    python3 scratch/au_wet_scale_wf_20261121.py BASE.json OUTDIR
"""
import collections, copy, json, math, os, re, statistics, subprocess, sys
from pathlib import Path
W = Path(__file__).resolve().parents[1]
WARMUP, LO, HI = 20, 0.0, 4.0
STATES = ("heavy", "soft7plus", "soft_other")


def state(going):
    g = str(going or "")
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)?", g, re.I)
    if not m:
        return None
    if m.group(1).lower() == "heavy":
        return "heavy"
    return "soft7plus" if m.group(2) and int(m.group(2)) >= 7 else "soft_other"


def solve(M, v):
    n = len(v); a = [row[:] + [v[i]] for i, row in enumerate(M)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(a[r][i]))
        if abs(a[p][i]) < 1e-12:
            raise ZeroDivisionError
        a[i], a[p] = a[p], a[i]
        for r in range(n):
            if r != i:
                k = a[r][i] / a[i][i]
                a[r] = [x - k * y for x, y in zip(a[r], a[i])]
    return [a[i][n] / a[i][i] for i in range(n)]


def logit(X, y):
    m = len(X[0]); w = [0.0] * m
    for _ in range(50):
        g = [0.0] * m; H = [[0.0] * m for _ in range(m)]
        for x, yy in zip(X, y):
            z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-max(-30, min(30, z)))); q = p * (1 - p)
            for j in range(m):
                g[j] += (yy - p) * x[j]
                for k in range(m):
                    H[j][k] += q * x[j] * x[k]
        try:
            step = solve(H, g)
        except ZeroDivisionError:
            return None
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            return w
    return None


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    races = [r for r in data["races"] if r["date"] >= "2026-08-05"]
    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    X, Y, mult, log = [], [], {}, []
    for i, d in enumerate(days):
        m = {s: 1.0 for s in STATES}
        if i >= WARMUP:
            w = logit(X, Y)
            if w and w[1] > 0:
                m = {s: max(LO, min(HI, w[2 + j] / w[1])) for j, s in enumerate(STATES)}
        mult[d] = m; log.append({"date": d, "n": len(X), **{s: round(v, 4) for s, v in m.items()}})
        for r in by_day[d]:
            rows = [x for x in r["rows"] if isinstance(x.get("pos"), int) and x["pos"] > 0]
            if len(rows) < 3:
                continue
            st = state(rows[0].get("going"))
            base = [x["ability"] - (x.get("wet") or 0.0) for x in rows]
            mu = statistics.mean(base)
            for x, b in zip(rows, base):
                wet = x.get("wet") or 0.0
                X.append([1.0, b - mu] + [wet if st == s else 0.0 for s in STATES])
                Y.append(1 if x["pos"] <= 3 else 0)
    cand = copy.deepcopy(data); moved = 0
    for r in cand["races"]:
        if r["date"] < "2026-08-05":
            continue
        st = state(r["rows"][0].get("going"))
        if not st:
            continue
        k = mult.get(r["date"], {}).get(st, 1.0)
        for x in r["rows"]:
            wet = x.get("wet") or 0.0
            if wet and k != 1.0:
                x["ability"] += (k - 1.0) * wet; moved += 1
    (out / "mult.json").write_text(json.dumps(log, indent=0))
    print(f"days {len(days)}; final m {log[-1]}; horses moved {moved}")
    p = out / "M1.json"; p.write_text(json.dumps(cand))
    subprocess.run([sys.executable, str(W / "scratch/au_short_straight_wf_judge_20261113.py"), str(base_path), str(p),
                    str(out / "M1.verdict.json")], check=True, env=dict(os.environ, JUDGE_MODE="walk_forward_oos"))


if __name__ == "__main__":
    main()
