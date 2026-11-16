"""Kelvin 2026-11-16 第三輪候選（dump 上做，base = live I1）。預先登記（diag_round3.py 揀，dev／holdout 兩段同方向）：
  R1  raw += β·[上仗騎法有疑問：策騎指示交代／騎法被查詢／騎師被告誡或未有力策]
  R2  R1 + β·[上兩仗任一受阻] + β·[上仗出閘慢]
出閘慢唔分慣性／一次性（慣性冇負殘差，見 diag）。β 逐季 walk-forward（2019/20 起），同 build_cand.py。
用法：python3 build_round3.py <I1.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

from diag import season
from diag_full import load_runs
from diag_round3 import BLK, INSTR, RIDE_Q, RIDE_WARN, SLOW, has

RIDE = f"{INSTR}|{RIDE_Q}|{RIDE_WARN}"


def flags(prev):
    rep = [v[2] for v in prev if v[2] is not None]
    if not prev or prev[-1][2] is None:
        return [0.0, 0.0, 0.0]
    last = prev[-1][2]
    blk2 = has(BLK, last) or (len(rep) >= 2 and has(BLK, rep[-2]))
    return [float(has(RIDE, last)), float(blk2), float(has(SLOW, last))]


ARMS = {"R1": [0], "R2": [0, 1, 2]}


def main():
    runs = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    ALL = {}
    for x in rows:
        out = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            out.append(flags([v for v in runs[c] if v[0] < x["date"]]) if c else [0.0, 0.0, 0.0])
        ALL[id(x)] = np.array(out)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in ARMS.items():
        F = {k: v[:, cols] for k, v in ALL.items()}

        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
            return (c[1:] / sd) / (c[0] / R.std())
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: [round(b, 3) for b in v] for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"round3_{arm}")
                if bb is not None:
                    add = F[id(x)] @ bb
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
