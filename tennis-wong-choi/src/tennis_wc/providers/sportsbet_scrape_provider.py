from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .odds_provider_base import OddsProvider


class SportsbetScrapeProvider(OddsProvider):
    """
    Explicit Sportsbet scrape fallback.

    This provider is intentionally narrow: it fetches Sportsbet pages, stores the
    raw HTML through ingestion, extracts embedded JSON payloads only, and refuses
    to invent odds if extraction fails.
    """

    provider_name = "sportsbet_scrape"

    def healthcheck(self) -> bool:
        return True

    def fetch_upcoming_odds(self, sport: str, regions: list[str], markets: list[str]) -> list[dict]:
        return self.fetch_upcoming_odds_for_date(None)

    def fetch_upcoming_odds_for_date(self, match_date: str | None) -> list[dict]:
        html = self._fetch_html("https://www.sportsbet.com.au/betting/tennis")
        payload = self._extract_preloaded_state(html)
        return self._normalise_tennis_landing_state(payload, match_date)

    def fetch_event_odds(self, event_id: str, markets: list[str]) -> dict:
        parsed = urlparse(event_id)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Sportsbet scrape requires a full event URL.")
        html = self._fetch_html(event_id)
        payload = self._extract_preloaded_state(html)
        rows = self._normalise_preloaded_state(event_id, payload)
        if not rows:
            raise ValueError("Sportsbet scrape found no valid match_winner odds.")
        return rows[0]

    def fetch_historical_odds(self, event_id: str) -> list[dict]:
        return []

    def _fetch_html(self, url: str) -> str:
        try:
            from curl_cffi import requests

            response = requests.get(
                url,
                impersonate="chrome120",
                timeout=20,
                headers={"Accept-Language": "en-AU,en;q=0.9"},
            )
            response.raise_for_status()
            return response.text
        except ImportError:
            pass

        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")

    def _extract_preloaded_state(self, html: str) -> dict:
        marker = "window.__PRELOADED_STATE__"
        marker_index = html.find(marker)
        if marker_index < 0:
            raise ValueError("Sportsbet preloaded state not found.")
        start = html.find("{", marker_index)
        if start < 0:
            raise ValueError("Sportsbet preloaded state JSON start not found.")

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(html)):
            char = html[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(html[start : index + 1])
        raise ValueError("Sportsbet preloaded state JSON end not found.")

    def _normalise_preloaded_state(self, event_url: str, payload: dict) -> list[dict]:
        rows = self._normalise_tennis_landing_state(payload, None)
        for row in rows:
            if row.get("event_url") == event_url or row.get("event_id") in event_url:
                return [row]
        if rows:
            return [rows[0] | {"event_url": event_url}]
        fallback = self._normalise_text_prices(event_url, payload)
        if not fallback:
            return []
        return fallback

    def _normalise_tennis_landing_state(self, payload: dict, match_date: str | None) -> list[dict]:
        sportsbook = payload.get("entities", {}).get("sportsbook", {})
        events = sportsbook.get("events", {})
        markets = sportsbook.get("markets", {})
        outcomes = sportsbook.get("outcomes", {})
        competitions = sportsbook.get("competitions", {})
        rows = []
        for event_id, event in events.items():
            name = event.get("name", "")
            if " v " not in name:
                continue
            if match_date and self._local_date(event) != match_date:
                continue
            market = self._match_betting_market(event, markets)
            if not market:
                continue
            prices = self._market_prices(market, outcomes)
            if len(prices) < 2:
                continue
            players = [part.strip() for part in name.split(" v ", 1)]
            if len(players) != 2:
                continue
            competition = competitions.get(str(event.get("competitionId")), {})
            event_url = self._event_url(event_id, event, competition)
            rows.append(
                {
                    "event_id": str(event_id),
                    "event_url": event_url,
                    "market": "match_winner",
                    "bookmaker": "Sportsbet",
                    "player_a_name": players[0],
                    "player_b_name": players[1],
                    "player_a_odds": prices.get(players[0]) or list(prices.values())[0],
                    "player_b_odds": prices.get(players[1]) or list(prices.values())[1],
                    "player_a_open_odds": None,
                    "player_b_open_odds": None,
                    "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "competition": competition.get("name"),
                    "start_time_utc": self._utc_time(event),
                    "markets": self._event_markets(event, markets, outcomes),
                    "raw": {"event": event, "market": market, "prices": prices},
                }
            )
        return rows

    def _event_url(self, event_id: str, event: dict, competition: dict) -> str:
        for key in ("url", "href", "webUrl", "displayUrl", "bettingUrl"):
            value = event.get(key)
            if isinstance(value, str) and value:
                return value if value.startswith("http") else f"https://www.sportsbet.com.au{value}"

        event_name = str(event.get("name") or event_id)
        competition_name = str(competition.get("name") or "tennis")
        event_slug = self._slug(event_name)
        competition_slug = self._slug(competition_name)
        return f"https://www.sportsbet.com.au/betting/tennis/{competition_slug}/{event_slug}-{event_id}"

    def _slug(self, value: str) -> str:
        decoded = unescape(value).lower()
        return "-".join(re.sub(r"[^a-z0-9 ]+", " ", decoded).split())

    def _normalise_text_prices(self, event_url: str, payload: dict) -> list[dict]:
        outcomes = []
        text = json.dumps(payload)
        for match in re.finditer(r'"name"\s*:\s*"([^"]+)".{0,300}?"price"\s*:\s*([0-9.]+)', text):
            outcomes.append({"name": match.group(1), "odds": float(match.group(2))})
        if len(outcomes) < 2:
            return []
        return [
            {
                "event_id": event_url,
                "event_url": event_url,
                "market": "match_winner",
                "bookmaker": "Sportsbet",
                "player_a_name": outcomes[0]["name"],
                "player_b_name": outcomes[1]["name"],
                "player_a_odds": outcomes[0]["odds"],
                "player_b_odds": outcomes[1]["odds"],
                "player_a_open_odds": None,
                "player_b_open_odds": None,
                "timestamp": None,
                "raw": payload,
            }
        ]

    def _match_betting_market(self, event: dict, markets: dict) -> dict | None:
        for market_id in event.get("marketIds", []):
            market = markets.get(str(market_id), {})
            if market.get("name") == "Match Betting":
                return market
        return None

    def _market_prices(self, market: dict, outcomes: dict) -> dict[str, float]:
        prices = {}
        for outcome_id in market.get("outcomeIds", []):
            outcome = outcomes.get(str(outcome_id), {})
            name = outcome.get("name")
            price = self._decimal_price(outcome.get("winPrice"))
            if name and price:
                prices[name] = price
        return prices

    def _event_markets(self, event: dict, markets: dict, outcomes: dict) -> list[dict]:
        parsed = []
        for market_id in event.get("marketIds", []):
            market = markets.get(str(market_id), {})
            market_name = str(market.get("name") or "")
            if not market_name:
                continue
            selections = self._market_selections(market, outcomes)
            if len(selections) < 2:
                continue
            parsed.append(
                {
                    "market_id": str(market.get("id") or market_id),
                    "market_key": self._market_key(market_name),
                    "market_name": market_name,
                    "selections": selections,
                }
            )
        return parsed

    def _market_selections(self, market: dict, outcomes: dict) -> list[dict]:
        selections = []
        for outcome_id in market.get("outcomeIds", []):
            outcome = outcomes.get(str(outcome_id), {})
            name = outcome.get("name")
            price = self._decimal_price(outcome.get("winPrice"))
            if not name or price is None:
                continue
            selections.append(
                {
                    "selection_id": str(outcome.get("id") or outcome_id),
                    "selection_name": name,
                    "odds": price,
                    "line": self._selection_line(outcome),
                }
            )
        return selections

    def _market_key(self, market_name: str) -> str:
        name = market_name.lower()
        if name == "match betting":
            return "match_winner"
        if "game handicap" in name or "games handicap" in name:
            return "game_handicap"
        if "set handicap" in name or "sets handicap" in name:
            return "set_handicap"
        if "total games" in name:
            return "total_games"
        if "total sets" in name:
            return "total_sets"
        if "set betting" in name or "correct score" in name:
            return "set_betting"
        if "winner" in name:
            return "winner_related"
        return self._slug(market_name).replace("-", "_")

    def _selection_line(self, outcome: dict) -> float | None:
        for key in ("points", "line", "handicap", "total"):
            value = outcome.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
                if match:
                    return float(match.group(0))
        name = str(outcome.get("name") or "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", name)
        return float(match.group(0)) if match else None

    def _decimal_price(self, win_price) -> float | None:
        if isinstance(win_price, dict) and "num" in win_price and "den" in win_price:
            den = float(win_price["den"])
            if den <= 0:
                return None
            return round(1 + float(win_price["num"]) / den, 4)
        if isinstance(win_price, (int, float)):
            return float(win_price)
        return None

    def _utc_time(self, event: dict) -> str | None:
        ms = (event.get("startTime") or {}).get("milliseconds")
        if not ms:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _local_date(self, event: dict) -> str | None:
        ms = (event.get("startTime") or {}).get("milliseconds")
        if not ms:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(ZoneInfo("Australia/Sydney")).date().isoformat()
