import copy
import json
import re
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
for path in (REPO, REPO / '.agents/skills/hkjc_racing/hkjc_reflector/scripts', REPO / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts', REPO / '.agents/skills/shared_racing'):
    sys.path.insert(0, str(path))
import hkjc_auto_orchestrator as orch
from eval_metrics import race_metrics
from hkjc_racing_engine import scoring
from hkjc_racing_engine.engine_core import RacingEngine
from model_evaluation_decision import evaluate_full_record
METRICS = ('gold', 'good_positional', 'top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5', 'mean_top3_model_rank')


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]

def integer(value):
    m = re.search(r'\d+', str(value or ''))
    return int(m.group()) if m else 0

def field_bucket(n):
    return 'le8' if n <= 8 else '9_10' if n <= 10 else '11_12' if n <= 12 else '13plus'

def identity(ctx):
    v = str(ctx.get('venue') or ctx.get('course') or ctx.get('racecourse') or '')
    low = v.lower().replace(' ', '')
    venue = '沙田' if '沙田' in v or 'shatin' in low or v == 'ST' else (
        '跑馬地' if '跑馬地' in v or 'happyvalley' in low or v == 'HV' else '')
    text = ' '.join(str(ctx.get(k) or '') for k in ('venue', 'track', 'surface', 'track_type')).upper()
    track = 'AWT' if any(x in text for x in ('AWT', 'DIRT', '泥', '全天候', 'ALL WEATHER')) else 'Turf'
    return venue, track, integer(ctx.get('distance'))

def prepare(ev):
    horses = {}
    for number, rec in ev['horses'].items():
        horse = copy.deepcopy(rec['input'])
        auto = copy.deepcopy(rec['auto'])
        robust = auto.get('race_shape_robustness') or {}
        if 'base_race_shape' in robust:
            auto['matrix_scores']['race_shape'] = robust['base_race_shape']
        horse['python_auto'] = auto
        horses[number] = horse
    return horses

def score(horses):
    for horse in horses.values():
        auto = horse['python_auto']
        raw = round(RacingEngine(horse, {})._ability_score(auto['matrix_scores']), 2)
        auto.update(ability_score_raw=raw, ability_score=round(scoring.to_display_scale(raw), 2))
        auto['grade'] = scoring.compute_grade(auto['ability_score'])
        auto.pop('sip_flags', None)
    orch._apply_sip_enhancements(horses)
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(horses)
    return horses

def ranked(horses):
    return [int(n) for n in sorted(horses, key=lambda n: (-horses[n]['python_auto']['ability_score_raw'], int(n)))]

def row_for(base, horses, arm):
    picks = ranked(horses)
    pos = {h['n']: h['pos'] for h in base['horses'] if h.get('pos')}
    metrics = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
    metrics['mean_top3_model_rank'] = metrics.get('top3_mean_model_rank')
    return {**{k: v for k, v in base.items() if k != 'horses'},
            **{k: metrics.get(k) for k in METRICS}, 'picks': picks, 'arm': arm}

def screen(base, candidate, mode):
    return evaluate_full_record(domain='hkjc', mode=mode, dates=[r['date'] for r in base],
                                baseline_rows=base, candidate_rows=candidate,
                                leakage_audit_passed=True, ranking_metrics=METRICS[2:])
