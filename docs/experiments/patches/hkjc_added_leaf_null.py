"""EXP-20261112-12 null：「加一項」嘅隨機對照 —— 同樣比例、同樣加減分，但等級隨機（同結果無關）。

候選（離線，同真回放對數用）：raw += r × 加減分（r = raw 對段速分傳導，EXP-09 實測；clip 唔觸發）。
null：同一批有 W 嘅馬，等級隨機抽（比例同候選一樣），200 次；報候選喺 null 分佈嘅百分位。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_added_leaf_null.py <base.jsonl> <stdP2.jsonl> <figtable.json> <figcuts.json>
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for p in (REPO, REPO / ".agents/skills/shared_racing"):
    sys.path.insert(0, str(p))
POINTS = np.array((3.26, 0.71, -2.0, -4.0))
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5")


def main():
    from eval_metrics import race_metrics
    rows = [r for r in map(json.loads, open(sys.argv[1], encoding="utf-8")) if "error" not in r and r.get("horses")]
    alt = {(r["meeting"], r["race"]): {h["n"]: h for h in r["horses"]} for r in map(json.loads, open(sys.argv[2], encoding="utf-8"))
           if "error" not in r and r.get("horses")}
    T = json.load(open(sys.argv[3]))["table"]
    cuts = json.load(open(sys.argv[4]))["cuts_W"]
    races, slots = [], []
    for r in rows:
        tab = T.get(f"{r['meeting']}|{r['race']}") or {}
        hs = []
        for h in r["horses"]:
            a = alt[(r["meeting"], r["race"])][h["n"]]
            ds = a["f"]["speed_score"] - h["f"]["speed_score"]
            v = tab.get(str(h["n"]))
            hs.append({"n": h["n"], "raw": h["raw"], "pos": h["pos"], "r": (a["raw"] - h["raw"]) / ds if abs(ds) > 1e-9 else None,
                       "W": v[1] if v else None})
        races.append((r, hs))
    rmed = float(np.median([h["r"] for _r, hs in races for h in hs if h["r"]]))
    pop = [h for _r, hs in races for h in hs if h["W"] is not None]
    cand = np.array([0 if h["W"] >= cuts[0] else 1 if h["W"] >= cuts[1] else 2 if h["W"] >= cuts[2] else 3 for h in pop])
    idx = {id(h): i for i, h in enumerate(pop)}

    def metrics(lv, sel=lambda r: True):
        tot, n = np.zeros(len(KEYS)), 0
        for r, hs in races:
            if not sel(r):
                continue
            n += 1
            sc = []
            for h in hs:
                raw = h["raw"]
                if lv is not None and id(h) in idx:
                    raw += (h["r"] or rmed) * POINTS[lv[idx[id(h)]]]
                sc.append((-raw, h["n"]))
            picks = [x for _s, x in sorted(sc)]
            pos = {h["n"]: h["pos"] for h in hs if h["pos"] is not None}
            m = race_metrics(picks, [x for x, p in pos.items() if p <= 3], actual_pos=pos)
            tot += np.array([float(m.get(k) or 0) for k in KEYS])
        return tot / n
    base = metrics(None)
    c = metrics(cand) - base
    rng = np.random.default_rng(0)
    null = np.array([metrics(rng.permutation(cand)) - base for _ in range(200)])
    print(f"{len(races)} 場；加項馬 {len(pop)} 匹；r 中位 {rmed:.4f}")
    print(f"候選（離線）− base：Gold {c[0]*100:+.2f}  Good {c[1]*100:+.2f}  capture@5 {c[2]*100:+.2f}  NDCG {c[3]:+.4f}")
    print(f"null 均值：        Gold {null[:,0].mean()*100:+.2f}  Good {null[:,1].mean()*100:+.2f}  capture@5 {null[:,2].mean()*100:+.2f}  NDCG {null[:,3].mean():+.4f}")
    print(f"null 2.5–97.5%：   Gold [{np.percentile(null[:,0],2.5)*100:+.2f},{np.percentile(null[:,0],97.5)*100:+.2f}]  "
          f"Good [{np.percentile(null[:,1],2.5)*100:+.2f},{np.percentile(null[:,1],97.5)*100:+.2f}]  "
          f"capture@5 [{np.percentile(null[:,2],2.5)*100:+.2f},{np.percentile(null[:,2],97.5)*100:+.2f}]  "
          f"NDCG [{np.percentile(null[:,3],2.5):+.4f},{np.percentile(null[:,3],97.5):+.4f}]")
    print("候選喺 null 嘅百分位：" + "  ".join(f"{k} {np.mean(null[:,i] < c[i])*100:.0f}%" for i, k in enumerate(("Gold", "Good", "capture@5", "NDCG"))))


if __name__ == "__main__":
    main()
