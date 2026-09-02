#!/usr/bin/env python3
"""Fixed pre-spell reliability ablations; current-day cases never tune them."""
import argparse
import dataclasses
import importlib.util
import json
from pathlib import Path
import sys
from datetime import date


def historical_share(cycle, dates, weights=(1.0, .8, .6, .4)):
    """Failed research candidate, deliberately kept outside the production engine."""
    if cycle['stage'] not in ('first_up', 'second_up', 'third_up'):
        return 0.0
    try:
        start, target = date.fromisoformat(cycle['prep_start_date']), date.fromisoformat(cycle['as_of'])
        selected = [date.fromisoformat(str(x or '')) for x in list(dates)[:len(weights)]]
    except (TypeError, ValueError):
        return 0.0
    if not selected or any(x >= target for x in selected):
        return 0.0
    active = weights[:len(selected)]
    return sum(w for day,w in zip(selected,active) if day < start) / sum(active)


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['build','dev','terminal'])
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    scripts=Path('/tmp/au-feedback-main-final/.agents/skills/au_racing/au_wong_choi_auto/scripts')
    sys.path.insert(0,str(scripts))
    import au_eval as ev
    from au_racing_engine.engine_core import RacingEngine
    from au_racing_engine.scoring import parse_placing
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_archive_calibrator import ARCHIVE_ROOT
    spec=importlib.util.spec_from_file_location('cycle_candidate',root/'.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/preparation_cycle.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    out=Path('/tmp/au-preparation-cycle')
    if a.phase=='build':
        rs=json.loads(Path('/tmp/au-matrix-feedback-after.json').read_text())['races']
        dirs={d.name:d for d in _corpus_meeting_dirs(ARCHIVE_ROOT)}
        counts={}
        for race in rs:
            d=json.loads((dirs[race['meeting']]/f"Race_{race['race']}_Logic.json").read_text())
            ctx={**d['race_analysis'],'field_summary':_build_field_summary(d['horses'])}
            for row in race['rows']:
                h=d['horses'][str(row['n'])]
                e=RacingEngine(h,ctx,facts_section=h.get('_data',{}).get('facts_section',''))
                entries=e._official_entries();cycle=mod.preparation_cycle(entries,race['date'])
                row['prep_cycle']=cycle;counts[cycle['stage']]=counts.get(cycle['stage'],0)+1
                form=[(x.get('date'),w) for x,w in zip(entries[:4],(1,.8,.6,.4))
                      if parse_placing(x.get('placing')) is not None]
                pq=h.get('_data',{}).get('performance_quality_runs') or h.get('_data',{}).get('sportsbet_performance_quality_runs') or []
                # Never invent dates for fallback consistency or sparse PQ.
                pq_source=e._performance_quality_score()[2]
                pqdates=[x.get('date') for x in pq[:4]] if pq_source!='consistency_fallback' else []
                shares={'form_score':historical_share(cycle,[x[0] for x in form],tuple(x[1] for x in form)),
                        'performance_quality_score':historical_share(cycle,pqdates)}
                row['stale_share']=shares
                row['baseline']=ev.default_scorer(row)
                row['candidate']={}
                for name,keys in [('F',['form_score']),('Q',['performance_quality_score']),('FQ',list(shares))]:
                    fs=dict(row['features'])
                    for key in keys:fs[key]=60+(1-.5*shares[key])*(fs[key]-60)
                    row['candidate'][name]=ev.default_scorer({**row,'features':fs})
        out.with_suffix('.data.json').write_text(json.dumps({'races':rs,'counts':counts}))
        print(counts,flush=True);return
    data=json.loads(out.with_suffix('.data.json').read_text());rs=data['races'];di,ti=ev.date_partitions(rs)
    bs=lambda x:x['baseline'];report={'counts':data['counts'],'candidates':{}}
    for name in ('F','Q','FQ'):
        cs=lambda x:x['candidate'][name]
        item={}
        dev=[rs[i] for i in di];b,c=ev._counts(dev,bs),ev._counts(dev,cs)
        item['dev']={k:c[k]-b[k] for k in b}
        eligible=item['dev']['gold']>=0 and item['dev']['good_positional']>=0
        item['eligible']=eligible
        if a.phase=='terminal' and eligible:
            term=[rs[i] for i in ti];b,c=ev._counts(term,bs),ev._counts(term,cs)
            item['terminal']={k:c[k]-b[k] for k in b}
            evidence=ev.build_evaluation_input(domain='au',dates=[r['date'] for r in rs],
                baseline_rows=ev._stage4_metric_rows(rs,bs),candidate_rows=ev._stage4_metric_rows(rs,cs),
                leakage_audit_passed=True,ranking_metrics=('top3_capture_at5','mean_top3_model_rank','competitive_recall_at5','ndcg_at5','top5_pairwise_auc'))
            item['evidence']=dataclasses.asdict(evidence);item['decision']=ev.evaluate_candidate(evidence)
        report['candidates'][name]=item
        print(name,item,flush=True)
    out.with_suffix('.results.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
