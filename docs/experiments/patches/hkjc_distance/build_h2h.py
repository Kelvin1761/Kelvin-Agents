"""EXP-20261123-08 預先登記（Kelvin 2026-11-23：「一隻 99 分馬上次受讓 16 磅都贏唔到隻 118 分馬，今次一樣磅數點計都似會差咁遠；
淨係計最近嗰場對過」）。寫喺跑之前；回放尺 = main 現行 v5.2。

觸發例子（只用嚟提出假設，唔用嚟揀參數）：11-22 R7 嘉應奇兵（119 磅）10-25 跑第二、輸畀精算暴雪（135 磅）；今仗同磅 123，
模型將嘉應奇兵排第 2、精算暴雪第 4（實際第 5、第 2）。模型而家冇「今場對手之前直接交手」呢個訊號（賽績線只睇對手之後嘅表現）。

訊號 H（候選）：對今場每一對馬 (i, j)，搵佢哋**最近一次**同場（日期嚴格早過今仗、兩匹都有完成時間、365 日內），
  交手差 = (t_j − t_i) ＋ k·km_當時·(w_i當時 − w_j當時) − k·km_今仗·(w_i今仗 − w_j今仗)，正數 = i 預期跑快過 j
  k = 0.0112 秒／公里／磅（EXP「HKJC 負磅直接效應」量出嚟嘅數，唔喺度調）；每對截 ±1.0 秒（大敗嘅差距冇資訊）。
  h2h_i = 所有交過手對手嘅交手差平均（冇交手 = 0）；h2h_n_i = 交過手對手數 ÷ 10（俾模型分辨證據多少）。
做法同 J3 一樣：線性 L2 C=0.1、每季 walk-forward（2019/20 起 fit）、場內置中、加落 base raw。
arm：H（候選）、H0（唔做負磅換算，消融用，唔判）。
判（預先寫低）：dev v5.2 PASS（log-loss CI、Gold／Good 護欄、null、頭二護欄）＋ dev 頭二入頭三 Δ 點估計 ≥ 0；
  過咗先睇 holdout（第一次睇，記入 ledger）；11-22 只做否決。唔調 k、截斷、窗口。
限制：歷史賽果索引由 2019-09 開始，所以 2019/20 季交手覆蓋偏低（fit 窗內，唔影響判決窗）。
用法：python3 build_h2h.py <base.jsonl> <out_prefix>
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as hb  # noqa: E402

K = 0.0112
CLIP = 1.0
WINDOW = 365


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def secs(t):
    m = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", str(t or "").strip())
    return (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else None


def wt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    dist = {(x["date"], x["race"]): x.get("distance") for x in rows}
    idx = hb.load_index()["results"]
    race_info = {}          # (d, n) -> {code: (time, wt, horse_no)}
    by_code = defaultdict(list)   # code -> [(d, n)]
    for (d, n), race in sorted(idx.items()):
        info = {}
        for r in race.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(r.get("horse_name") or ""))
            if not m:
                continue
            info[m.group(1)] = (secs(r.get("finish_time")), wt(r.get("actual_wt")), str(r.get("horse_no")))
        race_info[(d, n)] = info
        for c in info:
            by_code[c].append((d, n))
    feats = {}
    for x in rows:
        key = (x["date"], x["race"])
        info = race_info.get(key, {})
        no2code = {v[2]: c for c, v in info.items()}
        codes = [no2code.get(str(h["n"])) for h in x["horses"]]
        km = (x.get("distance") or 0) / 1000.0
        H = np.zeros((len(codes), 4))
        today = date.fromisoformat(x["date"])
        past = {c: [(d, n) for d, n in by_code.get(c, []) if d < x["date"] and (today - date.fromisoformat(d)).days <= WINDOW]
                for c in codes if c}
        for i, ci in enumerate(codes):
            if not ci:
                continue
            adj, raw = [], []
            pi = set(past[ci])
            for j, cj in enumerate(codes):
                if j == i or not cj:
                    continue
                common = sorted(pi & set(past[cj]))
                if not common:
                    continue
                d0, n0 = common[-1]
                ti, wi, _ = race_info[(d0, n0)][ci]
                tj, wj, _ = race_info[(d0, n0)][cj]
                wti, wtj = info[ci][1], info[cj][1]
                if None in (ti, tj, wi, wj, wti, wtj):
                    continue
                km0 = (dist.get((d0, n0)) or x.get("distance") or 0) / 1000.0
                m0 = tj - ti
                raw.append(float(np.clip(m0, -CLIP, CLIP)))
                adj.append(float(np.clip(m0 + K * km0 * (wi - wj) - K * km * (wti - wtj), -CLIP, CLIP)))
            if adj:
                H[i] = [np.mean(adj), len(adj) / 10.0, np.mean(raw), len(raw) / 10.0]
        feats[key] = H
    import os, pickle
    if os.environ.get("H2H_DUMP"):
        pickle.dump(feats, open(os.environ["H2H_DUMP"], "wb"))
        return
    cov = np.vstack(list(feats.values()))
    print("有交手比例", round(float((cov[:, 1] > 0).mean()), 4), "平均對手數", round(float(cov[:, 1].mean() * 10), 2), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("H", [0, 1]), ("H0", [2, 3])):
        Z = {k: (v[:, cols] - v[:, cols].mean(axis=0)) for k, v in feats.items()}
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, ZZ, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); ZZ.append(Z[(x["date"], x["race"])][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, ZZ, Y = np.concatenate(R), np.vstack(ZZ), np.array(Y)
            sd = ZZ.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, ZZ / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
            print(arm, s, [round(float(b), 3) for b in models[s]], flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"])
                y = dict(x, arm=f"h2h_{arm}")
                if s in models:
                    r = np.array([h["raw"] for h in x["horses"]])
                    new = r + Z[(x["date"], x["race"])] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
