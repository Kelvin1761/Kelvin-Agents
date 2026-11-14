"""研究計劃：回放語料上「候選 vs baseline」比較（dev／holdout 分開；holdout 只准每家族睇一次 —— 見登記簿）。

窗（寫死，計劃 §1）：dev 2020-09-01..2024-07-31｜holdout 2024-09-01..2026-07-31｜terminal 2026-08-01..
指標：Gold、Good、capture@5、頭二選有中（eval_metrics），場次配對 bootstrap 2,000。
null：候選對 baseline 嘅 raw 改動（Δ）喺場內隨機洗牌 200 次加返落 baseline（同幅度、冇資訊）；報候選高過幾多 % null。
判法（計劃）：Gold、Good 都 ≥ 0；而且至少一個指標 CI 下界 > 0 或者高過 95% null 先算「有改善」；
          審計（剷走）：Gold、Good 都 ≥ 0 而且唔好過 null → 噪音，可剷。
用法：python3 hkjc_replay_compare.py <base.jsonl> <cand.jsonl> [--window dev|holdout|terminal] [--null 200]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31"), "terminal": ("2026-08-01", "2099-12-31")}
KEYS = ("Gold", "Good", "capture@5", "頭二選有中")


def met(picks, horses):
    pos = {h["n"]: h["pos"] for h in horses if h["pos"]}
    top = [k for k, p in pos.items() if p <= 3]
    if len(top) < 3:
        return None
    m = race_metrics(picks, top, actual_pos=pos)
    return [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"])]


def picks_of(ns, s):
    ns, s = np.asarray(ns), np.asarray(s, float)
    return [int(v) for v in ns[np.lexsort((ns, -s))]]


def main():
    a = sys.argv
    window = a[a.index("--window") + 1] if "--window" in a else "dev"
    nnull = int(a[a.index("--null") + 1]) if "--null" in a else 200
    lo, hi = WIN[window]
    load = lambda p: {(x["meeting"], x["race"]): x for x in map(json.loads, open(p)) if "horses" in x and lo <= x["date"] <= hi}
    B, C = load(a[1]), load(a[2])
    keys = sorted(set(B) & set(C))
    base, cand, prepared, changed = [], [], [], 0
    for k in keys:
        bh = {h["n"]: h for h in B[k]["horses"]}
        ch = {h["n"]: h for h in C[k]["horses"]}
        ns = sorted(set(bh) & set(ch))
        if len(ns) < 3:
            continue
        hs = [bh[n] for n in ns]
        mb, mc = met(B[k]["picks"], hs), met(C[k]["picks"], hs)
        if mb is None or mc is None:
            continue
        changed += B[k]["picks"] != C[k]["picks"]
        base.append(mb)
        cand.append(mc)
        rb = np.array([bh[n]["raw"] for n in ns])
        rc = np.array([ch[n]["raw"] for n in ns])
        prepared.append((ns, rb, rc - rb, hs))
    b, c = np.array(base), np.array(cand)
    d = c - b
    rng = np.random.default_rng(0)
    bs = d[rng.integers(0, len(d), (2000, len(d)))].mean(1)
    null = []
    for _ in range(nnull):
        out = []
        for ns, rb, dlt, hs in prepared:
            out.append(met(picks_of(ns, rb + rng.permutation(dlt)), hs))
        null.append(np.array(out).mean(0) - b.mean(0))
    null = np.array(null)
    print(f"窗 {window}（{lo}..{hi}）：{len(d)} 場，排名有郁 {changed} 場")
    print("指標｜baseline｜候選 − baseline [95%]｜null 均值｜高過 null %")
    for i, k in enumerate(KEYS):
        print(f"{k}｜{b[:, i].mean() * 100:.2f}%｜{d[:, i].mean() * 100:+.2f} [{np.percentile(bs[:, i], 2.5) * 100:+.2f},"
              f"{np.percentile(bs[:, i], 97.5) * 100:+.2f}]｜{null[:, i].mean() * 100:+.2f}｜{(null[:, i] < d[:, i].mean()).mean() * 100:.0f}%")


if __name__ == "__main__":
    main()
