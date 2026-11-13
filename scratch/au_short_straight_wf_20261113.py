#!/usr/bin/env python3
"""EXP-20261113-41：短直路前置加分，幅度 walk-forward 擬合（預先登記見 docs/experiments）。

    python3 scratch/au_short_straight_wf_20261113.py BASE.json OUTDIR
"""
import collections, copy, json, math, statistics, subprocess, sys, os
from pathlib import Path
W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W / "scratch"))
import au_newsignals_arms_20261113 as A  # noqa: E402  (geom／venue_of 同 L arm 一樣)

THRESH, WARMUP, LO, HI = 375.0, 20, 0.0, 10.0


def is_front(row):
    s = str(row.get("style") or "")
    return "前領" in s or "跟前" in s


def fit(samples):
    """logistic y ~ a + b·x + c·f（Newton）→ β = c/b；唔得 → 0。"""
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
        try:
            step = solve(H, g)
        except ZeroDivisionError:
            return 0.0, None
        a, b, c = a + step[0], b + step[1], c + step[2]
        if max(abs(s) for s in step) < 1e-8:
            break
    else:
        return 0.0, (a, b, c)
    if b <= 0:
        return 0.0, (a, b, c)
    return max(LO, min(HI, c / b)), (a, b, c)


def solve(M, v):
    n = len(v); A_ = [row[:] + [v[i]] for i, row in enumerate(M)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(A_[r][i]))
        if abs(A_[piv][i]) < 1e-12:
            raise ZeroDivisionError
        A_[i], A_[piv] = A_[piv], A_[i]
        for r in range(n):
            if r != i:
                k = A_[r][i] / A_[i][i]
                A_[r] = [x - k * y for x, y in zip(A_[r], A_[i])]
    return [A_[i][n] / A_[i][i] for i in range(n)]


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    races = [r for r in data["races"] if r["date"] >= "2026-08-05"]
    def short(r):
        g = A.geom(A.venue_of(r["meeting"]))
        return bool(g and g.get("straight_m") and g["straight_m"] < THRESH)
    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    samples, betas, beta_of = [], [], {}
    for i, d in enumerate(days):
        if i < WARMUP:
            beta, coef = 0.0, None
        else:
            beta, coef = fit(samples)
        beta_of[d] = beta; betas.append({"date": d, "beta": round(beta, 4), "n_train": len(samples),
                                         "coef": [round(x, 5) for x in coef] if coef else None})
        for r in by_day[d]:  # 當日收市之後先加入訓練（賽果）
            rows = [x for x in r["rows"] if isinstance(x.get("pos"), int) and x["pos"] > 0]
            if len(rows) < 3:
                continue
            m = statistics.mean(x["ability"] for x in rows); s = short(r)
            for x in rows:
                samples.append((x["ability"] - m, 1.0 if (s and is_front(x)) else 0.0, 1 if x["pos"] <= 3 else 0))
    cand = copy.deepcopy(data); moved = races_moved = 0
    for r in cand["races"]:
        if r["date"] < "2026-08-05" or not short(r):
            continue
        beta = beta_of.get(r["date"], 0.0); hit = False
        for x in r["rows"]:
            if beta and is_front(x):
                x["ability"] = x["ability"] + beta; moved += 1; hit = True
        races_moved += hit
    (out / "betas.json").write_text(json.dumps(betas, indent=0))
    print(f"days {len(days)} warmup {WARMUP} final beta {betas[-1]['beta']} median beta(post-warmup) "
          f"{statistics.median(b['beta'] for b in betas[WARMUP:]):.3f}; horses moved {moved}, races {races_moved}")
    p = out / "W1.json"; p.write_text(json.dumps(cand))
    env = dict(os.environ, JUDGE_MODE="walk_forward_oos")
    subprocess.run([sys.executable, str(W / "scratch/au_short_straight_wf_judge_20261113.py"),
                    str(base_path), str(p), str(out / "W1.verdict.json")], check=True, env=env)
    p.unlink()


if __name__ == "__main__":
    main()
