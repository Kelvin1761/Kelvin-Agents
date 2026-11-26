# ruff: noqa: F821  — rows／info／is_front 由 exec(build_pace.py) 提供
"""殘差表（獨放 +、擠迫 −）同入分 β≈0 點解唔夾：pooled dev logistic，逐步加項。"""
import json, sys
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]
src = open("build_pace.py").read().split("print(\"F 匹次")[0]
exec(src)
X, Y = [], []
for x in rows:
    if not ("2020-09" <= x["date"] <= "2024-07-31"): continue
    keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
    if len(keep) < 4: continue
    r = np.array([x["horses"][i]["raw"] for i in keep]); N = len(keep)
    meta = info.get((x["date"], x["race"]), {})
    fr = np.array([is_front(meta.get(str(x["horses"][i]["n"]), (None, 0))[0], x["date"]) for i in keep], float)
    nF = fr.sum()
    for j, i in enumerate(keep):
        oth = nF - fr[j]
        X.append([r[j] - r.mean(), np.log(3/(N-3)) if N > 3 else 0, fr[j], fr[j]*min(oth, 3), (1-fr[j])*min(oth+fr[j], 3)])
        Y.append(int(x["horses"][i]["pos"] <= 3))
X = np.array(X); Y = np.array(Y)
for name, cols in [("raw＋N", [0, 1]), ("＋F", [0, 1, 2]), ("＋F·擠迫", [0, 1, 2, 3]), ("＋非F·場內放頭數", [0, 1, 2, 3, 4]), ("raw＋N＋F·擠迫（冇 F 主效應）", [0, 1, 3])]:
    m = LogisticRegression(C=1e6, max_iter=5000).fit(X[:, cols], Y)
    print(f"{name:<28}", dict(zip(["raw", "N", "F", "F·擠迫", "非F·放頭數"][:len(cols)] if cols == list(range(len(cols))) else [["raw","N","F","F·擠迫","非F·放頭數"][c] for c in cols], np.round(m.coef_[0], 4))))
# 原始分佈：F 擠迫 vs 獨放 嘅模型排名
