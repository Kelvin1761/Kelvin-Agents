from __future__ import annotations
import logging
from tennis_wc.config import get_settings
from .bsd_tennis_provider import BsdTennisProvider
from .espn_provider import EspnTennisProvider
from .official_ranking_provider import OfficialRankingFetchError, OfficialRankingProvider
from .sackmann_ranking_provider import SackmannRankingProvider
from .mock_provider import MockNewsProvider, MockOddsProvider, MockTennisProvider
from .news_provider_base import NewsProvider
from .odds_provider_base import OddsProvider
from .sportsbet_provider import SportsbetOddsProvider
from .tennis_provider_base import TennisProvider

logger = logging.getLogger(__name__)


class CompositeTennisProvider(TennisProvider):
    provider_name = 'composite'

    def __init__(self):
        self.espn = EspnTennisProvider()
        self.official_rankings = OfficialRankingProvider()
        self.sackmann = SackmannRankingProvider()

    def healthcheck(self) -> bool:
        return self.espn.healthcheck()

    def fetch_upcoming_matches(self, date_str: str) -> list[dict]:
        matches = self.espn.fetch_upcoming_matches(date_str)
        for m in matches:
            m['provider'] = self.provider_name
        return matches

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        return self.espn.fetch_historical_matches(start_date, end_date)

    def fetch_match_stats(self, match_id: str) -> dict:
        return self.espn.fetch_match_stats(match_id)

    def fetch_player_profile(self, player_id: str) -> dict:
        return self.espn.fetch_player_profile(player_id)

    def fetch_player_stats(self, player_id: str) -> dict:
        return self.espn.fetch_player_stats(player_id)

    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        official_error: OfficialRankingFetchError | None = None
        try:
            return self.official_rankings.fetch_rankings(tour, date)
        except OfficialRankingFetchError as exc:
            official_error = exc
            logger.info("Official rankings unavailable for %s: %s", tour, exc)
        try:
            return self.sackmann.fetch_rankings(tour, date)
        except Exception as exc:  # noqa: BLE001 - rankings are advisory for daily runs.
            logger.warning("Sackmann rankings unavailable for %s: %s", tour, exc)
            raise OfficialRankingFetchError(
                f"All ranking providers unavailable for {tour}: official={official_error}; sackmann={exc}"
            ) from exc

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        return self.espn.fetch_tournaments(start_date, end_date)

def get_tennis_provider() -> TennisProvider:
    provider = get_settings().tennis_provider
    if provider == 'mock':
        return MockTennisProvider()
    if provider == 'bsd_tennis':
        return BsdTennisProvider()
    if provider == 'espn':
        return EspnTennisProvider()
    if provider == 'composite':
        return CompositeTennisProvider()
    raise ValueError(f'Unsupported tennis provider: {provider}')

def get_odds_provider() -> OddsProvider:
    provider = get_settings().odds_provider
    if provider == 'mock':
        return MockOddsProvider()
    if provider == 'sportsbet':
        return SportsbetOddsProvider()
    raise ValueError(f'Unsupported odds provider: {provider}')

def get_news_provider() -> NewsProvider:
    provider = get_settings().news_provider
    if provider == 'mock':
        return MockNewsProvider()
    raise ValueError(f'Unsupported news provider: {provider}')
