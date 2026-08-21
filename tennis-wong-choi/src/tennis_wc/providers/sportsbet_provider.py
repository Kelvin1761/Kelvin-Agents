from __future__ import annotations

import collections
from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from tennis_wc.config import get_settings

from .http import get_json, post_json
from .odds_provider_base import OddsProvider

logger = logging.getLogger(__name__)

# The market this provider looks for, by the tokens its name may contain. If
# Sportsbet renames the market, every fixture drops and the listing comes back
# empty -- which is byte-for-byte what "the book is not open yet" looks like.
# That ambiguity is the defect this whole go-live phase exists to remove, so the
# tokens are named here and the drop is counted rather than passed over.
MATCH_WINNER_TOKENS = ("moneyline", "match winner", "winner")


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
        # Every `continue` below used to be silent. Seven of them, and an empty
        # return told you nothing about which one fired.
        drops: collections.Counter = collections.Counter()
        if not isinstance(fixtures, dict):
            drops["response_was_not_an_object"] += 1
            self._record_parse_stats(0, drops, rows)
            return rows
        seen = 0
        for league_games in fixtures.values():
            if not isinstance(league_games, dict):
                drops["league_was_not_an_object"] += 1
                continue
            for fixture in league_games.values():
                seen += 1
                if not self._fixture_matches(fixture, sport):
                    drops["not_the_requested_sport"] += 1
                    continue
                odds_data_id = self._sportsbet_odds_data_id(fixture)
                if not odds_data_id:
                    drops["fixture_carried_no_odds_data_id"] += 1
                    continue
                odds_body = post_json(f"{self.base_url}/api/odds", self.headers, {"odds_data_id": odds_data_id})
                parsed = self._normalise_wagerwise_fixture(fixture, odds_body, drops)
                if not parsed:
                    drops["odds_body_yielded_no_row"] += 1
                rows.extend(parsed)
        self._record_parse_stats(seen, drops, rows)
        return rows

    def _record_parse_stats(self, seen: int, drops: collections.Counter,
                            rows: list) -> None:
        """Publish what the response CONTAINED against what was parsed.

        Rule one of this project: never conclude "no data" from an empty result.
        An empty listing is a legitimate output -- the book genuinely is not open
        in the evening -- so the only way to tell that apart from a parser that
        has stopped recognising the market is to count both numbers and say which
        is being quoted.
        """
        self.last_parse_stats = {
            "fixtures_in_response": seen,
            "rows_parsed": len(rows),
            "drops": dict(drops),
        }
        if seen and not rows:
            # Loud on purpose: input present, output empty. This is the shape
            # that ran three days dark while every log line looked normal.
            logger.warning(
                "sportsbet: %d fixtures in the response and 0 rows parsed -- "
                "drops: %s. An empty listing with a NON-empty response is a "
                "parser problem, not a closed book.",
                seen, dict(drops) or "none recorded",
            )
        else:
            logger.info("sportsbet: %d fixtures in the response, %d rows parsed, "
                        "drops: %s", seen, len(rows), dict(drops) or "none")

    def fetch_upcoming_odds_for_date(self, match_date: str) -> list[dict]:
        if hasattr(self, "_fallback"):
            return self._fallback.fetch_upcoming_odds_for_date(match_date)
        return [
            row
            for row in self.fetch_upcoming_odds("tennis", ["au"], ["match_winner"])
            if not row.get("local_date") or row.get("local_date") == match_date
        ]

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

    def _normalise_wagerwise_fixture(self, fixture: dict, odds_body: dict | list,
                                     drops: collections.Counter | None = None) -> list[dict]:
        def dropped(reason: str) -> list:
            if drops is not None:
                drops[reason] += 1
            return []

        if not isinstance(odds_body, dict):
            return dropped("odds_response_was_not_an_object")
        odds_data = odds_body.get("odds_data", odds_body)
        if not isinstance(odds_data, dict):
            return dropped("odds_data_was_not_an_object")
        team_names = fixture.get("team_names", {})
        home_name = str(team_names.get("home_team", "")).lower()
        away_name = str(team_names.get("away_team", "")).lower()
        candidates = []
        markets_seen = 0
        for market_name, market in odds_data.items():
            if not isinstance(market, dict):
                continue
            markets_seen += 1
            market_type = str(market.get("type", "")).lower()
            name = str(market_name).lower()
            if not any(token in market_type or token in name
                       for token in MATCH_WINNER_TOKENS):
                continue
            candidates.append((name, market))
        if len(candidates) < 2:
            # Distinguish "no markets at all" from "markets present, none of
            # them recognised" -- the second is a renamed market, the first is
            # a fixture with no book yet, and they need opposite responses.
            return dropped(
                "no_markets_in_odds_data" if not markets_seen
                else f"markets_present_none_matched_{'/'.join(MATCH_WINNER_TOKENS)}"
            )

        home_market = self._find_selection(candidates, home_name)
        away_market = self._find_selection(candidates, away_name)
        if not home_market or not away_market:
            return dropped("selection_name_did_not_match_either_team")

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
                "start_time_utc": self._fixture_utc_time(fixture),
                "local_date": self._fixture_local_date(fixture),
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

    def _fixture_utc_time(self, fixture: dict) -> str | None:
        parsed = self._fixture_datetime(fixture)
        if not parsed:
            return None
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _fixture_local_date(self, fixture: dict) -> str | None:
        parsed = self._fixture_datetime(fixture)
        if not parsed:
            return None
        return parsed.astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()

    def _fixture_datetime(self, fixture: dict) -> datetime | None:
        for key in ("start_time", "startTime", "commence_time", "commenceTime", "game_time", "date", "match_date"):
            value = fixture.get(key)
            parsed = _parse_datetime(value)
            if parsed:
                return parsed
        return None


def _parse_datetime(value) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
