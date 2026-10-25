"""Opponent context for the shadow season-rate model S_v2 (EXP-20261025-13). Never a probability.

One league team game log capture per run, shared by every game, cut at the last
completed US game day. For each team it records what that team ALLOWED per game
(the other side's PTS/REB/AST/FG3M), plus the league per-team-game average from
regular-season games. Early in a season the league average falls back to the
previous regular season and says so.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from nba_opportunities import at, digest
from nba_schedule import canonical_team_abbr

CONTRACT = 'nba-team-context/v1'
CACHE_SECONDS = 1800
STATS = ('PTS', 'REB', 'AST', 'FG3M')
SEASON_TYPES = ('Regular Season', 'PlayIn', 'Playoffs')
MIN_LEAGUE_TEAM_GAMES = 100
REQUIRED = {'GAME_ID', 'GAME_DATE', 'TEAM_ID', 'TEAM_ABBREVIATION', *STATS}


def _table(season, season_type, cutoff, fetch=None):
    record = {'season': season, 'season_type': season_type, 'history_date_to': cutoff, 'status': 'unavailable'}
    try:
        if fetch is None:
            from nba_api.stats.endpoints.leaguegamelog import LeagueGameLog
            fetch = LeagueGameLog
        payload = fetch(season=season, season_type_all_star=season_type, player_or_team_abbreviation='T',
                        date_to_nullable=cutoff, timeout=15).get_dict()
        tables = payload.get('resultSets', [])
        if not isinstance(tables, list) or len(tables) != 1:
            raise ValueError('ambiguous source tables')
        headers, rows = tables[0]['headers'], tables[0]['rowSet']
        if not REQUIRED <= set(headers) or any(len(row) != len(headers) for row in rows):
            raise ValueError('malformed source schema')
        record.update(status='available', rows=[{h: row[headers.index(h)] for h in REQUIRED} for row in rows],
                      source_sha256=digest(payload))
    except Exception as exc:  # recorded, never raised: shadow data only
        record['error_type'] = type(exc).__name__
    record['captured_at'] = datetime.now(timezone.utc).isoformat()
    return record


def fetch_bundle(season, previous_season, cutoff, cache_path, *, now=None, fetch=None):
    now = now or datetime.now(timezone.utc)
    path = Path(cache_path)
    if os.environ.get('WC_NBA_TEAM_CONTEXT', '1') == '0':
        return {'contract': CONTRACT, 'status': 'disabled', 'tables': {}}
    try:
        cached = json.loads(path.read_text())
        captured = at(cached.get('captured_at'))
        if (cached.get('contract') == CONTRACT and cached.get('season') == season
                and cached.get('history_date_to') == cutoff and captured
                and 0 <= (now - captured).total_seconds() <= CACHE_SECONDS
                and cached.get('tables_sha256') == digest(cached['tables'])):
            return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    tables = {kind: _table(season, kind, cutoff, fetch) for kind in SEASON_TYPES}
    tables['previous_regular'] = _table(previous_season, 'Regular Season', '', fetch)
    bundle = {'contract': CONTRACT, 'season': season, 'history_date_to': cutoff,
              'captured_at': datetime.now(timezone.utc).isoformat(), 'tables': tables,
              'tables_sha256': digest(tables), 'status': 'captured'}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        temporary.write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return bundle


def _day(value):
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%b %d, %Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(str(value)[:19] if fmt.startswith('%Y-%m-%dT') else str(value), fmt).date()
        except ValueError:
            continue
    return None


def opponent_context(bundle, opponent_abbr, cutoff_day):
    """What `opponent_abbr` allowed per game before cutoff_day (a date), newest first, + league average."""
    tables = (bundle or {}).get('tables') or {}
    current = [r for kind in SEASON_TYPES for r in (tables.get(kind) or {}).get('rows', [])
               if (tables.get(kind) or {}).get('status') == 'available']
    current = [dict(r, _day=_day(r['GAME_DATE'])) for r in current]
    current = [r for r in current if r['_day'] is not None and r['_day'] < cutoff_day]
    if not current and (tables.get('Regular Season') or {}).get('status') != 'available':
        return {'status': 'source_unavailable'}
    by_game = {}
    for r in current:
        by_game.setdefault(r['GAME_ID'], []).append(r)
    target = canonical_team_abbr(opponent_abbr)
    allowed = []
    for rows in by_game.values():
        if len(rows) != 2:
            continue
        mine = [r for r in rows if canonical_team_abbr(r['TEAM_ABBREVIATION']) == target]
        if len(mine) == 1:
            other = rows[0] if rows[1] is mine[0] else rows[1]
            allowed.append((mine[0]['_day'], {s: float(other[s]) for s in STATS}))
    allowed.sort(key=lambda x: x[0], reverse=True)
    rs_rows = [dict(r, _day=_day(r['GAME_DATE'])) for r in (tables.get('Regular Season') or {}).get('rows', [])]
    rs_rows = [r for r in rs_rows if r['_day'] is not None and r['_day'] < cutoff_day]
    league_source = 'current_regular'
    if len(rs_rows) < MIN_LEAGUE_TEAM_GAMES:
        prev = tables.get('previous_regular') or {}
        if prev.get('status') != 'available' or not prev.get('rows'):
            return {'status': 'league_average_unavailable'}
        rs_rows, league_source = prev['rows'], 'previous_regular'
    league = {s: sum(float(r[s]) for r in rs_rows) / len(rs_rows) for s in STATS}
    return {'status': 'available', 'opponent': target,
            'allowed': {'dates': [d.isoformat() for d, _ in allowed],
                        **{s: [v[s] for _, v in allowed] for s in STATS}},
            'league_avg': league, 'league_team_games': len(rs_rows), 'league_source': league_source,
            'captured_at': bundle.get('captured_at'), 'tables_sha256': bundle.get('tables_sha256')}
