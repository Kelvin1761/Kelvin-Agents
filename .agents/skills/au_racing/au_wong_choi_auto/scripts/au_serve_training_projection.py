"""Exact AU six-coefficient training projection using the production scorer.

Capture is an internal fresh-process operation. It provides algorithm equivalence,
not a source/PIT PASS; the parent serving/provenance boundary remains mandatory.
No result labels, market values or alternative shadow outputs are exported.
"""
from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import math
from au_prediction_intake import content_hash, _require


def replay_projection(projection, weights):
    from au_racing_engine.scoring import MATRIX_WEIGHTS, compose_matrix_score, compute_grade
    from au_racing_engine.renderer import ensure_verdict
    _require(projection.get('schema') == 'au-serving-training-projection/v1', 'projection_schema_changed')
    _require(set(weights) == set(MATRIX_WEIGHTS), 'projection_dimension_keys_changed')
    _require(all(type(v) in (int,float) and math.isfinite(v) and v >= 0 for v in weights.values()), 'projection_invalid_weights')
    # Production updates the registered mapping in place, preserving its key order.
    weights={k:weights[k] for k in MATRIX_WEIGHTS}
    rows = projection['rows'];roster=projection['runner_ids']
    _require(len(roster)==len(set(roster)) and set(roster)==set(rows), 'projection_runner_roster_changed')
    data={'horses':{}}
    for number in roster:
        row=rows[number]
        _require(all(type(row[k]) in (int,float) and math.isfinite(row[k]) for k in ['wet_raw','class_raw']), 'projection_nonfinite_overlay')
        matrix=row['matrix_scores']
        _require(set(MATRIX_WEIGHTS) <= set(matrix) and all(type(v) in (int,float) and math.isfinite(v) for v in matrix.values()), 'projection_invalid_matrix')
        pure=round(compose_matrix_score(matrix,weights=weights),4)
        ability=round(pure+row['wet_raw']+row['class_raw'],4)
        data['horses'][number]={'horse_name':row['horse_name'],'python_auto':{
            'ability_score':ability,'rank_score':ability,'final_rank_score':ability,
            'pure_7d_score':pure,'base_7d_score':pure,'grade':compute_grade(ability),
            'matrix_scores':deepcopy(matrix),'feature_scores':deepcopy(row['feature_scores'])}}
    verdict=ensure_verdict(data)
    return {'ability':{n:data['horses'][n]['python_auto']['ability_score'] for n in roster},
            'ranking':[str(x['horse_number']) for x in verdict['ranking']]}


def _capture_worker(payload):
    import au_auto_orchestrator as auto
    from au_racing_engine.scoring import MATRIX_WEIGHTS, wet_form_feature
    original=auto.RacingEngine;captured={}
    class CapturingEngine(original):
        def _proven_class_feature(self):
            value,detail=super()._proven_class_feature()
            self._projection_class_raw=value
            return value,detail
        def analyze_horse(self):
            result=super().analyze_horse()
            number=str(self.horse_data['horse_number'])
            captured[number]={'matrix_scores':deepcopy(result['matrix_scores']),
                              'feature_scores':deepcopy(result['feature_scores']),
                              'class_raw':self._projection_class_raw,
                              'wet_raw':wet_form_feature(self._today_going(),self.data.get('going_stats_line'))}
            return result
    auto.RacingEngine=CapturingEngine
    try:
        with redirect_stdout(sys.stderr):logic=auto.score_logic_data(Path(payload['logic_path']),payload.get('going_override'))
    finally:auto.RacingEngine=original
    roster=list(logic['horses'])
    _require(set(captured)==set(roster),'projection_capture_roster_changed')
    for number in roster:captured[number]['horse_name']=logic['horses'][number].get('horse_name','')
    projection={'schema':'au-serving-training-projection/v1','runner_ids':roster,'rows':captured}
    production={'ability':{n:logic['horses'][n]['python_auto']['ability_score'] for n in roster},
                'ranking':[str(x['horse_number']) for x in logic['python_auto_verdict']['ranking']]}
    _require(replay_projection(projection,dict(MATRIX_WEIGHTS))==production,'projection_baseline_not_exact')
    return {'projection':projection,'projection_hash':content_hash(projection),'baseline':production,
            'scope':'exact scoring projection; independent full source/PIT audit required'}


if __name__=='__main__':
    _require(sys.argv[1:]==['--worker'],'projection_worker_only_entry')
    print(json.dumps(_capture_worker(json.load(sys.stdin)),allow_nan=False))
