"""EXP-20261118-04：近績合併＋refit（Kelvin 2026-11-18「同一樣嘢分開兩個 section 好亂」）。
base = M1（段速已剷走輸頭馬差距）。將「狀態與穩定性」（近績 5/9 ＋ 上名／大敗 4/9）連埋輸頭馬，合成一個「近績」組件：
  raw' = raw_M1 − W_STAB·(穩定性 − 60) + Σ β_k·(x_k − 場均)
  x = [近績分, 上名／大敗紀錄分, −近 3 仗平均輸頭馬（馬位，HKJC 馬匹頁存檔，日期早過今仗；冇 = 場均）]
β 逐季 walk-forward（2019/20 起只用之前季），條件 logit 等價：入頭三 ~ (raw_M1 扣穩定性) + x，場內置中、newton-cg（同 build_kelvin7）。
預先登記三個 arm（Holm 家族 3）：
  F1 合併兩個名次分（x = 近績、上名／大敗），輸頭馬唔入
  F2 F1 ＋ 輸頭馬
  F3 單一合成分：x = 上名／大敗 only（最簡單）＋ 輸頭馬
用法：python3 build_form_merge.py <M1.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from consistency_audit import lbw  # noqa: E402
from diag import horse_runs, season  # noqa: E402

W_STAB = 0.2451
ARMS = {"F1": ["form", "cons"], "F2": ["form", "cons", "margin"], "F3": ["cons", "margin"]}


def main():
    import hkjc_history_replay_pit as p
    rows = [json.loads(l) for l in open(sys.argv[1])]
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    key = defaultdict(list)
    for r in df.itertuples():
        key[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append(r.HorseID)
    runs, _ = horse_runs()
    races = [x for x in rows if "horses" in x]
    X = {}
    for x in races:
        feats = []
        for h in x["horses"]:
            m = None
            if h["pos"] and not h["debut"]:
                k = key.get((x["date"], x["race"], h["pos"]))
                if k and len(k) == 1:
                    v = [lbw(q) for q in [q for q in runs.get(k[0], []) if q["d"] < x["date"]][-3:]]
                    v = [a for a in v if a is not None]
                    m = -float(np.mean(v)) if len(v) >= 2 else None
            feats.append({"form": h["f"]["form_score"], "cons": h["f"]["consistency_score"], "margin": m,
                          "debut": h["debut"]})
        ms = [f["margin"] for f in feats if f["margin"] is not None]
        fill = float(np.mean(ms)) if ms else 0.0
        for f in feats:
            if f["margin"] is None:
                f["margin"] = fill
        X[id(x)] = feats
    by = defaultdict(list)
    for x in races:
        by[season(x["date"])].append(x)
    for arm, cols in ARMS.items():
        def mat(x):
            # 初出馬冇近績：設做同場非初出馬嘅平均 → 置中後 = 0（唔郁佢哋）
            z = np.array([[np.nan if f["debut"] else f[c] for c in cols] for f in X[id(x)]], dtype=float)
            mu = np.nanmean(z, axis=0) if (~np.isnan(z)).any() else np.zeros(len(cols))
            mu = np.where(np.isnan(mu), 0.0, mu)
            return np.where(np.isnan(z), mu, z)

        def base(x):
            # 非初出馬：拎走穩定性相對同場非初出平均嘅部分（初出馬水平唔變）
            st = [h["m"]["stability"] for h in x["horses"] if not h["debut"]]
            ms = float(np.mean(st)) if st else 60.0
            return np.array([h["raw"] - (0.0 if h["debut"] else W_STAB * (h["m"]["stability"] - ms)) for h in x["horses"]])

        def fit(rs):
            R, Z, Y = [], [], []
            for x in rs:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                b = base(x); z = mat(x)
                R.append((b - b.mean())[keep]); Z.append((z - z.mean(axis=0))[keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
            return (c[1:] / sd) / (c[0] / R.std())
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, cols, {s: [round(float(b), 3) for b in v] for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as fh:
            for x in rows:
                y = dict(x, arm=f"form_merge_{arm}")
                if "horses" in x and season(x["date"]) in betas:
                    bb = betas[season(x["date"])]
                    b = base(x); z = mat(x)
                    nd = np.array([not h["debut"] for h in x["horses"]])
                    add = (z - (z[nd].mean(axis=0) if nd.any() else z.mean(axis=0))) @ bb
                    y["horses"] = [dict(h, raw=round(float(bv + av), 4)) for h, bv, av in zip(x["horses"], b, add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                fh.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
