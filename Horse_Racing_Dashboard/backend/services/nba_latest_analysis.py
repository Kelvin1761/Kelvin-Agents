"""Latest NBA game analysis remains visible independently of BET eligibility."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

NBA_DIR = Path(__file__).resolve().parents[3] / '.agents/skills/nba'


def _read(path):
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _review_price(candidate, odds):
    quote = candidate.get('sgm_quote') or {}
    try:
        added = str(NBA_DIR) not in sys.path
        if added:
            sys.path.insert(0, str(NBA_DIR))
        from nba_sgm_quote import quote_valid
        from nba_availability import aware_time
        captured = aware_time(quote.get('captured_at'))
        now = datetime.now(timezone.utc)
        if not captured or captured > now or not quote_valid(quote, odds, candidate.get('legs', []), now=captured):
            return None, 'unverified'
        return quote['decimal_odds'], 'current' if quote_valid(quote, odds, candidate['legs'], now=now) else 'expired'
    except (ImportError, KeyError, TypeError, ValueError, AttributeError):
        return None, 'unverified'
    finally:
        if added:
            sys.path.remove(str(NBA_DIR))


def build_latest_analysis(folder, target_date, firewall, saved_reports=()):
    folder = Path(folder)
    saved = {row[0]: row for row in saved_reports}
    games = []
    for odds_path in sorted(folder.glob('Sportsbet_Odds_*.json')):
        odds = _read(odds_path)
        if (odds.get('target_analysis_date') or odds.get('event_local_date')) != target_date:
            continue
        tag = odds_path.stem.removeprefix('Sportsbet_Odds_')
        props = odds.get('player_props') or {}
        names = {name for players in props.values() if isinstance(players, dict) for name in players}
        game = {'game_tag': tag, 'event_name': tag.replace('_', ' @ '),
                'start_time_utc': odds.get('event_start_time'), 'status': 'awaiting_analysis',
                'status_reason': '等候最新分析。', 'priced_players': len(names),
                'formal_sgm_count': 0, 'review_candidates': [], 'player_markets': []}
        if not names:
            game.update(status='waiting_player_markets', status_reason='球員市場未開，會保留重試。')
        elif len(names) < 3:
            game.update(status='data_insufficient', status_reason='只有少於三名球員盤口，資料未達完整分析要求。')
        report = folder/f'Game_{tag}_Full_Analysis.md'
        accepted = False
        if report.is_file():
            accepted, _ = firewall(report, odds_path)
        if accepted is not True and tag in saved:
            _, report, odds_path, _ = saved[tag]
            odds = _read(odds_path)
            accepted = True
        if accepted is True:
            content = report.read_text(encoding='utf-8')
            sidecar = _read(Path(str(report)+'.market_legs.json'))
            if sidecar.get('report_sha256') == hashlib.sha256(content.encode()).hexdigest():
                legs = [row for row in sidecar.get('legs', []) if isinstance(row, dict)
                        and _number(row.get('p_final')) and _number(row.get('price'))
                        and 0 <= row['p_final'] <= 1 and row['price'] > 1]
                markets = [{'player': row.get('player'), 'market': row.get('market'), 'line': row.get('line'),
                            'odds': row['price'], 'model_probability': row['p_final'],
                            'l10_hit_rate': row.get('p_l10_base_rate'),
                            'expected_value': row['p_final']*row['price']-1} for row in legs]
                markets.sort(key=lambda row: (-row['expected_value'], str(row['player']), str(row['market']), row['line']))
                reviews = []
                for item in sidecar.get('review_candidates', [])[:3]:
                    if not isinstance(item, dict) or item.get('analysis_only') is not True or item.get('decision') != 'OBSERVE':
                        continue
                    candidate_legs = item.get('legs')
                    max_legs = 4 if item.get('version') == 'banker-ev-shadow-v1' else 3
                    if (not isinstance(candidate_legs, list) or not 2 <= len(candidate_legs) <= max_legs
                            or any(not isinstance(leg, dict) or not leg.get('selection')
                                   or not _number(leg.get('odds')) or leg['odds'] <= 1 for leg in candidate_legs)
                            or not _number(item.get('model_probability'))
                            or not 0 <= item['model_probability'] <= 1):
                        continue
                    price, quote_status = _review_price(item, odds)
                    reviews.append({**item, 'odds': price, 'quote_status': quote_status,
                                    'analysis_only': True, 'decision': 'OBSERVE',
                                    'expected_value': item.get('expected_value') if price is not None else None})
                game.update(status='analysed', status_reason='賽前分析已保存。',
                            analysis_time=((sidecar.get('availability') or {}).get('meta', {}).get('availability', {}).get('captured_at')
                                           or sidecar.get('odds_extraction_time')),
                            market_count=len(markets), positive_ev_count=sum(row['expected_value'] > 0 for row in markets),
                            formal_sgm_count=len(sidecar.get('combos', [])),
                            diagnostics=sidecar.get('selection_diagnostics', {}), review_candidates=reviews,
                            player_markets=markets, report_markdown=content[:100000],
                            injuries=(sidecar.get('availability') or {}).get('injuries', {}),
                            source_files=[str(report.relative_to(folder)), str(odds_path.relative_to(folder))])
            else:
                game.update(status='source_invalid', status_reason='分析側檔與報告不一致，等候重新驗證。')
        elif report.is_file() and game['status'] == 'awaiting_analysis':
            game.update(status='refresh_required', status_reason='資料或發佈驗證需刷新，暫不顯示未驗證選擇。')
        games.append(game)
    games.sort(key=lambda game: (game['status'] != 'analysed', str(game.get('start_time_utc') or '9999'), game['game_tag']))
    return {'event_date': target_date, 'games': games,
            'coverage': {'scheduled_games': len(games), 'analysed_games': sum(g['status']=='analysed' for g in games),
                         'pending_games': sum(g['status']!='analysed' for g in games),
                         'review_candidates': sum(len(g['review_candidates']) for g in games),
                         'formal_sgm_count': sum(g['formal_sgm_count'] for g in games)}}
