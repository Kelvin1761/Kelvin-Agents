"""晨操特徵 × 模型殘差篩選（EXP-20261115-21，只用現役馬）。

join：回放 v3 base（date, race, pos）→ 賽果庫 HorseID → features.py 輸出。
只計「同場至少 4 匹有晨操紀錄」嘅場次；特徵喺同場有紀錄嘅馬之間減場均（冇紀錄嘅馬唔入統計）。
殘差 = 入頭三 − p，p = 用之前季校準嘅 raw（同 EXP-18 一樣）。
報告：(1) 每個特徵按五分位嘅殘差（pp）；(2) 逐季 walk-forward logistic（raw＋特徵，標準化 newton-cg）係數方向同 t 值。
預先登記：揀特徵用 2022/23–2025/26；2026/27 同 forward 做確認。用法：python3 screen.py <base.jsonl> <feat.jsonl>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
FEATS = ["g14", "g28", "jg28", "sj28", "sw14", "tr14", "mach14", "trial42", "dlg", "fast21", "g28_vs_own"]


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    feat = {(x["date"], x["race"], x["brand"]): x for x in map(json.loads, open(sys.argv[2]))}
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    brand = defaultdict(list)
    for r in df.itertuples():
        brand[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append(r.HorseID)
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in [y for t in by if t < s for y in by[t]] or by[s]:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        calib[s] = (m.intercept_[0], m.coef_[0][0])
    recs = []          # (season, race_id, raw_c, y, resid, {feat: demeaned})
    races = 0
    for x in rows:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, b = calib[season(x["date"])]
        cov = []
        for h, z in zip(hs, rc):
            bb = brand.get((x["date"], x["race"], h["pos"]))
            f = feat.get((x["date"], x["race"], bb[0])) if bb and len(bb) == 1 else None
            if f:
                cov.append((h, z, f))
        if len(cov) < 4:
            continue
        races += 1
        means = {}
        for k in FEATS:
            v = [f[k] for _, _, f in cov if f[k] is not None]
            means[k] = sum(v) / len(v) if len(v) >= 3 else None
        for h, z, f in cov:
            y = int(h["pos"] <= 3); pr = 1 / (1 + np.exp(-(a + b * z)))
            dm = {k: (f[k] - means[k]) if f[k] is not None and means[k] is not None else None for k in FEATS}
            recs.append((season(x["date"]), f"{x['date']}|{x['race']}", z, y, y - pr, dm, f))
    sel = [r for r in recs if 2022 <= r[0] <= 2025]
    conf = [r for r in recs if r[0] >= 2026]
    print(f"場次 {races}｜馬次 {len(recs)}｜揀選窗 {len(sel)}｜確認窗 {len(conf)}")
    print("季分佈", {s: sum(1 for r in recs if r[0] == s) for s in sorted({r[0] for r in recs})})
    for k in FEATS:
        def quint(rs):
            v = [(r[5][k], r[4]) for r in rs if r[5][k] is not None]
            if len(v) < 200:
                return None, len(v)
            v.sort(key=lambda t: t[0]); q = np.array_split(np.array(v), 5)
            return [round(100 * c[:, 1].mean(), 1) for c in q], len(v)
        qs, ns = quint(sel); qc, nc = quint(conf)
        # 揀選窗：raw＋特徵 logistic（race 內 demean 已做）
        v = [(r[2], r[5][k], r[3]) for r in sel if r[5][k] is not None]
        t = None
        if len(v) >= 300:
            A = np.array(v); R, Z, Y = A[:, 0], A[:, 1], A[:, 2]
            if Z.std() > 0:
                Xs = np.column_stack([R / R.std(), Z / Z.std()])
                m = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(Xs, Y)
                pr = m.predict_proba(Xs)[:, 1]; W = pr * (1 - pr)
                H = np.linalg.inv((np.column_stack([np.ones(len(Y)), Xs]) * W[:, None]).T @ np.column_stack([np.ones(len(Y)), Xs]))
                t = m.coef_[0][1] / np.sqrt(H[2, 2])
        print(f"{k:11s} 揀選 n={ns:5d} 五分位殘差(pp,低→高) {qs}  t={t if t is None else round(float(t), 2)}｜確認 n={nc} {qc}")


if __name__ == "__main__":
    main()
