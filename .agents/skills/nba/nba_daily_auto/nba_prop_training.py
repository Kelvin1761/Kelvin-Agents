"""Forward-only prop inputs and separate Final targets. Never produces a bet or probability."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr

CONTRACT = 'nba-prop-training/v1'
STAT = {'pts': 'PTS', 'reb': 'REB', 'ast': 'AST', 'fg3m': 'FG3M'}
NY = ZoneInfo('America/New_York')


def at(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _snapshot_source(snapshot, manifest, tag, tip, tip_source):
    """Only load bytes explicitly bound by the scheduler's native manifest."""
    name = f'nba_game_data_{tag}.json'
    if tip_source != 'official_schedule':
        return {'status': 'official_schedule_missing'}
    cutoff = at(manifest.get('created_at'))
    if not tip or not cutoff or cutoff >= tip:
        return {'status': 'snapshot_not_pretip'}
    records = [r for r in manifest.get('files', []) if isinstance(r, dict) and r.get('name') == name]
    if len(records) != 1 or tag not in manifest.get('game_tags', []):
        return {'status': 'game_not_manifest_bound'}
    try:
        raw = (Path(snapshot) / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != records[0].get('sha256'):
            return {'status': 'game_hash_mismatch'}
        game = json.loads(raw)
        meta = game['meta']
        source_tag = '_'.join(canonical_team_abbr(meta[s]['abbr']) for s in ('away', 'home'))
        if source_tag != tag or at(meta.get('date')) != tip:
            return {'status': 'official_game_identity_mismatch'}
        return {'status': 'bound', 'game': game, 'artifact': name,
                'sha256': records[0]['sha256'], 'available_at': cutoff.isoformat(), 'tip_off': tip.isoformat(),
                'tip_source': tip_source}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'game_unreadable'}


def snapshot_source(snapshot, manifest, tag, tip, *, tip_source=None):
    try:
        return _snapshot_source(snapshot, manifest, tag, tip, tip_source)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {'status': 'snapshot_source_error'}


