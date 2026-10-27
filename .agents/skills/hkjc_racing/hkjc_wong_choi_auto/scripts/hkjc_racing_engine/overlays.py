"""Situational overlays — the one place they are defined, weighted and switched.

An overlay is a pre-race situation (e.g. "today's jockey is a top-6 jockey")
that adds a fixed number of **raw** points to `ability_score_raw` after the 9D
matrix and the field-level shape robustness step, before the official ranking.

Rules that keep this clean for refit / ML:

* ``OVERLAY_WEIGHTS`` is the only switch.  Weight 0 = shadow: the overlay is
  still computed, recorded per horse and exported, but adds nothing.
  Experiment arms mutate this dict; nothing else reads a hidden constant.
* Every horse carries ``python_auto["overlays"][key] = {value, weight,
  applied_delta, evidence, experiment}`` whether it fired or not, so the
  harness dump and CSV expose each overlay as its own column.
* Signals use only information dated strictly before the race date.  The
  top-jockey table is rebuilt from the results database for every race date,
  so live scoring and archive replay take the same path (no injection).
* ``validation.py`` adds Σ applied_delta to the expected raw score, so an
  overlay can never silently desync the ability formula (SCORE-004).
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
import sys as _sys; _sys.path.insert(0, str(ROOT))
from wongchoi_paths import HK_RACING

RESULTS_DB = HK_RACING / "HKJC_Race_Results_Database"
TOP_JOCKEY_COUNT = 6
TOP_JOCKEY_WINDOW_DAYS = 365


@dataclass(frozen=True)
class OverlaySpec:
    key: str
    label: str
    experiment: str
    description: str


OVERLAYS = {
    spec.key: spec
    for spec in (
        OverlaySpec(
            "top_jockey_today",
            "頂級騎師",
            "EXP-20261027-13",
            "今仗騎師屬賽日前 365 日勝出數頭 6 名（EXP-20261027-12 掃描：模型低估）",
        ),
        OverlaySpec(
            "top_jockey_upgrade",
            "換上頂級騎師",
            "EXP-20261027-13",
            "今仗頂級騎師，而上仗騎師唔係（EXP-20261027-12 P1）",
        ),
    )
}

# 唯一開關。0 = shadow（照計、照記錄、照匯出，唔加分）。
OVERLAY_WEIGHTS = {key: 0.0 for key in OVERLAYS}


def _parse_date(text):
    """ISO `YYYY-MM-DD` (race context) or HKJC `DD/MM/YYYY` / `DD/MM/YY` (form rows)."""
    text = str(text or "").strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    parts = text.split("/")
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(part) for part in parts)
        return date(year + 2000 if year < 100 else year, month, day)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _jockey_wins_by_day(db_root: str) -> dict:
    """{race date: {jockey: wins}} from every results-database day file."""
    wins: dict = defaultdict(lambda: defaultdict(int))
    for path in glob.glob(f"{db_root}/hkjc results */*/*.json"):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for race in payload.values():
            if not isinstance(race, dict):
                continue
            try:
                day = date.fromisoformat(str(race.get("racedate") or ""))
            except ValueError:
                continue
            for row in race.get("results") or []:
                if str(row.get("pos") or "").strip() == "1" and row.get("jockey"):
                    wins[day][row["jockey"]] += 1
    return {day: dict(by_jockey) for day, by_jockey in wins.items()}


def top_jockeys_as_of(race_date: date, db_root: str | None = None) -> tuple[frozenset, dict] | None:
    """Top-N jockeys by wins in the window strictly before ``race_date``."""
    by_day = _jockey_wins_by_day(str(db_root or RESULTS_DB))
    if not by_day:
        return None
    start = race_date - timedelta(days=TOP_JOCKEY_WINDOW_DAYS)
    totals: dict = defaultdict(int)
    for day, by_jockey in by_day.items():
        if start <= day < race_date:
            for jockey, count in by_jockey.items():
                totals[jockey] += count
    if not totals:
        return None
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_JOCKEY_COUNT]
    return frozenset(j for j, _w in ranked), dict(ranked)


def jockey_context(engine) -> dict | None:
    """Today's / last-run jockey and the PIT top-jockey table for one horse."""
    race_date = _parse_date((engine.race_context or {}).get("race_date"))
    if race_date is None:
        return None
    table = top_jockeys_as_of(race_date)
    if table is None:
        return None
    top, wins = table
    today = engine._clean(engine.horse_data.get("jockey", "") or engine._current_declared_jockey())
    rows = [
        row for row in engine._recent_jockey_history_rows()
        if (_parse_date(row.get("date")) or date.min) < race_date
    ]
    last = rows[0].get("jockey") if rows else None
    return {"today": today, "last": last, "top": top, "wins": wins}


def evaluate_overlays(engine) -> dict:
    """Return {key: {value, evidence}} for one horse; value is 0.0 or 1.0."""
    ctx = jockey_context(engine)
    out = {key: {"value": 0.0, "evidence": "資料不足（冇賽日或騎師表）"} for key in OVERLAYS}
    if not ctx or not ctx["today"]:
        return out
    top_today = ctx["today"] in ctx["top"]
    wins = ctx["wins"].get(ctx["today"])
    out["top_jockey_today"] = {
        "value": 1.0 if top_today else 0.0,
        "evidence": (f"{ctx['today']} 賽日前365日 {wins} 勝，屬頭{TOP_JOCKEY_COUNT}" if top_today
                     else f"{ctx['today']} 唔屬賽日前365日頭{TOP_JOCKEY_COUNT}"),
    }
    upgrade = top_today and bool(ctx["last"]) and ctx["last"] not in ctx["top"]
    out["top_jockey_upgrade"] = {
        "value": 1.0 if upgrade else 0.0,
        "evidence": (f"上仗 {ctx['last']} → 今仗 {ctx['today']}（頭{TOP_JOCKEY_COUNT}）" if upgrade
                     else "唔係換上頂級騎師"),
    }
    return out


def overlay_record(hits: dict) -> dict:
    """Attach the live weight and applied delta to each overlay hit."""
    record = {}
    for key, spec in OVERLAYS.items():
        hit = hits.get(key) or {"value": 0.0, "evidence": ""}
        weight = float(OVERLAY_WEIGHTS.get(key, 0.0))
        record[key] = {
            "value": float(hit["value"]),
            "weight": weight,
            "applied_delta": round(weight * float(hit["value"]), 4),
            "evidence": hit["evidence"],
            "experiment": spec.experiment,
            "status": "live" if weight else "shadow",
        }
    return record


def applied_total(auto: dict) -> float:
    return sum(float((item or {}).get("applied_delta", 0.0) or 0.0)
               for item in (auto.get("overlays") or {}).values())
