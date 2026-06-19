#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "Archive_Race_Analysis" / "AU_Racing"
REPORT_PATH = ROOT / "scratch" / "au_combined_walkforward_report.md"
ROWS_PATH = ROOT / "scratch" / "au_combined_walkforward_rows.csv"

FEATURE_KEYS = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "rating_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "confidence_score",
)


@dataclass
class EvalResult:
    races: int
    gold: int
    good: int
    pass_: int
    one_hit: int
    miss: int
    top3_hits: int
    winner_in_top3: int
    top1: int

    @property
    def top3_precision(self) -> float:
        return self.top3_hits / (self.races * 3) if self.races else 0.0

    @property
    def winner_in_top3_rate(self) -> float:
        return self.winner_in_top3 / self.races if self.races else 0.0

    @property
    def top1_rate(self) -> float:
        return self.top1 / self.races if self.races else 0.0


def read_text_retry(path: Path, attempts: int = 3) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return path.read_text(encoding="utf-8")
        except TimeoutError as exc:
            last_exc = exc
            print(f"Read timeout ({attempt}/{attempts}): {path}", flush=True)
            time.sleep(float(attempt))
    if last_exc:
        raise last_exc
    return path.read_text(encoding="utf-8")


def parse_int(value, default: int | None = None) -> int | None:
    if value is None:
        return default
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else default


