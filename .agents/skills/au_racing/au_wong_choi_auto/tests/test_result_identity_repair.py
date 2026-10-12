from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from au_result_identity_repair import propose_track_identity_repairs
SCOPE=('2026-08-05','2026-09-26')
def row(track='Ipswich',pos='3'):
 return {'Date':'2026-08-07','Track':track,'Race':'6','Horse':'Cutepi','Pos':pos,'IsTrial':'0','Opaque':'unchanged'}
def link(track='Ipswich'):
 return {'key':['2026-08-07',track,'6','Cutepi'],'dated_run_track':track,'dated_run_date':'2026-08-07','dated_run_race':'6','is_trial':False,'source_sha256':'a'*64,'source_path':'verified_by_caller'}
def run(original,sources=None,links=None):
 return propose_track_identity_repairs(original,sources or [row()],links or [link()],date_scope=SCOPE)
def test_cross_venue_move_preserves_every_other_field_and_input():
 old=[row('Coffs Harbour')];before=deepcopy(old);new,audit=run(old)
 assert new==[row()] and old==before and len(audit['changes'])==1
 assert audit['availability_status']=='NOT_CERTIFIED'
def test_fill_missing_semantics_are_not_used_for_nonblank_identity():
 new,audit=run([row('Coffs Harbour')]);assert new[0]['Track']=='Ipswich'
 assert new[0]['Pos']=='3' and new[0]['Opaque']=='unchanged'
def test_mismatched_mapping_track_is_quarantined():
 source=row('Coffs Harbour');metadata=link('Coffs Harbour');metadata['dated_run_track']='Ipswich'
 original=[row('Coffs Harbour')];new,audit=run(original,[source],[metadata]);assert new==original
 assert audit['quarantined_sources'][0]['reason']=='source_track_mismatch'
def test_ambiguous_venue_does_not_choose_first_match():
 original=[row('Coffs Harbour')];new,audit=run(original,[row(),row('Taree')],[link(),link('Taree')]);assert new==original
 assert audit['conflicts'][0]['reason']=='ambiguous_dated_venues'
def test_finish_mismatch_does_not_move_identity():
 original=[row('Coffs Harbour','2')];new,audit=run(original);assert new==original
 assert audit['conflicts'][0]['reason']=='finish_label_mismatch'
def test_existing_target_is_collision_not_silent_dedup():
 original=[row('Coffs Harbour'),row()];new,audit=run(original);assert new==original
 assert audit['conflicts'][0]['reason']=='target_identity_collision'
def test_duplicate_original_is_rejected():
 with pytest.raises(ValueError,match='duplicate original'):run([row(),row()])
def test_idempotent_and_outside_scope_untouched():
 new,audit=run([row('Coffs Harbour')]);again,audit2=run(new);assert again==new and not audit2['changes']
 old=row('Coffs Harbour');old['Date']='2026-09-27';new,audit=run([old]);assert new==[old] and not audit['changes']
def test_trial_is_not_an_identity_source():
 original=[row('Coffs Harbour')];source=row();source['IsTrial']='1';new,audit=run(original,[source]);assert new==original
 assert audit['quarantined_sources'][0]['reason']=='trial_source'
def test_bad_source_hash_fails_source_admission():
 original=[row('Coffs Harbour')];metadata=link();metadata['source_sha256']='missing';new,audit=run(original,links=[metadata]);assert new==original
 assert audit['quarantined_sources'][0]['reason']=='missing_source_hash'
