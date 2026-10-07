#!/usr/bin/env python3
"""PIT A/B for HKJC course/draw and predicted-running-style hypotheses.

Arms are intentionally independent:

* ``style_observed_only`` removes predicted running-style / draw-style-match
  signals while retaining observed position-PI and trip-consumption history.
* ``running_style_only_removed`` removes only the next-race style label and its
  confidence adjustment; observed lane/draw fit stays intact.
* ``venue_distance_record`` adds a small empirical-Bayes adjustment from the
  horse's pre-race same-venue-and-distance record.
* ``rail_draw_prior`` replaces the fixed inner/middle/outer ordering with a
  point-in-time rail x distance x field-size empirical ordering.

Nothing in this file changes production.  It monkey-patches the live engine in
memory and restores every method after each arm.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

REPO = Path(__file__).resolve().parents[3]
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
AUTO = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
for path in (REFLECTOR, AUTO, REPO):
    sys.path.insert(0, str(path))

import pit_backtest as pit  # noqa: E402
import rescore_backtest as backtest  # noqa: E402
from hkjc_racing_engine import engine_core, scoring  # noqa: E402


METRICS = ("gold", "good", "gold_strict", "min", "champion", "ndcg5")
ORIG_FIT = engine_core.RacingEngine._draw_position_fit_score
ORIG_DELTA = engine_core.RacingEngine._race_shape_context_delta
ORIG_SHAPE = engine_core.RacingEngine._race_shape_context_score
ORIG_DRAW = engine_core.DrawScorer.compute
RAIL_ROWS = pd.DataFrame()


def _race_flags(race: dict) -> list[float]:
    actual = race["actual"]
    best = min(actual.values())
    winners = {horse for horse, pos in actual.items() if pos == best}
    top3 = {horse for horse, pos in actual.items() if pos <= 3}
    order = [
        row["hn"]
        for row in sorted(race["scored"], key=lambda row: (-row["ability"], row["hn"]))
    ]
    picks = order[:4]
    first3_hits = sum(horse in top3 for horse in picks[:3])
    gains = [1.0 if horse in top3 else 0.0 for horse in order[:5]]
    dcg = sum(gain / np.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sum(1.0 / np.log2(index + 2) for index in range(min(3, len(order), len(top3))))
    return [
        float(bool(top3) and top3.issubset(set(picks))),
        float(len(picks) >= 2 and picks[0] in top3 and picks[1] in top3),
        float(first3_hits == 3),
        float(first3_hits >= 2),
        float(bool(picks) and picks[0] in winners),
        float(dcg / ideal if ideal else 0.0),
    ]


def _reset() -> None:
    engine_core.RacingEngine._draw_position_fit_score = ORIG_FIT
    engine_core.RacingEngine._race_shape_context_delta = ORIG_DELTA
    engine_core.RacingEngine._race_shape_context_score = ORIG_SHAPE
    engine_core.DrawScorer.compute = ORIG_DRAW


def _observed_fit(self):
    text = self._text("position_pi")
    weights = scoring.RACE_SHAPE_FIT_WEIGHTS
    score = weights["base"]
    details = []
    if "上升軌" in text:
        score += weights["pi_up_bonus"]
        details.append("走位 PI 有上升軌")
    elif "微升" in text:
        score += weights["pi_micro_up_bonus"]
        details.append("走位 PI 微升")
    elif "衰退中" in text:
        score += weights["pi_down_pen"]
        details.append("走位 PI 衰退")
    elif "微跌" in text:
        score += weights["pi_micro_down_pen"]
        details.append("走位 PI 微跌")
    detail = "；".join(details) if details else "已移除低準確度預測跑法，只保留實際走位 PI"
    return scoring.clip_score(score), f"實際走位面：{detail}。"


def _observed_delta(self):
    text = self._text("position_pi")
    weights = scoring.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS
    delta = 0.0
    items = []

    def add(factor, value, why):
        nonlocal delta
        delta += value
        items.append({"factor": factor, "delta": round(value, 2), "why": why})

    if "上升軌" in text:
        add("走位PI", weights["pi_up_bonus"], "走位 PI 上升")
    elif "衰退中" in text:
        add("走位PI", weights["pi_down_pen"], "走位 PI 衰退")
    recent = self._clean(self._value("position_window") or "").split("|")[0]
    if "低消耗" in recent:
        add("近仗消耗", weights["recent_low_consumption_bonus"], "最近走位低消耗")
    elif "極高" in recent:
        add("近仗消耗", weights["recent_extreme_consumption_pen"], "最近走位極高消耗")
    elif "高" in recent:
        add("近仗消耗", weights["recent_high_consumption_pen"], "最近走位高消耗")
    context = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
    delta = max(context["non_sha_tin_delta_floor"], min(context["non_sha_tin_delta_cap"], delta))
    return delta, items


def _no_style_fit(self):
    """Production fit logic, without allowing the predicted style string in."""
    text = self._text("draw_position_fit", "position_pi")
    weights = scoring.RACE_SHAPE_FIT_WEIGHTS
    score = weights["base"]
    details = []
    if "✅匹配" in text:
        score += weights["match_bonus"]
        details.append("檔位與歷史走位匹配")
    if "❌錯配" in text or "錯配!" in text:
        score += weights["mismatch_pen"]
        self.risk_flags.append("draw_position_mismatch")
        details.append("檔位與歷史走位有錯配")
    if "⚠️需主動切入" in text:
        score += weights["active_slot_pen"]
        self.risk_flags.append("needs_active_slotting")
        details.append("排檔需要主動切入")
    if "上升軌" in text:
        score += weights["pi_up_bonus"]
        details.append("走位 PI 有上升軌")
    elif "微升" in text:
        score += weights["pi_micro_up_bonus"]
        details.append("走位 PI 微升")
    elif "衰退中" in text:
        score += weights["pi_down_pen"]
        details.append("走位 PI 衰退")
    elif "微跌" in text:
        score += weights["pi_micro_down_pen"]
        details.append("走位 PI 微跌")
    detail = "；".join(details) if details else "歷史檔位走位未見鮮明偏差"
    return scoring.clip_score(score), f"歷史匹配面：{detail}。"


def _no_style_delta(self):
    """Production HV delta, excluding predicted style and its confidence tag."""
    text = self._text("draw_position_fit", "position_pi")
    weights = scoring.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS
    delta = 0.0
    items = []

    def add(factor, value, why):
        nonlocal delta
        delta += value
        items.append({"factor": factor, "delta": round(value, 2), "why": why})

    if "✅匹配" in text:
        add("歷史走位匹配", weights["match_bonus"], "檔位與歷史走位匹配")
    if "❌錯配" in text or "錯配!" in text:
        self.risk_flags.append("draw_position_mismatch")
        add("歷史走位匹配", weights["mismatch_pen"], "檔位與歷史走位錯配")
    if "⚠️需主動切入" in text:
        self.risk_flags.append("needs_active_slotting")
        add("歷史走位匹配", weights["active_slot_pen"], "排檔需要主動切入")
    if "上升軌" in text:
        add("走位PI", weights["pi_up_bonus"], "走位 PI 上升")
    elif "衰退中" in text:
        add("走位PI", weights["pi_down_pen"], "走位 PI 衰退")
    recent = self._clean(self._value("position_window") or "").split("|")[0]
    if "低消耗" in recent:
        add("近仗消耗", weights["recent_low_consumption_bonus"], "最近走位低消耗")
    elif "極高" in recent:
        add("近仗消耗", weights["recent_extreme_consumption_pen"], "最近走位極高消耗")
    elif "高" in recent:
        add("近仗消耗", weights["recent_high_consumption_pen"], "最近走位高消耗")
    context = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
    delta = max(context["non_sha_tin_delta_floor"], min(context["non_sha_tin_delta_cap"], delta))
    return delta, items


def _same_venue_distance_record(self):
    text = self._clean(self.horse_data.get("season_stats") or self._value("season_stats_line") or "")
    match = re.search(r"同場同程\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
    if not match:
        return None
    wins, seconds, thirds, rest = map(int, match.groups())
    return {"starts": wins + seconds + thirds + rest, "places": wins + seconds + thirds}


def _surface_delta(self) -> float:
    record = _same_venue_distance_record(self)
    if not record or record["starts"] < 2:
        return 0.0
    # Beta(2, 6) prior = 25% place rate, deliberately conservative.
    posterior = (record["places"] + 2.0) / (record["starts"] + 8.0)
    return max(-4.0, min(4.0, (posterior - 0.25) * 20.0))


def _surface_shape(self, features):
    score, note, source = ORIG_SHAPE(self, features)
    delta = _surface_delta(self)
    if delta:
        score = scoring.clip_score(score + delta)
        note += f"；同場同程往績作 EB 微調 {delta:+.1f}"
    return score, note, source


def _draw_group(draw: int) -> str:
    return "inner" if draw <= 4 else ("middle" if draw <= 8 else "outer")


def _field_bucket(size: int) -> str:
    if size <= 8:
        return "le8"
    if size <= 10:
        return "9_10"
    if size <= 12:
        return "11_12"
    return "ge13"


def _norm_venue(value: object) -> str:
    text = str(value or "")
    if "跑馬地" in text or text.upper() == "HV":
        return "跑馬地"
    if "沙田" in text or text.upper() == "ST":
        return "沙田"
    return text.strip()


def _rail_scores(context: dict, cutoff: str, *, continuous: bool = False) -> dict[str, float] | None:
    if RAIL_ROWS.empty:
        return None
    venue = _norm_venue(context.get("venue"))
    rail = str(context.get("rail") or context.get("course") or "").replace(" ", "").upper()
    distance_match = re.search(r"\d+", str(context.get("distance") or ""))
    if not venue or not rail or not distance_match:
        return None
    distance = int(distance_match.group())
    field_size = int(context.get("field_size") or len(context.get("field_horse_names") or []))
    prior = RAIL_ROWS[RAIL_ROWS["Date"] < cutoff]
    if prior.empty:
        return None

    levels = (
        (prior["Venue"].eq(venue) & prior["Rail"].eq(rail) & prior["Distance"].eq(distance)
         & prior["FieldBucket"].eq(_field_bucket(field_size))),
        (prior["Venue"].eq(venue) & prior["Rail"].eq(rail) & prior["Distance"].eq(distance)),
        (prior["Venue"].eq(venue) & prior["Distance"].eq(distance)),
        prior["Venue"].eq(venue),
    )
    grouped = None
    for mask in levels:
        sample = prior[mask]
        candidate = sample.groupby("DrawGroup").agg(starts=("Place", "size"), places=("Place", "sum"))
        if set(candidate.index) == {"inner", "middle", "outer"} and int(candidate["starts"].min()) >= 20:
            grouped = candidate
            break
    if grouped is None:
        return None

    base = float(prior[prior["Venue"].eq(venue)]["Place"].mean())
    posterior = {
        group: (float(row.places) + 30.0 * base) / (float(row.starts) + 30.0)
        for group, row in grouped.iterrows()
    }
    if continuous:
        # One place-rate percentage point equals one score point.  This keeps
        # the familiar 60 neutral centre while allowing a C-course outer draw
        # to be nearly neutral instead of receiving the fixed 50-point floor.
        return {
            group: max(45.0, min(75.0, 60.0 + 100.0 * (rate - base)))
            for group, rate in posterior.items()
        }
    ordered = sorted(posterior, key=lambda group: (-posterior[group], group))
    return {ordered[0]: 75.0, ordered[1]: 65.0, ordered[2]: 50.0}


def _pit_draw(self):
    draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return 60.0, "Invalid Draw"
    cutoff = str(self.race_context.get("race_date") or "")
    scores = _rail_scores(self.race_context, cutoff)
    if scores is None:
        return ORIG_DRAW(self)
    score = scores[_draw_group(draw_num)]
    return score, "PIT rail-distance-field EB ordering"


def _pit_draw_continuous(self):
    draw = self.horse_data.get("barrier") or self.horse_data.get("draw")
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return 60.0, "Invalid Draw"
    cutoff = str(self.race_context.get("race_date") or "")
    scores = _rail_scores(self.race_context, cutoff, continuous=True)
    if scores is None:
        return ORIG_DRAW(self)
    return scores[_draw_group(draw_num)], "PIT rail-distance-field EB excess"


def _install(arm: str) -> None:
    _reset()
    if arm == "style_observed_only":
        engine_core.RacingEngine._draw_position_fit_score = _observed_fit
        engine_core.RacingEngine._race_shape_context_delta = _observed_delta
    elif arm == "running_style_only_removed":
        engine_core.RacingEngine._draw_position_fit_score = _no_style_fit
        engine_core.RacingEngine._race_shape_context_delta = _no_style_delta
    elif arm == "venue_distance_record":
        engine_core.RacingEngine._race_shape_context_score = _surface_shape
    elif arm == "rail_draw_prior":
        engine_core.DrawScorer.compute = _pit_draw
    elif arm == "rail_draw_continuous":
        engine_core.DrawScorer.compute = _pit_draw_continuous
    elif arm != "baseline":
        raise ValueError(arm)


def _run(arm: str, meeting_dirs: list[Path], rows: pd.DataFrame):
    _install(arm)
    out = []
    try:
        for meeting in meeting_dirs:
            meeting_date = pit.meeting_date_from_dir(meeting)
            pit.inject_as_of(rows, meeting_date)
            races, _errors = backtest.rescore_meeting(meeting, include_legacy=False)
            venue = "沙田" if "ShaTin" in meeting.name else "跑馬地"
            for race in races:
                out.append((meeting_date, venue, _race_flags(race)))
    finally:
        _reset()
    return out


def _paired(base: np.ndarray, candidate: np.ndarray, seed: int = 7, boot: int = 2000):
    rng = np.random.default_rng(seed)
    n = len(base)
    deltas = np.empty((boot, base.shape[1]))
    for index in range(boot):
        sample = rng.integers(0, n, n)
        deltas[index] = candidate[sample].mean(axis=0) - base[sample].mean(axis=0)
    point = candidate.mean(axis=0) - base.mean(axis=0)
    return point, np.percentile(deltas, 2.5, axis=0), np.percentile(deltas, 97.5, axis=0)


def _summary(rows, mask=None):
    values = np.asarray([row[2] for row in rows if mask is None or mask(row)], dtype=float)
    return values, {metric: float(values[:, i].mean()) for i, metric in enumerate(METRICS)}


def _load_rail(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    frame = pd.DataFrame(rows)
    for column in ("Distance", "FieldSize", "Draw", "Place"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["Date", "Venue", "Rail", "Distance", "FieldSize", "Draw", "Place"])
    frame["Distance"] = frame["Distance"].astype(int)
    frame["FieldSize"] = frame["FieldSize"].astype(int)
    frame["Draw"] = frame["Draw"].astype(int)
    frame["Rail"] = frame["Rail"].astype(str).str.replace(" ", "", regex=False).str.upper()
    frame["DrawGroup"] = frame["Draw"].map(_draw_group)
    frame["FieldBucket"] = frame["FieldSize"].map(_field_bucket)
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=pit.bcs.HK_RACING)
    parser.add_argument("--rail-csv", type=Path, default=pit.bcs.DB_ROOT / "comprehensive_stats/rail_draw_results.csv")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--arms", nargs="+", choices=(
        "baseline", "running_style_only_removed", "style_observed_only",
        "venue_distance_record", "rail_draw_prior", "rail_draw_continuous",
    ))
    args = parser.parse_args()

    global RAIL_ROWS
    RAIL_ROWS = _load_rail(args.rail_csv)
    meeting_dirs = sorted({path.parent for path in args.root.rglob("Race_*_Logic.json")
                           if list(path.parent.glob("*全日賽果.json"))})
    rows = pit.load_all_rows()
    arms = tuple(args.arms or (
        "baseline",
        "running_style_only_removed",
        "style_observed_only",
        "venue_distance_record",
        "rail_draw_prior",
        "rail_draw_continuous",
    ))
    if "baseline" not in arms:
        arms = ("baseline", *arms)
    results = {}
    raw = {}
    for arm in arms:
        arm_rows = _run(arm, meeting_dirs, rows)
        raw[arm] = arm_rows
        _values, result = _summary(arm_rows)
        results[arm] = {"races": len(arm_rows), "all": result, "venue": {}}
        for venue in ("沙田", "跑馬地"):
            _venue_values, venue_result = _summary(arm_rows, lambda row, v=venue: row[1] == v)
            results[arm]["venue"][venue] = venue_result
        print(arm, len(arm_rows), " ".join(f"{key}={100*value:.2f}" for key, value in result.items()), flush=True)

    base, _ = _summary(raw["baseline"])
    for arm in arms[1:]:
        candidate, _ = _summary(raw[arm])
        point, low, high = _paired(base, candidate)
        results[arm]["paired_delta"] = {
            metric: {"point": float(point[i]), "low": float(low[i]), "high": float(high[i])}
            for i, metric in enumerate(METRICS)
        }
        print(f"paired {arm}")
        for i, metric in enumerate(METRICS):
            print(f"  {metric}: {100*point[i]:+.2f}pp [{100*low[i]:+.2f}, {100*high[i]:+.2f}]", flush=True)

    if args.json_out:
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
