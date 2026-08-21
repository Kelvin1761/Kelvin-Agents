import sys, random
sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts"); sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"); sys.path.insert(0,".agents/skills/shared_racing")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float, metrics_for_races
from au_racing_engine.scoring import MATRIX_WEIGHTS
def clip(v): return max(0.0,min(100.0,float(v)))
FULL={"stability":[("form_score",0.6),("consistency_score",0.4)],"pace_perf":[("pace_figure_score",0.759174),("sectional_score",0.193864),("trial_score",0.046962)],"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],"class_weight":[("class_score",0.159),("rating_score",0.70),("weight_score",0.141)],"track":[("track_score",1.0)]}
DIMS=list(FULL.keys())
def mx(fs):
    o={}
    for d,comps in FULL.items():
        s=sum(w for _,w in comps) or 1; o[d]=sum(clip(fs.get(k,60))*(w/s) for k,w in comps)
    return o
def sr(races,w): return [[{**r,"_score":sum(mx(r)[d]*w[d] for d in DIMS)} for r in race] for race in races]
def key(races,w):
    m=metrics_for_races(sr(races,w)); return (m["good_positional"]+m["good"])/max(1,m["races"])
races=group_races(materialize_dataset())
dates=sorted({r[0]["date"] for r in races}); cut=dates[int(len(dates)*0.6)]
train=[r for r in races if r[0]["date"]<cut]; hold=[r for r in races if r[0]["date"]>=cut]
cur={d:MATRIX_WEIGHTS[d] for d in DIMS}
# coordinate ascent from current, on train
rng=random.Random(7); best=dict(cur); bk=key(train,best)
for _ in range(1500):
    w=dict(best); d=rng.choice(DIMS); w[d]=max(0.0,w[d]+rng.uniform(-0.06,0.06))
    s=sum(w.values()); w={k:v/s for k,v in w.items()}
    k=key(train,w)
    if k>bk: bk,best=k,w
def L(m): return f"gp {m['good_positional']} ({100*m['good_positional']/m['races']:.1f}%) g2 {m['good']} miss {m['miss']} top1 {100*m['top1_win']:.1f}% wT3 {100*m['winner_in_top3']:.1f}% top3 {100*m['top3_precision']:.1f}%"
print(f"train {len(train)} races, HOLDOUT {len(hold)} races (dates >= {cut})")
print("current weights:",{d:round(cur[d],3) for d in DIMS})
print("retuned weights:",{d:round(best[d],3) for d in DIMS})
print("\nHOLDOUT (never seen in tuning):")
print("  current:",L(metrics_for_races(sr(hold,cur))))
print("  retuned:",L(metrics_for_races(sr(hold,best))))
