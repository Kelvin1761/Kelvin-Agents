from __future__ import annotations

from .tennis_provider_base import TennisProvider


class SportradarTennisProvider(TennisProvider):
    provider_name = "sportradar"

    def healthcheck(self) -> bool:
        raise NotImplementedError("Map exact Sportradar endpoints after credentials are confirmed.")

    def fetch_upcoming_matches(self, date: str) -> list[dict]:
        raise NotImplementedError

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        raise NotImplementedError

    def fetch_match_stats(self, match_id: str) -> dict:
        raise NotImplementedError

    def fetch_player_profile(self, player_id: str) -> dict:
        raise NotImplementedError

    def fetch_player_stats(self, player_id: str) -> dict:
        raise NotImplementedError

    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        raise NotImplementedError

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        raise NotImplementedError
