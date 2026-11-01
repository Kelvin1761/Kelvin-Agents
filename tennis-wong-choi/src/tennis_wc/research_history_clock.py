"""Last recorded history states before a cutoff, never runtime/PIT certification.

Only immutable observation after-images may supply values. Current mutable
history rows, tournament dates, legacy before-images and restored created_at
values cannot establish earlier availability. This research projector has no
live pricing caller and does not validate source publication or person identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json


POLICY = 'recorded-history-clock-v1'


@dataclass(frozen=True)
class ClockSelection:
    rows: list[dict]
    held: dict[int, str]
    observed_at: dict[int, str]
    qualification: str = 'LAST_RECORDED_STATE_NOT_RUNTIME_PARITY'


def _time(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('an explicit timezone is required')
    return parsed.astimezone(timezone.utc)


def _snapshot(value):
    if not isinstance(value, dict) or type(value.get('id')) is not int:
        raise ValueError('invalid history after-image')
    required = ('player_id', 'opponent_id', 'history_status', 'created_at', 'match_date')
    if any(k not in value for k in required):
        raise ValueError('incomplete history after-image')
    if type(value['player_id']) is not int or type(value['opponent_id']) is not int:
        raise ValueError('invalid player IDs')
    date.fromisoformat(value['match_date'])
    return dict(value)


def _batch(payload, rolled_back):
    if not isinstance(payload, dict):
        raise ValueError('invalid batch payload')
    active_key, retired_key = ('restored', 'new_retired') if rolled_back else ('new', 'retired')
    active = [_snapshot(r) for r in payload[active_key]]
    retired = [_snapshot(r) for r in payload[retired_key]]
    if (len(active) != 2 or len(retired) != 2
            or len({r['id'] for r in active+retired}) != 4
            or any(r['history_status'] != 'ACTIVE' for r in active)
            or any(r['history_status'] != 'SUPERSEDED' for r in retired)
            or active[0]['player_id'] != active[1]['opponent_id']
            or active[1]['player_id'] != active[0]['opponent_id']):
        raise ValueError('invalid paired repair after-images')
    return active+retired


def select_recorded_history(observations, cutoff, *, known_history_ids=()):
    """Project recorded values using strict observed_at < cutoff.

    Missing observations remain held; snapshots are not enriched from today's
    mutable DB. Return only ACTIVE recorded states dated before the cutoff day.
    This is a source for further qualification, not a qualified training corpus.
    """
    limit = _time(cutoff)
    known = set(known_history_ids)
    state, clocks, held, previous = {}, {}, {}, {}
    selected_events, malformed = [], set()
    for item in observations:
        event = dict(item)
        hid = event.get('history_id')
        if type(hid) is not int:
            raise ValueError('observation has no valid history_id')
        known.add(hid)
        try:
            when = _time(event.get('observed_at'))
        except (ValueError, TypeError, OverflowError):
            malformed.add(hid)
            continue
        if when < limit:
            if type(event.get('id')) is not int:
                malformed.add(hid)
            else:
                selected_events.append((event['id'], when, event))
    ids = [item[0] for item in selected_events]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate observation IDs')
    for _, when, event in sorted(selected_events, key=lambda item: item[0]):
        hid, kind = event['history_id'], event.get('observation_kind')
        affected = {hid}
        backdated = hid in previous and when < previous[hid]
        try:
            payload = event['payload_json']
            payload = json.loads(payload) if isinstance(payload, str) else payload
            if kind == 'CREATED':
                snapshots = [_snapshot(payload)]
                if snapshots[0]['id'] != hid or hid in state:
                    raise ValueError('contradictory/misattributed creation')
            elif kind in {'IDENTITY_SPLIT_APPLIED', 'IDENTITY_SPLIT_ROLLED_BACK'}:
                if isinstance(payload, dict):
                    for key in ('new','retired','restored','new_retired'):
                        for row in payload.get(key, []):
                            if isinstance(row, dict) and type(row.get('id')) is int:
                                affected.add(row['id'])
                snapshots = _batch(payload, kind == 'IDENTITY_SPLIT_ROLLED_BACK')
                if hid not in {r['id'] for r in snapshots}:
                    raise ValueError('batch receipt history_id disagrees')
                # Receipt and all after-images share the transaction's clock.
                if _time(payload['observed_at']) != when:
                    raise ValueError('batch receipt clock disagrees')
            elif kind == 'SOURCE_REFERENCE_CHANGED':
                snapshot = _snapshot(payload)
                if snapshot['id'] != hid or hid not in state:
                    raise ValueError('reference change lacks a prior creation')
                snapshot.pop('new_source_match_ref', None)
                snapshot['source_match_ref'] = payload['new_source_match_ref']
                snapshots = [snapshot]
            else:
                # Legacy/supersession before-images do not establish earlier
                # availability. Pending split/link/restore receipts need the
                # final batch after-image; unknown kinds fail closed as well.
                held[hid] = ('BEFORE_IMAGE_OR_PENDING_CHANGE' if kind in {
                    'SUPERSEDED','LEGACY_CAPTURE','LEGACY_SOURCE_CONTEXT_HOLD',
                    'IDENTITY_SPLIT_BEFORE','IDENTITY_SPLIT_LINKED',
                    'IDENTITY_SPLIT_ROLLBACK_BEFORE','IDENTITY_SPLIT_RESTORED',
                } else 'UNSUPPORTED_OBSERVATION_KIND')
                if backdated:
                    malformed.add(hid)
                previous[hid] = when
                continue
            # Validate the entire batch before publishing any member state.
            if backdated:
                raise ValueError('observation clock moved backwards')
            for snapshot in snapshots:
                sid = snapshot['id']
                if _time(snapshot['created_at']) > when or when < previous.get(sid, when):
                    raise ValueError('after-image clock is inconsistent')
            for snapshot in snapshots:
                sid = snapshot['id']
                known.add(sid)
                state[sid] = snapshot
                previous[sid] = when
                clocks[sid] = when.isoformat()
                held.pop(sid, None)
        except (ValueError, TypeError, KeyError, OverflowError):
            malformed.update(affected)
            known.update(affected)
    for hid in malformed:
        held[hid] = 'INVALID_OBSERVATION_OR_CLOCK'
    rows = []
    for hid in sorted(known):
        snapshot = state.get(hid)
        if hid in held:
            continue
        if snapshot is None:
            held[hid] = 'NO_AFTER_IMAGE_BEFORE_CUTOFF'
        elif snapshot['history_status'] != 'ACTIVE':
            held[hid] = 'RECORDED_STATE_INACTIVE'
        elif snapshot['player_id'] == snapshot['opponent_id']:
            held[hid] = 'SELF_PAIR'
        elif str(snapshot['match_date']) >= limit.date().isoformat():
            held[hid] = 'MATCH_NOT_BEFORE_CUTOFF_DAY'
        else:
            rows.append(snapshot)
    return ClockSelection(rows, held, clocks)
