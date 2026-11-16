"""Kelvin 2026-11-16「事件報告每次用字唔同，捉唔捉得齊？」—— 用字覆蓋審計後嘅候選（base = 事件組件之前嘅 live，同 I1 一樣 walk-forward）。
審計（65k 句）：醫療漏咗「氣管內有很多血」（內窺鏡見出血）647 句；「帶出較／更外疊」（被帶出走外）~400 句；割傷／擦傷／受傷 ~550 句。
預先登記（對 live I1 比，Holm 3）：
  I1m   走外疊（不變）＋ 醫療加「氣管內有.{0,4}血」                     ← 正確性：定義漏同義字
  I1mw  I1m ＋ 走外疊加「(帶|迫)出(較|更)外疊」
  I1mi  I1m ＋ 醫療再加「割傷|擦傷|受傷」
用法：python3 build_wording.py <base.jsonl> <old_incidents.json> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

from diag import season
from diag_full import load_runs

WIDE = r"沒有遮擋|走外疊|三疊|四疊"
MED = r"喘鳴|流鼻血|鼻孔流血|心律|跛|呼吸|肺部有血|不良於行"
BLEED = r"氣管內有.{0,4}血"
CARRIED = r"(帶|迫)出(較|更)外疊"
INJ = r"割傷|擦傷|受傷"
ARMS = {"I1m": [WIDE, f"{MED}|{BLEED}"], "I1mw": [f"{WIDE}|{CARRIED}", f"{MED}|{BLEED}"],
        "I1mi": [WIDE, f"{MED}|{BLEED}|{INJ}"]}


def main():
    runs = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    last = {}
    for x in rows:
        out = []
        for h in x["horses"]:
            c = code_of.get((x["date"], x["race"], str(h["n"])))
            prev = [v for v in runs[c] if v[0] < x["date"]] if c else []
            out.append(prev[-1][2] if prev and prev[-1][2] else "")
        last[id(x)] = out
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, pats in ARMS.items():
        F = {id(x): np.array([[float(bool(re.search(p, s))) for p in pats] for s in last[id(x)]]) for x in rows}
        hit = np.mean(np.vstack(list(F.values())), axis=0)

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
        print(arm, "命中率", np.round(hit, 4), {s: np.round(v, 3).tolist() for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"wording_{arm}")
                if bb is not None:
                    add = F[id(x)] @ bb
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
