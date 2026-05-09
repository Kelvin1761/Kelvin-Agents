from __future__ import annotations

import json


def get_surface_elo(surface_elo_json: str | None, surface: str | None, fallback: float | None) -> float | None:
    if not surface_elo_json or not surface:
        return fallback
    data = json.loads(surface_elo_json)
    return data.get(surface) or data.get(surface.title()) or fallback
