#!/usr/bin/env python3
"""EXP-20261121-39 A 組判決：同一份 code 嘅 BASE／G50／G25 dump。  judge_similarity.py DIR OUT.json"""
import collections, json, sys
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_logloss_ruler as L  # noqa: E402


def family(r):
    g = str(r["rows"][0].get("going") or "")
    return "Heavy" if "Heavy" in g else "Soft" if "Soft" in g else "Good/other"


def pvalue(base, cand):
    cb, cc = L.calibrations(base), L.calibrations(cand); rows = []
    for b, c in zip(base, cand):
        if b["date"] in cb:
            lb, n = L._nll(b, cb[b["date"]]); lc, _ = L._nll(c, cc[c["date"]]); rows.append((b["date"], lc - lb, n, family(b)))
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r[0]].append(i)
    days = sorted(by); dl = np.array([r[1] for r in rows]); nn = np.array([r[2] for r in rows]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))]); bs.append(dl[ii].sum() / nn[ii].sum())
    fam = {}
    for f in ("Good/other", "Soft", "Heavy"):
        m = np.array([r[3] == f for r in rows]); fam[f] = float(dl[m].sum() / nn[m].sum()) if m.any() else None
    return float((np.array(bs) >= 0).mean()), fam


def subset(base, cand):
    out = {}
    for f in ("Good/other", "Soft", "Heavy"):
        g = gd = n = 0
        for b, c in zip(base, cand):
            if family(b) == f:
                mb, mc = L._metrics(b), L._metrics(c); g += mc[0] - mb[0]; gd += mc[1] - mb[1]; n += 1
        out[f] = (round(100 * g / max(1, n), 2), round(100 * gd / max(1, n), 2), n)
    return out


def main():
    d = Path(sys.argv[1]); load = lambda p: L.eligible(json.loads(p.read_text())["races"])  # noqa: E731
    base = load(d / "BASE.json"); out = {}
    for name in ("G50", "G25"):
        cand = load(d / f"{name}.json")
        v = L.evaluate(base, cand, nnull=200); v["p"], v["dlogloss_by_going"] = pvalue(base, cand); v["gold_good_by_going"] = subset(base, cand)
        out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]], flush=True)
        print("   by going Δll", {k: (round(x, 6) if x is not None else None) for k, x in v["dlogloss_by_going"].items()}, "G/G", v["gold_good_by_going"], flush=True)
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
