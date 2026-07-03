from __future__ import annotations
import csv
import logging
from datetime import date
from io import StringIO
from urllib.request import Request, urlopen
from tennis_wc.providers.tennis_provider_base import TennisProvider

logger = logging.getLogger(__name__)


class RankingFetchError(RuntimeError):
    pass


class SackmannRankingProvider(TennisProvider):
    provider_name = 'sackmann_ranking'

    def __init__(self):
        self._player_cache: dict[str, dict[str, str]] = {}

    def healthcheck(self) -> bool:
        return True

    def _load_players(self, tour: str):
        tour = tour.upper()
        if tour in self._player_cache:
            return
        prefix = tour.lower()
        url = f'https://raw.githubusercontent.com/JeffSackmann/tennis_{prefix}/master/{prefix}_players.csv'
        try:
            logger.info(f'Loading player names from {url}')
            text = self._fetch_csv_text(url, timeout=30)
            reader = csv.DictReader(StringIO(text))
            cache: dict[str, str] = {}
            for row in reader:
                player_id = row.get('player_id')
                if not player_id:
                    continue
                first = row.get('first_name') or row.get('name_first') or ''
                last = row.get('last_name') or row.get('name_last') or ''
                full_name = f"{first} {last}".strip()
                if full_name:
                    cache[player_id] = full_name
            self._player_cache[tour] = cache
        except Exception as e:
            logger.error(f'Failed to load player names: {e}')
            self._player_cache[tour] = {}

    def fetch_rankings(self, tour: str, date_str: str | None = None) -> list[dict]:
        tour = tour.upper()
        self._load_players(tour)
        url = self._ranking_url(tour, date_str)
        try:
            text = self._fetch_csv_text(url, timeout=20)
            rows = list(csv.DictReader(StringIO(text)))
            ranking_date = self._latest_ranking_date(rows, date_str)
            if not ranking_date:
                raise RankingFetchError(f'No ranking rows found in {url}')

            player_names = self._player_cache.get(tour, {})
            results = []
            for row in rows:
                if _normalise_date(row.get('ranking_date')) != ranking_date:
                    continue
                player_id = row.get('player_id') or row.get('player')
                rank = _int_or_none(row.get('ranking') or row.get('rank'))
                if not player_id or rank is None:
                    continue
                name = player_names.get(player_id, f'Unknown Sackmann Player {player_id}')
                results.append(
                    {
                    'player_id': player_id,
                    'name': name,
                    'player_name': name,
                    'tour': tour,
                    'ranking_date': ranking_date,
                    'rank': rank,
                    'ranking_points': _int_or_none(row.get('ranking_points') or row.get('points')),
                    'raw': row
                    }
                )
            if not results:
                raise RankingFetchError(f'No parseable ranking rows found in {url} for {ranking_date}')
            return sorted(results, key=lambda item: item['rank'])[:500]
        except Exception as e:
            logger.error(f'Failed to fetch rankings: {e}')
            raise RankingFetchError(str(e)) from e

    def _ranking_url(self, tour: str, date_str: str | None) -> str:
        prefix = tour.lower()
        year = _year_from_date(date_str) or date.today().year
        decade = (year % 100) // 10 * 10
        return f'https://raw.githubusercontent.com/JeffSackmann/tennis_{prefix}/master/{prefix}_rankings_{decade:02d}s.csv'

    def _latest_ranking_date(self, rows: list[dict], date_str: str | None) -> str | None:
        cutoff = _normalise_date(date_str)
        dates = sorted(
            {
                normalised
                for row in rows
                if (normalised := _normalise_date(row.get('ranking_date')))
            }
        )
        if not dates:
            return None
        if cutoff:
            eligible = [value for value in dates if value <= cutoff]
            if eligible:
                return eligible[-1]
        return dates[-1]

    def _fetch_csv_text(self, url: str, timeout: int) -> str:
        request = Request(url, headers={'User-Agent': 'Antigravity/0.1'})
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode('utf-8-sig')
        if text.lstrip().startswith('<!DOCTYPE') or text.strip() == '404: Not Found':
            raise RankingFetchError(f'Unexpected non-CSV response from {url}')
        return text

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


def _year_from_date(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except (TypeError, ValueError):
        return None


def _normalise_date(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    if len(value) == 8 and value.isdigit():
        return f'{value[:4]}-{value[4:6]}-{value[6:8]}'
    return value


def _int_or_none(value) -> int | None:
    if value in {None, ''}:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