def as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def date_key(name: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return match.group(1) if match else "0000-00-00"


def venue_key(name: str) -> str:
    value = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", name)
    value = re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", value)
    return value.strip() or "Unknown"


def parse_reflector_top3(path: Path) -> dict[int, list[int]]:
    if not path.exists():
        return {}
    try:
        text = read_text_retry(path)
    except TimeoutError:
        return {}
    top3_by_race: dict[int, list[int]] = {}
    current_race = None
    for line in text.splitlines():
        race_match = re.match(r"## Race\s+(\d+)", line.strip())
        if race_match:
            current_race = int(race_match.group(1))
            top3_by_race[current_race] = []
            continue
        if current_race is None:
            continue
        result_match = re.match(r"(?:1st|2nd|3rd):\s+#(\d+)\s+", line.strip())
        if result_match and len(top3_by_race[current_race]) < 3:
            top3_by_race[current_race].append(int(result_match.group(1)))
    return {race_no: nums for race_no, nums in top3_by_race.items() if len(nums) >= 3}


def class_bucket(meeting: str, race_no: int) -> str:
    # Scoring CSV does not carry race class. Keep a conservative unknown bucket
    # unless a future export adds class metadata.
    return "Class unknown"


def field_bucket(size: int) -> str:
    if size <= 8:
        return "Field <=8"
    if size <= 12:
        return "Field 9-12"
    return "Field 13+"


def condition_bucket(_meeting: str) -> str:
    return "Condition unknown"


def load_archive_races() -> list[dict]:
    races = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        top3_by_race = parse_reflector_top3(meeting_dir / "Race_Results_Reflector.md")
        if not top3_by_race:
            continue
        csv_paths = [meeting_dir / "Meeting_Auto_Scoring.csv"]
        if not csv_paths[0].exists():
            csv_paths = sorted(meeting_dir.glob("Race_*_Auto_Scoring.csv"))
        rows_by_race: dict[int, list[dict]] = defaultdict(list)
        for csv_path in csv_paths:
            if not csv_path.exists():
                continue
            try:
                text = read_text_retry(csv_path)
            except TimeoutError:
                continue
            for row in csv.DictReader(text.splitlines()):
                race_no = parse_int(row.get("race_number"))
                horse_no = parse_int(row.get("horse_number"))
                if not race_no or not horse_no or race_no not in top3_by_race:
                    continue
                actual_top3 = top3_by_race[race_no]
                actual_pos = actual_top3.index(horse_no) + 1 if horse_no in actual_top3 else 99
                feature_scores = {key: as_float(row.get(key), 60.0) for key in FEATURE_KEYS}
                matrix_scores = {
                    "stability": feature_scores["consistency_score"],
                    "sectional": feature_scores["sectional_score"],
                    "race_shape": feature_scores["pace_map_score"],
                    "jockey_trainer": mean([
                        feature_scores["jockey_score"],
                        feature_scores["trainer_score"],
                        feature_scores["jockey_horse_fit_score"],
                    ]),
                    "class_weight": mean([
                        feature_scores["class_score"],
                        feature_scores["rating_score"],
                        feature_scores["weight_score"],
                    ]),
                    "track": feature_scores["track_score"],
                    "form_line": feature_scores["formline_score"],
                }
                rows_by_race[race_no].append(
                    {
                        "horse_number": horse_no,
                        "horse_name": str(row.get("horse_name") or "").strip(),
                        "actual_pos": actual_pos,
                        "ability_score": as_float(row.get("ability_score")),
                        "rank_score": as_float(row.get("rank_score"), as_float(row.get("ability_score"))),
                        "feature_scores": feature_scores,
                        "matrix_scores": matrix_scores,
                    }
                )
        for race_no, horses in rows_by_race.items():
            if len(horses) < 4:
                continue
            base_ranked = rank_horses(horses, lambda horse, race: horse["rank_score"], {})
            meta = {
                "date": date_key(meeting_dir.name),
                "meeting": meeting_dir.name,
                "venue": venue_key(meeting_dir.name),
                "race_no": race_no,
                "field_bucket": field_bucket(len(horses)),
                "condition_bucket": condition_bucket(meeting_dir.name),
                "class_bucket": class_bucket(meeting_dir.name, race_no),
                "_base_ranked": base_ranked,
            }
            races.append({**meta, "horses": horses})
    return sorted(races, key=lambda race: (race["date"], race["meeting"], race["race_no"]))


def rank_horses(horses: list[dict], score_fn, race: dict) -> list[dict]:
    return sorted(
        ({**horse, "_score": score_fn(horse, race)} for horse in horses),
        key=lambda row: (-row["_score"], -row["ability_score"], row["horse_number"]),
    )


def baseline_score(horse: dict, _race: dict) -> float:
    return horse["rank_score"]


def close_gap_score(horse: dict, race: dict) -> float:
    score = horse["rank_score"]
    base_ranked = race.get("_base_ranked") or rank_horses(race["horses"], baseline_score, race)
    rank_map = {row["horse_number"]: idx for idx, row in enumerate(base_ranked, start=1)}
    rank = rank_map.get(horse["horse_number"], 999)
    if 4 <= rank <= 6:
        third_score = base_ranked[2]["rank_score"] if len(base_ranked) >= 3 else score
        gap = third_score - score
        mx = horse["matrix_scores"]
        if gap <= 3.0 and (
            as_float(mx.get("stability"), 60) >= 66
            or as_float(mx.get("form_line"), 60) >= 66
            or as_float(mx.get("class_weight"), 60) >= 66
        ):
            score += 1.15
    return score


def jt_conf_score(horse: dict, _race: dict) -> float:
    score = horse["rank_score"]
    mx = horse["matrix_scores"]
    fs = horse["feature_scores"]
    jt = as_float(mx.get("jockey_trainer"), 60)
    confidence = as_float(fs.get("confidence_score"), 60)
    fit = as_float(fs.get("jockey_horse_fit_score"), 60)
    if jt >= 66 and confidence >= 82:
        score += 1.0
    if fit >= 68 and confidence >= 80:
        score += 0.45
    return score


def pace_track_score(horse: dict, _race: dict) -> float:
    score = horse["rank_score"]
    mx = horse["matrix_scores"]
    fs = horse["feature_scores"]
    race_shape = as_float(mx.get("race_shape"), 60)
    track = as_float(mx.get("track"), 60)
    pace = as_float(fs.get("pace_map_score"), 60)
    sectional = as_float(mx.get("sectional"), 60)
    if race_shape >= 65 and track >= 64:
        score += 0.75
    if pace >= 64 and sectional >= 62:
        score += 0.45
    return score


def combined_score(horse: dict, race: dict) -> float:
    score = horse["rank_score"]
    score += close_gap_score(horse, race) - horse["rank_score"]
    score += (jt_conf_score(horse, race) - horse["rank_score"]) * 0.75
    score += (pace_track_score(horse, race) - horse["rank_score"]) * 0.75
    return score


def race_label(ranked: list[dict]) -> str:
    hits = sum(1 for row in ranked[:3] if row["actual_pos"] <= 3)
    top2_hits = sum(1 for row in ranked[:2] if row["actual_pos"] <= 3)
    if hits == 3:
        return "Gold"
    if top2_hits == 2:
        return "Good"
    if hits >= 2:
        return "Pass"
    if hits == 1:
        return "1 Hit"
    return "Miss"


def evaluate(races: list[dict], score_fn) -> tuple[EvalResult, list[dict]]:
    labels = Counter()
    top3_hits = 0
    winner_in_top3 = 0
    top1 = 0
    rows = []
    for race in races:
        ranked = rank_horses(race["horses"], score_fn, race)
        label = race_label(ranked)
        labels[label] += 1
        hits = sum(1 for row in ranked[:3] if row["actual_pos"] <= 3)
        top3_hits += hits
        if any(row["actual_pos"] == 1 for row in ranked[:3]):
            winner_in_top3 += 1
        if ranked[0]["actual_pos"] == 1:
            top1 += 1
        rows.append(
            {
                "date": race["date"],
                "meeting": race["meeting"],
                "venue": race["venue"],
                "race_no": race["race_no"],
                "field_bucket": race["field_bucket"],
                "condition_bucket": race["condition_bucket"],
                "class_bucket": race["class_bucket"],
                "label": label,
                "hits": hits,
                "top3": " / ".join(f"#{row['horse_number']} {row['horse_name']}({row['actual_pos']})" for row in ranked[:3]),
            }
        )
    return (
        EvalResult(
            races=len(races),
            gold=labels["Gold"],
            good=labels["Good"],
            pass_=labels["Pass"],
            one_hit=labels["1 Hit"],
            miss=labels["Miss"],
            top3_hits=top3_hits,
            winner_in_top3=winner_in_top3,
            top1=top1,
        ),
        rows,
    )


def delta_summary(base: EvalResult, trial: EvalResult) -> dict:
    return {
        "top3_precision_delta": trial.top3_precision - base.top3_precision,
        "winner_in_top3_delta": trial.winner_in_top3_rate - base.winner_in_top3_rate,
        "top1_delta": trial.top1_rate - base.top1_rate,
        "miss_delta": trial.miss - base.miss,
        "pass_plus_delta": (trial.gold + trial.good + trial.pass_) - (base.gold + base.good + base.pass_),
    }


def month_key(date: str) -> str:
    return date[:7]


def grouped_eval(races: list[dict], key_fn, min_races: int = 1) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for race in races:
        groups[str(key_fn(race))].append(race)
    output = []
    for key, group in sorted(groups.items()):
        if len(group) < min_races:
            continue
        base, _ = evaluate(group, baseline_score)
        trial, _ = evaluate(group, combined_score)
        output.append({"bucket": key, "base": base, "trial": trial, **delta_summary(base, trial)})
    return output


def gate_result(overall: dict, walk: list[dict], venue: list[dict]) -> tuple[str, list[str]]:
    reasons = []
    status = "REJECT"
    if overall["top3_precision_delta"] < 0:
        reasons.append("overall top3 precision worsened")
    if overall["winner_in_top3_delta"] < 0:
        reasons.append("overall winner-in-top3 worsened")
    if overall["miss_delta"] > 0:
        reasons.append("overall miss count increased")
    walk_positive = sum(1 for row in walk if row["top3_precision_delta"] > 0)
    walk_negative = sum(1 for row in walk if row["top3_precision_delta"] < 0)
    if walk_negative > walk_positive:
        reasons.append("walk-forward monthly negatives exceed positives")
    venue_negative = [row for row in venue if row["base"].races >= 8 and row["top3_precision_delta"] < -0.02]
    if venue_negative:
        reasons.append("material venue bucket regressions detected")
    if not reasons and overall["top3_precision_delta"] > 0:
        status = "PASS_TO_SIP_REVIEW"
    elif overall["top3_precision_delta"] > 0:
        status = "OBSERVE_ONLY"
    return status, reasons


def render_eval(label: str, base: EvalResult, trial: EvalResult) -> list[str]:
    return [
        f"## {label}",
        "",
        f"- Races: **{base.races}**",
        f"- Top3 precision: **{pct(base.top3_precision)} -> {pct(trial.top3_precision)}**",
        f"- Winner in Top3: **{pct(base.winner_in_top3_rate)} -> {pct(trial.winner_in_top3_rate)}**",
        f"- Top1 winner: **{pct(base.top1_rate)} -> {pct(trial.top1_rate)}**",
        f"- Labels baseline: Gold {base.gold}, Good {base.good}, Pass {base.pass_}, 1 Hit {base.one_hit}, Miss {base.miss}",
        f"- Labels combined: Gold {trial.gold}, Good {trial.good}, Pass {trial.pass_}, 1 Hit {trial.one_hit}, Miss {trial.miss}",
        "",
    ]


def render_bucket_table(title: str, rows: list[dict], limit: int = 40) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Bucket | Races | Top3 Precision | Winner Top3 | Miss | Pass+ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:limit]:
        base = row["base"]
        trial = row["trial"]
        lines.append(
            f"| {row['bucket']} | {base.races} | {pct(base.top3_precision)} -> {pct(trial.top3_precision)} "
            f"({row['top3_precision_delta']:+.1%}) | {pct(base.winner_in_top3_rate)} -> {pct(trial.winner_in_top3_rate)} "
            f"({row['winner_in_top3_delta']:+.1%}) | {base.miss} -> {trial.miss} ({row['miss_delta']:+d}) | "
            f"{base.gold + base.good + base.pass_} -> {trial.gold + trial.good + trial.pass_} ({row['pass_plus_delta']:+d}) |"
        )
    lines.append("")
    return lines


