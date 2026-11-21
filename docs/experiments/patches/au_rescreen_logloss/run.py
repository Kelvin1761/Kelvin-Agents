#!/usr/bin/env python3
"""EXP-20261121-37 重新篩選（見 PROTOCOL.md）。    run.py BASE.json FEATURES.json OUT.json"""
import collections, glob, importlib.util, json, math, re, statistics, sys
from pathlib import Path
import numpy as np
WT = Path(__file__).resolve().parents[3]  # repo root（需要 EXP-34 measure.py 同 au_logloss_ruler.py）
sys.path.insert(0, str(WT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_logloss_ruler as L  # noqa: E402
spec = importlib.util.spec_from_file_location("measure", WT / "docs/experiments/patches/au_labels/measure.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
REC = re.compile(r"\s*(\d+)\s*:\s*(\d+)-(\d+)-(\d+)\s*$")


def shrunk(text, twice=False):
    m = REC.match(text or "")
    if not m:
        return 0.0
    s, w, a, b = map(int, m.groups())
    if not s:
        return 0.0
    if twice:
        return (w + a + b + w + 4 * 0.40) / (s + 4) - 0.40
    return (w + a + b + 4 * 0.30) / (s + 4) - 0.30


def fit(samples):
    X = np.array(samples, float)
    a = b = c = 0.0
    for _ in range(60):
        z = np.clip(a + b * X[:, 0] + c * X[:, 1], -30, 30); p = 1 / (1 + np.exp(-z)); w = p * (1 - p)
        V = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
        g = V.T @ (X[:, 2] - p); H = (V * w[:, None]).T @ V
        try:
            st = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return 0.0
        a, b, c = a + st[0], b + st[1], c + st[2]
        if np.abs(st).max() < 1e-8:
            break
    return float(max(-20, min(20, c / b))) if b > 0 else 0.0


def arm(base, xs):
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    days = sorted(by); samples = []; cand = [None] * len(base); betas = []
    for k, d in enumerate(days):
        beta = fit(samples) if k >= 20 and samples else 0.0
        betas.append(beta)
        for i in by[d]:
            r = base[i]
            cand[i] = dict(r, rows=[dict(x, ability=x["ability"] + beta * xs[i][j]) for j, x in enumerate(r["rows"])])
        for i in by[d]:
            r = base[i]; m = statistics.mean(x["ability"] for x in r["rows"])
            samples += [(x["ability"] - m, xs[i][j], 1 if x["pos"] <= 3 else 0) for j, x in enumerate(r["rows"])]
    return cand, betas


def pvalue(base, cand):
    """單邊 p = bootstrap Δlog-loss ≥ 0 嘅比例（同 evaluate 一樣嘅校準同抽樣）。"""
    cb, cc = L.calibrations(base), L.calibrations(cand)
    rows = []
    for b, c in zip(base, cand):
        if b["date"] in cb:
            lb, n = L._nll(b, cb[b["date"]]); lc, _ = L._nll(c, cc[c["date"]]); rows.append((b["date"], lc - lb, n))
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r[0]].append(i)
    days = sorted(by); dl = np.array([r[1] for r in rows]); nn = np.array([r[2] for r in rows])
    rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))]); bs.append(dl[ii].sum() / nn[ii].sum())
    return float((np.array(bs) >= 0).mean())


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
    feats = json.loads(Path(sys.argv[2]).read_text())
    dirs = {Path(d).name: d for d in glob.glob(M.ROOT + "/2026-*") + glob.glob(M.ROOT + "/Archive/**/2026-*", recursive=True)}
    cache = {}; lab = []
    for r in base:
        if r["meeting"] not in cache:
            cache[r["meeting"]] = M.facts(dirs[r["meeting"]]) if r["meeting"] in dirs else {}
        F = cache[r["meeting"]]; race_f = {n: v for (rn, n), v in F.items() if rn == r["race"]}
        lab.append([set(M.labels(x, race_f[x["n"]], race_f)) if x["n"] in race_f else set() for x in r["rows"]])
    def fx(key, f):
        return [[f(r, x, lab[i][j], feats.get(f'{r["meeting"]}|{r["race"]}|{x["n"]}') or {}) for j, x in enumerate(r["rows"])]
                for i, r in enumerate(base)]
    arms = {
        "D1": fx("D1", lambda r, x, l, f: shrunk(f.get("dist"))),
        "D2": fx("D2", lambda r, x, l, f: shrunk(f.get("vdist"))),
        "D3": fx("D3", lambda r, x, l, f: shrunk(f.get("dist"), True)),
        "OLD": fx("OLD", lambda r, x, l, f: float("old_horse" in l)),
        "FUNIL": fx("FUNIL", lambda r, x, l, f: float("first_up_nil" in l)),
        "SUNIL": fx("SUNIL", lambda r, x, l, f: float("second_up_nil" in l)),
        "QB": fx("QB", lambda r, x, l, f: float("quick_backup" in l)),
        "UPGOOD": fx("UPGOOD", lambda r, x, l, f: float(bool({"first_up_good", "second_up_good"} & l))),
        "UPNIL": fx("UPNIL", lambda r, x, l, f: float(bool({"first_up_nil", "second_up_nil"} & l))),
    }
    out = {}
    for name, xs in arms.items():
        cand, betas = arm(base, xs)
        v = L.evaluate(base, cand, nnull=100)
        v["p"] = pvalue(base, cand); v["beta_median"] = statistics.median(betas[20:]); v["beta_final"] = betas[-1]
        v["n_flagged"] = int(sum(1 for row in xs for t in row if t))
        out[name] = v
        print(name, v["verdict"], v["reason"], "Δ", [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "null", v["beats_null_share"],
              "gold", [round(t, 2) for t in v["gold_pp"]], "good", [round(t, 2) for t in v["good_pp"]],
              "β", round(v["beta_median"], 2), flush=True)
    ps = sorted((v["p"], k) for k, v in out.items()); m = len(ps)
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (m - j) * ps[j][0]) for j in range(rank + 1)))
    for k, v in out.items():
        v["final"] = "PASS" if v["verdict"] == "PASS" and v["holm_p"] < 0.05 else "REJECT"
    print({k: (v["final"], round(v["holm_p"], 4)) for k, v in out.items()})
    Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
