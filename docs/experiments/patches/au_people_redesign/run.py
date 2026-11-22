#!/usr/bin/env python3
"""EXP-20261122-04（見 PROTOCOL.md）。 run.py BASE.json RESULTS.csv SNAPSHOTS.jsonl CACHE.json OUT.json"""
import ast, bisect, collections, csv, json, math, re, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[3]
SC = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score  # noqa: E402
MID = {"$0 - $5,000": 2500, "$5,001 - $10,000": 7500, "$10,001 - $20,000": 15000, "$20,001 - $50,000": 35000,
       "$50,001 - $100,000": 75000, "$100,001 - $200,000": 150000, "$200,001 - $500,000": 350000, "$500,000+": 750000}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\([^)]*\)", "", str(s or "")).lower())


def prize(table, per_start):
    t = (table or {}).get("Last 12 Months") or {}
    n = sum((v or {}).get("starts") or 0 for v in t.values())
    if not n:
        return None
    tot = sum(((t.get(b) or {}).get("starts") or 0) * m for b, m in MID.items())
    return math.log10((tot / n if per_start else tot) + 1)


def load_snaps(path, cache):
    names = {k: norm(v.get("name")) for k, v in cache.items()}
    out = {"tot": collections.defaultdict(list), "eps": collections.defaultdict(list)}
    with open(path) as f:
        for line in f:
            r = json.loads(line); cs = r.get("contextual_stats")
            if isinstance(cs, str):
                try:
                    cs = ast.literal_eval(cs)
                except Exception:
                    continue
            nm = names.get(r["key"]) or norm(r.get("name"))
            if not nm:
                continue
            pm = (cs or {}).get("Prize Money")
            for k, ps in (("tot", False), ("eps", True)):
                v = prize(pm, ps)
                if v is not None:
                    out[k][(r["kind"], nm)].append((r["captured_at"][:10], v))
    for d in out.values():
        for k in d:
            d[k].sort()
    return out


def asof(rows, date):
    i = bisect.bisect_left(rows or [], (date,)) - 1
    return rows[i][1] if i >= 0 else None


def compose(features):
    return compose_matrix_score(map_features_to_matrix_scores(features))


