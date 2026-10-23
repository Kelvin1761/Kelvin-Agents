"""Point-in-time evidence for NBA feature datasets, independent of outcomes."""
from __future__ import annotations
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timestamp(value, *, legacy_sydney=False):
    try:parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except (ValueError,TypeError):return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo('Australia/Sydney')) if legacy_sydney else None
    return parsed


def game_day(meta):
    tip=timestamp(meta.get('date'))
    return tip.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat() if tip else ''


def log_day(value):
    text=str(value).strip()
    try:return datetime.strptime(text.title(),'%b %d, %Y').date() if ',' in text else datetime.fromisoformat(text[:10]).date()
    except (ValueError,TypeError):return None


def snapshot_provenance(game_path,odds_path,tip):
    game_path,odds_path=Path(game_path),Path(odds_path)
    if not tip:return None
    candidates=[game_path.parent/'manifest.json',*sorted(game_path.parent.glob('_prediction_snapshots/*/manifest.json'))]
    for path in candidates:
        if not path.is_file():continue
        try:
            data=json.loads(path.read_text());captured=timestamp(data.get('created_at'))
            files={row['name']:row for row in data['files']}
            if (not captured or captured>=tip or data.get('sport')!='nba'
                    or files[game_path.name]['sha256']!=sha(game_path)
                    or files[odds_path.name]['sha256']!=sha(odds_path)):continue
            return {'game_modified_at':captured.isoformat(),'odds_modified_at':captured.isoformat(),
                    'manifest_path':str(path),'manifest_sha256':sha(path),'kind':'immutable_prediction_snapshot'}
        except (OSError,ValueError,KeyError,TypeError):continue
    return None


def validate_capture(payload,game_path,odds_path=None,provenance=None):
    meta=payload.get('meta') or {};tip=timestamp(meta.get('date'));day=game_day(meta);flags=[]
    captured=timestamp(meta.get('extracted_at'),legacy_sydney=True)
    if not tip:flags.append('event_tip_unknown_or_naive')
    if not captured or not tip or captured>=tip:flags.append('feature_capture_not_verified_pre_tip')
    if not day:flags.append('US_game_day_unknown')
    if provenance is None and odds_path is not None:provenance=snapshot_provenance(game_path,odds_path,tip)
    if not provenance:flags.append('immutable_or_independent_source_provenance_missing')
    else:
        for key in ('game_modified_at','odds_modified_at'):
            source_time=timestamp(provenance.get(key))
            if not source_time or not tip or source_time>=tip:flags.append(key+'_not_pre_tip')
    for players in payload.get('players',{}).values():
        for player in players:
            gl=player.get('gamelog') or {};dates=gl.get('l10_dates') or []
            # Missing histories are excluded per player, never fabricated.
            if not any(gl.get(stat) for stat in ('PTS','REB','AST','FG3M')):continue
            parsed=[log_day(value) for value in dates]
            if not dates or any(value is None for value in parsed):flags.append('history_dates_missing_or_invalid');continue
            if day and any(value.isoformat()>=day for value in parsed):flags.append('target_or_future_game_in_history')
            if any(gl.get(stat) and len(gl[stat])!=len(dates) for stat in ('PTS','REB','AST','FG3M')):flags.append('history_date_alignment_invalid')
    return {'pit_status':'verified' if not flags else 'unverified','pit_flags':sorted(set(flags)),
            'game_date':day,'event_start':tip.isoformat() if tip else None,
            'captured_at':captured.isoformat() if captured else None,'provenance':provenance}


def capture_order(row):
    """Earliest independently evidenced market snapshot, across UTC offsets."""
    provenance=row.get('source_provenance')
    if isinstance(provenance,str):provenance=json.loads(provenance)
    provenance=provenance or {}
    captured=timestamp(row.get('captured_at'))
    market=timestamp(provenance.get('odds_modified_at')) or captured
    return (row.get('pit_status')!='verified',market.timestamp() if market else float('inf'),
            captured.timestamp() if captured else float('inf'),row.get('source_game_path') or '')
