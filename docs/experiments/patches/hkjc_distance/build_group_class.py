"""EXP-20261123-09 預先登記（Kelvin 2026-11-23：「交手訊號應唔應該上咗先」「精算暴雪咁有級數同實力點解咁低分」）。寫喺跑之前；尺 v5.2。

假設：讓磅賽嘅負磅已經抵銷大部分評分差（EXP「負磅直接效應」：抵銷約 70%），所以標準馬「評分與經驗」權重 0 冇問題；
但級際賽（Group）負磅差唔多，評分差冇嘢抵銷 —— 評分應該喺級際賽先入分。交手訊號同理（EXP-20261123-08：級際 β 大六倍）。
觸發例子：11-22 R7 精算暴雪 118 分 vs 嘉應奇兵 99 分，同磅 123，評分差 0 分入分。只用嚟提出假設。

特徵（全部場內置中）：
  h2h_grp／h2hn_grp、h2h_oth／h2hn_oth：EXP-20261123-08 交手差（最近一次同場、按負磅換算、±1 秒），分級際／其他
  rat_grp、rat_oth：今仗官方評分 ÷ 10（馬匹頁當日評分；冇評分 = 場均），分級際／其他
arm（各自獨立加落 base_live，同 J3 一樣：線性 L2 C=0.1、每季 walk-forward）：
  HG（交手分組）、RG（評分分組）、HRG（兩樣）
判：dev v5.2 PASS ＋ dev 頭二入頭三 Δ ≥ 0；過咗先睇 holdout。
  **披露**：HG 嘅分組 β 喺 holdout 睇過（EXP-20261123-07 診斷，冇睇 log-loss）→ HG 嘅 holdout 唔算獨立，只報；RG 嘅 holdout 未睇過。
  11-22 只做否決。唔調任何參數。
用法：python3 build_group_class.py <base.jsonl> <out_prefix>（要 <out_prefix>_h2h.pkl，由 build_h2h.py 出）
"""
import json
import pickle
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402
import hkjc_history_replay_build as hb  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = sys.argv[2]
    hf = pickle.load(open(out + "_h2h.pkl", "rb"))
    idx = hb.load_index()["results"]
    grp = {k: str((r.get("_header") or {}).get("RaceClass") or "").startswith("Group") for k, r in idx.items()}
    no2code = {}
    for k, r in idx.items():
        for q in r.get("results") or []:
            m = re.search(r"\(([A-Z]\d{3})\)", str(q.get("horse_name") or ""))
            if m:
                no2code[(k, str(q.get("horse_no")))] = m.group(1)
    pages, _ = F.load()
    rating = {}
    for c, rr in pages.items():
        for q in rr:
            rating[(c, q["d"])] = F.num(q.get("rating"))
    feats = {}
    cov = [0, 0]
    for x in rows:
        k = (x["date"], x["race"])
        g = float(grp.get(k, False))
        rat = []
        for h in x["horses"]:
            c = no2code.get((k, str(h["n"])))
            rat.append(rating.get((c, x["date"])) if c else None)
        have = [v for v in rat if v is not None]
        mu = np.mean(have) if have else 0.0
        cov[0] += len(have); cov[1] += len(rat)
        r = np.array([((v if v is not None else mu) - mu) / 10.0 for v in rat])
        h = hf[k][:, :2]; h = h - h.mean(axis=0)
        feats[k] = np.column_stack([h * g, h * (1 - g), r * g, r * (1 - g)])
    print("評分覆蓋", round(cov[0] / cov[1], 4), flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols, names in (("HG", [0, 1, 2, 3], ["h2h_grp", "h2hn_grp", "h2h_oth", "h2hn_oth"]),
                             ("RG", [4, 5], ["rat_grp", "rat_oth"]),
                             ("HRG", [0, 1, 2, 3, 4, 5], ["h2h_grp", "h2hn_grp", "h2h_oth", "h2hn_oth", "rat_grp", "rat_oth"])):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, ZZ, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, hh in enumerate(x["horses"]) if hh["pos"]]
                r = np.array([hh["raw"] for hh in x["horses"]])
                R.append((r - r.mean())[keep]); ZZ.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, ZZ, Y = np.concatenate(R), np.vstack(ZZ), np.array(Y)
            sd = ZZ.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, ZZ / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items() if s in (2020, 2023, 2026)}, names, flush=True)
        with open(f"{out}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"])
                y = dict(x, arm=f"grpcls_{arm}")
                if s in models:
                    r = np.array([hh["raw"] for hh in x["horses"]])
                    new = r + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(hh, raw=round(float(v), 4)) for hh, v in zip(x["horses"], new)]
                    y["picks"] = [hh["n"] for hh in sorted(y["horses"], key=lambda hh: -hh["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
