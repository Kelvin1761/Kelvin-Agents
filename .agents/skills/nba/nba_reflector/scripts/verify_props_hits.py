#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
verify_props_hits.py — NBA Props 命中自動驗證器

讀取 Results_Brief JSON + 分析報告,自動比對每個 SGM Leg 嘅命中/未中。
供 NBA Reflector 覆盤消費,取代 LLM 手動逐 Leg 對比。

Usage:
  python verify_props_hits.py \
    --results "Results_Brief_2026-04-07.json" \
    --predictions "/path/to/analysis/dir" \
    --output "Props_Verification_2026-04-07.json"

Version: 1.0.0
"""

import argparse
import json
import os
import re
import sys
import io
import glob

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
    """Find a player's actual stats from box score data."""
    name_lower = player_name.lower().strip()
    for p in players_list:
        if p['name'].lower().strip() == name_lower:
            return p
        # Partial match (last name)
        if name_lower.split()[-1] in p['name'].lower():
            return p
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


def extract_legs_from_report(report_path):
    """Extract SGM Legs from an analysis report (V5 or V4 format).

    Returns list of dicts: {player, stat, line, odds, combo_id}
    """
    legs = []
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ⚠️ 無法讀取報告: {report_path} — {e}")
        return legs

    # Pattern: Leg lines like "### 🧩 Leg 1: LeBron James PTS 25+ @1.85"
    # or "Leg 1: LeBron James — Points 25+ @1.85"
    # or "**Leg 1:** LeBron James PTS Over 25.5 @1.85"
    leg_pattern = re.compile(
        r'[Ll]eg\s*\d+[:\s]*'
        r'([A-Z][a-zA-Z\'\-\.\s]+?)\s+'          # Player name
        r'(PTS|REB|AST|3PM|PRA|PR|PA|RA|SB|Points|Rebounds|Assists|Threes Made?|'
        r'Pts\+Reb\+Ast|Pts\+Reb|Pts\+Ast|Reb\+Ast|Stl\+Blk)\s+'  # Stat
        r'(?:Over\s+)?(\d+(?:\.\d+)?)\+?\s*'      # Line
        r'(?:@\s*(\d+\.\d+))?',                    # Odds (optional)
        re.IGNORECASE
    )

    # Detect combo sections
    combo_pattern = re.compile(
        r'(?:###?\s*)?(?:🛡️|🔥|💎|💣)\s*(?:組合|Combo|SGM)\s*(\d+|X)',
        re.IGNORECASE
    )

    current_combo = '?'
    for line in content.split('\n'):
        combo_match = combo_pattern.search(line)
        if combo_match:
            current_combo = combo_match.group(1)

        leg_match = leg_pattern.search(line)
        if leg_match:
            player = leg_match.group(1).strip()
            stat = leg_match.group(2).strip()
            prop_line = float(leg_match.group(3))
            odds = float(leg_match.group(4)) if leg_match.group(4) else None

            legs.append({
                'player': player,
                'stat': stat,
                'stat_normalized': normalize_stat(stat),
                'line': prop_line,
                'odds': odds,
                'combo_id': current_combo,
            })

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
        home = game.get('home', {}).get('team', '').upper()
        away = game.get('away', {}).get('team', '').upper()
        if home and away and (home in basename and away in basename):
            return game
        # Also try reversed
        if home and away and (away in basename and home in basename):
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

    # Find analysis reports (V5 + V4 format)
    pred_dir = args.predictions
    reports = (
        glob.glob(os.path.join(pred_dir, '*_NBA_*_Analysis.md')) +
        glob.glob(os.path.join(pred_dir, 'Game_*_Full_Analysis.md')) +
        glob.glob(os.path.join(pred_dir, 'Game_*_Full_Analysis.txt'))
    )
    print(f"📋 搵到 {len(reports)} 份分析報告")

    all_verified = []
    summary = {
        'total_legs': 0,
        'hits': 0,
        'misses': 0,
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
            else:
                summary['unverified'] += 1

            # By combo
            combo = v.get('combo_id', '?')
            if combo not in summary['by_combo']:
                summary['by_combo'][combo] = {'hits': 0, 'misses': 0, 'total': 0}
            summary['by_combo'][combo]['total'] += 1
            if v['cleared'] is True:
                summary['by_combo'][combo]['hits'] += 1
            elif v['cleared'] is False:
                summary['by_combo'][combo]['misses'] += 1

            # By stat
            stat = v.get('stat_normalized', '?')
            if stat not in summary['by_stat']:
                summary['by_stat'][stat] = {'hits': 0, 'misses': 0, 'total': 0}
            summary['by_stat'][stat]['total'] += 1
            if v['cleared'] is True:
                summary['by_stat'][stat]['hits'] += 1
            elif v['cleared'] is False:
                summary['by_stat'][stat]['misses'] += 1

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
