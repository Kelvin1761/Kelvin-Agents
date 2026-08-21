import sys, random
from statistics import mean
sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts"); sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"); sys.path.insert(0,".agents/skills/shared_racing")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float, date_folds, metrics_for_races
from au_racing_engine.scoring import MATRIX_WEIGHTS
def clip(v): return max(0.0,min(100.0,float(v)))
# full formulas
FULL={"stability":[("form_score",0.6),("consistency_score",0.4)],
"pace_perf":[("pace_figure_score",0.759174),("sectional_score",0.193864),("trial_score",0.046962)],
"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],
"class_weight":[("class_score",0.159),("rating_score",0.70),("weight_score",0.141)],"track":[("track_score",1.0)]}
# lean: drop weak sub-features (weight, class, sectional, trial)
LEAN={"stability":[("form_score",0.6),("consistency_score",0.4)],
"pace_perf":[("pace_figure_score",1.0)],
"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],
"class_weight":[("rating_score",1.0)],"track":[("track_score",1.0)]}
def mxscores(fs,formulas):
    out={}
    for dim,comps in formulas.items():
        s=sum(w for _,w in comps) or 1
        out[dim]=sum(clip(fs.get(k,60))*(w/s) for k,w in comps)
    return out
def score_races(races,formulas,weights):
    out=[]
    for race in races:
        rows=[]
        for r in race:
            mx=mxscores(r,formulas)
            rows.append({**r,"_score":sum(mx[d]*weights[d] for d in weights)})
        out.append(rows)
    return out
DIMS=list(FULL.keys())
def rand_weights(rng):
    v=[rng.random() for _ in DIMS]; s=sum(v); return {d:v[i]/s for i,d in enumerate(DIMS)}
def optimize(train,formulas,rng,iters=400):
    best={d:MATRIX_WEIGHTS[d] for d in DIMS}; bestk=-1
    def key(w):
        m=metrics_for_races(score_races(train,formulas,w)); return (m["good_positional"]+m["good"])/max(1,m["races"])
    bestk=key(best)
    for _ in range(iters):
        w=rand_weights(rng); k=key(w)
        if k>bestk: bestk,best=k,w
    return best
def L(m): return f"gp {m['good_positional']} g2 {m['good']} miss {m['miss']} top1 {100*m['top1_win']:.1f}% wT3 {100*m['winner_in_top3']:.1f}% top3 {100*m['top3_precision']:.1f}%"
races=group_races(materialize_dataset()); folds=date_folds(races)
rng=random.Random(20260724)
configs={"current (full, orig weights)":(FULL,None),
         "full + RETUNED weights":(FULL,"opt"),
         "LEAN + RETUNED weights":(LEAN,"opt")}
agg={name:[] for name in configs}
for train,valid in folds:
    for name,(formulas,mode) in configs.items():
        w={d:MATRIX_WEIGHTS[d] for d in DIMS} if mode is None else optimize(train,formulas,rng)
        agg[name].extend(score_races(valid,formulas,w))
base=metrics_for_races(agg["current (full, orig weights)"])
for name in configs:
    m=metrics_for_races(agg[name])
    d=f"Δgp {m['good_positional']-base['good_positional']:+d} Δg2 {m['good']-base['good']:+d} Δmiss {m['miss']-base['miss']:+d}" if name!="current (full, orig weights)" else ""
    print(f"{name:<30}: {L(m)}  {d}")
