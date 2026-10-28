"""Prop-specific opportunity evidence. Descriptive features, never probabilities."""
from __future__ import annotations
import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from nba_schedule import canonical_team_abbr

CONTRACT = 'nba-opportunities/v1'
CACHE_SECONDS = 1800
TRACKING = {'passing': 'Passing', 'rebounding': 'Rebounding', 'possessions': 'Possessions',
            'catch_shoot': 'CatchShoot', 'pull_up': 'PullUpShot'}
PLAYER_SOURCES = [*TRACKING, 'player_base']


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError):
        return None


def at(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def request_table(name, season, cutoff, fetch=None):
    unit = 'Per100Possessions' if name == 'team_base' else 'PerGame'
    params = {'season': season, 'season_type_all_star': 'Regular Season', 'date_to_nullable': cutoff, 'timeout': 10}
    record = {'season': season, 'history_date_to': cutoff, 'unit': unit, 'status': 'unavailable'}
    try:
        if name == 'team_base':
            if fetch is None:
                from nba_api.stats.endpoints.leaguedashteamstats import LeagueDashTeamStats
                fetch = LeagueDashTeamStats
            params.update(measure_type_detailed_defense='Base', per_mode_detailed=unit)
        elif name == 'player_base':
            if fetch is None:
                from nba_api.stats.endpoints.leaguedashplayerstats import LeagueDashPlayerStats
                fetch = LeagueDashPlayerStats
            params.update(measure_type_detailed_defense='Base', per_mode_detailed=unit)
        else:
            if fetch is None:
                from nba_api.stats.endpoints.leaguedashptstats import LeagueDashPtStats
                fetch = LeagueDashPtStats
            params.update(player_or_team='Player', pt_measure_type=TRACKING[name], per_mode_simple=unit)
        record['params'] = params
        payload = fetch(**params).get_dict()
        tables = payload.get('resultSets', [])
        if not isinstance(tables, list) or len(tables) != 1:
            raise ValueError('ambiguous source tables')
        headers, rows = tables[0]['headers'], tables[0]['rowSet']
        if len(headers) != len(set(headers)) or any(len(row) != len(headers) for row in rows):
            raise ValueError('malformed source schema')
        required = {'TEAM_ID', 'GP', 'MIN'} | ({'PLAYER_ID', 'TEAM_ABBREVIATION'} if name != 'team_base' else {'FGA', 'FGM'})
        if not required <= set(headers):
            raise ValueError('source identity/sample columns missing')
        record.update(status='available' if rows else 'empty', rows=[dict(zip(headers, row)) for row in rows],
                      source_sha256=digest(payload))
    except Exception as exc:
        record['error_type'] = type(exc).__name__
    record['captured_at'] = datetime.now(timezone.utc).isoformat()
    return record


def fetch_sources(season, cutoff, cache_path, *, now=None, fetchers=None):
    """Shared bounded league cache, with content integrity and no season fallback."""
    now = now or datetime.now(timezone.utc)
    path = Path(cache_path)
    if os.environ.get('WC_NBA_OPPORTUNITIES', '1') == '0':
        return {'contract': CONTRACT, 'status': 'disabled', 'sources': {}}
    try:
        cached = json.loads(path.read_text())
        captured = at(cached.get('captured_at'))
        if (cached.get('contract') == CONTRACT and cached.get('season') == season
                and cached.get('history_date_to') == cutoff and captured
                and 0 <= (now - captured).total_seconds() <= CACHE_SECONDS
                and cached.get('sources_sha256') == digest(cached['sources'])):
            return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass
    names = [*PLAYER_SOURCES, 'team_base']
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda name: request_table(name, season, cutoff, (fetchers or {}).get(name)), names))
    sources = dict(zip(names, values))
    bundle = {'contract': CONTRACT, 'season': season, 'history_date_to': cutoff,
              'captured_at': datetime.now(timezone.utc).isoformat(), 'sources': sources,
              'sources_sha256': digest(sources), 'status': 'captured', 'model_input_enabled': False}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        temporary.write_text(json.dumps(bundle, ensure_ascii=False, allow_nan=False))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return bundle


