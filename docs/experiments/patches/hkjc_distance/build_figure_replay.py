"""EXP-20261123-10 預先登記（Kelvin 2026-11-23：「先修段速三項冇按負磅換算」）。寫喺跑之前；尺 v5.2；base = base_live_20261122。

觸發：11-22 R7 精算暴雪上仗負 135 磅贏，段速分 68.3 vs 嘉應奇兵（119 磅跑第二）84.8；「輸頭馬差距」「能量趨勢」「L400 走勢」
三項冇按負磅換算。只用嚟提出假設。

舊證據（開工前 grep 過，要披露）：
  - 輸頭馬秒數按負磅換算：EXP-20261112-07（今仗 − 當時負磅，雙重罰降班馬）REJECT；EXP-20261112-10（對頭馬／對全場）leaf AUC 0.646 vs 0.648 冇用。
    → 唔再測「喺輸頭馬上換算」。
  - 表現數字（扣賽事效應、按負磅換算到今仗）：leaf 層最強（EXP-20261112-10 AUC 0.669 vs 0.648；EXP-20261112-06 換算 0.6647→0.6728），
    但喺舊 389 場尺（fixed_rule、Gold CI 護欄）上做 overlay／取代全部 REJECT（EXP-20261112-06／-08／-12、EXP-20261113-03）。
    舊護欄後來證實對同幅度雜訊冇判別力（EXP-20261122-33），而回放尺 v5 有 6,047 場。今次係第一次喺回放尺上測，屬同一家族重測，要披露。
表現數字定義一字不改：`patches/hkjc_figure_concept_walkforward.py` build()（β 只用 2019/20 估；逐賽日 PIT 重估賽事效應；
  近 6 仗 1/k 加權；輸頭馬 >3 秒封頂；figW = 每仗再按今仗負磅換算）。

arm（同 J3 做法：場內置中、線性 L2 C=0.1、每季 walk-forward、加落 base raw；冇表現數字 = 場均＋缺失旗）：
  WD  只加「負磅換算嗰部分」figW − figU（主 arm；直接回應「冇按負磅換算」）
  W   加 figW（換算後表現數字）
  U   加 figU（唔換算；消融，唔判）
判：dev v5.2 PASS ＋ dev 頭二入頭三 Δ ≥ 0。過咗先開 holdout（呢個家族喺回放尺 holdout 未睇過）；11-22 只做否決。唔調 β、窗、封頂。
用法：python3 build_figure_replay.py <base.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

PATCHES = Path("/Users/imac/Antigravity-repo/docs/experiments/patches")
sys.path.insert(0, str(PATCHES))
sys.path.insert(0, "/Users/imac/Antigravity-repo")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def figures(out):
    cache = Path(out + "_fig.pkl")
    if cache.exists():
        return pd.read_pickle(cache)
    import wongchoi_paths
    from hkjc_figure_concept_walkforward import build
    R, beta = build(Path(wongchoi_paths.HK_RACING))
    print("β", beta, flush=True)
    R = R[["date", "code", "figU", "figW", "w"]]
    R.to_pickle(cache)
    return R


def main():
    out = sys.argv[2]
    R = figures(out)
    fig = {(d, c): (u, w) for d, c, u, w in zip(R.date, R.code, R.figU, R.figW)}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    import hkjc_history_replay_build as hb
    idx = hb.load_index()["results"]
    no2code = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                no2code[(k, str(q.get("horse_no")))] = m.group(1)
    feats, have, tot = {}, 0, 0
    for x in rows:
        k = (x["date"], x["race"])
        vals = []
        for h in x["horses"]:
            u, w = fig.get((x["date"], no2code.get((k, str(h["n"])))), (np.nan, np.nan))
            vals.append((u, w))
        a = np.array(vals, dtype=float)
        miss = np.isnan(a[:, 1]) | np.isnan(a[:, 0])
        have += int((~miss).sum()); tot += len(a)
        for j in (0, 1):
            col = a[:, j]
            mu = np.nanmean(col[~miss]) if (~miss).any() else 0.0
            col[miss] = mu
        m = np.column_stack([a[:, 0], a[:, 1], a[:, 1] - a[:, 0], miss.astype(float)])
        feats[k] = m - m.mean(axis=0)
    print("表現數字覆蓋", round(have / tot, 4), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("WD", [2, 3]), ("W", [1, 3]), ("U", [0, 3])):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            Rr, ZZ, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, hh in enumerate(x["horses"]) if hh["pos"]]
                r = np.array([hh["raw"] for hh in x["horses"]])
                Rr.append((r - r.mean())[keep]); ZZ.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            Rr, ZZ, Y = np.concatenate(Rr), np.vstack(ZZ), np.array(Y)
            sd = ZZ.std(axis=0); sd[sd == 0] = 1
            rs = Rr.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([Rr / rs, ZZ / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"])
                y = dict(x, arm=f"figure_{arm}")
                if s in models:
                    r = np.array([hh["raw"] for hh in x["horses"]])
                    new = r + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(hh, raw=round(float(v), 4)) for hh, v in zip(x["horses"], new)]
                    y["picks"] = [hh["n"] for hh in sorted(y["horses"], key=lambda hh: -hh["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
