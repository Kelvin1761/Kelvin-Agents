#!/usr/bin/env python3
"""EXP-20261122-03（見 PROTOCOL.md）。 run.py BASE.json RESULTS.csv SNAPSHOTS.jsonl CACHE.json OUT.json"""
import ast, bisect, collections, csv, json, math, re, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[3]
SC = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import importlib.util
spec = importlib.util.spec_from_file_location("L", str(REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_logloss_ruler.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score  # noqa: E402

MID = {"$0 - $5,000": 2500, "$5,001 - $10,000": 7500, "$10,001 - $20,000": 15000, "$20,001 - $50,000": 35000,
       "$50,001 - $100,000": 75000, "$100,001 - $200,000": 150000, "$200,001 - $500,000": 350000, "$500,000+": 750000}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def eps(table):
    t = (table or {}).get("Last 12 Months") or {}
    n = sum((v or {}).get("starts") or 0 for v in t.values())
    if not n:
        return None
    return math.log10(sum(((t.get(b) or {}).get("starts") or 0) * m for b, m in MID.items()) / n + 1)


def load_snaps(path, cache):
    names = {k: norm(v.get("name")) for k, v in cache.items()}
    out = collections.defaultdict(list)
    with open(path) as f:
        for line in f:
            r = json.loads(line); cs = r.get("contextual_stats")
            if isinstance(cs, str):
                try:
                    cs = ast.literal_eval(cs)
                except Exception:
                    continue
            v = eps((cs or {}).get("Prize Money"))
            nm = names.get(r["key"]) or norm(r.get("name"))
            if v is not None and nm:
                out[(r["kind"], nm)].append((r["captured_at"][:10], v))
    for k in out:
        out[k].sort()
    return out


def asof(snaps, kind, name, date):
    rows = snaps.get((kind, name)) or []
    i = bisect.bisect_left(rows, (date,)) - 1
    return rows[i][1] if i >= 0 else None


def fit(S):
    X = np.array(S, float); th = np.zeros(X.shape[1])
    V = np.column_stack([np.ones(len(X)), X[:, :-1]]); Y = X[:, -1]; th = np.zeros(V.shape[1])
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


def walk(base_abil, feats, races, by):
    """base_abil: per race list of abilities；feats: per race array (n,2)；→ candidate ability lists（walk-forward β）。"""
    samples = []; out = [None] * len(races)
    for k, d in enumerate(sorted(by)):
        th = fit(samples) if k >= 20 and samples else None
        beta = np.clip(th[2:] / th[1], -30, 30) if th is not None and th[1] > 0 else np.zeros(2)
        for i in by[d]:
            out[i] = list(np.array(base_abil[i]) + feats[i] @ beta)
        for i in by[d]:
            a = np.array(base_abil[i]); ac = a - a.mean(); y = [int(x["pos"] <= 3) for x in races[i]["rows"]]
            samples += [[ac[j], feats[i][j, 0], feats[i][j, 1], y[j]] for j in range(len(y))]
    return out


def with_ab(races, abil):
    return [dict(r, rows=[dict(x, ability=float(v)) for x, v in zip(r["rows"], abil[i])]) for i, r in enumerate(races)]


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
    people = {}
    for r in csv.DictReader(open(sys.argv[2], encoding="utf-8-sig")):
        people[(r["Date"], r["Race"], norm(r["Horse"]))] = (norm(r["Jockey"]), norm(r["Trainer"]))
    snaps = load_snaps(sys.argv[3], json.loads(Path(sys.argv[4]).read_text()))
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    feats, cover, P1base, who_t = [], [0, 0], [], []
    for r in base:
        F = []
        tl = []
        for x in r["rows"]:
            j, t = people.get((r["date"], str(r["race"]), norm(x["name"])), (None, None))
            ej, et = asof(snaps, "jockey", j, r["date"]) if j else None, asof(snaps, "trainer", t, r["date"]) if t else None
            cover[0] += ej is not None; cover[1] += et is not None; F.append([ej, et]); tl.append(t)
        F = np.array([[np.nan if v is None else v for v in row] for row in F], float)
        for c in range(2):
            col = F[:, c]; m = np.nanmean(col) if np.isfinite(col).any() else 0.0
            col[~np.isfinite(col)] = m; F[:, c] = col - col.mean()
        feats.append(F); who_t.append(tl)
        ab = []
        for x in r["rows"]:
            f0 = dict(x["features"]); f1 = dict(f0, jockey_score=60.0, trainer_score=60.0)
            ab.append(x["ability"] - (compose_matrix_score(map_features_to_matrix_scores(f0))
                                      - compose_matrix_score(map_features_to_matrix_scores(f1))))
        P1base.append(ab)
    n = sum(len(r["rows"]) for r in base)
    print("coverage jockey/trainer", round(cover[0] / n, 3), round(cover[1] / n, 3), flush=True)
    ability = [[x["ability"] for x in r["rows"]] for r in base]
    # TRES（EXP-20261122-02 同一計法）
    cal = L.calibrations(base); resid = collections.defaultdict(float); cnt = collections.defaultdict(int); tres = [None] * len(base)
    for d in sorted(by):
        for i in by[d]:
            R = np.array([resid[t] / (cnt[t] + 50.0) if t else 0.0 for t in who_t[i]]); tres[i] = list(np.array(ability[i]) + 40.0 * (R - R.mean()))
        if d in cal:
            for i in by[d]:
                a = np.array(ability[i]); p = 1 / (1 + np.exp(-(cal[d][0] + cal[d][1] * (a - a.mean()))))
                for t, x, pp in zip(who_t[i], base[i]["rows"], p):
                    if t:
                        resid[t] += int(x["pos"] <= 3) - pp; cnt[t] += 1
    arms = {"P1": (ability, walk(P1base, feats, base, by)), "P2": (ability, walk(ability, feats, base, by)),
            "P3": (tres, walk(tres, feats, base, by))}
    out = {}
    for name, (b_ab, c_ab) in arms.items():
        B, C = with_ab(base, b_ab), with_ab(base, c_ab)
        v = L.evaluate(B, C, nnull=100)
        cb, cc = L.calibrations(B), L.calibrations(C); rows = []
        for b_, c_ in zip(B, C):
            if b_["date"] in cb:
                lb, nn = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rows.append((b_["date"], lc - lb, nn))
        byd = collections.defaultdict(list)
        for ii, rr in enumerate(rows):
            byd[rr[0]].append(ii)
        days = sorted(byd); dl = np.array([rr[1] for rr in rows]); nnn = np.array([rr[2] for rr in rows]); rng = np.random.default_rng(0); bs = []
        for _ in range(2000):
            jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
        v["p"] = float((np.array(bs) >= 0).mean()); out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]], flush=True)
    ps = sorted((v["p"], k) for k, v in out.items())
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
    print({k: round(v["holm_p"], 4) for k, v in out.items()})
    Path(sys.argv[5]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
