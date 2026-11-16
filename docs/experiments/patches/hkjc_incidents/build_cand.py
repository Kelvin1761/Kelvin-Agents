"""EXP-20261116-06：上仗事件報告「藉口」入分（dump 候選，唔重跑引擎）。Kelvin 2026-11-16 揀 B：全語料測試過閘就直接入分。

預先登記（EXP-20261115-22 診斷揀，2023-10 起數據；全語料診斷見 diag_full.py）：
  I1  raw' = raw + β_wide·[上仗走外疊冇遮擋] + β_med·[上仗醫療事故]                      （主候選）
  I2  I1 + β_blk·[上仗受阻／搵唔到位] + β_slow·[上仗出閘慢／失地]                          （次候選）
β 逐季 walk-forward（只用之前季，2019/20 起；標準化 logistic，newton-cg，同 hkjc_weight_resid/build_hiclass.py），
用 raw 係數換算成 raw 分。上仗 = 同一匹馬喺賽果索引入面、日期早過今仗嘅最近一仗；事件報告賽後公開，賽前已知。
用法：python3 build_cand.py <base.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

from diag import CATS, season
from diag_full import load_runs

ARMS = {"I1": ["走外疊冇遮擋", "醫療（喘鳴／流鼻血／心律／跛）"],
        "I2": ["走外疊冇遮擋", "醫療（喘鳴／流鼻血／心律／跛）", "受阻／搵唔到位", "出閘慢／失地"]}


def main():
    runs = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]

    def feats(x, cats):
        out = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            prev = [v for v in runs[c] if v[0] < x["date"]] if c else []
            sent = prev[-1][2] if prev and prev[-1][2] else ""
            out.append([float(bool(re.search(CATS[k], sent))) for k in cats])
        return np.array(out)

    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cats in ARMS.items():
        F = {id(x): feats(x, cats) for x in rows}

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
        print(arm, cats, {s: v.tolist() for s, v in betas.items()})
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"incident_{arm}")
                if bb is not None:
                    add = F[id(x)] @ bb
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
