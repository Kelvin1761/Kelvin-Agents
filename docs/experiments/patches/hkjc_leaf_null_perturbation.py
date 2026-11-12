"""EXP-20261112-10 第三部分：隨機擾動 null —— 「改呢個 leaf 就跌 Gold」係咪任何同等幅度嘅改動都會咁。

觀察：今日 ~25 個改「步速修正等級」嘅 arm，Gold 全部跌（−0.5～−2.5pp），而 Good／capture@5／NDCG 經常升。
假設（跑之前寫死）：如果 baseline 喺呢批場次上揀過／調過，任何擾動都會令 Gold 均值回歸向下。
null：b = c × z(P3) + √(1−c²) × 噪音，c = 候選同 P3 嘅相關（figW 0.55），之後同候選一樣用 dev 分位數分四級、
同一 population、同一加減分。200 次；報 ΔGold／ΔGood／ΔNDCG／Δcapture@5 嘅分佈，同候選對比。
候選嘅「真貢獻」= 候選 − null 均值；排名 = 候選喺 null 分佈嘅百分位。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_leaf_null_perturbation.py <base.jsonl> <stdP2.jsonl> <stdtable.json> <figtable.json>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
for p in (REPO, REPO / ".agents/skills/shared_racing", REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"):
    sys.path.insert(0, str(p))
LEVELS = ("仍具競爭力", "接近平均", "仍偏慢", "明顯落後")
SPLIT = "2026-09-06"
KEYS = ("gold", "good_positional", "top3_capture_at5", "ndcg_at5")


def main():
    import wongchoi_paths
    from eval_metrics import race_metrics
    from hkjc_racing_engine import scoring
    W = scoring.SPEED_MICRO_WEIGHTS
    PTS = np.array((W["finish_competitive_bonus"], W["finish_avg_bonus"], W["finish_slow_pen"], W["finish_far_behind_pen"]))
    root = Path(wongchoi_paths.HK_RACING)
    rows = [r for r in map(json.loads, open(sys.argv[1], encoding="utf-8")) if "error" not in r and r.get("horses")]
    alt = {(r["meeting"], r["race"]): {h["n"]: h for h in r["horses"]} for r in map(json.loads, open(sys.argv[2], encoding="utf-8"))
           if "error" not in r and r.get("horses")}
    std = json.load(open(sys.argv[3]))["table"]
    fig = json.load(open(sys.argv[4]))["table"]
    races = []
    for r in rows:
        logic = json.loads((root / r["meeting"] / f"Race_{r['race']}_Logic.json").read_text(encoding="utf-8")).get("horses") or {}
        st, fg = std.get(f"{r['meeting']}|{r['race']}") or {}, fig.get(f"{r['meeting']}|{r['race']}") or {}
        hs = []
        for h in r["horses"]:
            lvl = str(((logic.get(str(h["n"])) or {}).get("_data") or {}).get("finish_time_adj_level") or "")
            cur = next((i for i, s in enumerate(LEVELS) if s in lvl), None)
            m = re.search(r"修正平均:\s*([+-]?\d+\.\d+)s", lvl)
            a = alt[(r["meeting"], r["race"])][h["n"]]
            ds = a["f"]["speed_score"] - h["f"]["speed_score"]
            ok = cur is not None and m is not None and str(h["n"]) in st and str(h["n"]) in fg
            hs.append({"n": h["n"], "raw": h["raw"], "speed": h["f"]["speed_score"], "pos": h["pos"], "cur": cur, "ok": ok,
                       "p3": float(m.group(1)) if m else 0.0, "p2": st[str(h["n"])][2] if ok else 0.0,
                       "figW": -fg[str(h["n"])][1] if ok else 0.0, "r": (a["raw"] - h["raw"]) / ds if abs(ds) > 1e-9 else None})
        races.append((r, hs))
    rmed = float(np.median([h["r"] for _r, hs in races for h in hs if h["r"]]))
    pop = [h for r, hs in races for h in hs if h["ok"]]
    devpop = [h for r, hs in races for h in hs if h["ok"] and r["date"] < SPLIT]
    shares = np.array([np.mean([h["cur"] == i for h in devpop]) for i in range(4)])
    q = np.cumsum(shares)[:3]
    z = {k: (np.array([h[k] for h in pop]) - 0) / np.std([h[k] for h in devpop]) for k in ("p3", "p2", "figW")}
    isdev = np.array([any(h is x for x in devpop) for h in pop]) if len(pop) < 0 else None
    dev_mask = np.zeros(len(pop), bool)
    ids = {id(h): i for i, h in enumerate(pop)}
    for h in devpop:
        dev_mask[ids[id(h)]] = True

    def metrics(newlv):
        tot = np.zeros(len(KEYS))
        k = 0
        for r, hs in races:
            sc = []
            for h in hs:
                raw = h["raw"]
                if h["ok"]:
                    lv = newlv[k]
                    k += 1
                    new = min(100.0, max(0.0, h["speed"] - PTS[h["cur"]] + PTS[lv]))
                    raw += (h["r"] or rmed) * (new - h["speed"])
                sc.append((-raw, h["n"]))
            picks = [n for _s, n in sorted(sc)]
            pos = {h["n"]: h["pos"] for h in hs if h["pos"] is not None}
            m = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
            tot += np.array([float(m.get(x) or 0) for x in KEYS])
        return tot / len(races)

    def level_of(b):
        cuts = np.quantile(b[dev_mask], q)
        return np.searchsorted(cuts, b, side="right")
    cur = np.array([h["cur"] for h in pop])
    base = metrics(cur)

    def show(lab, v):
        d = (v - base)
        return f"{lab:<22} Gold {d[0]*100:+.2f}  Good {d[1]*100:+.2f}  capture@5 {d[2]*100:+.2f}  NDCG {d[3]:+.4f}"
    cands = {"figW w=1": z["figW"], "figW w=0.5": 0.5 * z["figW"] + 0.5 * z["p3"], "P2 w=1": z["p2"], "P2 w=0.5": 0.5 * z["p2"] + 0.5 * z["p3"]}
    cres = {k: metrics(level_of(b)) for k, b in cands.items()}
    print(f"{len(races)} 場；可改 {len(pop)} 匹；base Gold {base[0]*100:.2f}%  Good {base[1]*100:.2f}%")
    rng = np.random.default_rng(0)
    for lab, b, peer in (("figW w=1", z["figW"], z["figW"]), ("figW w=0.5", cands["figW w=0.5"], cands["figW w=0.5"]),
                         ("P2 w=1", z["p2"], z["p2"])):
        c = float(np.corrcoef(peer, z["p3"])[0, 1])
        null = np.array([metrics(level_of(c * z["p3"] + np.sqrt(1 - c * c) * rng.standard_normal(len(pop)))) for _ in range(200)]) - base
        d = cres[lab] - base
        print(f"\n{lab}（corr 同 P3 = {c:.2f}）")
        print("  " + show("候選 − base", cres[lab]))
        print(f"  null 均值              Gold {null[:,0].mean()*100:+.2f}  Good {null[:,1].mean()*100:+.2f}  capture@5 {null[:,2].mean()*100:+.2f}  NDCG {null[:,3].mean():+.4f}")
        print(f"  null 2.5–97.5%         Gold [{np.percentile(null[:,0],2.5)*100:+.2f},{np.percentile(null[:,0],97.5)*100:+.2f}]"
              f"  Good [{np.percentile(null[:,1],2.5)*100:+.2f},{np.percentile(null[:,1],97.5)*100:+.2f}]"
              f"  NDCG [{np.percentile(null[:,3],2.5):+.4f},{np.percentile(null[:,3],97.5):+.4f}]")
        print("  候選喺 null 嘅百分位   " + "  ".join(f"{k} {np.mean(null[:,i] < d[i])*100:.0f}%" for i, k in enumerate(("Gold", "Good", "capture@5", "NDCG"))))
        print(f"  候選 − null 均值       Gold {(d[0]-null[:,0].mean())*100:+.2f}  Good {(d[1]-null[:,1].mean())*100:+.2f}  NDCG {d[3]-null[:,3].mean():+.4f}")


if __name__ == "__main__":
    main()
