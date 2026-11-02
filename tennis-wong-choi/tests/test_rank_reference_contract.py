import copy
from datetime import datetime,timezone
import json

import pytest

from tennis_wc.features.rank_reference import canonical_rank_references
from tennis_wc.features.data_quality import validate_data_freshness
from tennis_wc.research_evidence import build_prediction_artifacts
from test_stage5_research_evidence import (
    _snapshot,_pricing,_raws,_observation,_point,_projection,EVENT,CUTOFF,
)


def ranked_snapshot():
    snapshot = _snapshot()
    snapshot['match_context']['match_date'] = _point(EVENT)
    for player,rank in [('player_a',20),('player_b',30)]:
        point = _point(rank)
        point['provenance'].update(ranking_date='2026-08-31',ranking_source_origin='sackmann_ranking',
                                  ranking_date_kind='publication',
                                  ranking_selection_diagnostics={'rejected_sources':[{
                                      'rejected_raw_response_id':999,'issue':'ranking_source_date_unverified'}]})
        snapshot[player]['current_rank'] = point
        snapshot[player]['opponent_rank_buckets'] = {'TOP_25' if player=='player_b' else 'TOP_50':{
            'shrinked_win_rate':_point(.6)}}
    return snapshot


def rank_pricing():
    pricing = _pricing()
    for component in pricing['model']['components']:
        if component['name']=='opponent_rank_bucket_edge':
            component.update(active=True,probability=.6,warnings=[])
    return pricing


def build(snapshot):
    return build_prediction_artifacts(event_id=EVENT,captured_at=CUTOFF,
        observations=[_observation(snapshot,rank_pricing())],raw_responses=_raws())


def test_new_assembly_shape_passes_unchanged_writer_and_shared_v3_consumer():
    legacy = ranked_snapshot(); before=copy.deepcopy(legacy)
    with pytest.raises(ValueError,match='unverified Tennis feature point'):
        build(legacy)
    fixed = canonical_rank_references(legacy)
    assert legacy == before
    assert canonical_rank_references(fixed) == fixed
    for player in ['player_a','player_b']:
        point = fixed[player]['current_rank']
        assert set(point['provenance']) == set(_point(1)['provenance'])
        restored = {**point['provenance'],**fixed[player]['ranking_reference']}
        assert restored == legacy[player]['current_rank']['provenance']
    artifacts = build(fixed)
    name = f'Tennis_Feature_Evidence_{EVENT}.json'
    projection,blockers = _projection(artifacts[name],event_id=EVENT,cutoff=CUTOFF,
        recommendations={101:{'id':101,'edge':.08}},
        raw_artifacts={n:b for n,b in artifacts.items() if n.startswith('Tennis_Raw_Evidence_')})
    assert blockers == set()
    assert projection['rows'][0]['verified'] is True
    payload=json.loads(artifacts[name])
    assert payload['rows'][0]['raw_input_ids'] == [901,902]
    assert payload['rows'][0]['feature_snapshot']['player_a']['ranking_reference']==fixed['player_a']['ranking_reference']


@pytest.mark.parametrize('fault',['warning','future_source','future_calculation','wrong_raw','unknown_extra',
                                  'bad_date','future_date','missing_origin','bad_kind'])
def test_normalization_cannot_clear_existing_rejections(fault):
    snapshot = ranked_snapshot()
    prov = snapshot['player_a']['current_rank']['provenance']
    if fault=='warning':prov['warnings']=['ranking_source_date_unverified']
    elif fault=='future_source':prov['source_timestamp']='2030-01-01T00:00:00Z'
    elif fault=='future_calculation':prov['calculated_at']='2030-01-01T00:00:00Z'
    elif fault=='wrong_raw':prov['raw_response_id']=902
    elif fault=='unknown_extra':prov['invented_safe_flag']=True
    elif fault=='bad_date':prov['ranking_date']='bad'
    elif fault=='future_date':prov['ranking_date']='2030-01-01'
    elif fault=='missing_origin':prov['ranking_source_origin']=None
    elif fault=='bad_kind':prov['ranking_date_kind']='invented'
    with pytest.raises(ValueError):build(canonical_rank_references(snapshot))


@pytest.mark.parametrize('effective',['2020-01-01','2026-08-31',None,'bad'])
def test_freshness_preserves_legacy_effective_date_and_all_quality_outputs(monkeypatch,effective):
    from tennis_wc.features import data_quality as dq
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2026,9,1,0,tzinfo=timezone.utc)
    monkeypatch.setattr(dq,'datetime',Clock)
    legacy=ranked_snapshot()
    legacy['player_a']['current_rank']['provenance']['ranking_date']=effective
    fixed=canonical_rank_references(legacy)
    assert validate_data_freshness(fixed)==validate_data_freshness(legacy)


def test_conflicting_annotations_are_not_silently_overwritten():
    snapshot=ranked_snapshot()
    snapshot['player_a']['ranking_reference']={'ranking_date':'2026-08-01'}
    with pytest.raises(ValueError,match='conflicting'):
        canonical_rank_references(snapshot)
    with pytest.raises(ValueError,match='conflicting'):
        validate_data_freshness(snapshot)


def test_full_assembly_emits_the_canonical_point_and_keeps_annotations(tmp_path,monkeypatch):
    from contextlib import closing
    from conftest import configure_test_db
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db
    from tennis_wc.ingestion.ingest_matches import ingest_upcoming_matches
    from tennis_wc.ingestion.ingest_odds import ingest_odds
    from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments
    from tennis_wc.features import feature_builder as fb
    configure_test_db(tmp_path,monkeypatch);init_db()
    ingest_tournaments('2026-05-08','2026-05-08')
    ingest_upcoming_matches('2026-05-08');ingest_odds('2026-05-08')
    with closing(get_connection()) as conn:
        mid=conn.execute('SELECT id FROM matches LIMIT 1').fetchone()[0]
    monkeypatch.setattr(fb,'_rank_details',lambda conn,pid,day,player,**kwargs: {
        'rank':42,'raw_response_id':player['raw_response_id'],'ranking_date':'2026-05-01',
        'source_provider':'sackmann_ranking','warnings':[]})
    snapshot=fb.assemble_match_feature_snapshot(mid)[0]
    for name in ['player_a','player_b']:
        assert snapshot[name]['current_rank']['value']==42
        assert set(snapshot[name]['current_rank']['provenance'])==set(_point(1)['provenance'])
        assert snapshot[name]['ranking_reference']=={
            'ranking_date':'2026-05-01','ranking_source_origin':'sackmann_ranking','ranking_date_kind':'publication'}
