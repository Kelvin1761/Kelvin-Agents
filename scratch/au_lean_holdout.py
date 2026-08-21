import sys, random
sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts"); sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"); sys.path.insert(0,".agents/skills/shared_racing")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float, metrics_for_races
from au_racing_engine.scoring import MATRIX_WEIGHTS
def clip(v): return max(0.0,min(100.0,float(v)))
FULL={"stability":[("form_score",0.6),("consistency_score",0.4)],"pace_perf":[("pace_figure_score",0.759174),("sectional_score",0.193864),("trial_score",0.046962)],"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],"class_weight":[("class_score",0.159),("rating_score",0.70),("weight_score",0.141)],"track":[("track_score",1.0)]}
LEAN={"stability":[("form_score",0.6),("consistency_score",0.4)],"pace_perf":[("pace_figure_score",1.0)],"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],"class_weight":[("rating_score",1.0)],"track":[("track_score",1.0)]}
DIMS=list(FULL.keys())
def mk(formulas):
    def mx(fs):
        o={}
        for d,comps in formulas.items():
            s=sum(w for _,w in comps) or 1; o[d]=sum(clip(fs.get(k,60))*(w/s) for k,w in comps)
        return o
    return mx
def sr(races,w,mx): return [[{**r,"_score":sum(mx(r)[d]*w[d] for d in DIMS)} for r in race] for race in races]
def opt(train,mx,rng):
    cur={d:MATRIX_WEIGHTS[d] for d in DIMS}; best=dict(cur)
    def key(w): m=metrics_for_races(sr(train,w,mx)); return (m["good_positional"]+m["good"])/max(1,m["races"])
    bk=key(best)
    for _ in range(1500):
        w=dict(best); d=rng.choice(DIMS); w[d]=max(0.0,w[d]+rng.uniform(-0.06,0.06))
        s=sum(w.values()); w={k:v/s for k,v in w.items()}
        k=key(w)
        if k>bk: bk,best=k,w
    return best
races=group_races(materialize_dataset()); dates=sorted({r[0]["date"] for r in races}); cut=dates[int(len(dates)*0.6)]
train=[r for r in races if r[0]["date"]<cut]; hold=[r for r in races if r[0]["date"]>=cut]
def L(m): return f"gp {m['good_positional']} ({100*m['good_positional']/m['races']:.1f}%) g2 {m['good']} miss {m['miss']} top1 {100*m['top1_win']:.1f}% wT3 {100*m['winner_in_top3']:.1f}%"
mxF=mk(FULL); mxL=mk(LEAN); rng=random.Random(11)
cur={d:MATRIX_WEIGHTS[d] for d in DIMS}
leanw=opt(train,mxL,rng)
print(f"HOLDOUT {len(hold)} races (>= {cut}):")
print("  current full          :",L(metrics_for_races(sr(hold,cur,mxF))))
print("  LEAN + retuned        :",L(metrics_for_races(sr(hold,leanw,mxL))))
print("  lean weights:",{d:round(leanw[d],3) for d in DIMS})
