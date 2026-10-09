#!/usr/bin/env python3
"""Point-in-time WinningTime speed audit by AU racecourse.

Research-only.  The old ``speed_fig_best3`` harness fitted track/distance
standards once on the full corpus.  That lets future race times normalise older
targets.  This audit rebuilds the same medians as-of every target date, then
tests one fixed global candidate and two Gold-boundary candidates without
touching live scoring:

* global_add: add ``0.5 * within-race z(speed)`` to the existing score;
* boundary_all: swap model ranks 4/5 when rank 5 has the better speed figure;
* boundary_close: the same swap only when the base score gap is <= 0.5.

The two boundary candidates leave ranks 1-3 unchanged by construction.  Output
is descriptive/retrospective; promotion still needs genuinely new prospective
races.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AU_RACING = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))

from au_feature_ab import MEETING_RE, _historical_results  # noqa: E402
from au_leaf_power import norm, within_race_auc  # noqa: E402
from au_unused_field_power import RE_HDR_DIST, RE_RUNNER  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from sb_backfill_archive import scored_meeting_index  # noqa: E402


RUN_RE = re.compile(
    r"^(?P<track>.+?)\sR(?P<race>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<distance>\d+)m\s+cond:(?P<condition>\S+)"
)
WT_RE = re.compile(r"WinningTime:(?:(\d+):)?([\d.]+)")
MARGIN_RE = re.compile(r"margin:(-?[\d.]+)L?")
METRICS = (
    "gold",
    "good_positional",
    "pass",
    "champion",
    "winner_in_top3",
)
GLOBAL_SPEED_K = 0.5
SPEED_MIN_CELL_RACES = 10
SPEED_MIN_GOING_RACES = 40
SPEED_MIN_RUNNER_RUNS = 3


def parse_run(line: str) -> dict | None:
    match = RUN_RE.match(line)
    winning_time = WT_RE.search(line)
    if not match or not winning_time or "**(TRIAL)**" in line:
        return None
    seconds = float(winning_time.group(2))
    if winning_time.group(1):
        seconds += int(winning_time.group(1)) * 60
    if not 25.0 < seconds < 260.0:
        return None
    margin = MARGIN_RE.search(line)
    return {
        "track": match.group("track").strip(),
        "race": int(match.group("race")),
        "date": match.group("date"),
        "distance": int(match.group("distance")),
        "condition": match.group("condition"),
        "winning_time": seconds,
        "margin": float(margin.group(1)) if margin else 0.0,
    }


def collect_reference_races(root: Path) -> tuple[list[dict], int]:
    """Deduplicate race-level winning times repeated across horse form lines."""
    unique: dict[tuple, dict] = {}
    conflicts = 0
    for formguide in root.rglob("*Formguide.md"):
        text = formguide.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            run = parse_run(line)
            if run is None:
                continue
            key = (run["track"], run["date"], run["race"], run["distance"])
            previous = unique.get(key)
            if previous and previous["winning_time"] != run["winning_time"]:
                conflicts += 1
                continue
            unique.setdefault(key, run)
    return sorted(unique.values(), key=lambda row: row["date"]), conflicts


def build_asof_standards(observations: list[dict], target_dates: list[str]) -> dict:
    """For date D, fit every median using race observations strictly before D."""
    history: list[dict] = []
    cursor = 0
    output = {}
    for target_date in sorted(set(target_dates)):
        while cursor < len(observations) and observations[cursor]["date"] < target_date:
            history.append(observations[cursor])
            cursor += 1
        per_cell: dict[tuple, list[float]] = defaultdict(list)
        for row in history:
            per_cell[(row["track"], row["distance"])].append(row["winning_time"])
        base = {
            key: statistics.median(values)
            for key, values in per_cell.items()
            if len(values) >= SPEED_MIN_CELL_RACES
        }
        deviations: dict[str, list[float]] = defaultdict(list)
        for row in history:
            standard = base.get((row["track"], row["distance"]))
            if standard is not None:
                deviations[row["condition"]].append(row["winning_time"] - standard)
        going = {
            condition: statistics.median(values)
            for condition, values in deviations.items()
            if len(values) >= SPEED_MIN_GOING_RACES
        }
        output[target_date] = (base, going, len(history))
    return output


def runner_speed_best3(block: str, standards: tuple[dict, dict, int], target_date: str) -> float | None:
    base, going, _ = standards
    figures = []
    for line in block.splitlines():
        run = parse_run(line)
        if run is None or run["date"] >= target_date:
            continue
        standard = base.get((run["track"], run["distance"]))
        if standard is None:
            continue
        seconds_per_length = 2.4 / (run["distance"] / run["winning_time"])
        own_time = run["winning_time"] + run["margin"] * seconds_per_length
        adjusted = own_time - standard - going.get(run["condition"], 0.0)
        figures.append(-adjusted / (run["distance"] / 1000.0))
    if len(figures) < SPEED_MIN_RUNNER_RUNS:
        return None
    return sum(sorted(figures)[-3:]) / 3.0


def _zs(values: list[float | None]) -> list[float]:
    available = [value for value in values if value is not None]
    if len(available) < 2:
        return [0.0] * len(values)
    average = statistics.mean(available)
    spread = statistics.pstdev(available)
    if spread <= 0:
        return [0.0] * len(values)
    return [0.0 if value is None else (value - average) / spread for value in values]


def load_races(root: Path, clean_from: str, standards_by_date: dict) -> list[dict]:
    results = _historical_results(root)
    races = []
    for meeting_name, meeting_dir in sorted(scored_meeting_index(root).items()):
        meeting = MEETING_RE.match(meeting_name)
        if not meeting or meeting.group(1) < clean_from:
            continue
        date, venue = meeting.group(1), meeting.group(2).strip()
        actual_by_race = results.get((date, norm(venue)))
        standards = standards_by_date.get(date)
        if not actual_by_race or standards is None:
            continue
        scoring = defaultdict(dict)
        with open(meeting_dir / "Meeting_Auto_Scoring.csv", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                scoring[int(row["race_number"])][norm(row["horse_name"])] = row
        for formguide in sorted(meeting_dir.glob("*Formguide.md")):
            text = formguide.read_text(encoding="utf-8", errors="replace")
            header = RE_HDR_DIST.search(text)
            if not header:
                continue
            race_no = int(header.group(1))
            actual = actual_by_race.get(race_no)
            score_rows = scoring.get(race_no)
            if not actual or not score_rows:
                continue
            starts = [match.start() for match in RE_RUNNER.finditer(text)]
            runners = []
            for index, match in enumerate(RE_RUNNER.finditer(text)):
                end = starts[index + 1] if index + 1 < len(starts) else len(text)
                key = norm(match.group(2))
                score_row, position = score_rows.get(key), actual.get(key)
                if score_row is None or position is None:
                    continue
                block = text[match.start():end]
                runners.append({
                    "key": key,
                    "number": int(score_row["horse_number"]),
                    "score": float(score_row["final_rank_score"]),
                    "pace_figure": float(score_row["pace_figure_score"]),
                    "speed": runner_speed_best3(block, standards, date),
                    "position": int(position),
                })
            if len(runners) >= 5:
                races.append({
                    "date": date,
                    "venue": venue,
                    "race": race_no,
                    "runners": runners,
                })
    return sorted(races, key=lambda row: (row["date"], row["venue"], row["race"]))


def rankings(race: dict) -> dict[str, list[str]]:
    ordered = sorted(race["runners"], key=lambda row: (-row["score"], row["number"]))
    speed_z = dict(zip((row["key"] for row in ordered),
                       _zs([row["speed"] for row in ordered])))
    baseline = [row["key"] for row in ordered]
    global_add = [
        row["key"]
        for row in sorted(
            ordered,
            key=lambda row: (
                -(row["score"] + GLOBAL_SPEED_K * speed_z[row["key"]]),
                row["number"],
            ),
        )
    ]

    boundary_all = list(baseline)
    boundary_close = list(baseline)
    fourth, fifth = ordered[3], ordered[4]
    if fourth["speed"] is not None and fifth["speed"] is not None \
            and fifth["speed"] > fourth["speed"]:
        boundary_all[3], boundary_all[4] = boundary_all[4], boundary_all[3]
        if fourth["score"] - fifth["score"] <= 0.5:
            boundary_close[3], boundary_close[4] = boundary_close[4], boundary_close[3]
    return {
        "baseline": baseline,
        "global_add": global_add,
        "boundary_all": boundary_all,
        "boundary_close": boundary_close,
    }


def outcome(race: dict, picks: list[str]) -> dict:
    actual = {row["key"]: row["position"] for row in race["runners"]}
    top3 = {key for key, position in actual.items() if position <= 3}
    winner = next((key for key, position in actual.items() if position == 1), None)
    return race_metrics(picks, top3, winner=winner, actual_pos=actual,
                        field_size=len(actual))


def race_rows(races: list[dict]) -> list[dict]:
    output = []
    for race in races:
        ranks = rankings(race)
        row = {
            "date": race["date"],
            "venue": race["venue"],
            "race": race["race"],
            "field_size": len(race["runners"]),
        }
        row["coverage"] = sum(runner["speed"] is not None for runner in race["runners"]) / len(race["runners"])
        pairs = [(runner["speed"], runner["position"] <= 3)
                 for runner in race["runners"] if runner["speed"] is not None]
        row["speed_auc_parts"] = within_race_auc(pairs)
        speed_values = [runner["speed"] for runner in race["runners"]]
        pace_values = [runner["pace_figure"] for runner in race["runners"]]
        speed_z, pace_z = _zs(speed_values), _zs(pace_values)
        row["corr_parts"] = [(s, p) for s, p, raw in zip(speed_z, pace_z, speed_values)
                             if raw is not None]
        for name, picks in ranks.items():
            row[name] = outcome(race, picks)
        output.append(row)
    return output


def _rate(rows: list[dict], candidate: str, metric: str) -> float:
    return 100.0 * sum(bool(row[candidate][metric]) for row in rows) / len(rows)


def _delta(rows: list[dict], candidate: str, metric: str) -> float:
    return _rate(rows, candidate, metric) - _rate(rows, "baseline", metric)


def paired_ci(rows: list[dict], candidate: str, metric: str, seed: int = 7) -> tuple[float, float]:
    deltas = [float(row[candidate][metric]) - float(row["baseline"][metric]) for row in rows]
    rng = random.Random(seed)
    boot = []
    for _ in range(2000):
        boot.append(100.0 * sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas))
    boot.sort()
    return boot[50], boot[1949]


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    x_mean, y_mean = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = math.sqrt(sum((x - x_mean) ** 2 for x in xs)
                            * sum((y - y_mean) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def summary(rows: list[dict], candidate: str) -> dict:
    auc_c = sum(row["speed_auc_parts"][0] for row in rows)
    auc_n = sum(row["speed_auc_parts"][1] for row in rows)
    correlations = [pair for row in rows for pair in row["corr_parts"]]
    return {
        "races": len(rows),
        "coverage_pct": 100.0 * statistics.mean(row["coverage"] for row in rows),
        "speed_auc": auc_c / auc_n if auc_n else None,
        "speed_pace_corr": _pearson(correlations),
        "baseline": {metric: _rate(rows, "baseline", metric) for metric in METRICS},
        "candidate": {metric: _rate(rows, candidate, metric) for metric in METRICS},
        "delta": {metric: _delta(rows, candidate, metric) for metric in METRICS},
    }


def date_folds(rows: list[dict], folds: int = 5) -> list[list[dict]]:
    dates = sorted({row["date"] for row in rows})
    edges = [round(len(dates) * index / folds) for index in range(folds + 1)]
    output = []
    for index in range(folds):
        bucket = set(dates[edges[index]:edges[index + 1]])
        output.append([row for row in rows if row["date"] in bucket])
    return [fold for fold in output if fold]


def date_adjusted_residual(rows: list[dict], all_rows: list[dict], metric: str) -> float:
    """Venue pp minus the weighted all-venue rate on those same race dates."""
    by_date = defaultdict(list)
    for row in all_rows:
        by_date[row["date"]].append(row)
    expected = statistics.mean(
        _rate(by_date[row["date"]], "baseline", metric) for row in rows
    )
    return _rate(rows, "baseline", metric) - expected


def date_adjusted_ci(rows: list[dict], all_rows: list[dict], metric: str,
                     seed: int = 11) -> tuple[float, float]:
    """Date-cluster bootstrap CI for a venue's same-date residual."""
    all_by_date = defaultdict(list)
    venue_by_date = defaultdict(list)
    for row in all_rows:
        all_by_date[row["date"]].append(row)
    for row in rows:
        expected = _rate(all_by_date[row["date"]], "baseline", metric)
        actual = 100.0 * bool(row["baseline"][metric])
        venue_by_date[row["date"]].append(actual - expected)
    dates = sorted(venue_by_date)
    rng = random.Random(seed)
    boot = []
    for _ in range(2000):
        sample = [dates[rng.randrange(len(dates))] for _ in dates]
        values = [value for date in sample for value in venue_by_date[date]]
        boot.append(statistics.mean(values))
    boot.sort()
    return boot[50], boot[1949]


