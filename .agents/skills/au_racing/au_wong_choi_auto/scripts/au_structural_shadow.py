#!/usr/bin/env python3
"""Frozen market-free structural shadow scorer for AU Wong Choi.

The module writes separate shadow artefacts and never mutates Logic JSON,
``python_auto.ability_score``, or the official AU ranking outputs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR.parent / "resources/structural_shadow_v1.json"
OUTPUT_CSV = "Meeting_Structural_Shadow.csv"
OUTPUT_REVIEW = "Structural_Shadow_Forward_Review.md"
OUTPUT_JSON = "Structural_Shadow_Forward_Review.json"
TRACKER_JSON = "AU_Structural_Shadow_Tracker.json"
TRACKER_MD = "AU_Structural_Shadow_Tracker.md"


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clip(value: float, low: float = -3.0, high: float = 3.0) -> float:
    return min(high, max(low, value))


def zmap(values: list[float | None]) -> list[float]:
    available = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if len(available) < 3:
        return [0.0] * len(values)
    centre = median(available)
    scale = 1.4826 * median(abs(value - centre) for value in available)
    if scale < 1e-8:
        centre = mean(available)
        scale = math.sqrt(mean((value - centre) ** 2 for value in available))
    if scale < 1e-8:
        return [0.0] * len(values)
    return [0.0 if value is None else clip((float(value) - centre) / scale) for value in values]


def average(values: list[float]) -> float:
    return mean(values) if values else 0.0


def pace_bucket(value: str) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("快", "fast", "strong", "高")):
        return "fast"
    if any(token in text for token in ("慢", "slow", "soft", "低")):
        return "slow"
    return "normal"


def horse_style(speed_map: dict, horse_number: int) -> str:
    for source, label in (
        ("leaders", "leader"),
        ("pressers", "presser"),
        ("on_pace", "on_pace"),
        ("mid_pack", "mid"),
        ("closers", "closer"),
    ):
        numbers = set()
        for value in speed_map.get(source, []):
            try:
                numbers.add(int(value))
            except (TypeError, ValueError):
                continue
        if horse_number in numbers:
            return label
    return "unknown"


def performance_components(data: dict) -> dict[str, float | None]:
    aggregates = ((data.get("pf_metrics") or {}).get("pf_aggregates") or {})

    def negative(key: str):
        value = as_float(aggregates.get(key))
        return -value if value is not None else None

    return {
        "race_avg": negative("race_time_diff_avg"),
        "race_best": negative("race_time_diff_best"),
        "l600_avg": negative("l600_delta_avg"),
        "l600_best": negative("l600_delta_best"),
        "speed_recent": as_float(data.get("timing_600m_recent_speed")),
        "speed_avg": as_float(data.get("timing_600m_avg_speed")),
    }


def _race_number(path: Path, logic: dict) -> int:
    value = (logic.get("race_analysis") or {}).get("race_number")
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"Race_(\d+)", path.stem, flags=re.I)
        return int(match.group(1)) if match else 999


def _horse_number(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def score_logic(logic_path: Path, config: dict) -> list[dict]:
    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    race_number = _race_number(logic_path, logic)
    analysis = logic.get("race_analysis") or {}
    speed_map = analysis.get("speed_map") or {}
    pace = pace_bucket(speed_map.get("predicted_pace") or speed_map.get("expected_pace"))
    horses = []
    for number_text, horse in (logic.get("horses") or {}).items():
        auto = horse.get("python_auto") or {}
        ability = as_float(auto.get("ability_score"))
        matrices = auto.get("matrix_scores") or auto.get("matrix") or {}
        if ability is None:
            continue
        number = _horse_number(number_text)
        data = horse.get("_data") or {}
        horses.append({
            "race_number": race_number,
            "horse_number": number,
            "horse_name": str(horse.get("horse_name") or ""),
            "baseline_score": ability,
            "matrices": matrices,
            "data": data,
            "style": horse_style(speed_map, number),
            "pace": pace,
        })
    if not horses:
        return []

    component_rows = [performance_components(horse["data"]) for horse in horses]
    component_names = tuple(component_rows[0])
    component_z = {
        key: zmap([row[key] for row in component_rows])
        for key in component_names
    }
    performance_raw = []
    evidence_counts = []
    for index, horse in enumerate(horses):
        components = [component_z[key][index] for key in component_names if component_rows[index][key] is not None]
        aggregates = ((horse["data"].get("pf_metrics") or {}).get("pf_aggregates") or {})
        pf_count = as_float(aggregates.get("pf_run_count"), 0.0) or 0.0
        reliability = min(1.0, math.sqrt(max(0.0, pf_count) / 3.0))
        performance_raw.append(average(components) * reliability)
        evidence_counts.append(sum(component_rows[index][key] is not None for key in component_names))
    performance_z = zmap(performance_raw)

    matrix_z = {
        key: zmap([as_float(horse["matrices"].get(key), 60.0) for horse in horses])
        for key in config["matrix_order"]
    }
    pairwise_raw = []
    for index in range(len(horses)):
        pairwise_raw.append(sum(
            matrix_z[key][index] * weight
            for key, weight in zip(config["matrix_order"], config["pairwise_weights"])
        ))
    pairwise_z = zmap(pairwise_raw)
    shape_z = zmap([
        as_float(config["shape_table"].get(f"{horse['pace']}|{horse['style']}"), 0.0) or 0.0
        for horse in horses
    ])

    for index, horse in enumerate(horses):
        horse["performance_shadow_score"] = horse["baseline_score"] + config["performance_alpha"] * performance_z[index]
        horse["pairwise_shape_shadow_score"] = (
            horse["baseline_score"]
            + config["pairwise_alpha"] * pairwise_z[index]
            + config["shape_alpha"] * shape_z[index]
        )
        horse["performance_evidence_count"] = evidence_counts[index]
        horse["model_version"] = config["version"]
        horse.pop("matrices", None)
        horse.pop("data", None)

    for score_key, rank_key in (
        ("baseline_score", "baseline_rank"),
        ("performance_shadow_score", "performance_shadow_rank"),
        ("pairwise_shape_shadow_score", "pairwise_shape_shadow_rank"),
    ):
        ordered = sorted(horses, key=lambda horse: (-horse[score_key], horse["horse_number"]))
        for rank, horse in enumerate(ordered, 1):
            horse[rank_key] = rank
    return horses


def write_meeting_shadow(meeting_dir: Path, config_path: Path = DEFAULT_CONFIG) -> tuple[Path, list[dict]]:
    meeting_dir = meeting_dir.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows = []
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda path: _horse_number(re.search(r"Race_(\d+)", path.stem, flags=re.I).group(1)) if re.search(r"Race_(\d+)", path.stem, flags=re.I) else 999):
        rows.extend(score_logic(logic_path, config))
    if not rows:
        raise ValueError(f"No scoreable Logic files found in {meeting_dir}")
    output_path = meeting_dir / OUTPUT_CSV
    fieldnames = [
        "race_number", "horse_number", "horse_name",
        "baseline_rank", "performance_shadow_rank", "pairwise_shape_shadow_rank",
        "baseline_score", "performance_shadow_score", "pairwise_shape_shadow_score",
        "performance_evidence_count", "pace", "style", "model_version",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["race_number"], item["baseline_rank"])):
            writer.writerow(row)
    return output_path, rows


def parse_results_markdown(path: Path) -> dict[int, dict[int, int]]:
    """Read finish labels only; market/SP columns are ignored."""
    results: dict[int, dict[int, int]] = defaultdict(dict)
    race_number = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"## Race\s+(\d+):", line)
        if match:
            race_number = int(match.group(1))
            continue
        if race_number is None or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit() or not cells[1].isdigit():
            continue
        results[race_number][int(cells[1])] = int(cells[0])
    return dict(results)


def race_metrics(ranked: list[dict], actual: dict[int, int]) -> dict[str, float]:
    starters = [horse for horse in ranked if horse["horse_number"] in actual]
    winner_rank = next((index for index, horse in enumerate(starters, 1) if actual[horse["horse_number"]] == 1), len(starters))
    top2_hits = sum(actual[horse["horse_number"]] <= 3 for horse in starters[:2])
    top3_hits = sum(actual[horse["horse_number"]] <= 3 for horse in starters[:3])
    top4_hits = sum(actual[horse["horse_number"]] <= 3 for horse in starters[:4])
    top5_hits = sum(actual[horse["horse_number"]] <= 3 for horse in starters[:5])
    return {
        "top1_win": float(actual[starters[0]["horse_number"]] == 1),
        "top1_place": float(actual[starters[0]["horse_number"]] <= 3),
        "top2_place_strike": top2_hits / 2.0,
        "top2_both_place": float(top2_hits == 2),
        "top3_slot": top3_hits / 3.0,
        "top4_trifecta": float(top4_hits == 3),
        "top5_trifecta": float(top5_hits == 3),
        "winner_mrr": 1.0 / winner_rank,
    }


def evaluate(rows: list[dict], results: dict[int, dict[int, int]]) -> tuple[dict, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["race_number"])].append(row)
    variants = {
        "baseline": "baseline_score",
        "performance": "performance_shadow_score",
        "pairwise_shape": "pairwise_shape_shadow_score",
    }
    by_variant = {name: [] for name in variants}
    race_details = []
    for race_number in sorted(set(grouped) & set(results)):
        actual = results[race_number]
        detail = {"race_number": race_number, "actual_top3": [number for number, position in sorted(actual.items(), key=lambda item: item[1]) if position <= 3]}
        for variant, score_key in variants.items():
            ranked = sorted(grouped[race_number], key=lambda horse: (-horse[score_key], horse["horse_number"]))
            starters = [horse for horse in ranked if horse["horse_number"] in actual]
            metrics = race_metrics(ranked, actual)
            by_variant[variant].append(metrics)
            detail[variant] = {
                "top1": starters[0]["horse_number"],
                "top2": [horse["horse_number"] for horse in starters[:2]],
                "top4": [horse["horse_number"] for horse in starters[:4]],
                "top2_hits": int(metrics["top2_place_strike"] * 2),
                "top4_trifecta": bool(metrics["top4_trifecta"]),
                "top5_trifecta": bool(metrics["top5_trifecta"]),
            }
        race_details.append(detail)
    summaries = {}
    for variant, values in by_variant.items():
        summaries[variant] = {
            key: mean(row[key] for row in values)
            for key in values[0]
        } | {"races": len(values)} if values else {"races": 0}
    return summaries, race_details


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def render_review(config: dict, summaries: dict, race_details: list[dict]) -> str:
    baseline = summaries["baseline"]
    performance = summaries["performance"]
    pairwise = summaries["pairwise_shape"]
    lines = [
        "# AU Structural Shadow Forward Review",
        "",
        f"- Frozen model: `{config['version']}`; trained through **{config['trained_through']}**.",
        "- No odds, SP, favourite rank, market movement or market ranking is used by any shadow score.",
        "- Official `ability_score` and official ranks remain unchanged.",
        f"- Forward races evaluated: **{baseline['races']}**.",
        "",
        "## KPI comparison",
        "",
        "| KPI | Baseline | Performance | Pairwise + shape | Pairwise Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, label in (
        ("top1_win", "Top1 winner"),
        ("top1_place", "Top1 place"),
        ("top2_place_strike", "Top2 place strike"),
        ("top2_both_place", "Both Top2 placed"),
        ("top3_slot", "Top3 slot precision"),
        ("top4_trifecta", "Top4 trifecta coverage"),
        ("top5_trifecta", "Top5 trifecta coverage"),
        ("winner_mrr", "Winner MRR"),
    ):
        lines.append(
            f"| {label} | {pct(baseline[key])} | {pct(summaries['performance'][key])} "
            f"| {pct(summaries['pairwise_shape'][key])} | {100 * (summaries['pairwise_shape'][key] - baseline[key]):+.2f}pp |"
        )
    lines.extend([
        "",
        "## Race-level comparison",
        "",
        "| Race | Actual Top3 | Top1 B/P/C | Baseline Top2 | Perf Top2 | Pairwise+shape Top2 | T2 hits B/P/C | Top4 trifecta B/P/C | Top5 trifecta B/P/C |",
        "|---:|---|---|---|---|---|---|---|---|",
    ])
    for row in race_details:
        lines.append(
            f"| {row['race_number']} | {row['actual_top3']} | {row['baseline']['top1']}/{row['performance']['top1']}/{row['pairwise_shape']['top1']} "
            f"| {row['baseline']['top2']} | {row['performance']['top2']} "
            f"| {row['pairwise_shape']['top2']} | {row['baseline']['top2_hits']}/{row['performance']['top2_hits']}/{row['pairwise_shape']['top2_hits']} "
            f"| {int(row['baseline']['top4_trifecta'])}/{int(row['performance']['top4_trifecta'])}/{int(row['pairwise_shape']['top4_trifecta'])} "
            f"| {int(row['baseline']['top5_trifecta'])}/{int(row['performance']['top5_trifecta'])}/{int(row['pairwise_shape']['top5_trifecta'])} |"
        )
    perf_top1_delta = performance["top1_win"] - baseline["top1_win"]
    perf_top2_delta = performance["top2_place_strike"] - baseline["top2_place_strike"]
    perf_top5_delta = performance["top5_trifecta"] - baseline["top5_trifecta"]
    pair_top1_delta = pairwise["top1_win"] - baseline["top1_win"]
    pair_top2_delta = pairwise["top2_place_strike"] - baseline["top2_place_strike"]
    pair_top4_delta = pairwise["top4_trifecta"] - baseline["top4_trifecta"]
    lines.extend([
        "",
        "## Forward verdict",
        "",
        f"- Performance: Top1 {100 * perf_top1_delta:+.2f}pp; Top2 {100 * perf_top2_delta:+.2f}pp; Top5 trifecta {100 * perf_top5_delta:+.2f}pp — **mixed, keep in shadow**.",
        f"- Pairwise + shape: Top1 {100 * pair_top1_delta:+.2f}pp; Top2 {100 * pair_top2_delta:+.2f}pp; Top4 trifecta {100 * pair_top4_delta:+.2f}pp — **failed this forward batch**.",
        f"- Forward progress: **{baseline['races']}/{config['promotion_gate']['minimum_forward_races']} races**; not eligible for production promotion.",
        "- Promotion still follows the frozen gate in `structural_shadow_v1.json`.",
        "",
    ])
    return "\n".join(lines)


def bootstrap_ci(deltas: list[float], seed: int = 20260713) -> tuple[float, float]:
    if not deltas:
        return 0.0, 0.0
    rng = random.Random(seed)
    simulations = []
    for _ in range(2500):
        simulations.append(mean(deltas[rng.randrange(len(deltas))] for _ in deltas))
    simulations.sort()
    return simulations[int(0.025 * len(simulations))], simulations[int(0.975 * len(simulations))]


def meeting_track(meeting_path: str) -> str:
    name = Path(meeting_path).name
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[ _]", "", name)
    return re.sub(r"\s+Race\s+\d+(?:-\d+)?$", "", name, flags=re.I).strip()


def update_tracker(archive_root: Path, model_version: str) -> tuple[Path, Path]:
    batches = []
    for path in sorted(archive_root.glob(f"*/{OUTPUT_JSON}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (payload.get("model") or {}).get("version") != model_version:
            continue
        batches.append(payload)
    if not batches:
        raise ValueError(f"No forward review batches found for {model_version}")

    config = batches[-1]["model"]
    variant_names = ("performance", "pairwise_shape")
    metric_keys = (
        "top1_win", "top1_place", "top2_place_strike", "top2_both_place",
        "top3_slot", "top4_trifecta", "top5_trifecta", "winner_mrr",
    )
    total_races = sum(batch["summaries"]["baseline"]["races"] for batch in batches)
    aggregates = {}
    for variant in ("baseline", *variant_names):
        aggregates[variant] = {
            key: sum(batch["summaries"][variant][key] * batch["summaries"][variant]["races"] for batch in batches) / total_races
            for key in metric_keys
        } | {"races": total_races}

    top2_deltas = {variant: [] for variant in variant_names}
    block_rows = {variant: [] for variant in variant_names}
    for batch in batches:
        meeting = batch["meeting"]
        for detail in batch["race_details"]:
            for variant in variant_names:
                row = {
                    "meeting": meeting,
                    "race": detail["race_number"],
                    "top1_delta": float(detail[variant]["top1"] == detail["actual_top3"][0]) - float(detail["baseline"]["top1"] == detail["actual_top3"][0]),
                    "top2_delta": (detail[variant]["top2_hits"] - detail["baseline"]["top2_hits"]) / 2.0,
                    "top4_delta": float(detail[variant]["top4_trifecta"]) - float(detail["baseline"]["top4_trifecta"]),
                }
                block_rows[variant].append(row)
                top2_deltas[variant].append(row["top2_delta"])

    tracks = sorted({meeting_track(batch["meeting"]) for batch in batches})
    variants = {}
    gate = config["promotion_gate"]
    for variant in variant_names:
        deltas = {
            key: aggregates[variant][key] - aggregates["baseline"][key]
            for key in metric_keys
        }
        ci = bootstrap_ci(top2_deltas[variant])
        rows = block_rows[variant]
        nonnegative_blocks = 0
        block_summary = []
        for block_number in range(gate["time_blocks"]):
            start = (len(rows) * block_number) // gate["time_blocks"]
            end = (len(rows) * (block_number + 1)) // gate["time_blocks"]
            block = rows[start:end]
            values = {
                key: mean(row[key] for row in block) if block else 0.0
                for key in ("top1_delta", "top2_delta", "top4_delta")
            }
            passed = all(value >= 0 for value in values.values())
            nonnegative_blocks += passed
            block_summary.append({"block": block_number + 1, "races": len(block), **values, "nonnegative": passed})
        eligible = (
            total_races >= gate["minimum_forward_races"]
            and len(tracks) >= gate["minimum_tracks"]
            and deltas["top1_win"] * 100 >= gate["top1_delta_floor_pp"]
            and deltas["top2_place_strike"] * 100 >= gate["top2_delta_target_pp"]
            and ci[0] * 100 >= gate["top2_ci_lower_floor_pp"]
            and deltas["top4_trifecta"] * 100 >= gate["top4_delta_floor_pp"]
            and nonnegative_blocks >= gate["minimum_nonnegative_time_blocks"]
        )
        variants[variant] = {
            "metrics": aggregates[variant],
            "deltas": deltas,
            "top2_ci": ci,
            "nonnegative_blocks": nonnegative_blocks,
            "blocks": block_summary,
            "promotion_eligible": eligible,
        }

    tracker = {
        "model_version": model_version,
        "trained_through": config["trained_through"],
        "forward_races": total_races,
        "meetings": len(batches),
        "tracks": tracks,
        "promotion_gate": gate,
        "baseline": aggregates["baseline"],
        "variants": variants,
        "batch_files": [batch["meeting"] for batch in batches],
    }
    json_path = archive_root / TRACKER_JSON
    md_path = archive_root / TRACKER_MD
    json_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# AU Structural Shadow Tracker",
        "",
        f"- Model: `{model_version}`; trained through **{config['trained_through']}**.",
        f"- Progress: **{total_races}/{gate['minimum_forward_races']} races**; meetings: **{len(batches)}**; tracks: **{len(tracks)}/{gate['minimum_tracks']}**.",
        "- Official clean-7D ranking remains unchanged.",
        "",
        "| Candidate | Top1 Δ | Top2 Δ | Top2 95% CI | Top4 Δ | Nonnegative blocks | Promotion |",
        "|---|---:|---:|---|---:|---:|---|",
    ]
    for variant in variant_names:
        row = variants[variant]
        lines.append(
            f"| {variant} | {100 * row['deltas']['top1_win']:+.2f}pp | {100 * row['deltas']['top2_place_strike']:+.2f}pp "
            f"| [{100 * row['top2_ci'][0]:+.2f}pp, {100 * row['top2_ci'][1]:+.2f}pp] "
            f"| {100 * row['deltas']['top4_trifecta']:+.2f}pp | {row['nonnegative_blocks']}/{gate['time_blocks']} "
            f"| {'ELIGIBLE' if row['promotion_eligible'] else 'NOT YET'} |"
        )
    lines.extend(["", "## Recorded meetings", ""])
    lines.extend(f"- `{Path(batch['meeting']).name}` — {batch['summaries']['baseline']['races']} races" for batch in batches)
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def run_review(meeting_dir: Path, results_md: Path, config_path: Path = DEFAULT_CONFIG) -> tuple[Path, Path]:
    csv_path, rows = write_meeting_shadow(meeting_dir, config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    results = parse_results_markdown(results_md)
    summaries, race_details = evaluate(rows, results)
    payload = {
        "model": config,
        "meeting": str(meeting_dir.resolve()),
        "results_file": str(results_md.resolve()),
        "summaries": summaries,
        "race_details": race_details,
    }
    json_path = meeting_dir / OUTPUT_JSON
    review_path = meeting_dir / OUTPUT_REVIEW
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path.write_text(render_review(config, summaries, race_details), encoding="utf-8")
    update_tracker(meeting_dir.parent, config["version"])
    return csv_path, review_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AU market-free structural shadow scorer")
    parser.add_argument("meeting_dir", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--results-md", type=Path)
    args = parser.parse_args()
    meeting_dir = args.meeting_dir.resolve()
    if args.results_md:
        csv_path, review_path = run_review(meeting_dir, args.results_md.resolve(), args.config.resolve())
        print(csv_path)
        print(review_path)
    else:
        csv_path, rows = write_meeting_shadow(meeting_dir, args.config.resolve())
        print(f"rows={len(rows)}")
        print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
