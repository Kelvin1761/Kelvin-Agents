#!/usr/bin/env python3
"""Input-only AWT source trace with two isolated, independent correctness patches.

Never reads target results or fits weights. Raw historical runs are cutoff-filtered.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FACTS = ROOT / '.agents/scripts/inject_hkjc_fact_anchors.py'
AUTO = ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'
ENGINE = AUTO / 'hkjc_racing_engine/engine_core.py'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(AUTO))
from hkjc_racing_engine.engine_core import RacingEngine

FACTS_OLD = "            # Get race details block until next race or end\n"
FACTS_NEW = """            # Keep the quoted AWT surface before choosing sectional standards.
            if normalize_venue_surface(rail) == '沙田AWT':
                venue = normalize_venue_surface(f'{venue} {rail}')

            # Get race details block until next race or end
"""
ENGINE_OLD = '        sample_match = re.search(r"今場=.*?有效樣本(\\d+(?:\\.\\d+)?)", text)\n'
ENGINE_NEW = '''        target_match = re.search(r"今場=([^|]+?)\\s\\d+(?:\\.\\d+)?分", text)
        target = target_match.group(1).strip() if target_match else ""
        sample_match = re.search(
            rf"(?:^|\\|)\\s*{re.escape(target)}\\s+[^|]*?有效樣本(\\d+(?:\\.\\d+)?)",
            text,
        ) if target else None
'''


def original_source(path):
    baseline=ROOT/'docs/audits/hkjc-awt-source-trace-20261014/baseline'
    saved=baseline/('facts.py' if path==FACTS else 'engine_core.py')
    return saved.read_text() if saved.exists() else path.read_text()


def candidate_source(path, old, new):
    source=original_source(path)
    if source.count(old)!=1:
        raise ValueError(f'Source drift: {path}; refuse ambiguous patch')
    return source.replace(old,new,1)


def load_source(name,path,source):
    module=types.ModuleType(name);module.__file__=str(path)
    module.__package__=name.rpartition('.')[0]
    sys.modules[name]=module
    exec(compile(source,str(path),'exec'),module.__dict__)
    return module


def render_candidate_source():
    source=original_source(FACTS)
    changes=[("r.get('venue', p.get('venue_track', ''))[:4]", "normalize_venue_surface(r.get('venue', p.get('venue_track', '')))"),
             ("r.get('venue', '')[:4]", "normalize_venue_surface(r.get('venue', ''))")]
    for (old,new),expected in zip(changes,(2,1)):
        if source.count(old)!=expected:raise ValueError('Renderer source drift')
        source=source.replace(old,new)
    return source


def load_render_candidate():
    return load_source('hkjc_awt_trace_render_facts',FACTS,render_candidate_source())


def load_candidates():
    global RacingEngine
    RacingEngine=load_source('hkjc_racing_engine._awt_baseline_core',ENGINE,original_source(ENGINE)).RacingEngine
    facts=load_source('hkjc_awt_trace_baseline_facts',FACTS,original_source(FACTS))
    candidate=load_source('hkjc_awt_trace_candidate_facts',FACTS,candidate_source(FACTS,FACTS_OLD,FACTS_NEW))
    engine=load_source('hkjc_racing_engine._awt_sample_candidate',ENGINE,candidate_source(ENGINE,ENGINE_OLD,ENGINE_NEW))
    return facts,candidate,engine.RacingEngine


def write_patch(path, old, new, output):
    rel=str(path.relative_to(ROOT))
    output.write_text(''.join(difflib.unified_diff(original_source(path).splitlines(True),
        candidate_source(path,old,new).splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))


def only_path(paths,label):
    paths=list(paths)
    if len(paths)!=1:raise ValueError(f'{label}: expected one source, got {paths}')
    return paths[0]


def surface_text(horse):
    return str(horse.get('surface_performance_shadow') or (horse.get('_data') or {}).get('surface_performance_shadow') or '')


def metadata(reader,text):
    return reader({'surface_performance_shadow':text},{})._surface_performance_shadow_component()


def trace(dataset,output):
    facts,candidate,CandidateEngine=load_candidates()
    logic_parser_path=ROOT/'.agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py'
    logic_parser=load_source('hkjc_awt_trace_logic',logic_parser_path,logic_parser_path.read_text())
    # Explicit usecols prevents importing current-race results into the trace.
    frame=pd.read_csv(dataset,usecols=['meeting','meeting_name','date','race_number','horse_number','horse_name','track','distance_num'])
    frame=frame[frame.track=='AWT'];counts=Counter();records=[];source_hashes={}
    for path in (FACTS,ENGINE,Path(__file__),logic_parser_path,Path(dataset),
                 ROOT/'.agents/scripts/hkjc_reference_sectionals.json',
                 ROOT/'.agents/scripts/hkjc_standard_times.json'):
        source_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for (meeting,race),group in frame.groupby(['meeting','race_number'],sort=True):
        meeting=Path(meeting);logic_path=meeting/f'Race_{race}_Logic.json';raw=logic_path.read_bytes()
        source_hashes[str(logic_path)]=hashlib.sha256(raw).hexdigest();logic=json.loads(raw)
        form=only_path(meeting.glob(f'* Race {race} 賽績.md'),'formguide')
        source_hashes[str(form)]=hashlib.sha256(form.read_bytes()).hexdigest()
        facts_path=only_path(meeting.glob(f'* Race {race} Facts.md'),'Facts')
        facts_text=facts_path.read_text();source_hashes[str(facts_path)]=hashlib.sha256(facts_path.read_bytes()).hexdigest()
        related=[Path(str(form).replace('賽績.md','排位表.md'))]
        pdf=facts.get_pdf_path(str(form))
        if pdf:related.append(Path(pdf))
        for related_path in related:
            if related_path.is_file():source_hashes[str(related_path)]=hashlib.sha256(related_path.read_bytes()).hexdigest()
        old_form=facts.parse_hkjc_formguide(str(form));new_form=candidate.parse_hkjc_formguide(str(form))
        old_horses={h['num']:h for h in old_form['horses']};new_horses={h['num']:h for h in new_form['horses']}
        fact_blocks={int(m.group(1)):m.group(2) for m in re.finditer(
            r'^### 馬號\s+(\d+)\s+[^\n]+\n(.*?)(?=^### 馬號\s+\d+|\Z)',facts_text,re.M|re.S)}
        race_record={'date':str(group.iloc[0].date),'meeting':str(group.iloc[0].meeting_name),'race':int(race),'rows':[]}
        for _,row in group.iterrows():
            number=int(row.horse_number);horse=logic['horses'][str(number)]
            old=old_horses.get(number);new=new_horses.get(number)
            if old is None or new is None or old['name']!=str(row.horse_name):
                raise ValueError(f'Horse alignment failed: {meeting.name} R{race} #{number}')
            text=surface_text(horse);block=fact_blocks.get(number,'')
            old_meta=metadata(RacingEngine,text);new_meta=metadata(CandidateEngine,text)
            # Current-race or future historical rows are excluded, not evaluated.
            target=pd.Timestamp(row.date).to_pydatetime()
            prior=[r for r in old['races'] if r.get('date_dt') and r['date_dt']<target]
            new_prior=[r for r in new['races'] if r.get('date_dt') and r['date_dt']<target]
            distance=int(row.distance_num)
            old_perf=facts.compute_surface_performance_shadow(prior,'沙田AWT',distance,str(row.date),old['pdf_overseas_races'])
            new_perf=candidate.compute_surface_performance_shadow(new_prior,'沙田AWT',distance,str(row.date),new['pdf_overseas_races'])
            candidate_text=candidate.format_surface_performance_shadow(new_perf)
            staged=logic_parser.parse_summary('- **個別場地性能 (Shadow):** '+candidate_text).get('surface_performance_shadow')
            if staged!=candidate_text:raise ValueError('Facts→Logic surface transport failed')
            staged_meta=metadata(CandidateEngine,staged)
            if abs(staged_meta['effective_n']-new_perf['target_effective_n'])>.051:
                raise ValueError('Target surface effective sample failed round-trip')
            counts['candidate_facts_logic_roundtrip_verified']+=1
            awt_rows=[r for r in prior if facts.normalize_venue_surface(r.get('rail',''))=='沙田AWT']
            misclassified=[r for r in awt_rows if facts.normalize_venue_surface(r['venue'])!='沙田AWT']
            counts['runners']+=1;counts['facts_shadow_present']+='個別場地性能 (Shadow)' in block
            counts['logic_shadow_present']+=bool(text);counts['metadata_sample_changed']+=old_meta['effective_n']!=new_meta['effective_n']
            counts['correct_local_sample_present']+=bool(text and new_meta['effective_n']>0)
            counts['formguide_prior_awt_rows']+=len(awt_rows);counts['misclassified_prior_awt_rows']+=len(misclassified)
            counts['runners_with_misclassified_prior_awt']+=bool(misclassified)
            counts['reconstructed_local_awt_sample_before']+=old_perf['target_effective_n']>0
            counts['reconstructed_local_awt_sample_after']+=new_perf['target_effective_n']>0
            counts['local_awt_score_changed']+=old_perf['target_score']!=new_perf['target_score']
            true_foreign=[r for r in new['pdf_overseas_races'] if r.get('Surface') in ('DIRT','SYNTHETIC')]
            counts['raw_foreign_surface_runners']+=bool(true_foreign)
            counts['valid_foreign_fallback_runners']+=new_perf['fallback_source']=='foreign_dirt_synthetic'
            # Metadata-only candidate: verify score/matrix identity on transported inputs.
            baseline=RacingEngine(deepcopy(horse),dict(logic.get('race_analysis') or {})).analyze_horse()
            fixed=CandidateEngine(deepcopy(horse),dict(logic.get('race_analysis') or {})).analyze_horse()
            identical=(baseline['ability_score']==fixed['ability_score'] and baseline['matrix_scores']==fixed['matrix_scores'])
            if not identical:raise ValueError('Metadata patch unexpectedly changes ranking scores')
            # Sectional diagnostics compare every strictly prior row independently.
            changed_sectionals=sum(a['sectionals']!=b['sectionals'] for a,b in zip(prior,new_prior))
            counts['changed_prior_sectional_profiles']+=changed_sectionals
            race_record['rows'].append({'number':number,'name':str(row.horse_name),'facts_shadow_present':'個別場地性能 (Shadow)' in block,
                'logic_shadow_present':bool(text),'old_metadata':old_meta,'correct_metadata':new_meta,
                'prior_awt_rows':len(awt_rows),'misclassified_awt_rows':len(misclassified),
                'reconstructed_surface_before':old_perf,'reconstructed_surface_after':new_perf,
                'candidate_facts_logic_evidence':candidate_text,'candidate_transport_metadata':staged_meta,
                'changed_sectional_profiles':changed_sectionals,'metadata_patch_scores_identical':identical,
                'source_identity':'formguide number and name exact; no profile merge',
                'awt_examples':[{'date':r['date'],'venue_before':r['venue'],'rail':r['rail'],'distance':r['distance'],
                                  'finish':r['finish'],'field_size':r['field_size']} for r in misclassified]})
        records.append(race_record)
        print('Traced',race_record['meeting'],'R',race,flush=True)
    output.mkdir(parents=True,exist_ok=True)
    write_patch(FACTS,FACTS_OLD,FACTS_NEW,output/'candidate_preserve_awt_surface.patch')
    write_patch(ENGINE,ENGINE_OLD,ENGINE_NEW,output/'candidate_target_surface_sample.patch')
    rel=str(FACTS.relative_to(ROOT))
    (output/'candidate_preserve_awt_rendering.patch').write_text(''.join(difflib.unified_diff(
        original_source(FACTS).splitlines(True),render_candidate_source().splitlines(True),
        fromfile='a/'+rel,tofile='b/'+rel)))
    for source,digest in source_hashes.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=digest:raise ValueError(f'Source changed during trace: {source}')
    payload={'design':{'input_only':True,'candidate_patches_applied_to_live':False,'target_outcomes_read':False,
        'history_window':'formguide-only; no profiles; dates strictly before target; fixed existing surface scorer',
        'ranking_change_evidence':'metadata-only scores verified identical; AWT parser/rendering patches NOT promoted or evaluated as model improvement',
        'quarantine_unchanged':'2026-09-09'},'counts':dict(counts),'races':len(records),'source_sha256':source_hashes,'records':records}
    (output/'trace.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(json.dumps(payload['counts'],ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();trace(args.dataset,Path(args.output))
