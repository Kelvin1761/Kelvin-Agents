"""Read-only opening-meeting audit + PIT replay. All output goes to --out.
No archive mutation, network, priors regeneration on disk, or production changes.
Fixed diagnostic arms declared before measuring: shift 10pp shape to stability;
zero-start season treated as missing evidence. Neither arm implies promotion.
"""
import argparse, hashlib, json, math, sys
from unittest.mock import patch
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'.agents/skills/hkjc_racing/hkjc_reflector/scripts'),
               str(ROOT/'.agents/skills/shared_racing')]
import pit_backtest as pit
import rescore_backtest as bt
from eval_metrics import race_metrics
from hkjc_racing_engine import scoring
from hkjc_racing_engine.engine_core import RacingEngine

ORIGINAL_CLASS_SCORE = RacingEngine._class_score

def baseline_class_score(self, features):
    score, note, source = ORIGINAL_CLASS_SCORE(self, features)
    season = self._season_record()
    if not self._is_debut() and season and season["starts"] == 0 and "季內未上名" not in note:
        score = scoring.clip_score(score + scoring.CLASS_MICRO_WEIGHTS["season_place_0_pen"])
        self.risk_flags.append("class_edge_unproven")
    return score, note, source

SNAPSHOTS={'2026-09-06_ShaTin':'20260906T112332+1000',
           '2026-09-09_HappyValley':'20260909T111642+1000'}
KEYS=['gold','gold_strict','good_positional','champion','top3_capture_at5','ndcg_at5']

def metrics(horses, actual, arm='baseline'):
    scores={}
    for hn,h in horses.items():
        a=h['python_auto']; m=a['matrix_scores']; raw=a['ability_score_raw']
        engine=RacingEngine(h,{})
        debut=engine._is_debut()
        if arm=='shape_to_stability' and not debut:
            raw += .10*(m['stability']-m['race_shape'])
        if arm=='zero_season' and not debut:
            season=engine._season_record()
            if season and season['starts']==0:
                raw += -scoring.CLASS_MICRO_WEIGHTS['season_place_0_pen']*.75*scoring.MATRIX_WEIGHTS['class_advantage']
        scores[int(hn)]=raw
    picks=sorted(scores,key=lambda n:(-scores[n],n))
    t3={h for h,p in actual.items() if p<=3}; wins={h for h,p in actual.items() if p==1}
    m=race_metrics(picks,t3,winner=next(iter(wins),None),actual_pos=actual,field_size=len(actual))
    return {k:m[k] for k in KEYS}|{'picks':picks,'top3_ranks':[picks.index(h)+1 for h in sorted(t3,key=lambda h:(actual[h],h))]}

def summary(rows):
    return {'races':len(rows),**{k:round(float(np.mean([r[k] for r in rows])),6) for k in KEYS}}

