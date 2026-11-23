"""EXP-20261123-16 預先登記（Kelvin 2026-11-23「泥地表現可以點改善，dig deep」）。寫喺跑之前；尺 v5.2；base = SW＋DT。

診斷（全部季數，所以判決唔用同一份數據揀幅度）：泥地騎練訊號剩餘價值 0.50 [0.20,0.77] vs 沙田草地 1.14 [0.99,1.31]
（logit 入頭三 ~ (raw − 騎練部分) + 騎練部分）。騎練實績分係全部場地一齊計，泥地專屬能力冇入到。
特徵（只限泥地賽事；其他場 0；場內置中）：
  tsig  騎練維度部分 = 0.3296 × 騎練分（β < 0 = 泥地縮細騎練分）
  jawt  騎師泥地入頭三率（as-of：只用今仗日期之前嘅香港全天候騎乘；收縮 k=30 向全體泥地入頭三率）
  tawt  練馬師泥地入頭三率（同上）
arm（線性 L2 C=0.1、每季 walk-forward β，同 J3；β 全部由之前季 fit，唔用診斷個 0.5）：
  ATW  tsig
  AJT  tsig ＋ jawt ＋ tawt【主】
判：六季泥地場（2021/22–2026/27，judge_all_group.py awt）v5.2 PASS ＋ 頭二入頭三 Δ ≥ 0（主 arm）。
用法：python3 build_awt_jt.py <SW_DT.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as hb  # noqa: E402

K = 30


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = sorted((x for x in map(json.loads, open(sys.argv[1])) if "horses" in x), key=lambda x: (x["date"], x["race"]))
    idx = hb.load_index()["results"]
    awt = {k: "全天候" in str(r.get("course") or "") for k, r in idx.items()}
    jh, th, tot = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), [0, 0]
    buf, cur, feats, n = [], None, {}, 0
    for x in rows:
        if x["date"] != cur:
            for j, t, p in buf:
                jh[j][0] += p; jh[j][1] += 1; th[t][0] += p; th[t][1] += 1; tot[0] += p; tot[1] += 1
            buf.clear(); cur = x["date"]
        k = (x["date"], x["race"])
        m = np.zeros((len(x["horses"]), 3))
        if awt.get(k) or x.get("awt"):
            n += 1
            res = {str(r.get("horse_no")): r for r in (idx.get(k) or {}).get("results", [])}
            base = tot[0] / tot[1] if tot[1] else 0.25
            for i, h in enumerate(x["horses"]):
                r = res.get(str(h["n"])) or {}
                j, t = r.get("jockey") or "?", r.get("trainer") or "?"
                a, b = jh[j], th[t]
                m[i] = [0.3296 * (h["m"].get("trainer_signal") or 60.0),
                        (a[0] + K * base) / (a[1] + K), (b[0] + K * base) / (b[1] + K)]
                if h["pos"]:
                    buf.append((j, t, int(h["pos"] <= 3)))
        feats[k] = m - m.mean(axis=0)
    print("泥地場", n, flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in (("ATW", [0]), ("AJT", [0, 1, 2])):
        models = {}
        for s in sorted(by):
            if s < 2020:
                continue
            R, Z, Y = [], [], []
            for x in (x for t in by if 2019 <= t < s for x in by[t]):
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][:, cols][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
            sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
            c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
            models[s] = (c[1:] / sd) / (c[0] / rs)
        print(arm, {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                s = season(x["date"]); y = dict(x, arm=f"awtjt_{arm}")
                if s in models:
                    new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])][:, cols] @ models[s]
                    y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
