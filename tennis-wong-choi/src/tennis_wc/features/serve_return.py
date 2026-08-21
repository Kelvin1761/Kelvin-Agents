"""Walk-forward serve and return profiles.

Stage 1 of the serve-features plan.  Seven of the nine prop families derive
from a single scalar, ``P(match win)``, and the serve and return columns that
should drive them have sat unread in ``player_match_history`` -- one function,
``games_model.combined_hold``, touches any of them.

Everything here reads strictly before ``as_of_date``.  Sample counts travel
with the values because half the priced board has no serve history at all: a
caller must be able to tell "78% hold over 22 matches" from "78% over two", and
the model that consumes this has to degrade rather than pretend.
"""
from __future__ import annotations

from dataclasses import dataclass

# Long enough to be stable, short enough to track form. combined_hold uses 20
# on the same column; matching it keeps the two comparable while this is being
# validated against it.
DEFAULT_WINDOW = 25
MIN_SAMPLES = 5

_SERVE_COLUMNS = (
    "hold_rate",
    "first_serve_points_won_pct",
    "second_serve_points_won_pct",
    "ace_count",
    "service_games_played",
    "double_fault_count",
    "break_points_saved",
    "break_points_faced",
)
_RETURN_COLUMNS = (
    "break_rate",
    "return_points_won_pct",
    "break_points_converted",
    "break_points_chances",
)


@dataclass(frozen=True)
class ServeReturnProfile:
    player_id: int
    as_of_date: str
    matches: int
    serve: dict
    returning: dict
    opponent_elo_mean: float | None
    surface: str | None

    @property
    def is_usable(self) -> bool:
        """Enough serve history to say anything at all."""
        return self.matches >= MIN_SAMPLES and self.serve.get("hold_rate") is not None

    def get(self, name: str):
        if name in self.serve:
            return self.serve[name]
        return self.returning.get(name)


def _mean(values) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def serve_return_profile(
    conn,
    player_id: int,
    as_of_date: str,
    *,
    surface: str | None = None,
    window: int = DEFAULT_WINDOW,
) -> ServeReturnProfile:
    """Serve and return rates over the player's last ``window`` matches.

    ``surface`` narrows the window when the player has enough matches on it and
    is otherwise ignored.  Surface is recorded on 46.2% of history rows, so
    treating it as a filter would empty the window for half the board; it is an
    adjustment on a pooled rate, never a gate.
    """
    columns = ", ".join((*_SERVE_COLUMNS, *_RETURN_COLUMNS, "opponent_elo"))
    params: list = [player_id, as_of_date]
    surface_clause = ""
    if surface:
        surface_clause = " AND LOWER(COALESCE(surface,'')) = LOWER(?)"
        params.append(surface)
    params.append(window)
    rows = conn.execute(
        f"""
        SELECT {columns} FROM player_match_history
        WHERE player_id = ? AND match_date < ? AND hold_rate IS NOT NULL
          {surface_clause}
        ORDER BY match_date DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    used_surface = surface
    if surface and len(rows) < MIN_SAMPLES:
        return serve_return_profile(
            conn, player_id, as_of_date, surface=None, window=window
        )
    if not surface:
        used_surface = None

    serve = {name: _mean(row[name] for row in rows) for name in _SERVE_COLUMNS}
    returning = {name: _mean(row[name] for row in rows) for name in _RETURN_COLUMNS}
    # Break points are counts, not rates; the ratio is what a model wants and
    # the denominator is what tells it whether to believe the ratio.
    faced = serve.get("break_points_faced")
    saved = serve.get("break_points_saved")
    serve["break_point_save_rate"] = (
        saved / faced if faced and saved is not None and faced > 0 else None
    )
    chances = returning.get("break_points_chances")
    converted = returning.get("break_points_converted")
    returning["break_point_conversion_rate"] = (
        converted / chances if chances and converted is not None and chances > 0 else None
    )
    return ServeReturnProfile(
        player_id=int(player_id),
        as_of_date=str(as_of_date),
        matches=len(rows),
        serve=serve,
        returning=returning,
        opponent_elo_mean=_mean(row["opponent_elo"] for row in rows),
        surface=used_surface,
    )


def coverage(conn, since_date: str | None = None) -> dict:
    """How many priced fixtures resolve a usable profile for BOTH players.

    This is stage 1's exit test. Below roughly half, the work downstream only
    improves a minority of the board.
    """
    where = "1=1"
    params: list = []
    if since_date:
        where = "m.match_date >= ?"
        params.append(since_date)
    rows = conn.execute(
        f"""
        SELECT DISTINCT m.id, m.match_date, m.player_a_id, m.player_b_id
        FROM matches m JOIN market_odds_snapshots s ON s.match_id = m.id
        WHERE {where} AND m.player_a_id <> m.player_b_id
        """,
        tuple(params),
    ).fetchall()
    both = one = neither = 0
    for row in rows:
        a = serve_return_profile(conn, row["player_a_id"], row["match_date"]).is_usable
        b = serve_return_profile(conn, row["player_b_id"], row["match_date"]).is_usable
        if a and b:
            both += 1
        elif a or b:
            one += 1
        else:
            neither += 1
    total = len(rows) or 1
    return {
        "fixtures": len(rows),
        "both": both,
        "one": one,
        "neither": neither,
        "both_share": round(both / total, 4),
    }
