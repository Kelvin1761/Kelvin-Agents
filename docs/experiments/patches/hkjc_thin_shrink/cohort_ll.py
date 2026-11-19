import json, sys
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_replay_compare_v4 as c
base = c.load(sys.argv[1]); O = sys.argv[2]
lo, hi = c.WIN["dev"]
def per_season_fit(dd):
    by = {}
    for k, x in dd.items(): by.setdefault(c.season(x["date"]), []).append(x)
    return {s: c.fit([y for t in by if 2020 <= t < s for y in by[t]] or by[s]) for s in by}
fb = per_season_fit(base)
for arm in ("S1", "S3"):
    cand = c.load(f"{O}/cand_{arm}.jsonl"); fc = per_season_fit(cand)
    diffs = []; rk = []
    for k, x in base.items():
        if not (lo <= x["date"] <= hi): continue
        y = cand[k]
        changed = [i for i, (h, g) in enumerate(zip(x["horses"], y["horses"])) if h["raw"] != g["raw"] and h["pos"]]
        if not changed: continue
        s = c.season(x["date"])
        hs_b = [h for h in x["horses"] if h["pos"]]; hs_c = [h for h in y["horses"] if h["pos"]]
        rb = np.array([h["raw"] for h in hs_b]); rc_ = np.array([h["raw"] for h in hs_c])
        pb = 1/(1+np.exp(-(fb[s][0]+fb[s][1]*(rb-rb.mean())))); pc = 1/(1+np.exp(-(fc[s][0]+fc[s][1]*(rc_-rc_.mean()))))
        # 群組馬 = raw 同 base 唔同而且偏離最大嗰匹
        dev_ = np.abs(rb - rc_); i = int(np.argmax(dev_))
        yv = int(hs_b[i]["pos"] <= 3)
        llb = -(yv*np.log(pb[i])+(1-yv)*np.log(1-pb[i])); llc = -(yv*np.log(pc[i])+(1-yv)*np.log(1-pc[i]))
        diffs.append(llc - llb)
        rb_rank = sorted(range(len(rb)), key=lambda j: -rb[j]).index(i)+1; rc_rank = sorted(range(len(rc_)), key=lambda j: -rc_[j]).index(i)+1
        rk.append((rb_rank, rc_rank, yv))
    d = np.array(diffs); rng = np.random.default_rng(0)
    bt = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
    top2b = [r for r in rk if r[0] <= 2]
    print(f"{arm} dev 群組馬 n={len(d)}  Δlog-loss（每匹）{d.mean():+.4f} [{np.percentile(bt,2.5):+.4f},{np.percentile(bt,97.5):+.4f}]；"
          f"base 排頭2 嘅 {len(top2b)} 匹 → 收窄後排名 {[r[1] for r in top2b]}，入位 {[r[2] for r in top2b]}")