def fit(S):
    X = np.array(S, float); V = np.column_stack([np.ones(len(X)), X[:, :-1]]); Y = X[:, -1]; th = np.zeros(V.shape[1])
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(V @ th, -30, 30))); w = p * (1 - p)
        try:
            st = np.linalg.solve((V * w[:, None]).T @ V + 1e-9 * np.eye(V.shape[1]), V.T @ (Y - p))
        except np.linalg.LinAlgError:
            return None
        th += st
        if np.abs(st).max() < 1e-8:
            break
    return th


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
    people = {}
    for r in csv.DictReader(open(sys.argv[2], encoding="utf-8-sig")):
        people[(r["Date"], r["Race"], norm(r["Horse"]))] = (norm(r["Jockey"]), norm(r["Trainer"]))
    snaps = load_snaps(sys.argv[3], json.loads(Path(sys.argv[4]).read_text()))
    # per-row raw values
    rows = []
    for ri, r in enumerate(base):
        for x in r["rows"]:
            j, t = people.get((r["date"], str(r["race"]), norm(x["name"])), (None, None))
            rows.append((ri, x, {k: (asof(snaps[k].get(("jockey", j)), r["date"]) if j else None,
                                    asof(snaps[k].get(("trainer", t)), r["date"]) if t else None) for k in ("tot", "eps")}))
    def stats(vals):
        v = np.array([a for a in vals if a is not None], float); return v.mean(), v.std()
    leaf = {"J": stats([x["features"]["jockey_score"] for _, x, _ in rows]), "T": stats([x["features"]["trainer_score"] for _, x, _ in rows])}
    pz = {k: {"J": stats([v[k][0] for _, _, v in rows]), "T": stats([v[k][1] for _, _, v in rows])} for k in ("tot", "eps")}
    print("leaf mean/sd", {k: [round(a, 2) for a in v] for k, v in leaf.items()}, "coverage J/T",
          round(np.mean([v["tot"][0] is not None for _, _, v in rows]), 3), round(np.mean([v["tot"][1] is not None for _, _, v in rows]), 3), flush=True)
    def prize_leaf(kind, who, val):
        if val is None:
            return None
        m, s = pz[kind][who]; lm, ls = leaf[who]
        return float(np.clip(lm + ls * (val - m) / s, 0, 100))
    by_race = collections.defaultdict(list)
    for ri, x, v in rows:
        by_race[ri].append((x, v))
    def arm_fixed(kind, mix):
        out = []
        for ri, r in enumerate(base):
            new = []
            for x, v in by_race[ri]:
                f = dict(x["features"])
                for who, key, val in (("J", "jockey_score", v[kind][0]), ("T", "trainer_score", v[kind][1])):
                    pl = prize_leaf(kind, who, val)
                    if pl is not None:
                        f[key] = (1 - mix) * f[key] + mix * pl
                new.append(dict(x, ability=x["ability"] - compose(x["features"]) + compose(f)))
            out.append(dict(r, rows=new))
        return out
    # R4 walk-forward
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    def prep(ri):
        r = base[ri]; X = []; abil = []
        for x, v in by_race[ri]:
            f0 = dict(x["features"]); f1 = dict(f0, jockey_score=60.0, trainer_score=60.0)
            abil.append(x["ability"] - compose(f0) + compose(f1))
            zj = (v["tot"][0] - pz["tot"]["J"][0]) / pz["tot"]["J"][1] if v["tot"][0] is not None else np.nan
            zt = (v["tot"][1] - pz["tot"]["T"][0]) / pz["tot"]["T"][1] if v["tot"][1] is not None else np.nan
            X.append([f0["jockey_score"], f0["trainer_score"], zj, zt])
        X = np.array(X, float)
        for c in range(X.shape[1]):
            col = X[:, c]; m = np.nanmean(col) if np.isfinite(col).any() else 0.0; col[~np.isfinite(col)] = m; X[:, c] = col - col.mean()
        return np.array(abil), X
    samples = []; r4 = [None] * len(base); betas = []
    for k, d in enumerate(sorted(by)):
        th = fit(samples) if k >= 20 and samples else None
        beta = np.clip(th[2:] / th[1], -30, 30) if th is not None and th[1] > 0 else None
        if beta is not None:
            betas.append(beta)
        for i in by[d]:
            a, X = prep(i)
            vals = a + (X @ beta if beta is not None else np.array([x["ability"] for x in base[i]["rows"]]) - a)
            r4[i] = dict(base[i], rows=[dict(x, ability=float(v)) for x, v in zip(base[i]["rows"], vals)])
        for i in by[d]:
            a, X = prep(i); ac = a - a.mean(); y = [int(x["pos"] <= 3) for x in base[i]["rows"]]
            samples += [[ac[j], *X[j], y[j]] for j in range(len(y))]
    if betas:
        print("R4 beta median [J勝率分, T勝率分, J總獎金z, T總獎金z]", np.median(np.array(betas), 0).round(3).tolist(), flush=True)
    arms = {"R1": arm_fixed("tot", 1.0), "R2": arm_fixed("tot", 0.5), "R3": arm_fixed("eps", 1.0), "R4": r4}
    out = {}
    for name, cand in arms.items():
        v = L.evaluate(base, cand, nnull=100)
        cb, cc = L.calibrations(base), L.calibrations(cand); rr = []
        for b_, c_ in zip(base, cand):
            if b_["date"] in cb:
                lb, nn = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rr.append((b_["date"], lc - lb, nn))
        byd = collections.defaultdict(list)
        for ii, q in enumerate(rr):
            byd[q[0]].append(ii)
        days = sorted(byd); dl = np.array([q[1] for q in rr]); nnn = np.array([q[2] for q in rr]); rng = np.random.default_rng(0); bs = []
        for _ in range(2000):
            jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
        v["p"] = float((np.array(bs) >= 0).mean()); out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]], "top2any", round(v["top2_any_hit_pp"], 2), flush=True)
    ps = sorted((v["p"], k) for k, v in out.items())
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
    print({k: round(v["holm_p"], 4) for k, v in out.items()})
    Path(sys.argv[5]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
