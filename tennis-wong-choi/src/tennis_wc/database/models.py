from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    id: int
    tour: str
    match_date: str
    tournament_id: int
    player_a_id: int
    player_b_id: int
    round: str
    market_event_id: str | None
