"""EXP-20261109-02 arm R365: class_score reads the horse's 365-day record, not 季內.

Strictly prior: only rows with Date < race date.  Same thresholds as live.
"""
from __future__ import annotations

import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ARM_NAME = "r365_class_record"
REPO = Path(__file__).resolve().parents[3]
for p in (REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts",
          REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

WINDOW_DAYS = 365
_BY_HORSE: dict[str, list[tuple[str, int]]] = {}


def _load() -> None:
    import pit_backtest

    df = pit_backtest.load_all_rows()
    rows = defaultdict(list)
    for horse_id, day, rank in zip(df["HorseID"], df["Date"], df["Rank"]):
        try:
            rank = int(float(rank))
        except (TypeError, ValueError):
            continue
        if horse_id and rank > 0:
            rows[str(horse_id).strip()].append((str(day)[:10], rank))
    _BY_HORSE.update({k: sorted(v) for k, v in rows.items()})


def rolling_record(horse_id: str, race_day: str) -> dict | None:
    runs = _BY_HORSE.get(str(horse_id or "").strip())
    if not runs or not race_day:
        return None
    end = race_day[:10]
    start = (date.fromisoformat(end) - timedelta(days=WINDOW_DAYS)).isoformat()
    window = runs[bisect_left(runs, (start, 0)):bisect_left(runs, (end, 0))]   # Date < race day
    if not window:
        return None
    ranks = [rank for _day, rank in window]
    wins, seconds, thirds = (sum(r == k for r in ranks) for k in (1, 2, 3))
    return {"wins": wins, "seconds": seconds, "thirds": thirds,
            "starts": len(ranks), "places": wins + seconds + thirds}


def apply() -> None:
    from hkjc_racing_engine import _facts

    _load()

    def _season_record(self):
        code = self.horse_data.get("horse_code") or self._value("horse_code")
        return rolling_record(code, str((self.race_context or {}).get("race_date") or ""))

    _facts.HorseFacts._season_record = _season_record
