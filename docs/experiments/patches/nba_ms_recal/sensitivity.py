"""EXP-20261124-60 secondary checks (report only, not a verdict): per-day delta, the clean tail
11-20..11-24 (after the bias_check window that inspired the hypothesis), and R2 without the square."""
import sys, numpy as np
import evaluate as E
rows = E.load(sys.argv[1])
dev = [r for r in rows if E.DEV[0] <= r["d"] <= E.DEV[1]]
hold = [r for r in rows if E.HOLD[0] <= r["d"] <= E.HOLD[1]]
y = np.array([r["y"] for r in hold], float)
b = E.ll(np.array([r["pf"] for r in hold]), y)
p2, _ = E.preds(dev, hold, "R2"); p1, _ = E.preds(dev, hold, "R1")
# linear-only variant
def design_lin(rr):
    X = E.design(rr, "R2"); return X[:, :-1]
w = E.fit(design_lin(dev), np.array([r["y"] for r in dev], float))
pl = 1 / (1 + np.exp(-design_lin(hold) @ w))
d2 = E.ll(p2, y) - b
days = [r["d"] for r in hold]
print("per-day R2 - p_final:")
for d in sorted(set(days)):
    k = np.array(days) == d; print(f"  {d} n={k.sum():5d} {d2[k].mean():+.4f}")
k = np.array([d >= "2026-11-20" for d in days])
for name, v in (("R2-p_final", d2), ("R2-R1", E.ll(p2, y) - E.ll(p1, y)), ("linear-only - p_final", E.ll(pl, y) - b), ("R2 - linear-only", E.ll(p2, y) - E.ll(pl, y))):
    m, lo, hi = E.boot(days, v); mt, lot, hit = E.boot([d for d, kk in zip(days, k) if kk], v[k])
    print(f"{name}: all {m:+.4f} [{lo:+.4f},{hi:+.4f}] | 11-20..24 only (n={k.sum()}) {mt:+.4f} [{lot:+.4f},{hit:+.4f}]")
