#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
verify_props_hits.py — NBA Props 命中自動驗證器

讀取 Results_Brief JSON + 每份分析報告嘅 .market_legs.json sidecar（唔讀 Markdown），
自動比對每個 SGM Leg 嘅命中/未中。
供 NBA Reflector 覆盤消費,取代 LLM 手動逐 Leg 對比。

Usage:
  python verify_props_hits.py \
    --results "Results_Brief_2026-04-07.json" \
    --predictions "/path/to/analysis/dir" \
    --output "Props_Verification_2026-04-07.json"

Version: 1.0.0
"""

import argparse
import hashlib
import json
import re
import io
import glob
from pathlib import Path

NBA_SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_SKILL_DIR))
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Prop stat name normalization
STAT_ALIASES = {
    'points': 'pts', 'pts': 'pts',
    'rebounds': 'reb', 'reb': 'reb', 'rebs': 'reb',
    'assists': 'ast', 'ast': 'ast',
    'threes': 'fg3m', '3pm': 'fg3m', 'fg3m': 'fg3m', 'threes made': 'fg3m', '三分': 'fg3m',
    'steals': 'stl', 'stl': 'stl',
    'blocks': 'blk', 'blk': 'blk',
    'turnovers': 'tov', 'tov': 'tov',
    'pts+reb+ast': 'pra', 'pra': 'pra',
    'pts+reb': 'pr', 'pr': 'pr',
    'pts+ast': 'pa', 'pa': 'pa',
    'reb+ast': 'ra', 'ra': 'ra',
    'stl+blk': 'sb', 'sb': 'sb',
}


def normalize_stat(stat_str):
    """Normalize stat name to canonical form."""
    key = stat_str.lower().strip()
    return STAT_ALIASES.get(key, key)


def get_player_actual(players_list, player_name):
    """Find a player's actual stats from box score data.

    Order: exact lower-case name, then accent/punctuation-insensitive name
    (Sportsbet "Nikola Jokic" vs box score "Nikola Jokić"), then a unique surname
    match whose first name is prefix-compatible (nickname/initial).  The old surname fallback could
    settle a leg with another player's stats (Jalen vs Jaylin Williams); an
    unmatched leg is flagged PLAYER_NOT_FOUND instead, which is safe.
    """
    name_lower = player_name.lower().strip()
    exact = [
        player for player in players_list
        if str(player.get('name', '')).lower().strip() == name_lower
    ]
    if exact:
        return exact[0]
    key = player_name_key(player_name)
    keyed = [p for p in players_list if player_name_key(p.get('name', '')) == key]
    if len(keyed) == 1:
        return keyed[0]
    parts = key.split()
    if len(parts) < 2:
        return None
    last_name, first = parts[-1], parts[0]
    surname_matches = []
    for p in players_list:
        other = player_name_key(p.get('name', '')).split()
        if len(other) < 2 or other[-1] != last_name:
            continue
        # first names must be nickname-compatible: one is a prefix of the other
        # (Nic/Nicolas, Cam/Cameron, "J." initial). Jaylin vs Jalen is NOT a match.
        if other[0].startswith(first) or first.startswith(other[0]):
            surname_matches.append(p)
    return surname_matches[0] if len(surname_matches) == 1 else None


def parse_minutes(value):
    """Parse NBA box-score minutes; zero means DNP/void for player props."""
    if value in (None, "", "?"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper()
    iso = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
    if iso:
        return float(iso.group(1) or 0) + float(iso.group(2) or 0) / 60
    clock = re.fullmatch(r"(\d+):(\d+(?:\.\d+)?)", text)
    if clock:
        return float(clock.group(1)) + float(clock.group(2)) / 60
    try:
        return float(text)
    except ValueError:
        return None


def compute_actual_value(player_stats, stat_key):
    """Compute actual value for a given stat key from box score."""
    stat = normalize_stat(stat_key)

    direct_stats = {
        'pts': player_stats.get('pts', 0),
        'reb': player_stats.get('reb', 0),
        'ast': player_stats.get('ast', 0),
        'fg3m': player_stats.get('fg3m', 0),
        'stl': player_stats.get('stl', 0),
        'blk': player_stats.get('blk', 0),
        'tov': player_stats.get('tov', 0),
    }

    combo_stats = {
        'pra': direct_stats['pts'] + direct_stats['reb'] + direct_stats['ast'],
        'pr': direct_stats['pts'] + direct_stats['reb'],
        'pa': direct_stats['pts'] + direct_stats['ast'],
        'ra': direct_stats['reb'] + direct_stats['ast'],
        'sb': direct_stats['stl'] + direct_stats['blk'],
    }

    if stat in direct_stats:
        return direct_stats[stat]
    if stat in combo_stats:
        return combo_stats[stat]
    return None


SIDECAR_SUFFIX = '.market_legs.json'
STAT_LABELS = {'pts': 'PTS', 'reb': 'REB', 'ast': 'AST', 'fg3m': '3PM'}


def bound_sidecar(report_path):
    """The report's ``.market_legs.json``, or None when missing or not bound to the report.

    The sidecar is the report's only machine interface; ``report_sha256`` proves it was
    written with this exact report, so an edited report is never settled from stale data.
    """
    try:
        with open(f'{report_path}{SIDECAR_SUFFIX}', 'r', encoding='utf-8') as f:
            payload = json.load(f)
        with open(report_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get('report_sha256') != digest:
        return None
    return payload


def extract_legs_from_report(report_path):
    """Formal combo legs from the report's bound sidecar (never its Markdown).

    Returns list of dicts: {player, stat, stat_normalized, line, odds, combo_id}; [] when
    the sidecar is missing, stale, or the report has no formal combo.
    """
    payload = bound_sidecar(report_path)
    if payload is None:
        print(f"  ⚠️ sidecar 缺失或者對唔上報告: {os.path.basename(str(report_path))}")
        return []
    legs, seen = [], set()
    for combo in payload.get('combos') or []:
        for leg in combo.get('legs') or []:
            if leg.get('market_type') not in (None, 'PLAYER_MILESTONE') or not leg.get('player'):
                continue
            market = str(leg.get('market') or '').lower()
            try:
                line = float(leg['line'])
            except (KeyError, TypeError, ValueError):
                continue
            item = {
                'player': str(leg['player']).strip(),
                'stat': STAT_LABELS.get(market, market.upper()),
                'stat_normalized': normalize_stat(market),
                'line': line,
                'odds': float(leg['price']) if isinstance(leg.get('price'), (int, float)) else None,
                'combo_id': str(combo.get('combo_id')),
            }
            key = (item['combo_id'], item['player'], item['stat_normalized'], item['line'])
            if key not in seen:
                legs.append(item)
                seen.add(key)
    return legs


def verify_legs(legs, game_result):
    """Verify each leg against actual game results."""
    verified = []
    players = game_result.get('players', [])

    for leg in legs:
        player_stats = get_player_actual(players, leg['player'])

        result = {
            **leg,
            'game': game_result.get('final_score', '?'),
        }

        if not player_stats:
            result['status'] = '⚠️ PLAYER_NOT_FOUND'
            result['actual'] = None
            result['margin'] = None
            result['cleared'] = None
            verified.append(result)
            continue

        minutes = parse_minutes(player_stats.get('minutes'))
        if minutes is not None and minutes <= 0:
            result['status'] = '↩️ VOID_DNP'
            result['actual'] = None
            result['minutes'] = player_stats.get('minutes')
            result['margin'] = None
            result['cleared'] = None
            result['outcome'] = 'void'
            verified.append(result)
            continue

        actual = compute_actual_value(player_stats, leg['stat'])
        if actual is None:
            result['status'] = '⚠️ STAT_NOT_FOUND'
            result['actual'] = None
            result['margin'] = None
            result['cleared'] = None
            verified.append(result)
            continue

        result['actual'] = actual
        result['minutes'] = player_stats.get('minutes', '?')
        result['margin'] = round(actual - leg['line'], 1)
        result['cleared'] = actual >= leg['line']  # Milestones are always "Over X+"
        result['status'] = '✅ HIT' if result['cleared'] else '❌ MISS'

        verified.append(result)

    return verified


def match_report_to_game(report_path, games):
    """Match an analysis report to a game result by team abbreviations."""
    basename = os.path.basename(report_path).upper()

    for game in games:
        home = canonical_team_abbr(game.get('home', {}).get('team', ''))
        away = canonical_team_abbr(game.get('away', {}).get('team', ''))
        canonical_basename = basename.replace('WSH', 'WAS')
        if home and away and home in canonical_basename and away in canonical_basename:
            return game
    return None


def main():
    parser = argparse.ArgumentParser(description='NBA Props Hit Verifier')
    parser.add_argument('--results', required=True,
                        help='Path to Results_Brief JSON')
    parser.add_argument('--predictions', required=True,
                        help='Directory containing analysis reports')
    parser.add_argument('--output', required=True,
                        help='Output path for verification JSON')
    args = parser.parse_args()

    # Load results
    if not os.path.exists(args.results):
        print(f"❌ Results file not found: {args.results}")
        sys.exit(1)

    with open(args.results, 'r', encoding='utf-8') as f:
        results_brief = json.load(f)

    games = results_brief.get('games', [])
    print(f"📊 載入 {len(games)} 場賽果")

    # Legs come from each report's bound sidecar.
    reports = sorted(glob.glob(os.path.join(args.predictions, 'Game_*_Full_Analysis.md')))
    print(f"📋 搵到 {len(reports)} 份分析報告")

    all_verified = []
    summary = {
        'total_legs': 0,
        'hits': 0,
        'misses': 0,
        'voids': 0,
        'unverified': 0,
        'by_combo': {},
        'by_stat': {},
    }

    for report_path in reports:
        print(f"\n📄 處理: {os.path.basename(report_path)}")

        # Extract legs from report
        legs = extract_legs_from_report(report_path)
        if not legs:
            print(f"  ⚠️ 未提取到任何 Leg")
            continue

        print(f"  📍 提取到 {len(legs)} 個 Legs")

        # Match to game result
        game = match_report_to_game(report_path, games)
        if not game:
            print(f"  ⚠️ 無法配對到賽果")
            for leg in legs:
                all_verified.append({**leg, 'status': '⚠️ NO_GAME_MATCH',
                                     'actual': None, 'margin': None, 'cleared': None})
                summary['unverified'] += 1
                summary['total_legs'] += 1
            continue

        print(f"  🏀 配對到: {game.get('final_score', '?')}")

        # Verify each leg
        verified = verify_legs(legs, game)
        all_verified.extend(verified)

        for v in verified:
            summary['total_legs'] += 1
            if v['cleared'] is True:
                summary['hits'] += 1
            elif v['cleared'] is False:
                summary['misses'] += 1
            elif v.get('outcome') == 'void':
                summary['voids'] += 1
            else:
                summary['unverified'] += 1

            # By combo
            combo = v.get('combo_id', '?')
            if combo not in summary['by_combo']:
                summary['by_combo'][combo] = {'hits': 0, 'misses': 0, 'voids': 0, 'total': 0}
            summary['by_combo'][combo]['total'] += 1
            if v['cleared'] is True:
                summary['by_combo'][combo]['hits'] += 1
            elif v['cleared'] is False:
                summary['by_combo'][combo]['misses'] += 1
            elif v.get('outcome') == 'void':
                summary['by_combo'][combo]['voids'] += 1

            # By stat
            stat = v.get('stat_normalized', '?')
            if stat not in summary['by_stat']:
                summary['by_stat'][stat] = {'hits': 0, 'misses': 0, 'voids': 0, 'total': 0}
            summary['by_stat'][stat]['total'] += 1
            if v['cleared'] is True:
                summary['by_stat'][stat]['hits'] += 1
            elif v['cleared'] is False:
                summary['by_stat'][stat]['misses'] += 1
            elif v.get('outcome') == 'void':
                summary['by_stat'][stat]['voids'] += 1

            # Print each leg result
            if v['cleared'] is not None:
                margin_str = f" (margin: {v['margin']:+.1f})" if v['margin'] is not None else ""
                print(f"  {v['status']} | {v['player']} {v['stat']} {v['line']}+ → actual: {v['actual']}{margin_str}")
            else:
                print(f"  {v['status']} | {v['player']} {v['stat']}")

    # Calculate hit rate
    verifiable = summary['hits'] + summary['misses']
    hit_rate = (summary['hits'] / verifiable * 100) if verifiable > 0 else 0

    # Build output
    output = {
        '_version': 'PROPS_VERIFICATION_V1',
        '_generated_by': 'verify_props_hits.py',
        'summary': {
            'total_legs': summary['total_legs'],
            'hits': summary['hits'],
            'misses': summary['misses'],
            'voids': summary['voids'],
            'unverified': summary['unverified'],
            'hit_rate_pct': round(hit_rate, 1),
            'by_combo': summary['by_combo'],
            'by_stat': summary['by_stat'],
        },
        'legs': all_verified,
    }

    # Save
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"📊 Props 命中驗證完成")
    print(f"   總 Legs: {summary['total_legs']}")
    print(f"   ✅ 命中: {summary['hits']}")
    print(f"   ❌ 失敗: {summary['misses']}")
    print(f"   ↩️ DNP 作廢: {summary['voids']}")
    print(f"   ⚠️ 未驗證: {summary['unverified']}")
    print(f"   命中率: {hit_rate:.1f}%")
    print(f"\n   按組合:")
    for combo_id, stats in sorted(summary['by_combo'].items()):
        rate = (stats['hits'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"     Combo {combo_id}: {stats['hits']}/{stats['total']} ({rate:.0f}%)")
    print(f"\n   按盤口類型:")
    for stat, stats in sorted(summary['by_stat'].items()):
        rate = (stats['hits'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"     {stat.upper()}: {stats['hits']}/{stats['total']} ({rate:.0f}%)")
    print(f"\n📄 輸出: {args.output}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
