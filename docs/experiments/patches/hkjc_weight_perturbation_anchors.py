# ruff: noqa: F821  —— 名稱由 exec 前置腳本提供（R、met、score、w0 等）
# EXP-20261113-05/06 分析腳本（喺 repo root 行；參數見 EXP 記錄：labels_final.jsonl 所在 scratch 目錄／前置腳本路徑）
"""跟進：Gold 遇擾動就跌，係因為現行權重係最優，定係 Gold 呢把尺本身「加噪音就跌」？
預先登記：揀 20 個隨機錨點（現行權重 × exp(0.3ε)），每個錨點再擾動 100 次（σ 0.15），量（擾動 − 錨點）。
如果錨點附近都系統性跌 → 尺本身對噪音凹（任何真訊號都要先贏過噪音成本）；如果錨點附近 ≈ 0 → 現行權重係真最優。"""
import json, sys
import numpy as np
exec(open(sys.argv[2]).read().split("base = np.array")[0])
rng = np.random.default_rng(11)
out = []
for a in range(20):
    wa = w0 * np.exp(0.3 * rng.standard_normal(len(w0))); wa *= w0.sum() / wa.sum()
    ba = np.array([met(r, wa) for r in R])
    d = []
    for _ in range(100):
        w = wa * np.exp(0.15 * rng.standard_normal(len(w0))); w *= w0.sum() / w.sum()
        d.append((np.array([met(r, w) for r in R]) - ba).mean(0) * 100)
    d = np.array(d); out.append(d.mean(0))
    print(f"錨點 {a:>2}：錨點 Gold {ba[:,0].mean()*100:.1f}%｜擾動均值 Gold {d[:,0].mean():+.2f} Good {d[:,1].mean():+.2f} capture@5 {d[:,2].mean():+.2f} 頭二 {d[:,3].mean():+.2f}", flush=True)
o = np.array(out)
print(f"\n20 個錨點平均：Gold {o[:,0].mean():+.2f}（{(o[:,0]<0).sum()}/20 負）Good {o[:,1].mean():+.2f}（{(o[:,1]<0).sum()}/20 負）capture@5 {o[:,2].mean():+.2f} 頭二 {o[:,3].mean():+.2f}")
print("對照：現行權重 σ0.15 擾動 Gold −1.05、Good −1.25、capture@5 +0.30、頭二 +0.29")
