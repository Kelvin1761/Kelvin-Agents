"""EXP-20261123-17 預先登記（Kelvin 2026-11-23「精算暴雪同嘉應奇兵問題要再 dig deep」）。寫喺跑之前；尺 v5.2；base = live（SW＋DT，db_DT）。

觸發：11-22 R7（6 匹）嘉應奇兵 vs 精算暴雪差 5.4 分，最大一份係檔位×跑法 +2.73（1 檔放頭 +2.07、3 檔後上 −0.67）。
檔位×跑法嘅跑法格冇分馬匹數（逐檔格只分 ≥12 匹）；細場「內 1–4 檔」= 大半場馬，放頭著數理論上細啲。只用嚟提出假設。
量度：兩次 harness（同一份 code：base2 vs 關咗 draw_style 嘅 DSoff），每匹 Δds = base2 raw − DSoff raw = 檔位×跑法貢獻。
DSF  特徵 = Δds ×［出賽 ≤ 9 匹］（場內置中；β < 0 = 細場縮），線性 L2 C=0.1、每季 walk-forward β，加落 live base。
判：全期 dev v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0；holdout 照判；六季細場（≤9 匹）子集報；11-22 否決（用快照 draw_style_delta）。
另報診斷：Δds 每 1 分嘅入頭三效應，細場 vs 大場（同一 logit）。
用法：python3 build_draw_style_field.py <db_DT.jsonl> <base2.jsonl> <DSoff.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def load(p):
    return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}


def main():
    live = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    b, d = load(sys.argv[2]), load(sys.argv[3])
    feats, diag = {}, []
    for x in live:
        k = (x["meeting"], x["race"])
        bb = {h["n"]: h["raw"] for h in b[k]["horses"]} if k in b else {}
        dd = {h["n"]: h["raw"] for h in d[k]["horses"]} if k in d else {}
        ds = np.array([bb.get(h["n"], 0.0) - dd.get(h["n"], 0.0) for h in x["horses"]])
        n = sum(1 for h in x["horses"] if h["pos"])
        small = float(n <= 9)
        f = ds * small
        feats[(x["date"], x["race"])] = (f - f.mean())[:, None]
        r = np.array([h["raw"] for h in x["horses"]])
        for h, v, rr in zip(x["horses"], ds - ds.mean(), r - r.mean()):
            if h["pos"]:
                diag.append((rr, v * small, v * (1 - small), int(h["pos"] <= 3), x["date"]))
    D = np.array([t[:4] for t in diag], dtype=float)
    c = LogisticRegression(C=1e4, max_iter=5000).fit(D[:, :3], D[:, 3]).coef_[0]
    print(f"診斷（全部季）：每 1 分 raw 效應 {c[0]:.3f}；Δds 細場 {c[1]:.3f}、大場 {c[2]:.3f}（同 raw 一樣 = 1× raw 係數）", flush=True)
    by = defaultdict(list)
    for x in live:
        by[season(x["date"])].append(x)
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        R, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
        sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
        cc = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
        models[s] = (cc[1:] / sd) / (cc[0] / rs)
    print("DSF β", {s: round(float(m[0]), 2) for s, m in models.items()}, flush=True)
    with open(f"{sys.argv[4]}_DSF.jsonl", "w") as f:
        for x in live:
            s = season(x["date"]); y = dict(x, arm="draw_style_field")
            if s in models:
                new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
