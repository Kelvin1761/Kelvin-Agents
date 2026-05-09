from __future__ import annotations

from datetime import date, timedelta

from tennis_wc.config import get_settings

from .http import get_json
from .tennis_provider_base import TennisProvider


class BsdTennisProvider(TennisProvider):
    """
    Adapter for BSD Tennis API.

    Docs checked 2026-05-08:
    - Base URL: https://tennis.bzzoiro.com/api/
    - GET-only JSON API
    - Token auth via Authorization: Token YOUR_API_KEY
    - Endpoints include tournaments, players, matches, live, predictions, rankings.
    """

    provider_name = "bsd_tennis"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.tennis_api_key:
            raise ValueError("TENNIS_API_KEY is required for TENNIS_PROVIDER=bsd_tennis.")
        self.base_url = settings.tennis_api_base_url.rstrip("/")
        self.headers = {"Authorization": f"Token {settings.tennis_api_key}"}

    def _get(self, endpoint: str, params: dict | None = None) -> dict | list:
        return get_json(f"{self.base_url}/{endpoint.strip('/')}/", self.headers, params)

    def _paged_results(self, endpoint: str, params: dict | None = None, max_pages: int = 10) -> list[dict]:
        collected: list[dict] = []
        page = 1
        while page <= max_pages:
            try:
                body = self._get(endpoint, {**(params or {}), "page": page})
            except RuntimeError:
                if collected:
                    break
                raise
            rows = _results(body)
            collected.extend(rows)
            if not isinstance(body, dict) or not body.get("next"):
                break
            page += 1
        return collected

    def healthcheck(self) -> bool:
        try:
            self._get("rankings", {"type": "ATP"})
        except RuntimeError:
            try:
                self._get("tournaments", None)
            except RuntimeError:
                return False
        return True

    def fetch_upcoming_matches(self, date: str) -> list[dict]:
        lookup_dates = [date, (date_fromisoformat(date) - timedelta(days=1)).isoformat()]
        seen = set()
        rows = []
        for lookup_date in lookup_dates:
            for row in self._paged_results("matches", {"date_from": lookup_date, "date_to": lookup_date, "status": "scheduled"}):
                row_id = str(row.get("id"))
                if row_id in seen:
                    continue
                seen.add(row_id)
                normalised = self._normalise_match(row)
                normalised["analysis_date"] = date
                rows.append(normalised)
        return rows

    def fetch_historical_matches(self, start_date: str, end_date: str) -> list[dict]:
        body = self._paged_results("matches", {"date_from": start_date, "date_to": end_date, "status": "finished"}, max_pages=3)
        rows = []
        for row in body:
            rows.append(self._normalise_history_match(row, 1))
            rows.append(self._normalise_history_match(row, 2))
        return rows

    def fetch_match_stats(self, match_id: str) -> dict:
        body = self._get(f"matches/{match_id}", None)
        return body if isinstance(body, dict) else {"results": body}

    def fetch_player_profile(self, player_id: str) -> dict:
        body = self._get(f"players/{player_id}", None)
        if isinstance(body, dict) and "results" in body:
            results = body["results"]
            body = results[0] if results else {}
        return self._normalise_player(body if isinstance(body, dict) else {})

    def fetch_player_stats(self, player_id: str) -> dict:
        return self.fetch_player_profile(player_id)

    def fetch_rankings(self, tour: str, date: str | None = None) -> list[dict]:
        rows = self._paged_results("rankings", {"type": tour, "date": date, "top": 300}, max_pages=6)
        if date and not rows:
            rows = self._paged_results("rankings", {"type": tour, "top": 300}, max_pages=6)
        return [self._normalise_ranking(row, tour, date) for row in rows]

    def fetch_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        body = self._get("tournaments", None)
        return [self._normalise_tournament(row, start_date, end_date) for row in _results(body)]

    def _normalise_player(self, row: dict) -> dict:
        ranking = row.get("current_ranking") or {}
        tour = row.get("tour") or row.get("type") or row.get("ranking_type") or ranking.get("type")
        if not tour:
            tour = "WTA" if row.get("gender") == "F" else "ATP"
        return {
            "id": str(row.get("id") or row.get("player_id")),
            "name": row.get("name") or row.get("full_name") or row.get("player_name") or "Unknown Player",
            "tour": _normalise_tour(tour),
            "current_rank": ranking.get("position"),
            "hand": row.get("plays") or row.get("hand"),
            "raw": row,
        }

    def _normalise_ranking(self, row: dict, tour: str, ranking_date: str | None) -> dict:
        player = row.get("player") or row.get("player_obj") or {}
        player_id = row.get("player_id") or player.get("id") or row.get("id")
        name = row.get("player_name") or player.get("name") or row.get("name")
        return {
            "player_id": str(player_id),
            "player_name": name,
            "tour": row.get("type") or row.get("tour") or tour,
            "ranking_date": row.get("ranking_date") or row.get("date") or ranking_date,
            "rank": int(row.get("rank") or row.get("ranking") or row.get("position")),
            "ranking_points": row.get("points") or row.get("ranking_points"),
            "raw": row,
        }

    def _normalise_tournament(self, row: dict, start_date: str, end_date: str) -> dict:
        return {
            "id": str(row.get("id")),
            "name": row.get("name") or row.get("tournament_name") or "Unknown Tournament",
            "tour": _normalise_tour(row.get("tour") or row.get("type") or row.get("circuit")),
            "level": _normalise_level(row.get("category") or row.get("level") or row.get("tournament_level")),
            "surface": row.get("surface") or None,
            "indoor_outdoor": row.get("indoor_outdoor") or row.get("environment"),
            "start_date": row.get("start_date") or start_date,
            "end_date": row.get("end_date") or end_date,
            "raw": row,
        }

    def _normalise_match(self, row: dict) -> dict:
        tournament = row.get("tournament") or {}
        player1 = row.get("player1_obj") or row.get("player1") or row.get("home_player") or row.get("player_a") or {}
        player2 = row.get("player2_obj") or row.get("player2") or row.get("away_player") or row.get("player_b") or {}
        match_date = str(row.get("date") or row.get("start_time") or row.get("match_date") or "")[:10]
        return {
            "id": str(row.get("id")),
            "tour": _normalise_tour(row.get("tour") or tournament.get("tour") or tournament.get("type") or tournament.get("circuit")),
            "match_date": match_date,
            "player_a_id": str(row.get("player1_id") or player1.get("id")),
            "player_b_id": str(row.get("player2_id") or player2.get("id")),
            "player_a_name": row.get("player1_name") or player1.get("name"),
            "player_b_name": row.get("player2_name") or player2.get("name"),
            "player_a_current_rank": (player1.get("current_ranking") or {}).get("position"),
            "player_b_current_rank": (player2.get("current_ranking") or {}).get("position"),
            "tournament_id": str(row.get("tournament_id") or tournament.get("id")),
            "tournament_name": tournament.get("name"),
            "tournament_level": _normalise_level(tournament.get("category") or tournament.get("level")),
            "surface": tournament.get("surface") or None,
            "indoor_outdoor": tournament.get("indoor_outdoor") or tournament.get("environment"),
            "round": row.get("round") or row.get("round_name") or "UNKNOWN",
            "market_event_id": str(row.get("id")),
            "updated_at": row.get("updated_at"),
            "raw": row,
        }

    def _normalise_history_match(self, row: dict, player_number: int) -> dict:
        match = self._normalise_match(row)
        player_id = match["player_a_id"] if player_number == 1 else match["player_b_id"]
        opponent_id = match["player_b_id"] if player_number == 1 else match["player_a_id"]
        p1_sets = row.get("player1_sets")
        p2_sets = row.get("player2_sets")
        winner_id = _winner_id(row, match)
        if winner_id is None and p1_sets is not None and p2_sets is not None:
            winner_id = match["player_a_id"] if p1_sets > p2_sets else match["player_b_id"]
        tournament = row.get("tournament") or {}
        prefix = "p1" if player_number == 1 else "p2"
        sets_detail = row.get("sets_detail") or []
        return {
            "id": f"{match['id']}-{player_number}",
            "tour": match["tour"],
            "match_date": match["match_date"],
            "player_id": player_id,
            "opponent_id": opponent_id,
            "player_name": match["player_a_name"] if player_number == 1 else match["player_b_name"],
            "opponent_name": match["player_b_name"] if player_number == 1 else match["player_a_name"],
            "player_current_rank": match["player_a_current_rank"] if player_number == 1 else match["player_b_current_rank"],
            "opponent_current_rank": match["player_b_current_rank"] if player_number == 1 else match["player_a_current_rank"],
            "won": winner_id == player_id if winner_id is not None else False,
            "surface": row.get("surface") or tournament.get("surface") or None,
            "tournament_id": match["tournament_id"],
            "tournament_level": _normalise_level(tournament.get("category") or tournament.get("level")),
            "round": match["round"],
            "format": row.get("format") or "BO3",
            "opponent_elo": row.get("opponent_elo"),
            "hold_rate": None,
            "break_rate": None,
            "first_serve_points_won_pct": row.get(f"{prefix}_first_serve_won_pct"),
            "second_serve_points_won_pct": row.get(f"{prefix}_second_serve_won_pct"),
            "return_points_won_pct": None,
            "tiebreak_won": _tiebreak_won(sets_detail, player_number),
            "deciding_set_won": _deciding_set_won(sets_detail, player_number),
            "lost_first_set": _lost_first_set(sets_detail, player_number),
            "comeback_after_losing_first_set": _comeback_after_losing_first_set(sets_detail, player_number, winner_id == player_id if winner_id is not None else False),
            "raw": row,
        }


