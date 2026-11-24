"""EXP-20261124-61 design input (descriptive): is R2's gain our model or just a better de-vig of the
market? Walk-forward weekly refit (as RW) of R2 vs a market-only curve a_stat + c*logit(m) + d*logit(m)^2."""
import sys, numpy as np
import evaluate as E
rows = E.load(sys.argv[1]); days = sorted(set(r["d"] for r in rows))
def X(rr, form):
    A = E.design(rr, "R2")
    return np.delete(A, 4, axis=1) if form == "MKT" else A
def walk(form):
    o, b, lab = [], [], []
    for d in [x for x in days if x >= "2026-11-12"]:
        mon = np.datetime64(d) - ((np.datetime64(d).astype('datetime64[D]').view('int64') - 4) % 7)
        tr = [r for r in rows if r["d"] < str(mon)]; te = [r for r in rows if r["d"] == d]
        w = E.fit(X(tr, form), np.array([r["y"] for r in tr], float)) if form != "MKT" else None
        if form == "MKT":
            A = X(tr, form); yv = np.array([r["y"] for r in tr], float)
            w = np.zeros(A.shape[1]); w[4] = 1.0
            for _ in range(50):
                p = 1/(1+np.exp(-A@w)); g = A.T@(yv-p) - 1e-3*w; H = (A*(p*(1-p))[:,None]).T@A + 1e-3*np.eye(len(w)); w += np.linalg.solve(H, g)
        y = np.array([r["y"] for r in te], float)
        o.append(E.ll(1/(1+np.exp(-X(te, form)@w)), y)); b.append(E.ll(np.array([r["pf"] for r in te]), y)); lab += [d]*len(te)
    return np.concatenate(o), np.concatenate(b), lab
r2, base, lab = walk("R2"); mk, _, _ = walk("MKT")
for name, v in (("R2 weekly - p_final", r2-base), ("market-only weekly - p_final", mk-base), ("R2 - market-only (what p_final adds)", r2-mk)):
    m, lo, hi = E.boot(lab, v); print(f"{name}: {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