def _observation(source, leg):
    result = {'contract': CONTRACT, 'status': source['status'], 'training_ready': False}
    if source['status'] != 'bound':
        return result
    stat = STAT.get(leg.get('market'))
    line = number(leg.get('line'))
    if not stat or not line or line < 1 or not line.is_integer() or leg.get('side', 'over') != 'over':
        return dict(result, status='unsupported_milestone')
    team = canonical_team_abbr(str(leg.get('team') or ''))
    matches = [p for key, players in source['game'].get('players', {}).items()
               if canonical_team_abbr(key) == team and isinstance(players, list)
               for p in players if isinstance(p, dict)
               and player_name_key(p.get('name', '')) == player_name_key(leg.get('player', ''))]
    if len(matches) != 1:
        return dict(result, status='player_identity_missing_or_ambiguous')
    player = matches[0]
    player_id = number(player.get('player_id') or player.get('id'))
    if not player_id or player_id < 1 or not player_id.is_integer():
        return dict(result, status='player_id_missing')
    log = player.get('gamelog') or {}
    values = [number(v) for v in (log.get(stat) or [])[:10]]
    dates = (log.get('l10_dates') or [])[:10]
    try:
        from datetime import date
        days = [datetime.strptime(str(d).title(), '%b %d, %Y').date() if ',' in str(d)
                else date.fromisoformat(str(d)[:10]) for d in dates]
    except (TypeError, ValueError):
        return dict(result, status='invalid_history_dates')
    event_day = at(source['tip_off']).astimezone(NY).date()
    if (len(values) != 10 or len(days) != 10 or len(set(days)) != 10
            or days != sorted(days, reverse=True) or any(d >= event_day for d in days)
            or any(v is None or v < 0 for v in values)):
        return dict(result, status='not_ten_dated_prior_games')
    h10 = sum(v >= line for v in values) / 10
    h5 = sum(v >= line for v in values[:5]) / 5
    mins = [number(v) for v in (log.get('MIN') or [])[:10]]
    if len(mins) != 10 or any(v is None or v < 0 for v in mins):
        mins = None
    result.update(status='base_only', prop=stat, player_id=player.get('id') or player.get('player_id'),
                  source={k: source[k] for k in ('artifact', 'sha256', 'available_at', 'tip_off', 'tip_source')},
                  eligible_80_80=h10 >= .8 and h5 >= .8,
                  inputs={'l10_values': values, 'l10_dates': [d.isoformat() for d in days],
                          'l10_minutes': mins, 'hit_l10': h10, 'hit_l5': h5, 'opportunity': {},
                          'history_context': {k: log.get(k) for k in
                              ('l10_matchups', 'l10_seasons', 'l10_season_types')}},
                  player_context={k: player.get(k) for k in ('position', 'status', 'roster_verified')},
                  context_source_status=source['game'].get('meta', {}).get('data_sources'),
                  cautions=['Observed rates are not forecasts; source GP, role and minute forecasts need validation.',
                            'Usage/AST% references may be fallback; verify original context source before fitting.'])
    pack = player.get('opportunity_features')
    if not isinstance(pack, dict) or pack.get('contract') != 'nba-opportunities/v1':
        return dict(result, opportunity_status='not_captured')
    cutoff = at(source['available_at'])
    season_year = event_day.year if event_day.month >= 7 else event_day.year - 1
    expected_season = f'{season_year}-{str(season_year + 1)[-2:]}'
    refs = {}
    names = {'PTS': ['player_base'], 'REB': ['rebounding'], 'AST': ['passing', 'possessions'],
             'FG3M': ['player_base', 'catch_shoot', 'pull_up']}[stat]
    for name in [*names, 'opponent_source']:
        record = pack.get(name, {}) if name == 'opponent_source' else pack.get('sources', {}).get(name, {})
        refs[name] = {k: record.get(k) for k in ('status', 'sample_games', 'season', 'history_date_to',
                                               'captured_at', 'source_sha256', 'row_sha256')}
        if record.get('status') == 'available':
            captured = at(record.get('captured_at'))
            try:
                history_day = datetime.strptime(record.get('history_date_to', ''), '%m/%d/%Y').date()
            except (TypeError, ValueError):
                return dict(result, opportunity_status='source_cutoff_unknown')
            if not captured or captured > cutoff or history_day >= event_day:
                return dict(result, opportunity_status='source_not_pretip')
            if (record.get('season') != expected_season or not number(record.get('sample_games'))
                    or number(record.get('sample_games')) < 0
                    or any(not re.fullmatch(r'[0-9a-f]{64}', str(record.get(k, '')))
                           for k in ('source_sha256', 'row_sha256'))):
                return dict(result, opportunity_status='source_sample_or_provenance_invalid')
    fields = pack.get('props', {}).get(stat)
    if not isinstance(fields, dict):
        return dict(result, opportunity_status='prop_fields_missing')
    clean = {k: number(v) if v is not None else None for k, v in fields.items()}
    if any(v is not None and (number(v) is None or number(v) < 0) for v in fields.values()):
        return dict(result, opportunity_status='invalid_feature_value')
    if not any(v is not None for v in clean.values()) or not any(refs[n]['status'] == 'available' for n in names):
        return dict(result, opportunity_status='no_usable_new_source')
    result['inputs']['opportunity'] = clean
    result.update(status='opportunity_captured', opportunity_status='captured_not_validated_forecast',
                  source_refs=refs, missing_features=[k for k, v in clean.items() if v is None],
                  opportunity_history_status=(pack.get('history_reference') or {}).get('status'))
    return result


def observation(source, leg):
    try:
        return _observation(source, leg)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        # Optional evidence errors are visible; they cannot break ordinary picks.
        return {'contract': CONTRACT, 'status': 'observation_error', 'training_ready': False}


