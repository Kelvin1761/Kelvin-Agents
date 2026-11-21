#!/usr/bin/env python3
"""EXP-20261113-43：前置加分按直路長度（V1）／逐場地收縮（V2），walk-forward。預先登記見 docs/experiments。

    python3 scratch/au_front_straight_venue_20261113.py BASE.json OUTDIR
"""
import collections, copy, json, math, os, statistics, subprocess, sys
from pathlib import Path
W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / "scratch"))
import au_newsignals_arms_20261113 as A  # noqa: E402

WARMUP, LO, HI, K, Z0 = 20, -5.0, 10.0, 200.0, 350.0


def is_front(row):
    s = str(row.get("style") or "")
    return "前領" in s or "跟前" in s


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


def logit(X, y, offset=None):
    """Newton logistic → 係數或者 None。"""
    m = len(X[0]); w = [0.0] * m
    for _ in range(50):
        g = [0.0] * m; H = [[0.0] * m for _ in range(m)]
        for i, (x, yy) in enumerate(zip(X, y)):
            z = sum(a * b for a, b in zip(w, x)) + (offset[i] if offset else 0.0)
            p = 1 / (1 + math.exp(-max(-30, min(30, z)))); q = p * (1 - p)
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


def clip(x):
    return max(LO, min(HI, x))


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    races = [r for r in data["races"] if r["date"] >= "2026-08-05"]
    def info(r):
        v = A.venue_of(r["meeting"]); g = A.geom(v)
        sl = g.get("straight_m") if g else None
        return A.slugify(v) if hasattr(A, "slugify") else v.lower(), (sl if sl else None)
    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    S = []  # (x, F, z, venue, y)
    beta1, beta2, log = {}, {}, []
    for i, d in enumerate(days):
        b1, b2 = {}, {}
        if i >= WARMUP:
            X = [[1.0, s[0], s[1], s[1] * s[2]] for s in S]; y = [s[4] for s in S]
            w1 = logit(X, y)
            if w1 and w1[1] > 0:
                b1 = {"c0": w1[2], "c1": w1[3], "b": w1[1]}
            w2 = logit([[1.0, s[0], s[1]] for s in S], y)
            if w2 and w2[1] > 0:
                a, b, c0 = w2
                byv = collections.defaultdict(list)
                for s in S:
                    if s[1]:
                        byv[s[3]].append(s)
                dv = {}
                for v, rows in byv.items():
                    off = [a + b * s[0] + c0 for s in rows]
                    wv = logit([[1.0] for _ in rows], [s[4] for s in rows], off)
                    dv[v] = (wv[0] if wv else 0.0, len(rows))
                b2 = {"c0": c0, "b": b, "d": dv}
        beta1[d], beta2[d] = b1, b2
        log.append({"date": d, "n": len(S), "V1": {k: round(v, 5) for k, v in b1.items()} if b1 else None,
                    "V2_c0": round(b2["c0"], 5) if b2 else None})
        for r in by_day[d]:
            rows = [x for x in r["rows"] if isinstance(x.get("pos"), int) and x["pos"] > 0]
            if len(rows) < 3:
                continue
            m = statistics.mean(x["ability"] for x in rows); v, sl = info(r)
            z = ((sl - Z0) / 100.0) if sl else 0.0
            for x in rows:
                F = 1.0 if (sl and is_front(x)) else 0.0
                S.append((x["ability"] - m, F, z, v, 1 if x["pos"] <= 3 else 0))
    def beta_for(arm, d, v, sl):
        if not sl:
            return 0.0
        if arm == "V1":
            p = beta1.get(d)
            return clip((p["c0"] + p["c1"] * (sl - Z0) / 100.0) / p["b"]) if p else 0.0
        p = beta2.get(d)
        if not p:
            return 0.0
        dv, n = p["d"].get(v, (0.0, 0))
        return clip((p["c0"] + n / (n + K) * dv) / p["b"])
    final = {}
    for arm in ("V1", "V2"):
        cand = copy.deepcopy(data); moved = 0
        for r in cand["races"]:
            if r["date"] < "2026-08-05":
                continue
            v, sl = info(r); bt = beta_for(arm, r["date"], v, sl)
            if bt:
                for x in r["rows"]:
                    if is_front(x):
                        x["ability"] += bt; moved += 1
        last = days[-1]
        final[arm] = {v: round(beta_for(arm, last, v, sl), 3) for v, sl in
                      {info(r) for r in races if info(r)[1]}}
        p = out / f"{arm}.json"; p.write_text(json.dumps(cand))
        print(f"{arm}: horses moved {moved}")
        subprocess.run([sys.executable, str(W / "scratch/au_short_straight_wf_judge_20261113.py"), str(base_path), str(p),
                        str(out / f"{arm}.verdict.json")], check=True, env=dict(os.environ, JUDGE_MODE="walk_forward_oos"))
    (out / "betas.json").write_text(json.dumps({"log": log, "final": final}, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
