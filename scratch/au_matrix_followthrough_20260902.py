#!/usr/bin/env python3
"""EXP-07 fixed, isolated hypotheses; no live outputs or parameters written."""
import argparse
import dataclasses
import inspect
import json
from pathlib import Path
import re
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'))
import au_eval as ev
from au_racing_engine import engine_core as ec, matrix_mapper as mm
from au_auto_orchestrator import _build_field_summary
from au_dump_engine_leaves import _corpus_meeting_dirs
from au_archive_calibrator import ARCHIVE_ROOT
from au_matrix_feedback_20260902 import final_form, final_fit, replace_once, FROZEN_SCORING, FROZEN_MAPPER

OUT = Path('/tmp/au-matrix-followthrough')


def compile_method(source, name):
    ns = dict(ec.__dict__)
    exec(compile(source, '<EXP07>', 'exec'), ns)
    return ns[name]


def build():
    baseline = json.loads(Path('/tmp/au-matrix-followthrough-baseline.json').read_text())['races']
    dirs = {p.name: p for p in _corpus_meeting_dirs(ARCHIVE_ROOT)}
    prior = json.loads(Path('/tmp/au-matrix-feedback-eval.enriched.json').read_text())
    original = {(r['meeting'], r['race']): r for r in prior['races']}
    source = textwrap.dedent(inspect.getsource(ec.RacingEngine._form_score))
    a = source.index('        entry_tier = ')
    b = source.index('        race_score = ', a)
    l = source[:a] + '''        class_mult = 1.0
        prize = parse_float(entry.get("prize"))
        median = parse_float(self._field_summary().get("prize_level_field_median"))
        if prize and prize > 0 and median is not None and base_pts:
            class_mult += CLASS_PRIZE_K * (math.log10(prize) - median) / base_pts

''' + source[b:]
    l = replace_once(l, 'own_level = horse_prize_level(self.facts_section)', 'own_level = None')
    lm = compile_method(l, '_form_score')
    t = textwrap.dedent(inspect.getsource(ec.RacingEngine._jockey_horse_fit_score))
    t = replace_once(t, 'elif current_trial_rides > 0 and current_trial_top3 > 0:',
                     'if current_trial_rides > 0 and current_trial_top3 > 0:')
    tm = compile_method(t, '_jockey_horse_fit_score')
    case = prior['case']
    for race in baseline + [case]:
        path = dirs[race['meeting']] / f"Race_{race['race']}_Logic.json"
        logic = json.loads(path.read_text()); horses = logic['horses']
        ctx = dict(logic['race_analysis']); ctx['field_summary'] = _build_field_summary(horses)
        ctx['audit_date'] = race['date']
        ctx['field_horse_names'] = [h.get('horse_name') for h in horses.values()]
        old = original.get((race['meeting'], race['race']), case)
        prior_rows = {x['n']: x for x in old['rows']}
        race['going'] = ctx.get('track_condition', '')
        for row in race['rows']:
            h = dict(horses[str(row['n'])]);h.setdefault('horse_number', str(row['n']))
            eng = ec.RacingEngine(h, ctx, facts_section=h.get('_data', {}).get('facts_section',''),
                                 facts_path=str(path.parent / f"{race['date']}_dummy.md"))
            cs = row['features']['class_score']
            raw = ec.clip_score(eng._form_score()[0])
            if race is case:
                row['features']['form_score'] = final_form(raw, cs)
            elif abs(final_form(raw, cs) - row['features']['form_score']) > .011:
                raise ValueError(f'baseline mismatch {path} {row["n"]}')
            entries = eng._official_entries()[:4]
            today = surface(eng._today_going())
            known = [(surface(e.get('going')), wt) for e,wt in zip(entries,(1,.8,.6,.4))
                     if surface(e.get('going')) and str(e.get('date','')) < race['date']]
            same = sum(w for s,w in known if s == today)
            denom = sum(w for s,w in known)
            pq = row['features']['performance_quality_score']
            surface_pq = 60+(pq-60)*same/denom if pq>60 and today and denom else pq
            line = prior_rows[row['n']]['pure_formline']
            competitive = False
            for e in entries:
                pos = ec.parse_placing(e.get('placing'))
                m = re.search(r'\(([-+]?\d+(?:\.\d+)?)L\)', str(e.get('placing')))
                margin = abs(float(m[1])) if m else (0 if pos==1 else None)
                competitive |= bool(pos and pos<=6 and margin is not None and margin<=5)
            row['candidates'] = {
                'P': {'form_score': raw},
                'S': {'performance_quality_score': round(surface_pq,2)},
                'L': {'form_score': final_form(lm(eng)[0], cs)},
                'F': {'formline_score': min(60,line) if not competitive else line},
                'T': {'jockey_horse_fit_score': final_fit(tm(eng)[0],cs)},
            }
        if len(baseline) and baseline.index(race)%200==0 if race is not case else False:
            print(race['date'], flush=True)
    OUT.with_suffix('.data.json').write_text(json.dumps({'races':baseline, 'case':case}))