def dataset(rows, *, as_of=None):
    """Latest published observation, with separate first-write-wins Final label."""
    import nba_market_ledger as ledger
    as_of = as_of or datetime.now(timezone.utc)
    exclusions = ledger.no_prediction_exclusions(rows)
    rows = [r for r in rows if not ledger._excluded(r, exclusions) and r.get('season_phase') != 'PRESEASON']
    models, outcomes = {}, {}
    for row in rows:
        if row.get('row_type') == 'model_obs':
            models.setdefault(ledger._leg_key(row), []).append(row)
        elif row.get('row_type') == 'settlement':
            outcomes.setdefault(ledger._leg_key(row), row)
    output, excluded = [], Counter()
    for key, observations in models.items():
        snapshot_id = ledger._choose_snapshot(observations)
        if snapshot_id is None:
            excluded['no_published_pretip_snapshot'] += 1
            continue
        # Never recover an older feature-rich snapshot when the latest lacks it.
        row = next(r for r in observations if r.get('snapshot_id') == snapshot_id)
        if row.get('tip_source') != 'official_schedule':
            excluded['official_schedule_missing'] += 1
            continue
        feature = row.get('prop_training') or {}
        tip, recorded, created, captured = [at(row.get(k)) for k in
            ('tip_off', 'recorded_at', 'snapshot_created_at', 'odds_captured_at')]
        if not all((tip, recorded, created, captured)) or not captured <= created <= recorded < tip:
            excluded['timestamps_not_verified_pretip'] += 1
            continue
        if feature.get('contract') != CONTRACT or feature.get('status') != 'opportunity_captured':
            excluded['new_features_not_captured'] += 1
            excluded['feature_status:' + str(feature.get('status') or 'not_recorded')] += 1
            continue
        available = at((feature.get('source') or {}).get('available_at'))
        if (not available or available != created
                or feature.get('source', {}).get('tip_source') != 'official_schedule'):
            excluded['feature_snapshot_cutoff_mismatch'] += 1
            continue
        target = outcomes.get(key) or {}
        settled_at = at(target.get('settled_at'))
        y = target.get('y')
        label_ok = (type(y) in (int, float) and y in (0, 1)
                    and target.get('outcome') == ('hit' if y == 1 else 'miss')
                    and target.get('verify_status') == ('✅ HIT' if y == 1 else '❌ MISS')
                    and settled_at and tip < settled_at <= as_of
                    and re.fullmatch(r'[0-9a-f]{64}', str(target.get('results_sha256', ''))))
        output.append({'contract': CONTRACT, 'key': list(key), 'snapshot_id': snapshot_id,
                       'available_at': created.isoformat(), 'prop': feature['prop'],
                       'eligible_80_80': feature['eligible_80_80'], 'picked_by_C': bool(row.get('picked')),
                       'inputs': feature['inputs'], 'feature_evidence': {k: v for k, v in feature.items() if k != 'inputs'},
                       'baseline': {'probability': row.get('p_final'),
                                    'model_id': ledger.probability_model_id(row), 'price': row.get('price_at_model')},
                       'target': {'y': int(y) if label_ok else None,
                                  'available_at': settled_at.isoformat() if label_ok else None,
                                  'results_sha256': target.get('results_sha256') if label_ok else None,
                                  'status': 'Final' if label_ok else 'pending_void_or_unverified'}})
    return output, dict(excluded)


def summary(rows):
    try:
        records, excluded = dataset(rows)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {'contract': CONTRACT, 'status': 'evidence_report_error', 'promotion_allowed': False}
    return {'contract': CONTRACT, 'status': 'engineering_evidence_only', 'promotion_allowed': False,
            'feature_rows': len(records), 'excluded': excluded,
            'by_prop': {stat: {'rows': len(part := [r for r in records if r['prop'] == stat]),
                              'settled_rows': sum(r['target']['y'] is not None for r in part),
                              'eligible_80_80': sum(r['eligible_80_80'] for r in part),
                              'settled_events': len({tuple(r['key'][:2]) for r in part if r['target']['y'] is not None})}
                        for stat in STAT.values()}}


def main():
    import nba_market_ledger as ledger
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--since')
    parser.add_argument('--until')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = {day: ledger.ledger_path(args.root, day)
             for day in ledger._iter_dates(args.since, args.until, args.root)}
    if sum(path.stat().st_size for path in paths.values()) > 100_000_000:
        raise ValueError('export window exceeds 100MB; use an explicit smaller date window')
    blobs = {day: path.read_bytes() for day, path in paths.items()}
    if sum(map(len, blobs.values())) > 100_000_000:
        raise ValueError('export window exceeds 100MB; use an explicit smaller date window')
    rows = [json.loads(line) for raw in blobs.values() for line in raw.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid ledger row')
    records, excluded = dataset(rows)
    # A fresh output directory prevents replacing a previously evaluated cohort.
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'source_ledger').mkdir()
    for day, raw in blobs.items():
        (args.output / 'source_ledger' / f'{day}.jsonl').write_bytes(raw)
    (args.output / 'dataset.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in records))
    report = summary(rows)
    report['excluded'] = excluded
    report['source_ledger_sha256'] = {day: hashlib.sha256(raw).hexdigest() for day, raw in blobs.items()}
    (args.output / 'Readiness.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