def write_rows(base_rows: list[dict], trial_rows: list[dict]) -> None:
    by_key = {
        (row["date"], row["meeting"], row["race_no"]): row
        for row in base_rows
    }
    with ROWS_PATH.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "date",
            "meeting",
            "venue",
            "race_no",
            "base_label",
            "combined_label",
            "base_hits",
            "combined_hits",
            "base_top3",
            "combined_top3",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for trial in trial_rows:
            key = (trial["date"], trial["meeting"], trial["race_no"])
            base = by_key.get(key)
            if not base:
                continue
            writer.writerow(
                {
                    "date": trial["date"],
                    "meeting": trial["meeting"],
                    "venue": trial["venue"],
                    "race_no": trial["race_no"],
                    "base_label": base["label"],
                    "combined_label": trial["label"],
                    "base_hits": base["hits"],
                    "combined_hits": trial["hits"],
                    "base_top3": base["top3"],
                    "combined_top3": trial["top3"],
                }
            )


def main() -> int:
    print("Loading archive races with scoring CSV + reflector results...", flush=True)
    races = load_archive_races()
    print(f"Loaded races: {len(races)}", flush=True)
    base, base_rows = evaluate(races, baseline_score)
    trial, trial_rows = evaluate(races, combined_score)
    overall_delta = delta_summary(base, trial)
    by_month = grouped_eval(races, lambda race: month_key(race["date"]), min_races=3)
    by_venue = grouped_eval(races, lambda race: race["venue"], min_races=3)
    by_field = grouped_eval(races, lambda race: race["field_bucket"], min_races=3)
    by_condition = grouped_eval(races, lambda race: race["condition_bucket"], min_races=3)
    status, reasons = gate_result(overall_delta, by_month, by_venue)
    write_rows(base_rows, trial_rows)

    lines = [
        "# AU Combined Candidate Walk-Forward / Bucket Backtest",
        "",
        "Candidate: close-gap + JT/confidence + pace/track post-hoc score, applied after baseline `rank_score`.",
        "",
        f"- Archive races loaded: **{len(races)}**",
        f"- Gate status: **{status}**",
    ]
    if reasons:
        lines.append(f"- Gate reasons: {', '.join(reasons)}")
    lines.append("")
    lines.extend(render_eval("Overall Archive", base, trial))
    lines.extend(render_bucket_table("Walk-Forward By Month", by_month))
    lines.extend(render_bucket_table("Venue Buckets", by_venue))
    lines.extend(render_bucket_table("Field Size Buckets", by_field))
    lines.extend(render_bucket_table("Condition Buckets", by_condition))
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {REPORT_PATH}")
    print(f"Rows: {ROWS_PATH}")
    print(f"Gate: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