def verified_row(bundle, name, *, tip, season, cutoff, player_id=None, team_id=None, team=None):
    source = bundle.get('sources', {}).get(name, {})
    record = {key: source.get(key) for key in ('season', 'history_date_to', 'unit', 'captured_at', 'source_sha256')}
    captured, start = at(source.get('captured_at')), at(tip)
    try:
        historical_day = datetime.strptime(cutoff, '%m/%d/%Y').date()
        prior = bool(start and historical_day < start.astimezone(ZoneInfo('America/New_York')).date())
    except (ValueError, TypeError):
        prior = False
    reason = ('history_not_prior_to_event' if not prior else
              'source_unavailable' if source.get('status') != 'available' else
              'wrong_season_or_cutoff' if source.get('season') != season or source.get('history_date_to') != cutoff else
              'not_verified_pregame' if not captured or not start or captured >= start else None)
    if not reason:
        rows = [row for row in source.get('rows', [])
                if (player_id is None or str(row.get('PLAYER_ID')) == str(player_id))
                and (team_id is None or str(row.get('TEAM_ID')) == str(team_id))
                and (team is None or canonical_team_abbr(row.get('TEAM_ABBREVIATION')) == canonical_team_abbr(team))]
        if len(rows) != 1:
            reason = 'identity_missing_or_ambiguous'
        elif not number(rows[0].get('GP')) or not number(rows[0].get('MIN')):
            reason = 'insufficient_sample'
        else:
            record.update(status='available', row=rows[0], row_sha256=digest(rows[0]),
                          sample_games=number(rows[0]['GP']))
    if reason:
        record['status'] = reason
    return record


def ratio(numerator, denominator, *, probability=False):
    a, b = number(numerator), number(denominator)
    if a is None or b is None or b <= 0 or (probability and a > b):
        return None
    return a / b


def subtract(a, b):
    a, b = number(a), number(b)
    return a - b if a is not None and b is not None and a >= b else None


