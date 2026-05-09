from __future__ import annotations

from .odds_api_provider import OddsApiProvider


class BetfairProvider(OddsApiProvider):
    provider_name = "betfair"
