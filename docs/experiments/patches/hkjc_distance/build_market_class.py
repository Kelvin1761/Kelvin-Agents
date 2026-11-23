"""EXP-20261124-12 預先登記（Kelvin 2026-11-24「上仗賠率係咪應該計埋班次」）。寫喺跑之前；尺 v5.2。
base = 全面重測 base（現行 main 回放）；上仗賠率貢獻 c = base raw − off_market_history raw（場內置中）。
MHc：特徵 = c ×［今仗班次高過上仗（升班）］、c ×［今仗班次低過上仗（降班）］；線性 L2 C=0.1、每季 walk-forward β。
  升班 β < 0 = 上仗熱門喺低班，升班要打折；降班 β 反之。
班次級數：Group 1=0、Group 2=1、Group 3=2、Class 1=3 … Class 5=7（今仗／上仗冇級數 = 兩個都 0）。上仗 = 馬匹頁日期嚴格早過今仗嘅最近一仗。
判：全期 dev／holdout v5.2 PASS ＋ 兩窗頭二入頭三 Δ ≥ 0。
用法：python3 build_market_class.py <base.jsonl> <off_market_history.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402

LV = {"Group 1": 0, "Group 2": 1, "Group 3": 2, "Class 1": 3, "Class 2": 4, "Class 3": 5, "Class 4": 6, "Class 5": 7}
PAGE_LV = {"G1": 0, "G2": 1, "G3": 2, "1": 3, "2": 4, "3": 5, "4": 6, "5": 7}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def load(p):
    return {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x}


def page_level(q):
    c = str(q.get("class") or "").strip().upper().replace("第", "").replace("班", "")
    if c in PAGE_LV:
        return PAGE_LV[c]
    m = re.search(r"(\d)", c)
    return PAGE_LV.get(m.group(1)) if m else None


def main():
    base, off = load(sys.argv[1]), load(sys.argv[2])
    idx = hb.load_index()["results"]
    n2c = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                n2c[(k, str(q.get("horse_no")))] = m.group(1)
    pages, _ = F.load()
    feats, rows, cnt = {}, [], [0, 0]
    for key, x in base.items():
        k = (x["date"], x["race"])
        tl = LV.get(str((idx.get(k) or {}).get("_header", {}).get("RaceClass") or ""))
        od = {h["n"]: h["raw"] for h in off[key]["horses"]}
        c = np.array([h["raw"] - od.get(h["n"], h["raw"]) for h in x["horses"]])
        c = c - c.mean()
        up, dn = np.zeros(len(c)), np.zeros(len(c))
        for i, h in enumerate(x["horses"]):
            code = n2c.get((k, str(h["n"])))
            prev = [q for q in pages.get(code, []) if q["d"] < x["date"]] if code else []
            ll = page_level(prev[-1]) if prev else None
            if tl is not None and ll is not None:
                up[i], dn[i] = float(tl < ll), float(tl > ll)
        cnt[0] += int(up.sum()); cnt[1] += int(dn.sum())
        m = np.column_stack([c * up, c * dn])
        feats[key] = m - m.mean(axis=0)
        rows.append(x)
    print("升班匹次", cnt[0], "降班匹次", cnt[1], flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        R, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feats[(x["meeting"], x["race"])][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
        sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
        cc = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
        models[s] = (cc[1:] / sd) / (cc[0] / rs)
    print("MHc β（升班, 降班）", {s: [round(float(b), 3) for b in m] for s, m in models.items()}, flush=True)
    with open(f"{sys.argv[3]}_MHc.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm="market_class")
            if s in models:
                new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["meeting"], x["race"])] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