def report(races):
    arms=['baseline','shape_to_stability','zero_season']
    dates=sorted({r['date'] for r in races}); terminal=set(dates[-max(1,math.ceil(.15*len(dates))):])
    groups={'all':races,'dev':[r for r in races if r['date'] not in terminal],
            'terminal':[r for r in races if r['date'] in terminal]}
    for venue in ['ShaTin','HappyValley']:
        groups[venue]=[r for r in races if venue in r['meeting']]
    for label,lo,hi in [('field_le8',0,8),('field9_10',9,10),('field11_12',11,12),('field13plus',13,99)]:
        groups[label]=[r for r in races if lo<=r['field']<=hi]
    out={'terminal_dates':sorted(terminal),'groups':{}}
    for name,rs in groups.items():
        if not rs: continue
        out['groups'][name]={a:summary([r[a] for r in rs]) for a in arms}
        out['groups'][name]['paired']={}
        for arm in arms[1:]:
            out['groups'][name]['paired'][arm]={}
            for k in KEYS:
                ds=np.array([float(r[arm][k])-float(r['baseline'][k]) for r in rs]); rng=np.random.default_rng(7)
                ci=np.quantile(ds[rng.integers(len(ds),size=(2000,len(ds)))].mean(axis=1),[.025,.975])
                out['groups'][name]['paired'][arm][k]={'delta':round(float(ds.mean()),6),'ci':[round(float(v),6) for v in ci]}
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--archive',action='store_true');a=ap.parse_args()
    root=Path((ROOT/'.wongchoi_hk_data_root').read_text().strip()); output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    rows=[]; detail=[]; manifest=[]
    for meeting,snap in SNAPSHOTS.items():
        md=root/meeting; results=bt.load_results(bt.find_results_json(md)); sp=md/'Prediction_Snapshots'/snap
        for lp in sorted(sp.glob('Race_*_Logic.json'),key=bt.race_num_from_path):
            rn=bt.race_num_from_path(lp); logic=json.loads(lp.read_text()); horses=logic['horses']; actual=results[rn]
            record={'meeting':meeting,'date':meeting[:10],'race':rn,'field':len(horses)}
            persisted = sorted((int(hn) for hn in horses), key=lambda hn:horses[str(hn)]['python_auto']['rank'])
            assert persisted == metrics(horses,actual)['picks'], f'Persisted ranking mismatch: {lp}'
            for arm in ['baseline','shape_to_stability','zero_season']:record[arm]=metrics(horses,actual,arm)
            rows.append(record); manifest.append({'path':str(lp),'sha256':hashlib.sha256(lp.read_bytes()).hexdigest()})
            for hn,h in horses.items():
                engine=RacingEngine(h,logic['race_analysis']);season=engine._season_record(); auto=h['python_auto']
                detail.append({'meeting':meeting,'race':rn,'no':hn,'name':h['horse_name'],'finish':actual.get(int(hn)),
                    'rank':auto['rank'],'matrix':auto['matrix_scores'],'zero_season_penalty':bool(season and season['starts']==0 and not engine._is_debut()),
                    'medical':h.get('_data',{}).get('medical_flags'),'sectional_details':auto.get('speed_detail')})
    (output/'opening.json').write_text(json.dumps({'summary':report(rows),'races':rows,'horses':detail,'manifest':manifest},ensure_ascii=False,indent=2))
    print('OPENING',json.dumps(report(rows)['groups']['all'],ensure_ascii=False),flush=True)
    if not a.archive:return
    all_rows=pit.load_all_rows();replay=[];errors=[];files=[]
    for md in sorted(root.iterdir()):
        if not md.is_dir() or not md.name.startswith('2026-') or md.name[:10]>='2026-09-01':continue
        rp=bt.find_results_json(md)
        if not rp or bt.meeting_is_legacy_schema(md):continue
        actuals=bt.load_results(rp); pit.inject_as_of(all_rows,md.name[:10]);n=0
        for lp in sorted(md.glob('Race_*_Logic.json'),key=bt.race_num_from_path):
            rn=bt.race_num_from_path(lp)
            if rn not in actuals:continue
            logic=json.loads(lp.read_text());bt.resolve_meeting_context(logic,md)
            try:
                with patch.object(RacingEngine, "_class_score", baseline_class_score):
                    rescored=bt.rescore_logic(logic)
            except Exception as e:errors.append(f'{lp}: {e}');continue
            h=rescored['horses'];record={'meeting':md.name,'date':md.name[:10],'race':rn,'field':len(h)}
            for arm in ['baseline','shape_to_stability','zero_season']:record[arm]=metrics(h,actuals[rn],arm)
            replay.append(record);n+=1;files.append({'path':str(lp),'sha256':hashlib.sha256(lp.read_bytes()).hexdigest()})
        print(md.name,n,flush=True)
    (output/'archive.json').write_text(json.dumps({'summary':report(replay),'races':replay,'errors':errors,'manifest':files},ensure_ascii=False,indent=2))
    print('ARCHIVE',len(replay),'errors',len(errors),flush=True)
if __name__=='__main__':main()
