"""殘差顯著但入分唔過：拆 (a) 場間 vs 場內 (b) 旗同現有分數有幾重疊。v5 校準。"""
import sys, numpy as np
src = open("build_samedist_cls.py").read().split("by = defaultdict(list)")[0]
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]; ns = {"__name__": "x"}; exec(src, ns)
rows, F, season = ns["rows"], ns["F"], ns["season"]
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_replay_compare_v5 as v5
par = {s: v5.fit([x for x in rows if 2019 <= season(x["date"]) < s]) for s in sorted({season(x["date"]) for x in rows}) if s >= 2020}
out = {"dev": [], "hold": []}
for x in rows:
    s = season(x["date"])
    if s not in par: continue
    keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]; n = len(keep)
    r = np.array([x["horses"][i]["raw"] for i in keep]); rc = r - r.mean(); a, b, g = par[s]
    p = 1 / (1 + np.exp(-(a + b * rc + g * v5.field_logit(n)))); y = np.array([int(x["horses"][i]["pos"] <= 3) for i in keep])
    res = y - p; f = F[id(x)][keep, 1]
    w = "dev" if s <= 2023 else "hold"
    for j in range(n):
        out[w].append((f[j], res[j], res[j] - res.mean(), rc[j], f.mean(), (rc > rc[j]).sum() + 1))
for w, v in out.items():
    v = np.array(v); m = v[:, 0] == 1
    print(f"[{w}] 有旗 n {m.sum()}：原殘差 {100*v[m,1].mean():+.2f}pp｜場內置中殘差 {100*v[m,2].mean():+.2f}pp｜同場有旗比例 {100*v[m,4].mean():.0f}%（全部馬平均 {100*v[:,4].mean():.0f}%）")
    print(f"      有旗馬模型平均排第 {v[m,5].mean():.1f}，raw 比場均高 {v[m,3].mean():+.2f}；冇旗 {v[~m,3].mean():+.2f}")
