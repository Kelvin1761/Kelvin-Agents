"""Arm: continuous 同程表現 leaf from the Facts 距離分佈 line (EXP-20261010-16, pre-registered).

Kelvin 2026-10-11: 同程表現 only ever prints 75.8 / 60 / 53.9 — the live leaf is
`60 + adj / 0.02` where adj is a binary "placed / unplaced at this exact distance"
(+0.43 / −0.17). The V2 residual shadow is continuous but exists on 5% of Logic.

Fixed rule, nothing fitted (all constants chosen before seeing results):
  target evidence  runs within ±50 m count 1, ±51–200 m count 0.5
  all evidence     every distance in the 距離分佈 line
  rate_all         places / starts over all distances
  rate_target      (target places + K·rate_all) / (target starts + K), K = 3
  leaf             60 + 60 · (rate_target − rate_all), clipped to [40, 80]
  no line / debut / zero target evidence → 60 (no evidence)
The centred coefficient stays 0.02, so only the leaf's shape changes.
"""
from __future__ import annotations

import re
from pathlib import Path

ARM_NAME = "distance_fit_continuous_k3"
ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing")
K = 3.0
SCALE = 60.0
_DIST_RE = re.compile(r"(\d{3,4})m:\s*(\d+)場\s*\((\d+)-(\d+)-(\d+)\)")
_CACHE: dict[tuple[str, str], list[tuple[int, int, int]]] | None = None


def parse_distribution(block: str) -> list[tuple[int, int, int]]:
    """'距離分佈: 1400m: 6場 (0-0-6) | 1650m: 9場 (1-2-6)' → [(distance, starts, places)]."""
    if "距離分佈:" not in block:
        return []
    line = block.split("距離分佈:")[1].split("\n")[0]
    return [(int(d), int(n), int(w) + int(p)) for d, n, w, p, _rest in _DIST_RE.findall(line)]


def leaf(distribution: list[tuple[int, int, int]], distance: int | None) -> float:
    if not distribution or not distance:
        return 60.0
    starts = sum(n for _d, n, _p in distribution)
    places = sum(p for _d, _n, p in distribution)
    if starts <= 0:
        return 60.0
    rate_all = places / starts
    t_starts = t_places = 0.0
    for d, n, p in distribution:
        gap = abs(d - distance)
        w = 1.0 if gap <= 50 else 0.5 if gap <= 200 else 0.0
        t_starts += w * n
        t_places += w * p
    if t_starts <= 0:
        return 60.0
    rate_target = (t_places + K * rate_all) / (t_starts + K)
    return max(40.0, min(80.0, 60.0 + SCALE * (rate_target - rate_all)))


def _load() -> dict[tuple[str, str], list[tuple[int, int, int]]]:
    global _CACHE
    if _CACHE is None:
        _CACHE = {}
        for facts in ROOT.glob("20[0-9][0-9]-*_*/*Race * Facts.md"):
            if "(" in facts.parent.name:
                continue
            day = facts.parent.name[:10]
            text = facts.read_text(encoding="utf-8")
            for block in re.split(r"^### 馬號 \d+ — ", text, flags=re.M)[1:]:
                name = block.split("|")[0].strip()
                _CACHE[(day, name)] = parse_distribution(block)
    return _CACHE


def _distance(race_context) -> int | None:
    m = re.search(r"(\d{3,4})", str((race_context or {}).get("distance") or ""))
    return int(m.group(1)) if m else None


def apply():
    from hkjc_racing_engine import engine_core
    from hkjc_racing_engine.scoring import CENTRED_MATRIX_WEIGHTS

    weight = CENTRED_MATRIX_WEIGHTS["distance_fit"]
    original = engine_core.RacingEngine._distance_suitability_adjustment

    def continuous(self, features, matrix_scores):
        out = dict(original(self, features, matrix_scores))
        if self._is_debut():
            return out
        day = str((self.race_context or {}).get("race_date") or "")[:10]
        name = str(self.horse_data.get("horse_name") or "").strip()
        value = leaf(_load().get((day, name), []), _distance(self.race_context))
        out["raw_adjustment"] = round(weight * (value - 60.0), 6)
        out["signal"] = "continuous_distance_residual"
        return out

    engine_core.RacingEngine._distance_suitability_adjustment = continuous
