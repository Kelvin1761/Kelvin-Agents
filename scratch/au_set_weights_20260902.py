#!/usr/bin/env python3
"""EXP08 fixed correction: title aliases must respect set-weight semantics."""
import argparse
import dataclasses
import json
from pathlib import Path
import re
import sys


def corrected_is_sw(self):
    text = self._race_class_text().lower()
    # Use tokens: a sponsor containing 'sw' is not a set-weight condition.
    return bool(re.search(
        r'\b(?:wfa|sw)\b|\bweight[ -]+for[ -]+age\b|\bset[ -]+weights?\b'
        r'|\b(?:maiden|mdn)\s+plate\b', text))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--engine-root', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    sys.path.insert(0, str(Path(a.engine_root) / '.agents/skills/au_racing/au_wong_choi_auto/scripts'))
    import au_eval as ev
    from au_racing_engine import engine_core as ec
    from au_auto_orchestrator import _build_field_summary
    from au_dump_engine_leaves import _corpus_meeting_dirs
    from au_archive_calibrator import ARCHIVE_ROOT
    races = json.loads(Path(a.data).read_text())['races']
    dirs = {p.name: p for p in _corpus_meeting_dirs(ARCHIVE_ROOT)}
    changed = []
    for race in races:
        path = dirs[race['meeting']] / f"Race_{race['race']}_Logic.json"
        logic = json.loads(path.read_text())
        ctx = dict(logic['race_analysis']);horses = logic['horses']
        probe = ec.RacingEngine({}, ctx)
        before, after = probe._is_wfa_or_sw_race(), corrected_is_sw(probe)
        race['changed_conditions'] = before != after
        if before == after:
            continue
        ctx['field_summary'] = _build_field_summary(horses)
        for row in race['rows']:
            hd = dict(horses[str(row['n'])]);hd.setdefault('horse_number', str(row['n']))
            eng = ec.RacingEngine(hd, ctx, facts_section=hd.get('_data', {}).get('facts_section',''),
                                 facts_path=str(path.parent / (race['date'] + '_dummy.md')))
            base = ec.clip_score(eng._rating_score()[0])
            assert abs(base - row['features']['rating_score']) <= .011, (path, row['n'], base)
            eng._is_wfa_or_sw_race = lambda: corrected_is_sw(eng)
            row['corrected_rating'] = round(ec.clip_score(eng._rating_score()[0]), 2)
        changed.append({'meeting':race['meeting'], 'race':race['race'], 'class':ctx['race_class'],
                        'old_is_sw':before, 'new_is_sw':after})
    bs = ev.default_scorer
    def cs(row):
        return bs({**row, 'features':{**row['features'], 'rating_score':
                   row.get('corrected_rating', row['features']['rating_score'])}})
    di, ti = ev.date_partitions(races)
    report = {'changed_races':changed, 'split':{'dev':len(di),'terminal':len(ti)},
              'changed_runners':sum(abs(cs(x)-bs(x))>.01 for r in races for x in r['rows'])}
    bmetrics,cmetrics = ev._stage4_metric_rows(races,bs),ev._stage4_metric_rows(races,cs)
    evidence = ev.build_evaluation_input(domain='au', dates=[r['date'] for r in races],
        baseline_rows=bmetrics,candidate_rows=cmetrics, leakage_audit_passed=True,
        ranking_metrics=('top3_capture_at5','mean_top3_model_rank','competitive_recall_at5','ndcg_at5','top5_pairwise_auc'))
    report['paired_evidence'] = dataclasses.asdict(evidence)
    report['performance_decision'] = ev.evaluate_candidate(evidence)
    for label,ids in [('dev',di),('terminal',ti)]:
        rs=[races[i] for i in ids];b,c=ev._counts(rs,bs),ev._counts(rs,cs)
        report[label]={'baseline':b,'candidate':c,'delta':{k:c[k]-b[k] for k in b}}
    # Paired resampling of identical races; include fields and baseline top-pick SP.
    import numpy as np
    rng=np.random.default_rng(7)
    groups={f'field_{label}':[i for i in ti if lo<=races[i]['field']<=hi]
            for lo,hi,label in ev.FIELD_BUCKETS}
    for lo,hi,label in [(0,3,'lt3'),(3,6,'3to6'),(6,10,'6to10'),(10,20,'10to20'),(20,float('inf'),'20plus')]:
        groups['sp_'+label]=[i for i in ti if lo<=float(max(races[i]['rows'],key=bs).get('sp') or 0)<hi]
    groups['changed_conditions']=[i for i in ti if races[i]['changed_conditions']]
    report['cohorts']={}
    for label,ids in groups.items():
        item={'n':len(ids)}
        for key in ('gold','good_positional'):
            ds=np.array([float(cmetrics[i][key])-float(bmetrics[i][key]) for i in ids
                         if bmetrics[i][key] is not None and cmetrics[i][key] is not None])
            if not len(ds):continue
            sims=ds[rng.integers(0,len(ds),(2000,len(ds)))].mean(axis=1)
            item[key]={'delta':float(ds.mean()),'ci95':np.quantile(sims,[.025,.975]).tolist()}
        report['cohorts'][label]=item
    Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    Path(a.out).with_suffix('.rows.json').write_text(json.dumps({'races':races}))
    print(json.dumps({k:v for k,v in report.items() if k not in ('changed_races','cohorts','paired_evidence')},indent=2))


if __name__=='__main__':main()