def build_features(player, team, opponent_id, bundle, *, tip, season, cutoff, opponent_stats=None):
    """Separate each prop's inputs; retain raw same-source rows and missingness.

    Formula strings specify quantities for future validation. No projected
    probability/EV is produced and no component is applied to the C layer.
    """
    sources = {name: verified_row(bundle, name, tip=tip, season=season, cutoff=cutoff,
                                 player_id=player.get('player_id'), team=team)
               for name in PLAYER_SOURCES}
    # A missing ID must not silently match another player's unique team row.
    if player.get('player_id') is None:
        sources = {name: {'status': 'player_id_missing'} for name in PLAYER_SOURCES}
    opponent = verified_row(bundle, 'team_base', tip=tip, season=season, cutoff=cutoff, team_id=opponent_id)
    if opponent_id is None:
        opponent = {'status': 'opponent_id_missing'}
    raw = {name: source.get('row', {}) for name, source in sources.items()}
    passing, reb, poss = raw['passing'], raw['rebounding'], raw['possessions']
    gl = player.get('gamelog') or {}
    dates = []
    for value in gl.get('l10_dates') or []:
        try:
            dates.append(datetime.strptime(str(value).title(), '%b %d, %Y').date()
                         if ',' in str(value) else datetime.fromisoformat(str(value)[:10]).date())
        except (ValueError, TypeError):
            dates.append(None)
    event = at(tip)
    event_day = event.astimezone(ZoneInfo('America/New_York')).date() if event else None
    history_verified = (bool(dates) and len(dates) == len(gl.get('MIN') or []) and event_day
                        and all(day is not None and day < event_day for day in dates))
    stats = {}
    # Box-score rates use aligned arrays; never mix periods to construct a ratio.
    for field in ('MIN', 'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM'):
        arr = gl.get(field) or []
        stats[field] = sum(number(x) for x in arr) if arr and all(number(x) is not None for x in arr) else None
    aligned = bool(gl.get('MIN')) and all(len(gl.get(key) or []) == len(gl['MIN']) for key in stats)
    if not aligned or not history_verified:
        stats = dict.fromkeys(stats)
    historical_minutes = ratio(stats['MIN'], len(gl.get('MIN') or []))
    box = raw['player_base']
    if box:
        stats = {key: number(box.get(key)) for key in stats}
    two_a, two_m = subtract(stats['FGA'], stats['FG3A']), subtract(stats['FGM'], stats['FG3M'])
    base = opponent.get('row', {})
    allowed_mode = (((opponent_stats or {}).get('opponent_stats') or {}).get('modes') or {}).get('per_100_possessions', {})
    allowed_source = (opponent_stats or {}).get('opponent_stats') or {}
    allowed_capture, start = at(allowed_source.get('captured_at')), at(tip)
    allowed_ok = (allowed_mode.get('status') == 'available' and number(allowed_mode.get('games'))
                  and allowed_source.get('season') == season and allowed_source.get('history_date_to') == cutoff
                  and allowed_capture and start and allowed_capture < start)
    allowed = allowed_mode.get('values', {}) if allowed_ok else {}
    # The team's own shot misses and its opponents' shot misses are different quantities.
    points = {'two_pa_per_min': ratio(two_a, stats['MIN']), 'two_p_conversion': ratio(two_m, two_a, probability=True),
              'three_pa_per_min': ratio(stats['FG3A'], stats['MIN']), 'three_p_conversion': ratio(stats['FG3M'], stats['FG3A'], probability=True),
              'fta_per_min': ratio(stats['FTA'], stats['MIN']), 'ft_conversion': ratio(stats['FTM'], stats['FTA'], probability=True),
              'usage_pct': number((player.get('advanced') or {}).get('USG_PCT')), 'opponent_points_allowed_per100': number(allowed.get('OPP_PTS'))}
    assists = {'potential_ast_per_min': ratio(passing.get('POTENTIAL_AST'), passing.get('MIN')),
               'potential_ast_conversion': ratio(passing.get('AST'), passing.get('POTENTIAL_AST'), probability=True),
               'touches_per_min': ratio(poss.get('TOUCHES'), poss.get('MIN')),
               'time_of_possession_per_game': number(poss.get('TIME_OF_POSS')),
               'ast_pct': number((player.get('advanced') or {}).get('AST_PCT')),
               'opponent_assists_allowed_per100': number(allowed.get('OPP_AST'))}
    rebounds = {'oreb_chances_per_min': ratio(reb.get('OREB_CHANCES'), reb.get('MIN')),
                'oreb_conversion': ratio(reb.get('OREB'), reb.get('OREB_CHANCES'), probability=True),
                'dreb_chances_per_min': ratio(reb.get('DREB_CHANCES'), reb.get('MIN')),
                'dreb_conversion': ratio(reb.get('DREB'), reb.get('DREB_CHANCES'), probability=True),
                'contested_rebound_share': number(reb.get('REB_CONTEST_PCT')),
                'opponent_own_fg_misses_per100': subtract(base.get('FGA'), base.get('FGM')),
                'opponent_rebounds_allowed_per100': number(allowed.get('OPP_REB')),
                'opponent_offensive_rebounds_per100': number(base.get('OREB'))}
    threes = {'three_pa_per_min': points['three_pa_per_min'], 'three_p_conversion': points['three_p_conversion'],
              'catch_shoot_3pa_per_min': ratio(raw['catch_shoot'].get('CATCH_SHOOT_FG3A'), raw['catch_shoot'].get('MIN')),
              'pull_up_3pa_per_min': ratio(raw['pull_up'].get('PULL_UP_FG3A'), raw['pull_up'].get('MIN')),
              'opponent_3pa_allowed_per100': number(allowed.get('OPP_FG3A')),
              'opponent_3pm_allowed_per100': number(allowed.get('OPP_FG3M'))}
    props = {'PTS': points, 'AST': assists, 'REB': rebounds, 'FG3M': threes}
    formulas = {'PTS': 'minutes * (2*two_pa_rate*two_p_conversion + 3*three_pa_rate*three_p_conversion + fta_rate*ft_conversion)',
                'AST': 'minutes * potential_ast_rate * potential_ast_conversion',
                'REB': 'minutes * (oreb_chance_rate*oreb_conversion + dreb_chance_rate*dreb_conversion)',
                'FG3M': 'minutes * three_pa_rate * three_p_conversion'}
    return {'contract': CONTRACT, 'model_input_enabled': False, 'status': 'descriptive_features_only',
            'history_reference': {'status': 'dated_prior_history' if history_verified else 'unverified',
                                  'dates': gl.get('l10_dates') or [], 'minutes_mean': historical_minutes,
                                  'usage_and_ast_pct': 'inherited reference; verify game meta.data_sources season/fallback before modeling'},
            'box_reference': {'source': 'current_season_base' if box else 'dated_L10',
                              'games': number(box.get('GP')) if box else len(dates) if history_verified else None},
            'sources': sources, 'opponent_source': opponent, 'props': props, 'formula_components': formulas,
            'missing_by_prop': {stat: [key for key, value in fields.items() if value is None] for stat, fields in props.items()},
            'notes': ['raw rate*conversion identities are not validated forecasts', 'sources may have different GP; never merge denominators',
                      'minutes forecast, role changes, uncertainty and opponent effects require separate out-of-sample fitting']}


def summarize(players):
    """Coverage counts expose dead optional feeds without changing model gates."""
    from collections import Counter
    entries = [player.get('opportunity_features') for group in players.values() for player in group]
    entries = [entry for entry in entries if entry]
    coverage = {name: dict(Counter(entry['sources'][name]['status'] for entry in entries)) for name in PLAYER_SOURCES}
    return {'contract': CONTRACT, 'player_rows': len(entries), 'model_input_enabled': False,
            'source_status_counts': coverage,
            'nonmissing_by_prop': {stat: {field: sum(entry['props'][stat][field] is not None for entry in entries)
                                         for field in entries[0]['props'][stat]} for stat in entries[0]['props']} if entries else {}}
