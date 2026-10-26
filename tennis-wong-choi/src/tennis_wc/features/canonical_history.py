"""Conservative event observations; raw rows are retained outside this reader."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from tennis_wc.features.history_values import RATE_FIELDS, COUNT_FIELDS
from tennis_wc.features.round_labels import normalise_round

POLICY = 'history-canonical-v1'
PUBLIC_PROVIDERS = {'jeff_sackmann', 'tennismylife_history'}
KNOCKOUT_ROUNDS = {'F','SF','QF','R16','R32','R64','R128','Q1','Q2','Q3'}


@dataclass(frozen=True)
class HistorySelection:
    rows: list[dict]
    audit: dict


def _anchor(row):
    event = str(row.get('tournament_external_id') or '').strip()
    stage = normalise_round(row.get('round'))
    if row.get('source_provider') in PUBLIC_PROVIDERS and event and stage in KNOCKOUT_ROUNDS:
        return (row.get('tour'),event,stage,row.get('format'))
    return None


def _contradiction(rows):
    fields = ('won',*RATE_FIELDS,*COUNT_FIELDS)
    return any(len({r.get(field) for r in rows if r.get(field) is not None})>1 for field in fields)


def select_canonical_history(rows) -> HistorySelection:
    """Call after causal filtering. Unknown identity never becomes a merge."""
    rows = [dict(row) for row in rows]
    groups = defaultdict(list)
    for row in rows:
        groups[(row['player_id'],row.get('opponent_id'),row['match_date'])].append(row)
    selected, held, collapsed = [], [], []
    for key, members in groups.items():
        if key[0] == key[1]:
            held.extend({'id':r['id'],'reason':'self_pair'} for r in members)
            continue
        if len(members)==1:
            selected.extend(members)
            continue
        anchored, unknown = defaultdict(list), []
        for row in members:
            anchor = _anchor(row)
            if anchor is None:
                unknown.append(row)
            else:
                anchored[anchor].append(row)
        if not anchored:
            # Provider-local identities are comparable only inside that provider.
            providers = {r.get('source_provider') for r in members}
            local = all(str(r.get('tournament_external_id') or '').strip()
                        and normalise_round(r.get('round')) in KNOCKOUT_ROUNDS for r in members)
            if len(providers)==1 and local:
                unknown = []
                for row in members:
                    anchor = (row.get('tour'),row['tournament_external_id'],
                              normalise_round(row.get('round')),row.get('format'))
                    anchored[anchor].append(row)
            else:
                held.extend({'id':r['id'],'reason':'event_identity_unverified'} for r in members)
                continue
        for anchor, observations in anchored.items():
            # A conflicting unmapped outcome could belong to this event.
            # Different fully identified events are not conflated.
            possible = unknown if len(anchored)==1 else []
            outcome_conflict = any(r.get('won') is not None and r.get('won')!=observations[0].get('won') for r in possible)
            if _contradiction(observations) or outcome_conflict:
                held.extend({'id':r['id'],'reason':'source_facts_conflict'} for r in observations)
                continue
            first = min(observations,key=lambda r:r['id'])
            selected.append(first)
            if len(observations)>1:
                collapsed.append({'selected_id':first['id'],'member_ids':sorted(r['id'] for r in observations),
                                  'anchor':list(anchor)})
        held.extend({'id':r['id'],'reason':'unmapped_additional_observation'} for r in unknown)
    # Preserve chronological/query ordering for consumers that apply a window.
    chosen={row['id'] for row in selected}
    ordered=[dict(row) for row in rows if row['id'] in chosen]
    return HistorySelection(ordered,{'policy':POLICY,'selected_ids':[r['id'] for r in ordered],
                                    'held':held,'collapsed':collapsed})
