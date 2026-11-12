# EXP-20261113-05/06 分析腳本（喺 repo root 行；參數見 EXP 記錄：labels_final.jsonl 所在 scratch 目錄／前置腳本路徑）
"""權重係咪喺同一批場次揀出嚟：離線隨機擾動外層權重，分時段量 Gold／Good／capture@5／頭二選有中嘅變化。
預先登記：w' = w·exp(σε)，σ ∈ {0.15, 0.3}，再 renormalise 到同一總和；500 次；raw' = raw + Σ(w'−w)·m。
時段 A = ≤2026-07-10（權重 commit 4a048a025 之前，pit_backtest 153 場嘅窗）、B = 07-11..09-05、C = ≥09-06（holdout 半）。
如果係喺 A 揀出嚟：A 跌得多、C 唔跌（或者少啲）。如果係真最優：每段都跌。"""
import json, sys
import numpy as np
sys.path.insert(0, ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"); sys.path.insert(0, ".agents/skills/shared_racing")
from hkjc_racing_engine import scoring
from eval_metrics import race_metrics
W = dict(scoring.MATRIX_WEIGHTS); K = list(W); w0 = np.array([W[k] for k in K])
rows = [json.loads(l) for l in open(sys.argv[1])]
rows = [x for x in rows if "error" not in x and x.get("horses") and sum(1 for h in x["horses"] if h["pos"] and h["pos"] <= 3) >= 3]
def win(d): return "A" if d <= "2026-07-10" else "B" if d < "2026-09-06" else "C"
R = []
for x in rows:
    hs = [h for h in x["horses"]]
    M = np.array([[h["m"].get(k, 60.0) for k in K] for h in hs]); raw = np.array([h["raw"] for h in hs])
    R.append((win(x["date"]), np.array([h["n"] for h in hs]), raw, M, {h["n"]: h["pos"] for h in hs if h["pos"]}))
KEYS = ("gold", "good_positional", "top3_capture_at5", "top2")
def met(r, w):
    _, n, raw, M, pos = r
    s = raw + M @ (w - w0)
    order = list(n[np.lexsort((n, -s))])
    top = [k for k, p in pos.items() if p <= 3]
    m = race_metrics(order, top, actual_pos=pos)
    return [float(m.get("gold") or 0), float(m.get("good_positional") or 0), float(m.get("top3_capture_at5") or 0), float((m.get("top2_hits") or 0) >= 1)]
base = np.array([met(r, w0) for r in R]); wins = np.array([r[0] for r in R])
print("場數", {w: int((wins == w).sum()) for w in "ABC"})
print("baseline", {w: [round(v * 100, 1) for v in base[wins == w].mean(0)] for w in "ABC"}, "（Gold, Good, capture@5, 頭二選有中 %）")
rng = np.random.default_rng(7)
for sig in (0.15, 0.3):
    D = []
    for _ in range(500):
        w = w0 * np.exp(sig * rng.standard_normal(len(w0))); w *= w0.sum() / w.sum()
        D.append(np.array([met(r, w) for r in R]) - base)
    D = np.array(D)  # perm × race × key
    print(f"\nσ={sig}：擾動 − baseline（pp，500 次均值 [2.5%,97.5%]；括號後 = Gold 升嘅比例）")
    for wn in ("A", "B", "C", "ALL"):
        sel = np.ones(len(R), bool) if wn == "ALL" else wins == wn
        m = D[:, sel, :].mean(1) * 100
        s = "｜".join(f"{k} {m[:, i].mean():+.2f} [{np.percentile(m[:, i], 2.5):+.2f},{np.percentile(m[:, i], 97.5):+.2f}]" for i, k in enumerate(KEYS))
        print(f"  {wn:<3} {s}｜Gold↑ {np.mean(m[:, 0] > 0) * 100:.0f}%")
