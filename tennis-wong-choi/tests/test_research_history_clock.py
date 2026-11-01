from copy import deepcopy
import json

import pytest

from tennis_wc.research_history_clock import select_recorded_history


def row(hid=1, player=1, opponent=2, status='ACTIVE', created='2026-10-27T10:00:00Z'):
    return dict(id=hid,player_id=player,opponent_id=opponent,history_status=status,
                created_at=created,match_date='2021-01-01',hold_rate=0.8)


def event(oid,hid,kind,payload,when='2026-10-27T10:00:00Z'):
    return dict(id=oid,history_id=hid,observation_kind=kind,observed_at=when,
                payload_json=json.dumps(payload))


def test_old_match_and_created_at_are_not_observation_clocks():
    e=event(1,1,'CREATED',row(created='2021-01-01T00:00:00Z'))
    r=select_recorded_history([e],'2025-01-01T00:00:00Z',known_history_ids=[1,2])
    assert r.rows==[]
    assert r.held=={1:'NO_AFTER_IMAGE_BEFORE_CUTOFF',2:'NO_AFTER_IMAGE_BEFORE_CUTOFF'}


@pytest.mark.parametrize('cutoff,expected',[
    ('2026-10-27T09:59:59Z',0),('2026-10-27T10:00:00Z',0),
    ('2026-10-27T18:00:00+08:00',0),('2026-10-27T10:00:01Z',1),
])
def test_strict_cutoff_and_timezones(cutoff,expected):
    result=select_recorded_history([event(1,1,'CREATED',row())],cutoff)
    assert len(result.rows)==expected


def test_snapshot_is_not_enriched_from_mutable_values():
    snapshot=row();snapshot.pop('hold_rate')
    r=select_recorded_history([event(1,1,'CREATED',snapshot)],'2026-11-01T00:00:00Z')
    assert r.rows==[snapshot]
    assert 'hold_rate' not in r.rows[0]
    assert r.qualification=='LAST_RECORDED_STATE_NOT_RUNTIME_PARITY'


def test_future_valid_and_malformed_payloads_do_not_change_past_rows():
    first=event(1,1,'CREATED',row())
    future=event(2,1,'UNRECOGNISED',None,'2027-01-01T00:00:00Z')
    future['payload_json']='bad json'
    before=select_recorded_history([first],'2026-11-01T00:00:00Z')
    after=select_recorded_history([first,future],'2026-11-01T00:00:00Z')
    assert after.rows==before.rows and after.observed_at==before.observed_at


@pytest.mark.parametrize('kind',['LEGACY_CAPTURE','SUPERSEDED','LEGACY_SOURCE_CONTEXT_HOLD',
    'IDENTITY_SPLIT_BEFORE','IDENTITY_SPLIT_LINKED','IDENTITY_SPLIT_ROLLBACK_BEFORE','IDENTITY_SPLIT_RESTORED'])
def test_before_images_and_pending_changes_are_not_after_images(kind):
    first=event(1,1,'CREATED',row())
    pending=event(2,1,kind,row(),when='2026-10-28T10:00:00Z')
    assert len(select_recorded_history([first,pending],'2026-10-28T00:00:00Z').rows)==1
    r=select_recorded_history([first,pending],'2026-10-29T00:00:00Z')
    assert r.rows==[] and r.held[1]=='BEFORE_IMAGE_OR_PENDING_CHANGE'
    assert select_recorded_history([pending],'2026-10-27T00:00:00Z').rows==[]


def batches():
    old=[row(1,1,2,created='2021-01-01T00:00:00Z'),row(2,2,1,created='2021-01-01T00:00:00Z')]
    retired=[{**r,'history_status':'SUPERSEDED'} for r in old]
    new=[row(3,3,2,created='2026-10-28T10:00:00Z'),row(4,2,3,created='2026-10-28T10:00:00Z')]
    applied=dict(old=old,retired=retired,new=new,observed_at='2026-10-28T10:00:00Z')
    rolled=dict(old=old,restored=old,new_retired=[{**r,'history_status':'SUPERSEDED'} for r in new],observed_at='2026-10-29T10:00:00Z')
    return old,new,applied,rolled


