"""Keep rank annotations without changing the canonical six-field provenance."""
from __future__ import annotations

from copy import deepcopy
from datetime import date


RANK_REFERENCE_FIELDS = frozenset({
    'ranking_date', 'ranking_source_origin', 'ranking_date_kind',
    'ranking_selection_diagnostics',
})


def _well_formed_reference(annotations: dict, snapshot: dict) -> bool:
    stamp = annotations.get('ranking_date')
    try:
        if not isinstance(stamp,str) or date.fromisoformat(stamp).isoformat()!=stamp:
            return False
        match = snapshot.get('match_context',{}).get('match_date',{})
        match_day = match.get('value') if isinstance(match,dict) else match
        if match_day is not None and date.fromisoformat(stamp)>date.fromisoformat(match_day):
            return False
    except (TypeError,ValueError):
        return False
    return (isinstance(annotations.get('ranking_source_origin'),str)
            and bool(annotations['ranking_source_origin'].strip())
            and annotations.get('ranking_date_kind') in {'publication','historical_or_unverified_reference'}
            and ('ranking_selection_diagnostics' not in annotations
                 or isinstance(annotations['ranking_selection_diagnostics'],dict)))


def canonical_rank_references(snapshot: dict) -> dict:
    """Pure pre-pricing serialization; warnings and source clocks stay in place."""
    output = deepcopy(snapshot)
    for name in ('player_a','player_b'):
        player = output.get(name)
        if not isinstance(player,dict):
            continue
        point = player.get('current_rank')
        prov = point.get('provenance') if isinstance(point,dict) else None
        if not isinstance(prov,dict):
            continue
        annotations = {k:v for k,v in prov.items() if k in RANK_REFERENCE_FIELDS}
        if not annotations:
            continue
        # Invalid/future annotations stay in the legacy point: the unchanged
        # strict evidence validator must still reject them.
        if not _well_formed_reference(annotations,snapshot):
            continue
        existing = player.get('ranking_reference',{})
        if not isinstance(existing,dict) or any(k in existing and existing[k]!=v for k,v in annotations.items()):
            raise ValueError('conflicting ranking reference annotations')
        player['ranking_reference'] = {**existing,**annotations}
        point['provenance'] = {k:v for k,v in prov.items() if k not in RANK_REFERENCE_FIELDS}
    return output


def ranking_effective_date(snapshot: dict, path: str, prov: dict):
    """Read new annotations, while retaining legacy frozen-snapshot support."""
    if path in ('player_a.current_rank','player_b.current_rank'):
        player = snapshot.get(path.split('.')[0]) or {}
        reference = player.get('ranking_reference')
        if isinstance(reference,dict) and 'ranking_date' in reference:
            if 'ranking_date' in prov and prov['ranking_date']!=reference['ranking_date']:
                raise ValueError('conflicting ranking reference dates')
            return reference['ranking_date']
    return prov.get('ranking_date')