def _results(body: dict | list) -> list[dict]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        results = body.get("results", body.get("data", []))
        return results if isinstance(results, list) else []
    return []


def date_fromisoformat(value: str) -> date:
    return date.fromisoformat(value)


def _normalise_level(value: str | None) -> str:
    raw = str(value or "UNKNOWN").upper().replace(" ", "_").replace("-", "_")
    mapping = {
        "ATP_250": "ATP_250",
        "ATP_500": "ATP_500",
        "MASTERS_1000": "ATP_1000",
        "ATP_1000": "ATP_1000",
        "WTA_250": "WTA_250",
        "WTA_500": "WTA_500",
        "WTA_1000": "WTA_1000",
        "GRAND_SLAM": "GRAND_SLAM",
        "SLAM": "GRAND_SLAM",
        "ATP_FINALS": "ATP_FINALS",
        "WTA_FINALS": "WTA_FINALS",
    }
    return mapping.get(raw, "UNKNOWN")


def _normalise_tour(value: str | None) -> str:
    raw = str(value or "ATP").upper()
    return "WTA" if raw == "WTA" else "ATP"


def _winner_id(row: dict, match: dict) -> str | None:
    winner = row.get("winner") or {}
    value = row.get("winner_id") or winner.get("id")
    return str(value) if value is not None else None


