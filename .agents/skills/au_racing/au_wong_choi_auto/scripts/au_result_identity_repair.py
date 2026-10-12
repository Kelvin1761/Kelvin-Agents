"""Explicit dated-source identity repair, separate from fill-missing.

Pure proposal: caller must verify source asset bytes before/after and retain the
input baseline. Never certifies historical availability or rewrites production.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import date
import re
from au_dated_results_repair import key,track_key,horse_key


def _position(value):
    try:
        x=float(value)
        return int(x) if x>0 and x.is_integer() else None
    except (ValueError,TypeError,OverflowError):
        return None


def propose_track_identity_repairs(original,sources,lineage,*,date_scope):
    start,end=date_scope
    date.fromisoformat(start);date.fromisoformat(end)
    if start>end:raise ValueError('invalid date scope')
    if any(n>1 for n in Counter(key(r) for r in original).values()):
        raise ValueError('duplicate original identity')
    links={}
    for link in lineage:
        raw=link.get('key')
        if not isinstance(raw,(list,tuple)) or len(raw)!=4:raise ValueError('missing lineage identity')
        identity=(str(raw[0]),track_key(raw[1]),str(raw[2]),horse_key(raw[3]))
        if identity in links:raise ValueError('duplicate lineage identity')
        links[identity]=link
    if set(links)!={key(r) for r in sources}:raise ValueError('source/lineage mismatch')
    source_counts=Counter(key(r) for r in sources);lookup=defaultdict(list);quarantined=[]
    for row in sources:
        identity=key(row);link=links[identity]
        if not start<=identity[0]<=end:continue
        reason=None
        if source_counts[identity]!=1:reason='duplicate_source_identity'
        elif row.get('IsTrial')!='0' or link.get('is_trial'):reason='trial_source'
        elif not identity[1] or track_key(link.get('dated_run_track'))!=identity[1]:reason='source_track_mismatch'
        elif str(link.get('dated_run_date'))!=identity[0] or str(link.get('dated_run_race'))!=identity[2]:reason='source_date_race_mismatch'
        elif not re.fullmatch('[0-9a-f]{64}',str(link.get('source_sha256') or '')):reason='missing_source_hash'
        elif _position(row.get('Pos')) is None:reason='invalid_source_position'
        if reason:quarantined.append({'key':identity,'reason':reason});continue
        lookup[(identity[0],identity[2],identity[3])].append((row,link))
    proposed=[];conflicts=[];candidate=deepcopy(original)
    for i,row in enumerate(original):
        identity=key(row)
        if not start<=identity[0]<=end:continue
        matches=lookup.get((identity[0],identity[2],identity[3]),[])
        if not matches:continue
        venues={track_key(source['Track']) for source,link in matches}
        if len(venues)!=1:
            conflicts.append({'row':i,'key':identity,'reason':'ambiguous_dated_venues'});continue
        source,link=matches[0]
        if track_key(source['Track'])==identity[1]:continue
        if _position(row.get('Pos')) is None or _position(row['Pos'])!=_position(source['Pos']):
            conflicts.append({'row':i,'key':identity,'reason':'finish_label_mismatch'});continue
        candidate[i]['Track']=source['Track']
        proposed.append({'row':i,'before_key':identity,'after_key':key(candidate[i]),'before_track':row['Track'],'after_track':source['Track'],'source_path':link.get('source_path'),'source_sha256':link['source_sha256'],'usage':'retrospective_result_identity_only_not_PIT'})
    # Collisions never silently merge/drop runners; revert each involved proposal.
    counts=Counter(key(r) for r in candidate);accepted=[]
    for change in proposed:
        if counts[tuple(change['after_key'])]>1:
            candidate[change['row']]=deepcopy(original[change['row']])
            conflicts.append({'row':change['row'],'key':change['before_key'],'reason':'target_identity_collision'})
        else:accepted.append(change)
    if any(n>1 for n in Counter(key(r) for r in candidate).values()):raise ValueError('unresolved identity collision')
    return candidate,{'changes':accepted,'conflicts':conflicts,'quarantined_sources':quarantined,'availability_status':'NOT_CERTIFIED','limits':'Only Track may change; requires caller asset verification, retained input, and independent label/PIT admission.'}
