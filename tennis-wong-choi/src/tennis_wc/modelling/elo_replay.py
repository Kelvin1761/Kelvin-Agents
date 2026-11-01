"""Deterministic legacy Elo walk shared by ingestion and isolated research.

Rows must arrive in the caller's existing SQL order. No source qualification,
cache selection or clock policy is inferred here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from tennis_wc.features.elo import elo_probability
from tennis_wc.modelling.calibration import elo_k_factor


@dataclass
class EloReplay:
    overall: dict
    surface_ratings: dict
    matches_by_player: dict
    surfaces_seen: set
    history_rows: list
    post_rows: list
    opponent_updates: list


def replay_elo(rows, initial_rating: float = 1500.0,
               k_factor: float | None = None) -> EloReplay:
    overall: dict[int, float] = defaultdict(lambda: initial_rating)
    surface_ratings: dict[int, dict[str, float]] = defaultdict(dict)
    matches_by_player: dict[int, int] = defaultdict(int)
    surface_matches: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    surfaces_seen: set[str] = set()

    def k_for(played: int) -> float:
        return float(k_factor) if k_factor is not None else elo_k_factor(played)

    # The walk is already chronological, so the rating held at the top of
    # each iteration IS the pre-match rating. Capturing it here is what
    # makes an as-of lookup possible at all; without it the only rating
    # anyone can read is the final one, which contains every later result.
    history_rows: list[tuple] = []
    post_rows: list[tuple] = []   # shadow: post-match ratings for v2
    opponent_updates: list[tuple[str, str, float]] = []
    for row in rows:
        winner_id = int(row["player_id"])
        loser_id = int(row["opponent_id"])
        surface = _normalise_surface(row.get("surface"))

        winner_pre = overall[winner_id]
        loser_pre = overall[loser_id]
        match_date = row.get("match_date")
        history_rows.append(
            (winner_id, match_date, "", winner_pre, matches_by_player[winner_id])
        )
        history_rows.append(
            (loser_id, match_date, "", loser_pre, matches_by_player[loser_id])
        )
        winner_expected = elo_probability(winner_pre, loser_pre)
        k_winner = k_for(matches_by_player[winner_id])
        k_loser = k_for(matches_by_player[loser_id])
        overall[winner_id] = winner_pre + k_winner * (1 - winner_expected)
        overall[loser_id] = loser_pre + k_loser * (0 - (1 - winner_expected))
        post_rows.append((winner_id, match_date, "", overall[winner_id],
                          matches_by_player[winner_id] + 1))
        post_rows.append((loser_id, match_date, "", overall[loser_id],
                          matches_by_player[loser_id] + 1))

        winner_surface_pre = None
        loser_surface_pre = None
        if surface:
            surfaces_seen.add(surface)
            winner_surface_pre = surface_ratings[winner_id].get(surface, winner_pre)
            loser_surface_pre = surface_ratings[loser_id].get(surface, loser_pre)
            surface_expected = elo_probability(winner_surface_pre, loser_surface_pre)
            ks_winner = k_for(surface_matches[winner_id][surface])
            ks_loser = k_for(surface_matches[loser_id][surface])
            history_rows.append(
                (winner_id, match_date, surface, winner_surface_pre,
                 surface_matches[winner_id][surface])
            )
            history_rows.append(
                (loser_id, match_date, surface, loser_surface_pre,
                 surface_matches[loser_id][surface])
            )
            surface_ratings[winner_id][surface] = winner_surface_pre + ks_winner * (1 - surface_expected)
            surface_ratings[loser_id][surface] = loser_surface_pre + ks_loser * (0 - (1 - surface_expected))
            post_rows.append((winner_id, match_date, surface,
                              surface_ratings[winner_id][surface],
                              surface_matches[winner_id][surface] + 1))
            post_rows.append((loser_id, match_date, surface,
                              surface_ratings[loser_id][surface],
                              surface_matches[loser_id][surface] + 1))
            surface_matches[winner_id][surface] += 1
            surface_matches[loser_id][surface] += 1

        winner_match_id = row["provider_match_id"]
        loser_match_id = winner_match_id.removesuffix("-winner") + "-loser"
        provider = str(row["source_provider"])
        opponent_updates.append((provider, winner_match_id, loser_pre))
        opponent_updates.append((provider, loser_match_id, winner_pre))
        matches_by_player[winner_id] += 1
        matches_by_player[loser_id] += 1

    return EloReplay(dict(overall), surface_ratings, dict(matches_by_player),
                     surfaces_seen, history_rows, post_rows, opponent_updates)


def _normalise_surface(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower() or None
