from __future__ import annotations

from abc import abstractmethod

from .base import BaseProvider


class OddsProvider(BaseProvider):
    @abstractmethod
    def fetch_upcoming_odds(self, sport: str, regions: list[str], markets: list[str]) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_event_odds(self, event_id: str, markets: list[str]) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_historical_odds(self, event_id: str) -> list[dict]:
        raise NotImplementedError
