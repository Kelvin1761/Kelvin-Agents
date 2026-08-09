"""穩定性重新塑形嘅 shadow A/B。

實測（713 場，已修正馬群大細，超額前三率）：
    <65   −10.0      75–85  +0.1      95–100  +10.0
    65–75  −4.1      85–95  +2.0
即係 65→95 呢 30 分（住咗 65% 馬匹）只換到 6pp 訊號，真訊號集中兩端。
但排名係線性食呢個分嘅，而佢場內 SD 11.21 全矩陣最闊、影響力 21.6%。

做法：把分數換成「同實測超額成正比」嘅單調變換，再整體縮放到同原本一樣嘅
場內 SD —— 即係**淨係改形狀，唔改佢嘅話事權**。dev 85% / 未碰 holdout 15%。
唯讀。
"""
import json, statistics, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path('.agents/skills/au_racing/au_wong_choi_auto/scripts')))
sys.path.insert(0, str(Path('.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine')))
sys.path.insert(0, str(Path('.agents/skills/shared_racing')))
from eval_metrics import race_metrics, summarize_races
from matrix_mapper import map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS, clip_score

KEYS=("gold","good_pos","any2","pass1","champ","winT3","t3prec","mrr","blowout","compet","ndcg5")
LEAF="consistency_score"
# 實測錨點 (分數, 超額pp)
ANCH_X=[57.0, 70.0, 80.0, 90.0, 97.5]
ANCH_Y=[-10.0, -4.1, 0.1, 2.0, 10.0]

def digest(s):
    r,c=s["rates"],s["competitiveness"]
    return {"gold":100*r["gold"],"good_pos":100*r["good_positional"],"any2":100*r["good_any2"],
            "pass1":100*r["pass_any1"],"champ":100*r["champion"],"winT3":100*r["winner_in_top3"],
            "t3prec":100*s["top3_precision"],"mrr":100*s["mrr"],
            "blowout":100*c["top_pick_blowout"]["rate"],"compet":100*c["top_pick_competitive"]["rate"],
            "ndcg5":100*c["mean_ndcg_at5"]}

races=json.loads(Path('scratch/fl_new.json').read_text())['races']
orig=[h['features'][LEAF] for rc in races for h in rc['rows']]
sd_orig=statistics.mean(float(np.std([h['features'][LEAF] for h in rc['rows']],ddof=1))
                        for rc in races if len(rc['rows'])>1)

def reshape(v, k):
    return clip_score(60.0 + k*float(np.interp(v, ANCH_X, ANCH_Y)))

# 揀 k 令場內 SD 同原本一樣（純改形狀，唔改話事權）
lo,hi=0.1,10.0
for _ in range(40):
    k=(lo+hi)/2
    sd=statistics.mean(float(np.std([reshape(h['features'][LEAF],k) for h in rc['rows']],ddof=1))
                       for rc in races if len(rc['rows'])>1)
    if sd<sd_orig: lo=k
    else: hi=k
K=(lo+hi)/2
print(f"原本場內 SD {sd_orig:.3f} → 校準後 k={K:.4f}（保持同一 SD，只改形狀）")
print(f"變換示例： 50→{reshape(50,K):.1f}  65→{reshape(65,K):.1f}  75→{reshape(75,K):.1f}  "
      f"85→{reshape(85,K):.1f}  95→{reshape(95,K):.1f}  100→{reshape(100,K):.1f}")

def ev(transform, lo_i, hi_i):
    out=[]
    for rc in races[lo_i:hi_i]:
        scored=[]
        for h in rc['rows']:
            f=dict(h['features'])
            if transform: f[LEAF]=transform(f[LEAF])
            mx=map_features_to_matrix_scores(f)
            scored.append((round(sum(mx[kk]*MATRIX_WEIGHTS[kk] for kk in MATRIX_WEIGHTS),4)
                           + float(h['wet'] or 0), h['n']))
        picks=[n for _,n in sorted(scored,key=lambda t:(-t[0],t[1]))]
        pos={h['n']:h['pos'] for h in rc['rows']}
        t3=[n for n,p in pos.items() if p<=3]; w=[n for n,p in pos.items() if p==1]
        out.append(race_metrics(picks,t3,winner=w[0] if w else None,actual_pos=pos,field_size=rc['field']))
    return digest(summarize_races(out))

n=len(races); split=int(n*0.85)
for name,(a,b) in (("dev",(0,split)),("holdout 未碰過",(split,n))):
    base=ev(None,a,b); cand=ev(lambda v: reshape(v,K),a,b)
    print(f"\n===== {name} ({b-a} 場) =====")
    print(f"{'':10}"+"".join(f"{x:>11}" for x in KEYS))
    print(f"{'delta':10}"+"".join(f"{cand[x]-base[x]:>+11.2f}" for x in KEYS))
