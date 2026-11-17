"""EXP-20261117-07（Kelvin「13 個逐個睇」）：J1 逐個拎走（drop-one ablation），量每個特徵喺聯合模型入面嘅邊際貢獻。
同 build_joint.py 一樣特徵、L2 C=0.1、逐季 walk-forward；輸出 13 個 dump（J1 − k）。只睇 dev（holdout 已經喺 EXP-05 用過）。
用法：python3 ablate_joint.py <dist_D1.jsonl> <old_incidents.json> <out_dir>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_joint as B  # noqa: E402


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    inc = B.load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in inc.items() for d, n, _, hn in v}
    pages, _ = B.F.load()
    pidx = {c: {q["d"]: i for i, q in enumerate(rr)} for c, rr in pages.items()}
    X = {}
    for x in rows:
        mat = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            f = dict.fromkeys(B.NAMES, 0.0)
            if c:
                f.update(B.inc_feats([v for v in inc[c] if v[0] < x["date"]]))
                i = pidx.get(c, {}).get(x["date"])
                if i is not None:
                    f.update(B.page_feats(pages[c], i))
            mat.append([f[k] for k in B.NAMES])
        m = np.array(mat, dtype=float)
        X[id(x)] = m - m.mean(axis=0)
    by = defaultdict(list)
    for x in rows:
        by[B.season(x["date"])].append(x)
    out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)

    def design(races, cols):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(X[id(x)][keep][:, cols]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        return np.concatenate(R), np.vstack(Z), np.array(Y)

    variants = {"full": list(range(len(B.NAMES)))}
    variants.update({f"minus_{k}": [j for j in range(len(B.NAMES)) if j != i] for i, k in enumerate(B.NAMES)})
    for name, cols in variants.items():
        betas = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = design([x for t in by if 2019 <= t < s for x in by[t]], cols)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            betas[s] = (c[1:] / sd) / (c[0] / rs)
        with open(out / f"{name}.jsonl", "w") as f:
            for x in rows:
                s = B.season(x["date"])
                y = dict(x, arm=f"ablate_{name}")
                if s in betas:
                    r = np.array([h["raw"] for h in x["horses"]])
                    new = r + X[id(x)][:, cols] @ betas[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
        print(name, "done", flush=True)


if __name__ == "__main__":
    main()