def test_split_and_rollback_do_not_backfill_identity_availability():
    old,new,applied,rolled=batches()
    events=[event(1,1,'CREATED',old[0]),event(2,2,'CREATED',old[1]),
            event(3,1,'IDENTITY_SPLIT_APPLIED',applied,'2026-10-28T10:00:00Z'),
            event(4,1,'IDENTITY_SPLIT_ROLLED_BACK',rolled,'2026-10-29T10:00:00Z')]
    assert select_recorded_history(events,'2025-01-01T00:00:00Z').rows==[]
    assert select_recorded_history(events,'2026-10-28T00:00:00Z').rows==old
    assert select_recorded_history(events,'2026-10-29T00:00:00Z').rows==new
    r=select_recorded_history(events,'2026-10-30T00:00:00Z')
    assert r.rows==old
    assert r.observed_at[1]==r.observed_at[2]=='2026-10-29T10:00:00+00:00'


def test_bad_batch_is_atomic_and_holds_all_recognised_members():
    old,new,applied,_=batches()
    applied=deepcopy(applied);applied['new'][1]['created_at']='2028-01-01T00:00:00Z'
    events=[event(1,1,'CREATED',old[0]),event(2,2,'CREATED',old[1]),
            event(3,1,'IDENTITY_SPLIT_APPLIED',applied,'2026-10-28T10:00:00Z')]
    r=select_recorded_history(events,'2026-10-29T00:00:00Z')
    assert r.rows==[]
    assert set(r.held)=={1,2,3,4}
    assert set(r.held.values())=={'INVALID_OBSERVATION_OR_CLOCK'}


@pytest.mark.parametrize('changed',['naive_time','bad_json','wrong_id','future_created','bad_date','backdated'])
def test_invalid_clock_or_payload_is_held(changed):
    first=event(1,1,'CREATED',row())
    if changed=='naive_time':first['observed_at']='2026-10-27T10:00:00'
    elif changed=='bad_json':first['payload_json']='invalid'
    elif changed=='wrong_id':first['payload_json']=json.dumps(row(2))
    elif changed=='future_created':first['payload_json']=json.dumps(row(created='2027-01-01T00:00:00Z'))
    elif changed=='bad_date':
        value=row();value['match_date']='bad';first['payload_json']=json.dumps(value)
    events=[first]
    if changed=='backdated':events.append(event(2,1,'SOURCE_REFERENCE_CHANGED',{**row(),'new_source_match_ref':'new'},'2026-10-26T10:00:00Z'))
    r=select_recorded_history(events,'2026-11-01T00:00:00Z')
    assert r.rows==[] and r.held[1]=='INVALID_OBSERVATION_OR_CLOCK'


def test_duplicate_observation_ids_and_naive_cutoff_raise():
    e=event(1,1,'CREATED',row())
    with pytest.raises(ValueError,match='duplicate'):select_recorded_history([e,e],'2026-11-01T00:00:00Z')
    with pytest.raises(ValueError,match='timezone'):select_recorded_history([e],'2026-11-01')


def test_contradictory_creations_and_unknown_kinds_fail_closed():
    first=event(1,1,'CREATED',row())
    for second in [event(2,1,'CREATED',{**row(),'hold_rate':0.9}),event(2,1,'UNKNOWN',{})]:
        r=select_recorded_history([first,second],'2026-11-01T00:00:00Z')
        assert not r.rows and 1 in r.held


def test_reference_after_image_requires_known_creation():
    snapshot={**row(),'source_match_ref':'old','new_source_match_ref':'new'}
    changed=event(2,1,'SOURCE_REFERENCE_CHANGED',snapshot,'2026-10-28T10:00:00Z')
    assert not select_recorded_history([changed],'2026-11-01T00:00:00Z').rows
    r=select_recorded_history([event(1,1,'CREATED',row()),changed],'2026-11-01T00:00:00Z')
    assert r.rows[0]['source_match_ref']=='new'
    assert 'new_source_match_ref' not in r.rows[0]


@pytest.mark.parametrize('snapshot,reason',[
    ({**row(),'history_status':'DISPUTED'},'RECORDED_STATE_INACTIVE'),
    ({**row(),'player_id':2},'SELF_PAIR'),
    ({**row(),'match_date':'2026-11-01'},'MATCH_NOT_BEFORE_CUTOFF_DAY'),
])
def test_noneligible_recorded_states_are_reported(snapshot,reason):
    r=select_recorded_history([event(1,1,'CREATED',snapshot)],'2026-11-01T00:00:00Z')
    assert r.rows==[] and r.held[1]==reason
