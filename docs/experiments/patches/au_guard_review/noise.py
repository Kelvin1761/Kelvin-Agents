"""(2) 同幅度雜訊：真候選嘅 raw Δ（按場次＋馬號對齊套落現 baseline）喺場內洗牌 30 次（×1、×2 幅度）。
報 Gold／Good 護欄（95% 下界 ≤ −1.0pp）同場內 AUC 護欄（下界 ≤ 門檻）各自捉到幾多次；同埋真（冇洗牌）Δ 嘅數字。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import SCR, Bench, fmt, key, pair_delta  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CANDS = {
    "F1 近績質素尺度（EXP-20261111-31；logloss 好、Good 踩線）": (SCR / "fq-scale/BASE.json", SCR / "fq-scale/F1.json"),
    "G50 場地相似度（EXP-20261121-39；logloss 差）": (SCR / "au-going-sim/BASE.json", SCR / "au-going-sim/G50.json"),
    "S PIT 場地標準（EXP-20261101-31；打和）": (SCR / "EXP-20261101-31/arms/base.json", SCR / "EXP-20261101-31/arms/S.json"),
}
THR = (-0.10, -0.15, -0.20, -0.25, -0.30)
b = Bench()
rng = np.random.default_rng(7)
for name, (bp, cp) in CANDS.items():
    P = pair_delta(bp, cp)

    def real(i, r, P=P):
        d = P.get(key(r), {})
        return np.array([d.get(x["n"], 0.0) for x in r["rows"]])

    cover = np.mean([np.any(real(i, b.races[i]) != 0) for i in b.scored])
    sd = np.std(np.concatenate([real(i, b.races[i]) for i in b.scored]))
    m, lo, hi = b.run(real)
    ll = b.logloss(real)
    print(f"\n== {name}｜有郁場次 {cover:.0%}、Δ SD {sd:.3f}")
    print(f"真 Δ｜Gold {fmt(m, lo, hi, 0)}｜Good {fmt(m, lo, hi, 1)}｜AUC×100 {fmt(m, lo, hi, 2)}｜Δlog-loss {ll[0]:+.5f} [{ll[1]:+.5f},{ll[2]:+.5f}]")
    for scale in (1.0, 2.0):
        L, M = [], []
        for _ in range(N):
            sh = {i: rng.permutation(real(i, b.races[i])) * scale for i in b.scored}
            m, lo, hi = b.run(lambda i, r, sh=sh: sh.get(i, np.zeros(len(r["rows"]))))
            L.append(lo); M.append(m)
        L, M = np.array(L), np.array(M)
        old = ((L[:, 0] <= -1) | (L[:, 1] <= -1)).sum()
        pts = ((M[:, 0] <= -1) | (M[:, 1] <= -1)).sum()
        aucs = "、".join(f"≤{t:+.2f}：{(L[:, 2] <= t).sum()}" for t in THR)
        print(f"洗牌 ×{scale}（{N} 次）｜舊護欄捉到 Gold {(L[:,0] <= -1).sum()}、Good {(L[:,1] <= -1).sum()}、任一 {old}"
              f"｜Gold／Good 點估計 ≤−1：{pts}｜AUC 下界 {aucs}｜AUC 點估計中位 {np.median(M[:,2]):+.3f}、下界中位 {np.median(L[:,2]):+.3f}"
              f"（範圍 {L[:,2].min():+.3f}～{L[:,2].max():+.3f}）", flush=True)
