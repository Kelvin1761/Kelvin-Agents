import sys, random
sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts"); sys.path.insert(0,".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"); sys.path.insert(0,".agents/skills/shared_racing")
from au_cached_walkforward_ml import materialize_dataset, group_races, as_float, date_folds, metrics_for_races
from scoring import MATRIX_WEIGHTS
def clip(v): return max(0.0,min(100.0,float(v)))
FORM={"stability":[("form_score",0.6),("consistency_score",0.4)],"pace_perf":[("pace_figure_score",0.759174),("sectional_score",0.193864),("trial_score",0.046962)],"race_shape":[("pace_map_score",1.0)],"jockey_trainer":[("jockey_score",0.28),("trainer_score",0.20),("jockey_horse_fit_score",0.52)],"class_weight":[("class_score",0.159),("rating_score",0.70),("weight_score",0.141)],"track":[("track_score",1.0)]}
DIMS=list(FORM.keys())
def miss(r,k): return abs(as_float(r.get(k),60)-60)<1e-9
def mx_current(r,dim):
    comps=FORM[dim]; s=sum(w for _,w in comps) or 1
    return sum(clip(r.get(k,60))*(w/s) for k,w in comps)
def mx_coverage(r,dim):
    comps=[(k,w) for k,w in FORM[dim] if not miss(r,k)]
    if not comps: return 60.0
    s=sum(w for _,w in comps)
    return sum(clip(r.get(k,60))*(w/s) for k,w in comps)
def coverage(r,dim):  # fraction of dimension weight that is PRESENT
    comps=FORM[dim]; tot=sum(w for _,w in comps) or 1
    return sum(w for k,w in comps if not miss(r,k))/tot
def score(races,mxfn,w,cov_downweight=False):
    out=[]
    for race in races:
        rows=[]
        for r in race:
            wd={d:w[d]*(coverage(r,d) if cov_downweight else 1.0) for d in DIMS}
            s=sum(wd.values()) or 1; wd={d:v/s for d,v in wd.items()}
            rows.append({**r,"_score":sum(mxfn(r,d)*wd[d] for d in DIMS)})
        out.append(rows)
    return out
def plain(m):
    n=m["races"]
    return (f"頭兩揀齊入三甲 {m['good_positional']}場({100*m['good_positional']/n:.1f}%) | "
            f"Top3中2隻 {m['good']}場({100*m['good']/n:.1f}%) | "
            f"捉到冠軍 {100*m['winner_in_top3']:.1f}% | 頭揀贏 {100*m['top1_win']:.1f}% | "
            f"全失 {m['miss']}場({100*m['miss']/n:.1f}%)")
races=group_races(materialize_dataset()); folds=date_folds(races); valid=[r for _t,v in folds for r in v]
cur={d:MATRIX_WEIGHTS[d] for d in DIMS}
print(f"=== 全部 {len(races)} 場｜walk-forward 驗證窗 {len(valid)} 場 ===\n")
print("A. 現狀                        :",plain(metrics_for_races(score(valid,mx_current,cur))))
print("B. 缺失只計有嘅(renormalise)   :",plain(metrics_for_races(score(valid,mx_coverage,cur))))
print("C. 低覆蓋維度降權              :",plain(metrics_for_races(score(valid,mx_current,cur,cov_downweight=True))))
print("D. B+C 合併                    :",plain(metrics_for_races(score(valid,mx_coverage,cur,cov_downweight=True))))