def _set_score(sets_detail: list[dict], player_number: int, index: int) -> tuple[int, int] | None:
    if index >= len(sets_detail):
        return None
    row = sets_detail[index]
    own_key = "p1" if player_number == 1 else "p2"
    opp_key = "p2" if player_number == 1 else "p1"
    if row.get(own_key) is None or row.get(opp_key) is None:
        return None
    return int(row[own_key]), int(row[opp_key])


def _lost_first_set(sets_detail: list[dict], player_number: int) -> bool | None:
    score = _set_score(sets_detail, player_number, 0)
    return None if score is None else score[0] < score[1]


def _deciding_set_won(sets_detail: list[dict], player_number: int) -> bool | None:
    if len(sets_detail) < 3:
        return None
    score = _set_score(sets_detail, player_number, len(sets_detail) - 1)
    return None if score is None else score[0] > score[1]


def _comeback_after_losing_first_set(sets_detail: list[dict], player_number: int, won: bool) -> bool | None:
    lost_first = _lost_first_set(sets_detail, player_number)
    if lost_first is None:
        return None
    return bool(lost_first and won)


def _tiebreak_won(sets_detail: list[dict], player_number: int) -> bool | None:
    saw_tiebreak = False
    for index in range(len(sets_detail)):
        score = _set_score(sets_detail, player_number, index)
        if score is None:
            continue
        own, opp = score
        if max(own, opp) >= 7 and abs(own - opp) <= 2:
            saw_tiebreak = True
            if own > opp:
                return True
    return False if saw_tiebreak else None
