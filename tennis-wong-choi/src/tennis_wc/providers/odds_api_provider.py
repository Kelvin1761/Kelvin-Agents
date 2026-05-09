from __future__ import annotations

from .odds_provider_base import OddsProvider


class OddsApiProvider(OddsProvider):
    provider_name = "odds_api"

    def healthcheck(self) -> bool:
        raise NotImplementedError("Map exact odds endpoints after provider contract is confirmed.")

    def fetch_upcoming_odds(self, sport: str, regions: list[str], markets: list[str]) -> list[dict]:
        raise NotImplementedError

    def fetch_event_odds(self, event_id: str, markets: list[str]) -> dict:
        raise NotImplementedError

    def fetch_historical_odds(self, event_id: str) -> list[dict]:
        raise NotImplementedError
