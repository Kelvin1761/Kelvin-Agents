#!/usr/bin/env python3
"""Frozen dual-objective AU shadow scorer and forward promotion tracker.

The scorer is market-free and report-only.  It never mutates Logic JSON,
official ability scores, or official Top2/Top4 selections.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import joblib
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = SCRIPT_DIR.parent / "resources"
MODEL_PATH = RESOURCE_DIR / "dual_objective_shadow_v1.joblib"
MODEL_META = RESOURCE_DIR / "dual_objective_shadow_v1_model.json"
GATE_PATH = RESOURCE_DIR / "dual_objective_shadow_gate_v1.json"

OUTPUT_CSV = "Meeting_Dual_Objective_Shadow.csv"
OUTPUT_REVIEW = "Dual_Objective_Shadow_Forward_Review.md"
OUTPUT_JSON = "Dual_Objective_Shadow_Forward_Review.json"
STATUS_JSON = "Dual_Objective_Shadow_Update_Status.json"
TRACKER_JSON = "AU_Dual_Objective_Shadow_Tracker.json"
TRACKER_MD = "AU_Dual_Objective_Shadow_Tracker.md"
PROMOTION_READY_MD = "AU_Dual_Objective_Promotion_Ready.md"
PROMOTION_STATE_JSON = "AU_Dual_Objective_Promotion_State.json"

HORSE_HEADER = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)
PF_TOKEN = re.compile(r"PF\[(.+?)\]")
CANDIDATES = ("place_rating", "coverage_7d", "coverage_pf")
METRICS = (
    "top1_win", "top1_place", "top2_place_strike", "top2_both_place",
    "top3_slot", "top4_place_coverage", "top4_trifecta", "top5_trifecta",
    "winner_mrr",
)


def as_float(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def normalise_name(value: str) -> str:
    return "".join(character for character in str(value or "").lower() if character.isalnum())


def parse_pf_number(pattern: str, text: str):
    match = re.search(pattern, text)
    return as_float(match.group(1)) if match else None


def parse_pf_string(pattern: str, text: str):
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def going_bucket(value: str) -> str:
    number = parse_pf_number(r"(\d+(?:\.\d+)?)", str(value or ""))
    if number is None:
        text = str(value or "").lower()
        if "heavy" in text:
            return "Heavy"
        if "soft" in text:
            return "Soft"
        return "Unknown"
    if number >= 8:
        return "Heavy"
    if number >= 5:
        return "Soft"
    return "Good/Firm"


def parse_pf_token(token: str) -> dict:
    return {
        "race_time_diff": parse_pf_number(r"Race Time:\s*([-\d.]+)", token),
        "l800_delta": parse_pf_number(r"L800 Delta:\s*([-\d.]+)", token),
        "l600_delta": parse_pf_number(r"L600 Delta:\s*([-\d.]+)", token),
        "l400_delta": parse_pf_number(r"L400 Delta:\s*([-\d.]+)", token),
        "l200_delta": parse_pf_number(r"L200 Delta:\s*([-\d.]+)", token),
        "early_runner_pace": parse_pf_string(r"Early Runner Pace:\s*([^.]+)\.", token),
        "early_race_pace": parse_pf_string(r"Early Race Pace:\s*([^.]+)\.", token),
    }


def parse_run_line(line: str, target_date: str) -> dict | None:
    token_match = PF_TOKEN.search(line)
    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
    if not token_match or not date_match or "**(TRIAL)**" in line:
        return None
    run_date = date_match.group(1)
    if target_date and run_date >= target_date:
        return None
    prefix = line[:date_match.start()].strip()
    track_match = re.match(r"(.+?)\s+R(\d+)\s*$", prefix)
    distance_match = re.search(rf"{re.escape(run_date)}\s+(\d+)m", line)
    condition_match = re.search(r"\bcond:([^\s]+)", line)
    weight_match = re.search(r"\([^)]*\)\s+([0-9.]+)kg", line)
    parsed = parse_pf_token(token_match.group(1))
    parsed.update({
        "run_date": run_date,
        "track": track_match.group(1).strip() if track_match else "Unknown",
        "race_number": int(track_match.group(2)) if track_match else None,
        "distance": int(distance_match.group(1)) if distance_match else None,
        "going_bucket": going_bucket(condition_match.group(1) if condition_match else ""),
        "weight": as_float(weight_match.group(1)) if weight_match else None,
    })
    return parsed


def parse_formguide(path: Path, target_date: str) -> dict[int, dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    headers = list(HORSE_HEADER.finditer(text))
    horses = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[header.end():end]
        runs = [parsed for line in body.splitlines() if (parsed := parse_run_line(line, target_date))]
        horses[int(header.group(1))] = {"horse_name": header.group(2).strip(), "runs": runs}
    return horses


def formguide_map(meeting_dir: Path) -> dict[int, Path]:
    mapping = {}
    for path in meeting_dir.glob("*Formguide.md"):
        match = re.search(r"Race[ _](\d+).*Formguide", path.name, flags=re.I)
        if match:
            mapping[int(match.group(1))] = path
    return mapping


def raw_targets(run: dict) -> tuple[float | None, float | None]:
    sustained_parts = []
    for key, weight in (("race_time_diff", 0.45), ("l800_delta", 0.30), ("l600_delta", 0.25)):
        value = as_float(run.get(key))
        if value is not None:
            sustained_parts.append((value, weight))
    sustained = None
    if sustained_parts:
        sustained = sum(value * weight for value, weight in sustained_parts) / sum(weight for _, weight in sustained_parts)
    l800 = as_float(run.get("l800_delta"))
    late_parts = []
    if l800 is not None:
        for key, weight in (("l400_delta", 0.35), ("l200_delta", 0.65)):
            value = as_float(run.get(key))
            if value is not None:
                late_parts.append((value - l800, weight))
    burst = None
    if late_parts:
        burst = sum(value * weight for value, weight in late_parts) / sum(weight for _, weight in late_parts)
    return sustained, burst


def context_matrix(runs: list[dict]) -> np.ndarray:
    return np.asarray([
        [
            str(run.get("track") or "Unknown"),
            str(run.get("going_bucket") or "Unknown"),
            str(run.get("early_runner_pace") or "Unknown"),
            str(run.get("early_race_pace") or "Unknown"),
            as_float(run.get("distance")),
            as_float(run.get("weight")),
        ]
        for run in runs
    ], dtype=object)


def weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    available = [(value, weight) for value, weight in values if value is not None]
    if not available:
        return None
    return sum(value * weight for value, weight in available) / sum(weight for _, weight in available)


def pf_profile(runs: list[dict], pack: dict) -> dict:
    spec = pack["profile_spec"]
    selected = sorted(runs, key=lambda run: run.get("run_date") or "", reverse=True)[:spec["max_runs"]]
    targets = [raw_targets(run) for run in selected]
    capabilities = {"sustain": [None] * len(selected), "burst": [None] * len(selected)}
    normaliser = pack["pf_normaliser"]
    for index, name in enumerate(("sustain", "burst")):
        keep = [position for position, values in enumerate(targets) if values[index] is not None]
        if not keep:
            continue
        raw = np.asarray([targets[position][index] for position in keep], dtype=float)
        model = normaliser.get(f"{name}_model")
        if model is None:
            scores = -raw
        else:
            expected = model.predict(context_matrix([selected[position] for position in keep]))
            scale = max(as_float(normaliser.get(f"{name}_scale"), 1.0), 0.05)
            scores = -(raw - expected) / scale
        for position, score in zip(keep, scores):
            capabilities[name][position] = float(score)
    usable = sum(any(value is not None for value in pair) for pair in targets)
    shrink = usable / (usable + float(spec["shrinkage_prior_runs"])) if usable else 0.0
    weights = spec["recency_weights"]
    sustain = weighted_average([(value, weights[index]) for index, value in enumerate(capabilities["sustain"])])
    burst = weighted_average([(value, weights[index]) for index, value in enumerate(capabilities["burst"])])
    return {
        "std_sustain": sustain * shrink if sustain is not None else None,
        "std_burst": burst * shrink if burst is not None else None,
        "pf_count": math.log1p(usable),
        "pf_usable_runs": usable,
    }


def load_model_pack(model_path: Path = MODEL_PATH, metadata_path: Path = MODEL_META) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if digest != metadata["sha256"]:
        raise ValueError("Dual-objective model checksum mismatch")
    pack = joblib.load(model_path)
    if pack["version"] != metadata["version"] or pack.get("market_inputs") is not False:
        raise ValueError("Invalid dual-objective model metadata")
    return pack


def race_number(path: Path, logic: dict) -> int:
    value = (logic.get("race_analysis") or {}).get("race_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"Race_(\d+)", path.stem, flags=re.I)
        return int(match.group(1)) if match else 999


def meeting_date(logic: dict, meeting_dir: Path) -> str:
    analysis = logic.get("race_analysis") or {}
    value = (analysis.get("meeting_intelligence") or {}).get("date")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")):
        return str(value)
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting_dir.name)
    return match.group(1) if match else ""


def distance_family(value) -> str:
    match = re.search(r"(\d+)", str(value or ""))
    distance = int(match.group(1)) if match else 0
    if distance <= 1400:
        return "Sprint <=1400m"
    if distance <= 1800:
        return "Middle 1401-1800m"
    return "Staying 1801m+"


def score_meeting(meeting_dir: Path, pack: dict | None = None) -> list[dict]:
    meeting_dir = meeting_dir.resolve()
    pack = pack or load_model_pack()
    guides = formguide_map(meeting_dir)
    rows = []
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda path: race_number(path, {})):
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        number = race_number(logic_path, logic)
        analysis = logic.get("race_analysis") or {}
        target_date = meeting_date(logic, meeting_dir)
        guide_horses = parse_formguide(guides[number], target_date) if number in guides else {}
        race_rows = []
        for number_text, horse in (logic.get("horses") or {}).items():
            auto = horse.get("python_auto") or {}
            ability = as_float(auto.get("ability_score"))
            if ability is None:
                continue
            horse_number = int(number_text)
            guide = guide_horses.get(horse_number, {"runs": []})
            if guide and normalise_name(guide.get("horse_name")) != normalise_name(horse.get("horse_name")):
                guide = next((item for item in guide_horses.values() if normalise_name(item.get("horse_name")) == normalise_name(horse.get("horse_name"))), {"runs": []})
            matrices = auto.get("matrix_scores") or auto.get("matrix") or {}
            base = [as_float(matrices.get(key), 60.0) for key in pack["matrix_order"]]
            profile = pf_profile(guide.get("runs", []), pack)
            race_rows.append({
                "race_number": number,
                "horse_number": horse_number,
                "horse_name": str(horse.get("horse_name") or ""),
                "baseline_score": ability,
                "base_features": base,
                "pf_features": base + [profile["std_sustain"], profile["std_burst"], profile["pf_count"]],
                "pf_usable_runs": profile["pf_usable_runs"],
                "distance_family": distance_family(analysis.get("distance")),
                "going": str(analysis.get("going") or (analysis.get("speed_map") or {}).get("going") or "Unknown"),
                "track": str((analysis.get("meeting_intelligence") or {}).get("venue") or meeting_dir.name),
                "model_version": pack["version"],
            })
        if not race_rows:
            continue
        base_x = np.asarray([row["base_features"] for row in race_rows], dtype=float)
        pf_x = np.asarray([row["pf_features"] for row in race_rows], dtype=float)
        predictions = {
            "place_rating_score": pack["place_model"].predict_proba(base_x)[:, 1],
            "coverage_7d_score": pack["coverage_7d_model"].predict_proba(base_x)[:, 1],
            "coverage_pf_score": pack["coverage_pf_model"].predict_proba(pf_x)[:, 1],
        }
        for index, row in enumerate(race_rows):
            for key, values in predictions.items():
                row[key] = float(values[index])
            row.pop("base_features")
            row.pop("pf_features")
        for score_key, rank_key in (
            ("baseline_score", "baseline_rank"),
            ("place_rating_score", "place_rating_rank"),
            ("coverage_7d_score", "coverage_7d_rank"),
            ("coverage_pf_score", "coverage_pf_rank"),
        ):
            ordered = sorted(race_rows, key=lambda row: (-row[score_key], row["horse_number"]))
            for rank, row in enumerate(ordered, 1):
                row[rank_key] = rank
        rows.extend(race_rows)
    if not rows:
        raise ValueError(f"No scoreable Logic files found in {meeting_dir}")
    return rows


def write_meeting_shadow(meeting_dir: Path, pack: dict | None = None) -> tuple[Path, list[dict]]:
    rows = score_meeting(meeting_dir, pack)
    output = Path(meeting_dir).resolve() / OUTPUT_CSV
    fieldnames = [
        "race_number", "horse_number", "horse_name", "baseline_rank",
        "place_rating_rank", "coverage_7d_rank", "coverage_pf_rank",
        "baseline_score", "place_rating_score", "coverage_7d_score", "coverage_pf_score",
        "pf_usable_runs", "distance_family", "going", "track", "model_version",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["race_number"], row["baseline_rank"])))
    return output, rows


def parse_results_markdown(path: Path) -> dict[int, dict[int, int]]:
    results = defaultdict(dict)
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"## Race\s+(\d+):", line)
        if match:
            current = int(match.group(1))
            continue
        if current is None or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit() and cells[1].isdigit():
            results[current][int(cells[1])] = int(cells[0])
    return dict(results)


def race_metrics(ranked: list[dict], actual: dict[int, int]) -> dict[str, float]:
    starters = [row for row in ranked if row["horse_number"] in actual]
    if not starters:
        return {key: 0.0 for key in METRICS}
    winner_rank = next((index for index, row in enumerate(starters, 1) if actual[row["horse_number"]] == 1), len(starters))
    top2 = sum(actual[row["horse_number"]] <= 3 for row in starters[:2])
    top3 = sum(actual[row["horse_number"]] <= 3 for row in starters[:3])
    top4 = sum(actual[row["horse_number"]] <= 3 for row in starters[:4])
    top5 = sum(actual[row["horse_number"]] <= 3 for row in starters[:5])
    return {
        "top1_win": float(actual[starters[0]["horse_number"]] == 1),
        "top1_place": float(actual[starters[0]["horse_number"]] <= 3),
        "top2_place_strike": top2 / 2.0,
        "top2_both_place": float(top2 == 2),
        "top3_slot": top3 / 3.0,
        "top4_place_coverage": top4 / 3.0,
        "top4_trifecta": float(top4 == 3),
        "top5_trifecta": float(top5 == 3),
        "winner_mrr": 1.0 / winner_rank,
    }


def evaluate(rows: list[dict], results: dict[int, dict[int, int]]) -> tuple[dict, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["race_number"])].append(row)
    scores = {
        "baseline": "baseline_score",
        "place_rating": "place_rating_score",
        "coverage_7d": "coverage_7d_score",
        "coverage_pf": "coverage_pf_score",
    }
    values = {name: [] for name in scores}
    details = []
    for race_number_value in sorted(set(grouped) & set(results)):
        actual = results[race_number_value]
        sample = grouped[race_number_value][0]
        detail = {
            "race_number": race_number_value,
            "distance_family": sample["distance_family"],
            "going": sample["going"],
            "track": sample["track"],
            "actual_top3": [number for number, position in sorted(actual.items(), key=lambda item: item[1]) if position <= 3],
            "variants": {},
        }
        for name, score_key in scores.items():
            ranked = sorted(grouped[race_number_value], key=lambda row: (-row[score_key], row["horse_number"]))
            starters = [row for row in ranked if row["horse_number"] in actual]
            metrics = race_metrics(ranked, actual)
            values[name].append(metrics)
            detail["variants"][name] = {
                "top1": starters[0]["horse_number"],
                "top2": [row["horse_number"] for row in starters[:2]],
                "top4": [row["horse_number"] for row in starters[:4]],
                "metrics": metrics,
            }
        details.append(detail)
    summaries = {
        name: ({key: mean(row[key] for row in rows_for_variant) for key in METRICS} | {"races": len(rows_for_variant)})
        if rows_for_variant else {"races": 0}
        for name, rows_for_variant in values.items()
    }
    return summaries, details


def bootstrap_ci(values: list[float], seed: int = 20260713) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    simulations = sorted(mean(values[rng.randrange(len(values))] for _ in values) for _ in range(3000))
    return simulations[int(0.025 * len(simulations))], simulations[int(0.975 * len(simulations))]


def render_review(pack: dict, summaries: dict, details: list[dict]) -> str:
    baseline = summaries["baseline"]
    lines = [
        "# AU Dual-Objective Shadow Forward Review", "",
        f"- Frozen model: `{pack['version']}`; trained through **{pack['trained_through']}**.",
        "- Market odds, SP, favourite rank and market movement are not model inputs.",
        "- Official ability score and official Top2/Top4 remain unchanged.",
        f"- Forward races evaluated: **{baseline['races']}**.", "",
        "| Candidate | Top1 | Top2 place | Top2 both | Top4 coverage | Top4 exact | Top5 exact |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("baseline", *CANDIDATES):
        row = summaries[name]
        lines.append(
            f"| {name} | {100 * row['top1_win']:.2f}% | {100 * row['top2_place_strike']:.2f}% | "
            f"{100 * row['top2_both_place']:.2f}% | {100 * row['top4_place_coverage']:.2f}% | "
            f"{100 * row['top4_trifecta']:.2f}% | {100 * row['top5_trifecta']:.2f}% |"
        )
    lines.extend(["", "## Race-level selections", "", "| Race | Actual Top3 | Baseline Top2 | Place Top2 | Coverage 7D Top4 | Coverage PF Top4 |", "|---:|---|---|---|---|---|"])
    for detail in details:
        variants = detail["variants"]
        lines.append(
            f"| {detail['race_number']} | {detail['actual_top3']} | {variants['baseline']['top2']} | "
            f"{variants['place_rating']['top2']} | {variants['coverage_7d']['top4']} | {variants['coverage_pf']['top4']} |"
        )
    lines.extend(["", "Forward results are accumulated automatically by `AU_Dual_Objective_Shadow_Tracker.md`.", ""])
    return "\n".join(lines)


def meeting_track(path: str) -> str:
    name = Path(path).name
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", name)
    return re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", name, flags=re.I).strip()


def focus_spec(candidate: str, gate: dict) -> dict:
    if candidate == "place_rating":
        return {"metric": "top2_place_strike", "ci_metric": "top2_place_strike", "gate": gate["main_promotion_gate"]["place_rating"]}
    return {"metric": "top4_place_coverage", "ci_metric": "top4_place_coverage", "gate": gate["main_promotion_gate"]["trifecta_coverage_rating"]}


def update_tracker(archive_root: Path, model_version: str, gate_path: Path = GATE_PATH) -> tuple[Path, Path, Path | None]:
    batches = []
    for path in sorted(archive_root.glob(f"*/{OUTPUT_JSON}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (payload.get("model") or {}).get("version") == model_version:
            batches.append(payload)
    if not batches:
        raise ValueError(f"No dual-objective forward batches found for {model_version}")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    rows = []
    for batch in batches:
        meeting = batch["meeting"]
        for detail in batch["race_details"]:
            rows.append({"meeting": meeting, **detail})
    baseline_metrics = {key: mean(row["variants"]["baseline"]["metrics"][key] for row in rows) for key in METRICS}
    tracks = sorted({meeting_track(row["meeting"]) for row in rows})
    distance_counts = {family: sum(row["distance_family"] == family for row in rows) for family in gate["main_promotion_gate"]["distance_families"]}
    candidate_results = {}
    for candidate in CANDIDATES:
        metrics = {key: mean(row["variants"][candidate]["metrics"][key] for row in rows) for key in METRICS}
        deltas = {key: metrics[key] - baseline_metrics[key] for key in METRICS}
        focus = focus_spec(candidate, gate)
        per_race = [row["variants"][candidate]["metrics"][focus["metric"]] - row["variants"]["baseline"]["metrics"][focus["metric"]] for row in rows]
        ci = bootstrap_ci(per_race)
        blocks = []
        for block_number in range(gate["main_promotion_gate"]["time_consistency"]["blocks"]):
            start = len(rows) * block_number // gate["main_promotion_gate"]["time_consistency"]["blocks"]
            end = len(rows) * (block_number + 1) // gate["main_promotion_gate"]["time_consistency"]["blocks"]
            values = per_race[start:end]
            delta = mean(values) if values else 0.0
            blocks.append({"block": block_number + 1, "races": len(values), "focus_delta": delta, "nonnegative": delta >= 0})
        nonnegative_blocks = sum(block["nonnegative"] for block in blocks)
        windows = []
        if len(per_race) >= 100:
            for start in (len(per_race) - 100, len(per_race) - 50):
                window = per_race[start:start + 50]
                windows.append({"start": start + 1, "end": start + 50, "focus_delta": mean(window), "positive": mean(window) > 0})
        consecutive_positive = len(windows) == 2 and all(window["positive"] for window in windows)
        segment_rows = []
        segment_safe = True
        segment_gate = gate["main_promotion_gate"]["segment_safety"]
        for dimension in ("track", "distance_family", "going"):
            grouped = defaultdict(list)
            for row, value in zip(rows, per_race):
                group = meeting_track(row["meeting"]) if dimension == "track" else row[dimension]
                grouped[group].append((row, value))
            for group, pairs in grouped.items():
                if len(pairs) < segment_gate["minimum_segment_races"]:
                    continue
                focus_delta = mean(value for _, value in pairs)
                top1_delta = mean(pair[0]["variants"][candidate]["metrics"]["top1_win"] - pair[0]["variants"]["baseline"]["metrics"]["top1_win"] for pair in pairs)
                safe = focus_delta * 100 >= -segment_gate["maximum_focus_metric_decline_pp"] and top1_delta * 100 >= -segment_gate["maximum_top1_decline_pp"]
                segment_safe &= safe
                segment_rows.append({"dimension": dimension, "segment": group, "races": len(pairs), "focus_delta": focus_delta, "top1_delta": top1_delta, "safe": safe})
        common = (
            len(rows) >= gate["main_promotion_gate"]["minimum_forward_races"]
            and len(tracks) >= gate["main_promotion_gate"]["minimum_tracks"]
            and all(distance_counts[family] >= minimum for family, minimum in gate["main_promotion_gate"]["distance_families"].items())
            and nonnegative_blocks >= gate["main_promotion_gate"]["time_consistency"]["minimum_nonnegative_focus_blocks"]
            and consecutive_positive
            and segment_safe
        )
        if candidate == "place_rating":
            candidate_gate = focus["gate"]
            metric_gate = (
                deltas["top1_win"] * 100 >= candidate_gate["top1_delta_floor_pp"]
                and deltas["top2_place_strike"] * 100 >= candidate_gate["top2_place_delta_target_pp"]
                and ci[0] * 100 >= candidate_gate["top2_place_ci95_lower_floor_pp"]
                and deltas["top2_both_place"] * 100 >= candidate_gate["top2_both_delta_floor_pp"]
            )
        else:
            candidate_gate = focus["gate"]
            metric_gate = (
                deltas["top4_trifecta"] * 100 >= candidate_gate["top4_exact_delta_floor_pp"]
                and deltas["top4_place_coverage"] * 100 >= candidate_gate["top4_coverage_delta_target_pp"]
                and ci[0] * 100 >= candidate_gate["top4_coverage_ci95_lower_floor_pp"]
                and deltas["top5_trifecta"] * 100 >= candidate_gate["top5_exact_delta_floor_pp"]
            )
        eligible = bool(common and metric_gate)
        candidate_results[candidate] = {
            "metrics": metrics, "deltas": deltas, "focus_metric": focus["metric"], "focus_ci95": ci,
            "blocks": blocks, "nonnegative_blocks": nonnegative_blocks, "consecutive_positive_50_race_windows": consecutive_positive,
            "windows": windows, "segments": segment_rows, "segment_safe": segment_safe,
            "promotion_eligible": eligible,
            "next_action": "HUMAN_APPROVAL_FOR_50_RACE_CANARY" if eligible else "CONTINUE_FROZEN_FORWARD_SHADOW",
        }
    state_path = archive_root / PROMOTION_STATE_JSON
    canary_state = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {"status": "invalid_state_file"}
        if state.get("model_version") == model_version and state.get("candidate") in CANDIDATES:
            candidate = state["candidate"]
            start = int(state.get("started_after_forward_races") or 0)
            canary_rows = rows[start:]
            canary_state = {**state, "races": len(canary_rows), "required_races": gate["canary_and_rollback"]["canary_races"]}
            if len(canary_rows) >= gate["canary_and_rollback"]["canary_races"]:
                window = canary_rows[-gate["canary_and_rollback"]["canary_races"]:]
                canary_deltas = {
                    key: mean(row["variants"][candidate]["metrics"][key] - row["variants"]["baseline"]["metrics"][key] for row in window)
                    for key in METRICS
                }
                thresholds = gate["canary_and_rollback"]["automatic_rollback_on_rolling_50"]
                if candidate == "place_rating":
                    failed = (
                        canary_deltas["top2_place_strike"] * 100 <= thresholds["place_top2_delta_at_or_below_pp"]
                        or canary_deltas["top1_win"] * 100 <= thresholds["top1_delta_at_or_below_pp"]
                    )
                else:
                    failed = (
                        canary_deltas["top4_trifecta"] * 100 <= thresholds["coverage_top4_exact_delta_at_or_below_pp"]
                        or canary_deltas["top4_place_coverage"] * 100 <= thresholds["coverage_top4_coverage_delta_at_or_below_pp"]
                    )
                canary_state["rolling_50_deltas"] = canary_deltas
                canary_state["status"] = "CANARY_FAILED_STOP_AND_ROLLBACK" if failed else "CANARY_PASSED_MAIN_APPROVAL_REQUIRED"
            else:
                canary_state["status"] = "CANARY_ACTIVE"
            state_path.write_text(json.dumps(canary_state, ensure_ascii=False, indent=2), encoding="utf-8")

    tracker = {
        "model_version": model_version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "forward_races": len(rows), "meetings": len(batches), "tracks": tracks,
        "distance_family_counts": distance_counts, "promotion_gate": gate["main_promotion_gate"],
        "baseline": baseline_metrics, "candidates": candidate_results,
        "batch_files": [batch["meeting"] for batch in batches],
        "canary_state": canary_state,
        "official_model_changed": False,
    }
    json_path = archive_root / TRACKER_JSON
    md_path = archive_root / TRACKER_MD
    json_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# AU Dual-Objective Shadow Tracker", "",
        f"- Model: `{model_version}`; progress **{len(rows)}/{gate['main_promotion_gate']['minimum_forward_races']} races**.",
        f"- Meetings: **{len(batches)}**; tracks: **{len(tracks)}/{gate['main_promotion_gate']['minimum_tracks']}**.",
        "- Distance coverage: " + ", ".join(f"{family} {distance_counts[family]}/{minimum}" for family, minimum in gate["main_promotion_gate"]["distance_families"].items()) + ".",
        "- Official model remains unchanged; promotion requires explicit human approval and a 50-race canary.", "",
        "| Candidate | Top1 Δ | Top2 Δ | Top4 coverage Δ | Top4 exact Δ | Focus 95% CI | Blocks | Segment | Status |",
        "|---|---:|---:|---:|---:|---|---:|---|---|",
    ]
    for candidate in CANDIDATES:
        result = candidate_results[candidate]
        lines.append(
            f"| {candidate} | {100 * result['deltas']['top1_win']:+.2f}pp | {100 * result['deltas']['top2_place_strike']:+.2f}pp | "
            f"{100 * result['deltas']['top4_place_coverage']:+.2f}pp | {100 * result['deltas']['top4_trifecta']:+.2f}pp | "
            f"[{100 * result['focus_ci95'][0]:+.2f}, {100 * result['focus_ci95'][1]:+.2f}]pp | "
            f"{result['nonnegative_blocks']}/{gate['main_promotion_gate']['time_consistency']['blocks']} | {'SAFE' if result['segment_safe'] else 'FAIL'} | "
            f"{'READY FOR APPROVAL' if result['promotion_eligible'] else 'NOT YET'} |"
        )
    lines.extend(["", "## Recorded meetings", ""])
    lines.extend(f"- `{Path(batch['meeting']).name}` — {batch['summaries']['baseline']['races']} races" for batch in batches)
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    eligible = [candidate for candidate, result in candidate_results.items() if result["promotion_eligible"]]
    promotion_path = archive_root / PROMOTION_READY_MD
    if canary_state and canary_state.get("status") == "CANARY_PASSED_MAIN_APPROVAL_REQUIRED":
        promotion_path.write_text(
            "# AU Dual-Objective Canary Passed\n\n"
            f"Candidate `{canary_state['candidate']}` passed the frozen 50-race canary.\n\n"
            "No production change has been made. Explicit main-model approval is required.\n",
            encoding="utf-8",
        )
    elif canary_state and canary_state.get("status") == "CANARY_FAILED_STOP_AND_ROLLBACK":
        promotion_path.write_text(
            "# AU Dual-Objective Canary Failed\n\n"
            f"Candidate `{canary_state['candidate']}` breached the rolling 50-race rollback gate.\n\n"
            "Canary must stop. Official production ranking remains unchanged.\n",
            encoding="utf-8",
        )
    elif eligible and not canary_state:
        promotion_path.write_text(
            "# AU Dual-Objective Promotion Ready\n\n"
            f"Eligible frozen candidate(s): {', '.join(f'`{name}`' for name in eligible)}.\n\n"
            "No production change has been made. Explicit approval is required to start the 50-race canary.\n"
            "Use `au_dual_objective_shadow.py <AU_Racing archive> --approve-canary <candidate>`.\n",
            encoding="utf-8",
        )
    elif canary_state:
        promotion_path.write_text(
            "# AU Dual-Objective Canary Active\n\n"
            f"Candidate `{canary_state['candidate']}`: {canary_state['races']}/{canary_state['required_races']} races.\n\n"
            "Official production ranking remains unchanged. Race Reflector will continue updating this state automatically.\n",
            encoding="utf-8",
        )
    elif not canary_state and promotion_path.exists():
        promotion_path.unlink()
    ready = promotion_path if promotion_path.exists() else None
    return json_path, md_path, ready


def approve_canary(archive_root: Path, candidate: str) -> Path:
    archive_root = archive_root.resolve()
    tracker_path = archive_root / TRACKER_JSON
    if not tracker_path.exists():
        raise ValueError("Dual-objective tracker does not exist")
    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    if candidate not in CANDIDATES:
        raise ValueError(f"Unknown candidate: {candidate}")
    if not (tracker.get("candidates") or {}).get(candidate, {}).get("promotion_eligible"):
        raise ValueError(f"Candidate is not promotion-eligible: {candidate}")
    state = {
        "model_version": tracker["model_version"],
        "candidate": candidate,
        "status": "CANARY_ACTIVE",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "started_after_forward_races": tracker["forward_races"],
        "races": 0,
        "official_model_changed": False,
    }
    path = archive_root / PROMOTION_STATE_JSON
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_review(meeting_dir: Path, results_md: Path) -> tuple[Path, Path, Path]:
    pack = load_model_pack()
    csv_path, rows = write_meeting_shadow(meeting_dir, pack)
    summaries, details = evaluate(rows, parse_results_markdown(results_md))
    payload = {
        "model": {key: pack[key] for key in ("version", "trained_through", "training_races", "training_runners", "market_inputs")},
        "meeting": str(Path(meeting_dir).resolve()), "results_file": str(Path(results_md).resolve()),
        "summaries": summaries, "race_details": details,
    }
    meeting_dir = Path(meeting_dir).resolve()
    json_path = meeting_dir / OUTPUT_JSON
    review_path = meeting_dir / OUTPUT_REVIEW
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path.write_text(render_review(pack, summaries, details), encoding="utf-8")
    tracker_json, tracker_md, promotion = update_tracker(meeting_dir.parent, pack["version"])
    status = {
        "status": "updated", "updated_at": datetime.now(timezone.utc).isoformat(),
        "meeting": str(meeting_dir), "forward_races_in_meeting": summaries["baseline"]["races"],
        "csv": str(csv_path), "review": str(review_path), "tracker_json": str(tracker_json),
        "tracker_markdown": str(tracker_md), "promotion_ready": str(promotion) if promotion else None,
        "official_model_changed": False,
    }
    status_path = meeting_dir / STATUS_JSON
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, review_path, status_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AU frozen dual-objective shadow scorer")
    parser.add_argument("meeting_dir", type=Path)
    parser.add_argument("--results-md", type=Path)
    parser.add_argument("--approve-canary", choices=CANDIDATES)
    args = parser.parse_args()
    if args.approve_canary:
        print(approve_canary(args.meeting_dir, args.approve_canary))
    elif args.results_md:
        csv_path, review_path, status_path = run_review(args.meeting_dir, args.results_md)
        print(csv_path)
        print(review_path)
        print(status_path)
    else:
        csv_path, rows = write_meeting_shadow(args.meeting_dir)
        print(f"{csv_path} ({len(rows)} runners)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
