"""EXP-20261124-61 design input (descriptive, not a verdict): how would a periodic refit policy
have done on 11-12..11-24? Each target day is scored by an R1/R2 layer fitted only on MS-era legs
settled on earlier target days (expanding, or a trailing window), refitted every `cadence` days."""
import sys, numpy as np
import evaluate as E
rows = E.load(sys.argv[1])
days = sorted(set(r["d"] for r in rows))
test_days = [d for d in days if d >= "2026-11-12"]
def run(form, window=None, cadence=1):
    out, base, lab = [], [], []
    w_cache, last_fit = None, None
    for i, d in enumerate(test_days):
        if w_cache is None or i % cadence == 0:
            prior = [x for x in days if x < d]
            if window: prior = prior[-window:]
            tr = [r for r in rows if r["d"] in prior]
            w_cache = E.fit(E.design(tr, form), np.array([r["y"] for r in tr], float))
        te = [r for r in rows if r["d"] == d]; y = np.array([r["y"] for r in te], float)
        p = 1 / (1 + np.exp(-E.design(te, form) @ w_cache))
        out.append(E.ll(p, y)); base.append(E.ll(np.array([r["pf"] for r in te]), y)); lab += [d] * len(te)
    o, b = np.concatenate(out), np.concatenate(base)
    m, lo, hi = E.boot(lab, o - b)
    return m, lo, hi
for form in ("R1", "R2"):
    for window, cad in ((None, 1), (None, 7), (7, 1), (14, 1)):
        m, lo, hi = run(form, window, cad)
        print(f"{form} window={'all' if window is None else str(window)+'d'} refit every {cad}d: Δ vs p_final {m:+.4f} [{lo:+.4f}, {hi:+.4f}]")