def render(rows: list[dict], min_venue_races: int) -> dict:
    report = {
        "races": len(rows),
        "date_from": rows[0]["date"],
        "date_to": rows[-1]["date"],
        "candidates": {},
        "folds": {},
        "venues": {},
    }
    print(f"{len(rows)} 場：{rows[0]['date']} → {rows[-1]['date']}（speed standards 全部 as-of）\n")
    print("整體結果")
    print(f"{'候選':18}{'Gold Δ':>10}{'95% CI':>22}{'Good Δ':>10}{'Pass Δ':>10}{'WinT3 Δ':>10}")
    for candidate in ("global_add", "boundary_all", "boundary_close"):
        data = summary(rows, candidate)
        ci = paired_ci(rows, candidate, "gold")
        data["gold_ci"] = ci
        report["candidates"][candidate] = data
        print(f"{candidate:18}{data['delta']['gold']:>+10.2f}"
              f"  [{ci[0]:+.2f}, {ci[1]:+.2f}]"
              f"{data['delta']['good_positional']:>+10.2f}"
              f"{data['delta']['pass']:>+10.2f}"
              f"{data['delta']['winner_in_top3']:>+10.2f}")

    print("\n完整日期五段（Gold Δpp）")
    print(f"{'日期':24}{'場':>6}{'global':>10}{'rank4/5':>10}{'close':>10}")
    for fold in date_folds(rows):
        label = f"{fold[0]['date']}..{fold[-1]['date']}"
        values = {candidate: _delta(fold, candidate, "gold")
                  for candidate in ("global_add", "boundary_all", "boundary_close")}
        report["folds"][label] = {"races": len(fold), **values}
        print(f"{label:24}{len(fold):>6}{values['global_add']:>+10.2f}"
              f"{values['boundary_all']:>+10.2f}{values['boundary_close']:>+10.2f}")

    by_venue = defaultdict(list)
    for row in rows:
        by_venue[row["venue"]].append(row)
    eligible = [(venue, venue_rows) for venue, venue_rows in by_venue.items()
                if len(venue_rows) >= min_venue_races]
    eligible.sort(key=lambda item: date_adjusted_residual(item[1], rows, "gold"))
    print(f"\n低表現場地（最少 {min_venue_races} 場；按同日調整 Gold 排）")
    print(f"{'場地':22}{'n':>5}{'日':>4}{'Gold':>7}{'同日Δ':>8}{'同日95% CI':>20}"
          f"{'GoodΔ':>8}{'覆蓋':>8}{'speedAUC':>10}{'ρpace':>8}{'globalΔ':>9}")
    for venue, venue_rows in eligible:
        base_data = summary(venue_rows, "baseline")
        gold_residual = date_adjusted_residual(venue_rows, rows, "gold")
        gold_residual_ci = date_adjusted_ci(venue_rows, rows, "gold")
        good_residual = date_adjusted_residual(venue_rows, rows, "good_positional")
        global_delta = _delta(venue_rows, "global_add", "gold")
        global_ci = paired_ci(venue_rows, "global_add", "gold")
        all_delta = _delta(venue_rows, "boundary_all", "gold")
        close_delta = _delta(venue_rows, "boundary_close", "gold")
        venue_dates = sorted({row["date"] for row in venue_rows})
        middle = len(venue_dates) // 2
        halves = []
        for date_bucket in (set(venue_dates[:middle]), set(venue_dates[middle:])):
            half_rows = [row for row in venue_rows if row["date"] in date_bucket]
            if half_rows:
                halves.append({
                    "races": len(half_rows),
                    "date_from": half_rows[0]["date"],
                    "date_to": half_rows[-1]["date"],
                    "gold_residual": date_adjusted_residual(half_rows, rows, "gold"),
                    "global_add_gold_delta": _delta(half_rows, "global_add", "gold"),
                })
        venue_report = {
            **base_data,
            "date_adjusted_gold": gold_residual,
            "date_adjusted_gold_ci": gold_residual_ci,
            "date_adjusted_good": good_residual,
            "global_add_gold_delta": global_delta,
            "global_add_gold_ci": global_ci,
            "boundary_all_gold_delta": all_delta,
            "boundary_close_gold_delta": close_delta,
            "boundary_all_gold_ci": paired_ci(venue_rows, "boundary_all", "gold"),
            "boundary_close_gold_ci": paired_ci(venue_rows, "boundary_close", "gold"),
            "halves": halves,
        }
        report["venues"][venue] = venue_report
        print(f"{venue[:22]:22}{len(venue_rows):>5}{len(venue_dates):>4}"
              f"{base_data['baseline']['gold']:>8.1f}{gold_residual:>+8.1f}"
              f"  [{gold_residual_ci[0]:+.1f}, {gold_residual_ci[1]:+.1f}]"
              f"{good_residual:>+8.1f}"
              f"{base_data['coverage_pct']:>8.1f}"
              f"{(base_data['speed_auc'] or 0):>10.3f}"
              f"{(base_data['speed_pace_corr'] or 0):>8.3f}"
              f"{global_delta:>+9.1f}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--clean-from", default="2026-06-06")
    parser.add_argument("--min-venue-races", type=int, default=30)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    meeting_dates = []
    for name in scored_meeting_index(args.data_root):
        match = MEETING_RE.match(name)
        if match and match.group(1) >= args.clean_from:
            meeting_dates.append(match.group(1))
    observations, conflicts = collect_reference_races(args.data_root)
    standards = build_asof_standards(observations, meeting_dates)
    print(f"速度參考賽事：{len(observations)}（衝突重複 {conflicts}）；目標日 {len(standards)}")
    races = load_races(args.data_root, args.clean_from, standards)
    rows = race_rows(races)
    if not rows:
        raise SystemExit("❌ 冇可評場次")
    report = render(rows, args.min_venue_races)
    report["reference_races"] = len(observations)
    report["reference_conflicts"] = conflicts
    if args.json_out:
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        print(f"\n→ {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