def surface(text):
    text = str(text or '').lower()
    if any(s in text for s in ('synthetic','poly','tapeta','all weather')):return 'synthetic'
    if any(s in text for s in ('good','soft','heavy','firm','turf')):return 'turf'
    return ''


def scorer(name):
    coefficients={k:w*FROZEN_MAPPER['MATRIX_DISPLAY_GAINS'][k]/FROZEN_SCORING['MATRIX_ABILITY_SCALE']
                  for k,w in FROZEN_SCORING['MATRIX_WEIGHTS'].items()}
    def score(row):
        fs={**row['features'],**row.get('candidates',{}).get(name,{})}
        if name=='N':
            raw={k:round(ec.clip_score(60+sum((ec.clip_score(fs.get(n,60))-60)*w for n,w in comps)),2)
                 for k,comps in mm.MATRIX_FORMULAS.items()}
            return 60+sum((raw[k]-60)*w for k,w in coefficients.items())+row['wet']+row.get('proven_class',0)
        if name=='F':
            base=ev.default_scorer(row)-row['wet']-row.get('proven_class',0)
            return .97*base+.03*fs['formline_score']+row['wet']+row.get('proven_class',0)
        return ev.default_scorer({**row,'features':fs})
    return score


def delta(races, score):
    a,b=ev._counts(races,ev.default_scorer),ev._counts(races,score)
    return {k:b[k]-a[k] for k in ('gold','good_positional','champion','pass')}


def evaluate(terminal=False):
    d=json.loads(OUT.with_suffix('.data.json').read_text());rs=d['races']
    di,ti=ev.date_partitions(rs);dev=[rs[i] for i in di];term=[rs[i] for i in ti]
    report={}
    for name in ('N','P','S','L','F','T'):
        sc=scorer(name);item={'dev':delta(dev,sc)}
        item['eligible']=item['dev']['gold']>=0 and item['dev']['good_positional']>=0
        item['changed']=sum(abs(sc(x)-ev.default_scorer(x))>.01 for r in rs for x in r['rows'])
        item['case']=sorted([{'n':x['n'],'name':x['name'],'score':sc(x)} for x in d['case']['rows']],key=lambda x:-x['score'])
        item['dev_fields']={label:delta([r for r in dev if lo<=r['field']<=hi],sc) for lo,hi,label in ev.FIELD_BUCKETS}
        if terminal and item['eligible'] and name!='F':
            item['terminal']=delta(term,sc)
            item['verdict']=ev.verdict_dict(ev.compare(rs,cand_scorer=sc,label=name,leakage_audit_passed=True))
            item['terminal_fields']={label:delta([r for r in term if lo<=r['field']<=hi],sc) for lo,hi,label in ev.FIELD_BUCKETS}
        report[name]=item
        print(name,item['dev'],item.get('terminal'),flush=True)
    OUT.with_suffix('.results.json').write_text(json.dumps(report,indent=2))


def final_check():
    import hashlib
    baseline = json.loads(Path('/tmp/au-matrix-followthrough-baseline.json').read_text())['races']
    candidate = json.loads(Path('/tmp/au-exp07-engine-final.json').read_text())['races']
    identity = lambda rs: [(r['meeting'], r['race'], [(x['n'],x['pos']) for x in r['rows']]) for r in rs]
    assert identity(baseline) == identity(candidate), 'corpus or outcome mismatch'
    for a,b in zip(baseline,candidate):
        for x,y in zip(a['rows'],b['rows']):x['candidate_ability']=y['ability']
    bs=lambda x:x['ability'];cs=lambda x:x['candidate_ability']
    di,ti=ev.date_partitions(baseline)
    report={'races':len(baseline),'runners':sum(len(r['rows']) for r in baseline),
            'sample_hash':hashlib.sha256(json.dumps(identity(baseline)).encode()).hexdigest(),
            'max_ability_delta':max(abs(cs(x)-bs(x)) for r in baseline for x in r['rows'])}
    for name,ids in [('dev',di),('terminal',ti)]:
        rs=[baseline[i] for i in ids];a,b=ev._counts(rs,bs),ev._counts(rs,cs)
        report[name]={k:b[k]-a[k] for k in a}
        am,bm=ev._stage4_metric_rows(rs,bs),ev._stage4_metric_rows(rs,cs)
        report[name+'_primary_changed_races']={k:sum(x[k]!=y[k] for x,y in zip(am,bm))
                                               for k in ('gold','good_positional')}
    report['verdict']=ev.verdict_dict(ev.compare(baseline,bs,cs,label='structural refactor',leakage_audit_passed=True))
    Path('/tmp/au-exp07-final-ab.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['build','dev','terminal','final']);a=p.parse_args()
    if a.phase=='build':build()
    elif a.phase=='final':final_check()
    else:evaluate(a.phase=='terminal')
