from __future__ import annotations
import csv
import logging
from io import StringIO
from urllib.request import Request, urlopen
from tennis_wc.providers.tennis_provider_base import TennisProvider

logger = logging.getLogger(__name__)

class SackmannRankingProvider(TennisProvider):
    provider_name = 'sackmann_ranking'

    def __init__(self):
        self._player_cache = {}

    def healthcheck(self) -> bool:
        return True

    def _load_players(self, tour: str):
        if tour in self._player_cache:
            return
        url = f'https://raw.githubusercontent.com/JeffSackmann/tennis_{tour.lower()}/{tour.lower()}_players.csv'
        if tour.upper() == 'ATP':
             url = 'https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_players.csv'
        elif tour.upper() == 'WTA':
             url = 'https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_players.csv'
        
        try:
            logger.info(f'Loading player names from {url}')
            request = Request(url, headers={'User-Agent': 'Antigravity/0.1'})
            with urlopen(request, timeout=30) as response:
                text = response.read().decode('utf-8-sig')
            reader = csv.DictReader(StringIO(text))
            for row in reader:
                full_name = f"{row.get('name_first', '')} {row.get('name_last', '')}".strip()
                self._player_cache[row['player_id']] = full_name
        except Exception as e:
            logger.error(f'Failed to load player names: {e}')

    def fetch_rankings(self, tour: str, date_str: str | None = None) -> list[dict]:
        self._load_players(tour)
        url = f'https://raw.githubusercontent.com/JeffSackmann/tennis_{tour.lower()}/master/{tour.lower()}_rankings_current.csv'
        try:
            request = Request(url, headers={'User-Agent': 'Antigravity/0.1'})
            with urlopen(request, timeout=20) as response:
                text = response.read().decode('utf-8-sig')
            rows = list(csv.DictReader(StringIO(text)))
            
            results = []
            for row in rows[:500]:
                player_id = row['player']
                name = self._player_cache.get(player_id, f'Unknown Sackmann Player {player_id}')
                results.append({
                    'player_id': player_id,
                    'name': name,
                    'player_name': name, # backwards compatibility
                    'tour': tour,
                    'ranking_date': row['ranking_date'],
                    'rank': int(row['rank']),
                    'ranking_points': int(row['points']),
                    'raw': row
                })
            return results
        except Exception as e:
            logger.error(f'Failed to fetch rankings: {e}')
            return []

    def fetch_upcoming_matches(self, date_str: str) -> list[dict]:
        return []

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        return []

    def fetch_match_stats(self, match_id: str) -> dict:
        return {}

    def fetch_player_profile(self, player_id: str) -> dict:
        return {}

    def fetch_player_stats(self, player_id: str) -> dict:
        return {}

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        return []

