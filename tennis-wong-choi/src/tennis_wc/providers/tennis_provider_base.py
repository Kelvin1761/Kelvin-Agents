from __future__ import annotations

from abc import abstractmethod

from .base import BaseProvider


class TennisProvider(BaseProvider):
    @abstractmethod
    def fetch_upcoming_matches(self, date: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_match_stats(self, match_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_player_profile(self, player_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_player_stats(self, player_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        raise NotImplementedError
