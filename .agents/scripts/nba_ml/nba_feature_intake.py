#!/usr/bin/env python3
"""Capture a declared NBA basic/advanced/tracking catalogue for research.

Raw tables retain all returned columns and units. A capture is not automatically
point-in-time training evidence: it must later be bound to a future event.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.agents/skills/nba'))
sys.path.insert(0, str(ROOT / '.agents/skills/nba/nba_data_extractor/scripts'))
from nba_extractor import history_date_to, nba_season_for_date


def catalogue():
    requests = []
    for entity, endpoint in [('player', 'LeagueDashPlayerStats'), ('team', 'LeagueDashTeamStats')]:
        measures = ['Base', 'Advanced', 'Usage', 'Scoring', 'Misc', 'Defense', 'Four Factors']
        if entity == 'team':
            measures = ['Base', 'Advanced', 'Scoring', 'Misc', 'Defense', 'Four Factors', 'Opponent']
        for measure in measures:
            requests.append({'name': f'{entity}_{measure.lower().replace(" ", "_")}', 'endpoint': endpoint,
                             'entity': entity, 'unit': 'PerGame',
                             'params': {'measure_type_detailed_defense': measure, 'per_mode_detailed': 'PerGame'}})
    requests.append({'name': 'team_opponent_per100', 'endpoint': 'LeagueDashTeamStats', 'entity': 'team',
                     'unit': 'Per100Possessions', 'params': {'measure_type_detailed_defense': 'Opponent',
                                                          'per_mode_detailed': 'Per100Possessions'}})
    for entity in ['Player', 'Team']:
        for measure in ['Passing', 'Rebounding', 'Possessions', 'SpeedDistance', 'CatchShoot', 'PullUpShot',
                        'Drives', 'Defense', 'ElbowTouch', 'PostTouch', 'PaintTouch', 'Efficiency']:
            requests.append({'name': f'{entity.lower()}_tracking_{measure.lower()}', 'endpoint': 'LeagueDashPtStats',
                             'entity': entity.lower(), 'unit': 'PerGame',
                             'params': {'player_or_team': entity, 'pt_measure_type': measure, 'per_mode_simple': 'PerGame'}})
        requests.append({'name': f'{entity.lower()}_hustle', 'endpoint': 'LeagueHustleStats' + entity,
                         'entity': entity.lower(), 'unit': 'PerGame', 'params': {'per_mode_time': 'PerGame'}})
    return requests


def endpoint_class(name):
    from nba_api.stats.endpoints import (leaguedashplayerstats, leaguedashteamstats, leaguedashptstats,
                                         leaguehustlestatsplayer, leaguehustlestatsteam)
    modules = [leaguedashplayerstats, leaguedashteamstats, leaguedashptstats,
               leaguehustlestatsplayer, leaguehustlestatsteam]
    return next(getattr(module, name) for module in modules if hasattr(module, name))


def table_inventory(payload):
    tables = payload.get('resultSets', payload.get('resultSet', []))
    if isinstance(tables, dict):
        tables = [tables]
    inventory = []
    for table in tables:
        headers, rows = table.get('headers', []), table.get('rowSet', [])
        if not isinstance(headers, list) or not isinstance(rows, list) or any(len(row) != len(headers) for row in rows):
            raise ValueError('malformed table columns')
        if len(headers) != len(set(headers)):
            raise ValueError('ambiguous column names')
        gp = [row[headers.index('GP')] for row in rows] if 'GP' in headers else []
        numeric = [value for value in gp if isinstance(value, (int, float)) and not isinstance(value, bool)]
        inventory.append({'name': table.get('name'), 'headers': headers, 'rows': len(rows),
                          'gp_min': min(numeric) if numeric else None, 'gp_max': max(numeric) if numeric else None})
    return inventory


def capture(spec, *, season, cutoff, output, fetch=None):
    params = {**spec['params'], 'season': season, 'season_type_all_star': 'Regular Season',
              'date_to_nullable': cutoff, 'timeout': 10}
    began = datetime.now(timezone.utc).isoformat()
    record = {**spec, 'params': params, 'started_at': began, 'verification': 'single_NBA_source_research_only'}
    try:
        response = (fetch or endpoint_class(spec['endpoint']))(**params)
        payload = response.get_dict()
        inventory = table_inventory(payload)
        if not inventory:
            raise ValueError('result tables missing')
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        path = Path(output) / (spec['name'] + '.json')
        path.write_bytes(raw)
        record.update(status='available' if any(table['rows'] for table in inventory) else 'empty',
                      sha256=hashlib.sha256(raw).hexdigest(), path=path.name, tables=inventory)
    except Exception as exc:
        record.update(status='unavailable', error_type=type(exc).__name__)
    record['completed_at'] = datetime.now(timezone.utc).isoformat()
    return record


def run(output, as_of, *, season=None):
    when = datetime.fromisoformat(as_of.replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('as_of requires timezone')
    now = datetime.now(timezone.utc)
    if when > now:
        raise ValueError('future research as_of is not allowed')
    season = season or nba_season_for_date(as_of)
    cutoff = history_date_to(as_of)
    output = Path(output)
    output.mkdir(exist_ok=False)
    manifest = {'contract': 'nba-feature-intake/v1', 'started_at': now.isoformat(), 'season': season,
                'requested_as_of': as_of, 'history_date_to': cutoff,
                'point_in_time_status': 'research_capture_not_bound_to_event',
                'deployment_eligible': False, 'catalogue_scope': 'declared league basic/advanced/usage/scoring/defense/opponent/tracking/hustle tables; not every NBA endpoint',
                'requests': [], 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest_path = output / 'Manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(capture, spec, season=season, cutoff=cutoff, output=output) for spec in catalogue()]
        for future in as_completed(futures):
            record = future.result()
            manifest['requests'].append(record)
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"{record['name']}: {record['status']}", flush=True)
    manifest['requests'].sort(key=lambda row: row['name'])
    manifest['completed_at'] = datetime.now(timezone.utc).isoformat()
    manifest['status_counts'] = {status: sum(row['status'] == status for row in manifest['requests'])
                                 for status in ['available', 'empty', 'unavailable']}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest['status_counts']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-only', action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--as-of')
    parser.add_argument('--season')
    args = parser.parse_args()
    if args.catalogue_only:
        print(json.dumps(catalogue(), indent=2))
    elif not args.output or not args.as_of:
        parser.error('--output and --as-of are required for capture')
    else:
        run(args.output, args.as_of, season=args.season)
