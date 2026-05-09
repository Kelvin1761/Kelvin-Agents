from __future__ import annotations

from datetime import datetime, timezone

from .news_provider_base import NewsProvider
from .odds_provider_base import OddsProvider
from .tennis_provider_base import TennisProvider


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


PLAYERS = {
    "mock-a": {"id": "mock-a", "name": "Player A", "tour": "ATP", "hand": "R"},
    "mock-b": {"id": "mock-b", "name": "Player B", "tour": "ATP", "hand": "L"},
    "mock-c": {"id": "mock-c", "name": "Player C", "tour": "ATP", "hand": "R"},
    "mock-d": {"id": "mock-d", "name": "Player D", "tour": "ATP", "hand": "R"},
}


class MockTennisProvider(TennisProvider):
    provider_name = "mock"

    def healthcheck(self) -> bool:
        return True

    def fetch_upcoming_matches(self, date: str) -> list[dict]:
        return [
            {
                "id": f"mock-match-{date}-1",
                "tour": "ATP",
                "match_date": date,
                "player_a_id": "mock-a",
                "player_b_id": "mock-b",
                "tournament_id": "mock-rome",
                "round": "Round of 32",
                "market_event_id": f"mock-event-{date}-1",
                "updated_at": _now(),
            }
        ]

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        rows: list[dict] = []
        samples = [
            ("2025-05-10", "mock-a", "mock-c", True, "Clay", "QF", "ATP_1000", 1890, 0.81, 0.28),
            ("2025-06-12", "mock-a", "mock-d", True, "Grass", "R32", "GRAND_SLAM", 1820, 0.79, 0.24),
            ("2025-08-15", "mock-a", "mock-b", False, "Hard", "SF", "ATP_1000", 1850, 0.76, 0.21),
            ("2025-10-03", "mock-a", "mock-c", True, "Hard", "R16", "ATP_500", 1910, 0.80, 0.26),
            ("2026-01-18", "mock-a", "mock-d", True, "Hard", "R64", "GRAND_SLAM", 1840, 0.78, 0.25),
            ("2026-03-19", "mock-a", "mock-b", True, "Hard", "QF", "ATP_1000", 1865, 0.77, 0.23),
            ("2025-04-25", "mock-b", "mock-c", False, "Clay", "R32", "ATP_500", 1900, 0.72, 0.19),
            ("2025-07-05", "mock-b", "mock-d", True, "Grass", "R16", "GRAND_SLAM", 1815, 0.75, 0.20),
            ("2025-09-08", "mock-b", "mock-c", False, "Hard", "R16", "GRAND_SLAM", 1930, 0.73, 0.18),
            ("2025-11-01", "mock-b", "mock-d", True, "Hard", "QF", "ATP_250", 1800, 0.74, 0.22),
            ("2026-02-16", "mock-b", "mock-c", False, "Hard", "ATP 500 Final", "ATP_500", 1925, 0.71, 0.17),
            ("2026-04-20", "mock-b", "mock-d", True, "Clay", "R32", "ATP_1000", 1825, 0.73, 0.20),
        ]
        for idx, item in enumerate(samples, start=1):
            date, player_id, opponent_id, won, surface, round_name, level, opponent_elo, hold, brk = item
            if not (start_date <= date <= end_date):
                continue
            rows.append(
                {
                    "id": f"mock-hist-{idx}",
                    "tour": "ATP",
                    "match_date": date,
                    "player_id": player_id,
                    "opponent_id": opponent_id,
                    "won": won,
                    "surface": surface,
                    "tournament_id": f"mock-{level.lower()}",
                    "tournament_level": level,
                    "round": round_name,
                    "format": "BO5" if level == "GRAND_SLAM" else "BO3",
                    "opponent_elo": opponent_elo,
                    "hold_rate": hold,
                    "break_rate": brk,
                    "first_serve_points_won_pct": hold - 0.08,
                    "second_serve_points_won_pct": hold - 0.24,
                    "return_points_won_pct": brk + 0.15,
                    "tiebreak_won": won,
                    "deciding_set_won": won,
                    "lost_first_set": not won,
                    "comeback_after_losing_first_set": False,
                    "updated_at": _now(),
                }
            )
        return rows

    def fetch_match_stats(self, match_id: str) -> dict:
        return {"id": match_id, "status": "not_started", "updated_at": _now()}

    def fetch_player_profile(self, player_id: str) -> dict:
        return PLAYERS[player_id] | {"updated_at": _now()}

    def fetch_player_stats(self, player_id: str) -> dict:
        stats = {
            "mock-a": {"overall_elo": 1920, "surface_elo": {"Hard": 1955, "Clay": 1905, "Grass": 1880}},
            "mock-b": {"overall_elo": 1850, "surface_elo": {"Hard": 1805, "Clay": 1830, "Grass": 1865}},
            "mock-c": {"overall_elo": 1910, "surface_elo": {"Hard": 1920, "Clay": 1945, "Grass": 1810}},
            "mock-d": {"overall_elo": 1820, "surface_elo": {"Hard": 1815, "Clay": 1800, "Grass": 1875}},
        }
        return {"player_id": player_id, **stats[player_id], "updated_at": _now()}

    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        ranking_date = date or "2026-05-08"
        return [
            {"player_id": "mock-a", "tour": tour, "ranking_date": ranking_date, "rank": 18, "ranking_points": 2310},
            {"player_id": "mock-b", "tour": tour, "ranking_date": ranking_date, "rank": 42, "ranking_points": 1180},
            {"player_id": "mock-c", "tour": tour, "ranking_date": ranking_date, "rank": 9, "ranking_points": 3980},
            {"player_id": "mock-d", "tour": tour, "ranking_date": ranking_date, "rank": 76, "ranking_points": 770},
            {"player_id": "mock-a", "tour": tour, "ranking_date": "2025-05-01", "rank": 24, "ranking_points": 1900},
            {"player_id": "mock-b", "tour": tour, "ranking_date": "2025-05-01", "rank": 55, "ranking_points": 950},
            {"player_id": "mock-c", "tour": tour, "ranking_date": "2025-05-01", "rank": 12, "ranking_points": 3100},
            {"player_id": "mock-d", "tour": tour, "ranking_date": "2025-05-01", "rank": 88, "ranking_points": 620},
        ]

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        return [
            {
                "id": "mock-rome",
                "name": "Rome Masters",
                "tour": "ATP",
                "level": "ATP_1000",
                "surface": "Clay",
                "indoor_outdoor": "Outdoor",
                "start_date": start_date,
                "end_date": end_date,
                "updated_at": _now(),
            },
            {
                "id": "mock-grand_slam",
                "name": "Mock Slam",
                "tour": "ATP",
                "level": "GRAND_SLAM",
                "surface": "Hard",
                "indoor_outdoor": "Outdoor",
                "start_date": start_date,
                "end_date": end_date,
                "updated_at": _now(),
            },
        ]


class MockOddsProvider(OddsProvider):
    provider_name = "mock"

    def healthcheck(self) -> bool:
        return True

    def fetch_upcoming_odds(self, sport: str, regions: list[str], markets: list[str]) -> list[dict]:
        timestamp = _now()
        return [
            {
                "event_id": "mock-event-2026-05-08-1",
                "market": "match_winner",
                "bookmaker": "mockbook",
                "player_a_odds": 2.08,
                "player_b_odds": 1.84,
                "player_a_open_odds": 2.18,
                "player_b_open_odds": 1.76,
                "timestamp": timestamp,
                "updated_at": timestamp,
            }
        ]

    def fetch_event_odds(self, event_id: str, markets: list[str]) -> dict:
        return self.fetch_upcoming_odds("tennis_atp", ["us"], markets)[0] | {"event_id": event_id}

    def fetch_historical_odds(self, event_id: str) -> list[dict]:
        return []


class MockNewsProvider(NewsProvider):
    provider_name = "mock"

    def healthcheck(self) -> bool:
        return True

    def fetch_player_news(self, player_name: str, since_date: str | None = None) -> list[dict]:
        return [{"player_name": player_name, "risk": "UNKNOWN", "timestamp": _now()}]
