from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in {None, ""} else default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in {None, ""} else default


@dataclass(frozen=True)
class Settings:
    database_url: str
    tennis_provider: str
    odds_provider: str
    news_provider: str
    tennis_api_key: str
    tennis_api_base_url: str
    odds_api_key: str
    odds_api_base_url: str
    sportsbet_api_key: str
    sportsbet_api_base_url: str
    sportsbet_bookmaker_name: str
    sportsbet_source_mode: str
    sportsbet_allowed_scrape_fallback: bool
    data_max_staleness_minutes_odds: int
    data_max_staleness_hours_player_stats: int
    data_max_staleness_hours_rankings: int
    data_max_staleness_hours_tournament_metadata: int
    ai_review_enabled: bool
    min_edge_match_winner: float
    max_stake_units: float
    default_bankroll_units: float

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Stage 1-3 MVP only supports sqlite:/// DATABASE_URL.")
        path = self.database_url.removeprefix("sqlite:///")
        return Path(path).expanduser().resolve()


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///tennis_wc.db"),
        tennis_provider=os.getenv("TENNIS_PROVIDER", "mock"),
        odds_provider=os.getenv("ODDS_PROVIDER", "mock"),
        news_provider=os.getenv("NEWS_PROVIDER", "mock"),
        tennis_api_key=os.getenv("TENNIS_API_KEY", ""),
        tennis_api_base_url=os.getenv("TENNIS_API_BASE_URL", "https://tennis.bzzoiro.com/api"),
        odds_api_key=os.getenv("ODDS_API_KEY", ""),
        odds_api_base_url=os.getenv("ODDS_API_BASE_URL", ""),
        sportsbet_api_key=os.getenv("SPORTSBET_API_KEY", ""),
        sportsbet_api_base_url=os.getenv("SPORTSBET_API_BASE_URL", ""),
        sportsbet_bookmaker_name=os.getenv("SPORTSBET_BOOKMAKER_NAME", "Sportsbet"),
        sportsbet_source_mode=os.getenv("SPORTSBET_SOURCE_MODE", "api"),
        sportsbet_allowed_scrape_fallback=_bool_env("SPORTSBET_ALLOWED_SCRAPE_FALLBACK", False),
        data_max_staleness_minutes_odds=_int_env("DATA_MAX_STALENESS_MINUTES_ODDS", 10),
        data_max_staleness_hours_player_stats=_int_env("DATA_MAX_STALENESS_HOURS_PLAYER_STATS", 24),
        data_max_staleness_hours_rankings=_int_env("DATA_MAX_STALENESS_HOURS_RANKINGS", 168),
        data_max_staleness_hours_tournament_metadata=_int_env(
            "DATA_MAX_STALENESS_HOURS_TOURNAMENT_METADATA", 720
        ),
        ai_review_enabled=_bool_env("AI_REVIEW_ENABLED", True),
        min_edge_match_winner=_float_env("MIN_EDGE_MATCH_WINNER", 0.035),
        max_stake_units=_float_env("MAX_STAKE_UNITS", 1.0),
        default_bankroll_units=_float_env("DEFAULT_BANKROLL_UNITS", 100.0),
    )
