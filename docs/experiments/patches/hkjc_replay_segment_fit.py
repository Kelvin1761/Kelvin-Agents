"""Kelvin 2026-11-15：泥地相對草地、直路往績係真訊號 —— 搵方法令佢哋真正改善排名（EXP-20261115-01）。

之前（EXP-20261114-11）固定加分 δ 由 Gold+Good 喺網格揀 → 嘈、唔穩、冇考慮同維度重疊。今次兩個有原則嘅做法（預先登記）：
  A 校準加分：分段賽事入面，logit P(入頭三) = α·(raw − 場均) + β·z，用之前季 fit；δ = β／α（raw 尺）
      → 幅度由似然度決定，唔用 Gold 揀；z 缺失 = 0
  B 分段專屬權重：分段賽事入面，logit P(入頭三) ~ Σ w_d·(m_d − 場均) + β·z（場內置中、L2 C=1），之前季 fit；
      新 raw = Σ w_d·m_d + β·z，按 S 版權重總和縮放（只改分段賽事；初出馬維持原 raw）
  特徵：泥地 = A1 泥地相對草地（＋A2 泥地前段，兩個都過篩選）；直路 = S3 直路往績
  dev：逐季 walk-forward（測試 2021/22、2022/23、2023/24）；holdout：用全 dev fit 一次（A、B 各一次，Holm 2）
  判法：Gold、Good 都 ≥ 0，而且一個指標 CI 下界 > 0 或者贏 95% null
用法：python3 hkjc_replay_segment_fit.py <base_S.jsonl> <seg_awt.pkl> <seg_straight.pkl> <outdir>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

DIMS = ("stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "form_line", "class_advantage")
SEGS = {"awt": ["A1_awt_vs_turf", "A2_front_v"], "straight": ["S3_straight_pct"]}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    base, pa, ps, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(base) if '"horses"' in line]
    feats = {}
    for seg, p in (("awt", pa), ("straight", ps)):
        D = pd.read_pickle(p)
        cols = SEGS[seg]
        dev = D[(D.date >= "2020-09-01") & (D.date <= "2024-07-31")]
        st = {c: (dev[c].mean(), dev[c].std()) for c in cols}
        for r in D.itertuples():
            feats[(r.race[0], r.race[1], r.n)] = (seg, [0.0 if pd.isna(getattr(r, c)) else (getattr(r, c) - st[c][0]) / st[c][1] for c in cols])
    seg_of = {}
    for k, (seg, _) in feats.items():
        seg_of[(k[0], k[1])] = seg
    wS = None

    def design(x, seg):
        hs = [h for h in x["horses"] if h["pos"]]
        M = np.array([[h["m"].get(d, 60.0) for d in DIMS] for h in hs])
        Z = np.array([feats.get((x["meeting"], x["race"], h["n"]), (seg, [0.0] * len(SEGS[seg])))[1] for h in hs])
        raw = np.array([h["raw"] for h in hs])
        y = np.array([int(h["pos"] <= 3) for h in hs])
        return hs, M - M.mean(0), Z, raw - raw.mean(), y

    def fit_A(train, seg):
        X, Y = [], []
        for x in train:
            _, _, Z, r, y = design(x, seg)
            X.append(np.c_[r, Z])
            Y.append(y)
        X, Y = np.vstack(X), np.concatenate(Y)
        c = LogisticRegression(C=1e6, max_iter=5000).fit(X, Y).coef_[0]
        return c[1:] / c[0]                       # δ 每個 z（raw 尺）

    def fit_B(train, seg):
        X, Y = [], []
        for x in train:
            _, M, Z, _, y = design(x, seg)
            X.append(np.c_[M, Z])
            Y.append(y)
        X, Y = np.vstack(X), np.concatenate(Y)
        sd = X.std(0)
        sd[sd == 0] = 1
        c = LogisticRegression(C=1.0, max_iter=5000).fit(X / sd, Y).coef_[0] / sd
        w, b = c[:len(DIMS)], c[len(DIMS):]
        w = np.clip(w, 0, None)
        scale = 1.0 / w.sum() if w.sum() > 0 else 1.0   # S 版權重總和 = 1
        return w * scale, b * scale

    def apply_A(x, seg, delta):
        hs = [dict(h, raw=h["raw"] + float(np.dot(delta, feats.get((x["meeting"], x["race"], h["n"]), (seg, [0.0] * len(delta)))[1])))
              for h in x["horses"]]
        return reorder(x, hs)

    def apply_B(x, seg, wb):
        w, b = wb
        hs = []
        for h in x["horses"]:
            if h.get("debut"):
                hs.append(h)
                continue
            m = np.array([h["m"].get(d, 60.0) for d in DIMS])
            z = np.array(feats.get((x["meeting"], x["race"], h["n"]), (seg, [0.0] * len(b)))[1])
            hs.append(dict(h, raw=float(w @ m + b @ z)))
        # 初出馬 raw 喺另一把尺：將非初出馬嘅新 raw 平移，令非初出馬場均唔變（保持同初出馬可比）
        old = [h["raw"] for h in x["horses"] if not h.get("debut")]
        new = [h["raw"] for h in hs if not h.get("debut")]
        if old:
            shift = np.mean(old) - np.mean(new)
            hs = [h if h.get("debut") else dict(h, raw=h["raw"] + shift) for h in hs]
        return reorder(x, hs)

    def reorder(x, hs):
        ns = np.array([h["n"] for h in hs])
        raw = np.array([h["raw"] for h in hs])
        return dict(x, horses=hs, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]])

    report = {}
    for seg in SEGS:
        segrows = [x for x in rows if seg_of.get((x["meeting"], x["race"])) == seg]
        dev = [x for x in segrows if "2020-09-01" <= x["date"] <= "2024-07-31"]
        for name, fit, app in (("A", fit_A, apply_A), ("B", fit_B, apply_B)):
            params = {}
            with open(out / f"{seg}_{name}_wf.jsonl", "w") as fh:
                for ts in (2021, 2022, 2023):
                    p = fit([x for x in dev if season(x["date"]) < ts], seg)
                    params[ts] = p
                    for x in dev:
                        if season(x["date"]) == ts:
                            fh.write(json.dumps(app(x, seg, p), ensure_ascii=False) + "\n")
            full = fit(dev, seg)
            with open(out / f"{seg}_{name}_full.jsonl", "w") as fh:
                for x in segrows:
                    fh.write(json.dumps(app(x, seg, full), ensure_ascii=False) + "\n")
            with open(out / f"{seg}_base.jsonl", "w") as fh:
                for x in segrows:
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")
            show = (lambda p: [round(float(v), 3) for v in p]) if name == "A" else (lambda p: {"w": dict(zip(DIMS, [round(float(v), 3) for v in p[0]])), "b": [round(float(v), 3) for v in p[1]]})
            report[f"{seg}_{name}"] = {"full": show(full), "wf": {str(k): show(v) for k, v in params.items()}}
            print(seg, name, "全 dev：", report[f"{seg}_{name}"]["full"], flush=True)
    json.dump(report, open(out / "params.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
