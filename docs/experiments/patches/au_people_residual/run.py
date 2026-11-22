#!/usr/bin/env python3
"""EXP-20261122-02（見 PROTOCOL.md）。  run.py BASE.json RESULTS.csv OUT.json"""
import collections, csv, json, re, statistics, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import importlib.util
spec = importlib.util.spec_from_file_location("L", str(Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_logloss_ruler.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)
K = 50.0


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def fit(S):
    X = np.array(S, float); a = b = c = 0.0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(a + b * X[:, 0] + c * X[:, 1], -30, 30))); w = p * (1 - p)
        V = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
        try:
            st = np.linalg.solve((V * w[:, None]).T @ V, V.T @ (X[:, 2] - p))
        except np.linalg.LinAlgError:
            return 0.0
        a, b, c = a + st[0], b + st[1], c + st[2]
        if np.abs(st).max() < 1e-8:
            break
    return float(max(-40, min(40, c / b))) if b > 0 else 0.0


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
    people = {}
    for r in csv.DictReader(open(sys.argv[2], encoding="utf-8-sig")):
        people[(r["Date"], str(int(r["Race"])) if r["Race"].isdigit() else r["Race"], norm(r["Horse"]))] = (norm(r["Jockey"]), norm(r["Trainer"]))
    cal = L.calibrations(base)
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    out = {}
    for name, idx in (("JRES", 0), ("TRES", 1)):
        resid = collections.defaultdict(float); n = collections.defaultdict(int)
        samples = []; cand = list(base); matched = total = 0
        for k_day, d in enumerate(sorted(by)):
            beta = fit(samples) if k_day >= 20 and samples else 0.0
            day_rows = []
            for i in by[d]:
                r = base[i]
                who = [people.get((r["date"], str(r["race"]), norm(x["name"])), (None, None))[idx] for x in r["rows"]]
                total += len(who); matched += sum(1 for w in who if w)
                R = np.array([resid[w] / (n[w] + K) if w else 0.0 for w in who])
                Rc = R - R.mean()
                cand[i] = dict(r, rows=[dict(x, ability=x["ability"] + beta * v) for x, v in zip(r["rows"], Rc)])
                day_rows.append((i, who, Rc))
            for i, who, Rc in day_rows:          # 賽後先更新（之後賽日先用到）
                r = base[i]; a = np.array([x["ability"] for x in r["rows"]]); ac = a - a.mean()
                y = np.array([int(x["pos"] <= 3) for x in r["rows"]])
                samples += [(float(ac[j]), float(Rc[j]), int(y[j])) for j in range(len(y))]
                if d in cal:
                    p = 1 / (1 + np.exp(-(cal[d][0] + cal[d][1] * ac)))
                    for w, yy, pp in zip(who, y, p):
                        if w:
                            resid[w] += yy - pp; n[w] += 1
        v = L.evaluate(base, cand, nnull=100)
        cb, cc = L.calibrations(base), L.calibrations(cand); rows = []
        for b_, c_ in zip(base, cand):
            if b_["date"] in cb:
                lb, nn_ = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rows.append((b_["date"], lc - lb, nn_))
        byd = collections.defaultdict(list)
        for ii, rr in enumerate(rows):
            byd[rr[0]].append(ii)
        days = sorted(byd); dl = np.array([rr[1] for rr in rows]); nnn = np.array([rr[2] for rr in rows]); rng = np.random.default_rng(0); bs = []
        for _ in range(2000):
            jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
        v["p"] = float((np.array(bs) >= 0).mean())
        v["match_rate"] = matched / max(1, total)
        out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]], "match", round(v["match_rate"], 3), "p", v["p"], flush=True)
    ps = sorted((v["p"], k) for k, v in out.items())
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
    print({k: round(v["holm_p"], 4) for k, v in out.items()})
    Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
