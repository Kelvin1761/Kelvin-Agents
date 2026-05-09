from __future__ import annotations

from tennis_wc.config import get_settings

from .http import get_json, post_json
from .odds_provider_base import OddsProvider


class SportsbetOddsProvider(OddsProvider):
    """
    Sportsbet odds adapter.

    Default mode uses a structured API/aggregator. Scrape fallback is explicit
    and must be enabled with SPORTSBET_SOURCE_MODE=scrape and
    SPORTSBET_ALLOWED_SCRAPE_FALLBACK=true.
    """

    provider_name = "sportsbet"

    def __init__(self) -> None:
        settings = get_settings()
        self.source_mode = settings.sportsbet_source_mode
        self.scrape_allowed = settings.sportsbet_allowed_scrape_fallback
        if self.source_mode == "scrape" and self.scrape_allowed:
            from .sportsbet_scrape_provider import SportsbetScrapeProvider

            self._fallback = SportsbetScrapeProvider()
            return
        if not settings.sportsbet_api_base_url:
            raise ValueError("SPORTSBET_API_BASE_URL is required for ODDS_PROVIDER=sportsbet.")
        if not settings.sportsbet_api_key:
            raise ValueError("SPORTSBET_API_KEY is required for ODDS_PROVIDER=sportsbet.")
        self.base_url = settings.sportsbet_api_base_url.rstrip("/")
        self.bookmaker_name = settings.sportsbet_bookmaker_name
        self.headers = {"X-API-Key": settings.sportsbet_api_key}

    def healthcheck(self) -> bool:
        if hasattr(self, "_fallback"):
            return self._fallback.healthcheck()
        get_json(f"{self.base_url}/api/fixtures", self.headers)
        return True

    def fetch_upcoming_odds(self, sport: str, regions: list[str], markets: list[str]) -> list[dict]:
        if hasattr(self, "_fallback"):
            return self._fallback.fetch_upcoming_odds(sport, regions, markets)
        fixtures = get_json(f"{self.base_url}/api/fixtures", self.headers)
        rows = []
        if not isinstance(fixtures, dict):
            return rows
        for league_games in fixtures.values():
            if not isinstance(league_games, dict):
                continue
            for fixture in league_games.values():
                if not self._fixture_matches(fixture, sport):
                    continue
                odds_data_id = self._sportsbet_odds_data_id(fixture)
                if not odds_data_id:
                    continue
                odds_body = post_json(f"{self.base_url}/api/odds", self.headers, {"odds_data_id": odds_data_id})
                rows.extend(self._normalise_wagerwise_fixture(fixture, odds_body))
        return rows

    def fetch_upcoming_odds_for_date(self, match_date: str) -> list[dict]:
        if hasattr(self, "_fallback"):
            return self._fallback.fetch_upcoming_odds_for_date(match_date)
        return self.fetch_upcoming_odds("tennis", ["au"], ["match_winner"])

    def fetch_event_odds(self, event_id: str, markets: list[str]) -> dict:
        if hasattr(self, "_fallback"):
            return self._fallback.fetch_event_odds(event_id, markets)
        body = post_json(f"{self.base_url}/api/odds", self.headers, {"odds_data_id": event_id})
        rows = self._normalise_wagerwise_fixture({"game_masterID": event_id, "team_names": {}}, body)
        return rows[0] if rows else {}

    def fetch_historical_odds(self, event_id: str) -> list[dict]:
        if hasattr(self, "_fallback"):
            return self._fallback.fetch_historical_odds(event_id)
        return []

    def _fixture_matches(self, fixture: dict, sport: str) -> bool:
        wanted = sport.lower()
        fixture_sport = str(fixture.get("sport", "")).lower()
        league = str(fixture.get("league_name", "")).lower()
        return wanted in {fixture_sport, league} or "tennis" in {fixture_sport, league}

    def _sportsbet_odds_data_id(self, fixture: dict) -> str | None:
        bookmaker_data = fixture.get("bookmaker_data") or {}
        for key, value in bookmaker_data.items():
            if "sportsbet" in key.lower():
                return str(value)
        return None

    def _normalise_wagerwise_fixture(self, fixture: dict, odds_body: dict | list) -> list[dict]:
        if not isinstance(odds_body, dict):
            return []
        odds_data = odds_body.get("odds_data", odds_body)
        if not isinstance(odds_data, dict):
            return []
        team_names = fixture.get("team_names", {})
        home_name = str(team_names.get("home_team", "")).lower()
        away_name = str(team_names.get("away_team", "")).lower()
        candidates = []
        for market_name, market in odds_data.items():
            market_type = str(market.get("type", "")).lower()
            name = str(market_name).lower()
            if not any(token in market_type or token in name for token in ("moneyline", "match winner", "winner")):
                continue
            candidates.append((name, market))
        if len(candidates) < 2:
            return []

        home_market = self._find_selection(candidates, home_name)
        away_market = self._find_selection(candidates, away_name)
        if not home_market or not away_market:
            return []

        timestamp = fixture.get("last_updated_at") or home_market.get("last_updated_at")
        return [
            {
                "event_id": str(fixture.get("game_masterID") or home_market.get("odds_data_ID")),
                "market": "match_winner",
                "bookmaker": self.bookmaker_name,
                "player_a_odds": float(home_market["odds"]),
                "player_b_odds": float(away_market["odds"]),
                "player_a_open_odds": home_market.get("start_price"),
                "player_b_open_odds": away_market.get("start_price"),
                "timestamp": timestamp,
                "raw": {"fixture": fixture, "odds": odds_body},
            }
        ]

    def _find_selection(self, candidates: list[tuple[str, dict]], participant_name: str) -> dict | None:
        if not participant_name:
            return None
        for market_name, market in candidates:
            if participant_name in market_name:
                return market
        return None
