from __future__ import annotations

import json


def get_surface_elo(surface_elo_json: str | None, surface: str | None,
                    fallback: float | None) -> float | None:
    """The player's rating on this court, or `fallback`.

    Case-folded on both sides. `tournament_levels.surface` holds both spellings
    -- `hard` on 1,766 rows and `Hard` on 48, `clay` on 1,228 and `Clay` on 133
    -- while `surface_elo_json` is keyed in lower case only. The old lookup was
    `data.get(surface) or data.get(surface.title())`, and `"Hard".title()` is
    `"Hard"`, so every capitalised spelling missed twice and fell through to the
    OVERALL rating: the surface component silently became a duplicate of a
    component already in the blend, with no warning anywhere.
    """
    if not surface_elo_json or not surface:
        return fallback
    try:
        data = json.loads(surface_elo_json)
    except (TypeError, ValueError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    wanted = str(surface).strip().lower()
    for key, value in data.items():
        if str(key).strip().lower() == wanted and value is not None:
            return value
    return fallback
