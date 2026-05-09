from __future__ import annotations

from tennis_wc.config import get_settings

from .bsd_tennis_provider import BsdTennisProvider
from .mock_provider import MockNewsProvider, MockOddsProvider, MockTennisProvider
from .news_provider_base import NewsProvider
from .odds_provider_base import OddsProvider
from .sportsbet_provider import SportsbetOddsProvider
from .tennis_provider_base import TennisProvider


def get_tennis_provider() -> TennisProvider:
    provider = get_settings().tennis_provider
    if provider == "mock":
        return MockTennisProvider()
    if provider == "bsd_tennis":
        return BsdTennisProvider()
    raise ValueError(f"Unsupported tennis provider for MVP: {provider}")


def get_odds_provider() -> OddsProvider:
    provider = get_settings().odds_provider
    if provider == "mock":
        return MockOddsProvider()
    if provider == "sportsbet":
        return SportsbetOddsProvider()
    raise ValueError(f"Unsupported odds provider for MVP: {provider}")


def get_news_provider() -> NewsProvider:
    provider = get_settings().news_provider
    if provider == "mock":
        return MockNewsProvider()
    raise ValueError(f"Unsupported news provider for MVP: {provider}")
