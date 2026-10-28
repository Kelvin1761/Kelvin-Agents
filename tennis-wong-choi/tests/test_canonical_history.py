from __future__ import annotations

from tennis_wc.features.canonical_history import select_canonical_history


def row(id,**changes):
    return {'id':id,'player_id':18,'opponent_id':85,'match_date':'2026-07-24',
            'provider_match_id':f'ATP-2026-319-{id}-loser','tournament_external_id':'2026-319',
            'tour':'ATP','round':'SF','format':'BO3','won':0,
            'source_provider':'tennismylife_history','ace_count':7.0,**changes}


def test_revision_of_match_ordinal_is_one_event_observation():
    rows=[row(552944),row(3927662)]
    result=select_canonical_history(rows)
    assert result.audit['selected_ids']==[552944]
    assert result.audit['collapsed'][0]['member_ids']==[552944,3927662]
    assert len(rows)==2


def test_known_distinct_events_rounds_dates_and_player_perspectives_are_retained():
    rows=[row(1),row(2,round='F'),row(3,tournament_external_id='2026-320'),
          row(4,match_date='2026-07-25'),row(5,player_id=85,opponent_id=18,won=1)]
    assert select_canonical_history(rows).audit['selected_ids']==[1,2,3,4,5]


def test_contradictory_source_facts_are_held_without_choosing_a_winner():
    for changed in ({'won':1},{'ace_count':8.0}):
        result=select_canonical_history([row(1),row(2,**changed)])
        assert not result.rows
        assert {x['reason'] for x in result.audit['held']}=={'source_facts_conflict'}


def test_different_provider_event_ids_are_not_silently_merged():
    rows=[row(1),row(2,source_provider='tennisexplorer',tournament_external_id='Kitzbuhel',round='R')]
    result=select_canonical_history(rows)
    assert result.audit['selected_ids']==[1]
    assert not result.audit['collapsed']
    assert result.audit['held']==[{'id':2,'reason':'unmapped_additional_observation'}]
    conflict=select_canonical_history([rows[0],{**rows[1],'won':1}])
    assert not conflict.rows


def test_unanchored_ambiguous_groups_are_held_but_known_local_events_survive():
    rows=[row(1,source_provider='test',round='unknown'),row(2,source_provider='other',round='unknown')]
    assert not select_canonical_history(rows).rows
    rows=[row(1,source_provider='test'),row(2,source_provider='test',tournament_external_id='other-event')]
    assert select_canonical_history(rows).audit['selected_ids']==[1,2]


def test_selection_is_order_preserving_and_idempotent_even_from_a_generator():
    rows=[row(3),row(1),row(2,round='F')]
    result=select_canonical_history(iter(rows))
    assert result.audit['selected_ids']==[1,2]
    assert select_canonical_history(result.rows).rows==result.rows
