#!/usr/bin/env python3
"""Build the Step-2 HKJC common pre-race primitive replay layer.

Archive source Logic files are no longer available, so this does not pretend to
rerun the current RacingEngine on old meetings.  Instead it materializes the
intersection of structured pre-race primitives preserved in the archive
dataset and reconstructible from current Logic files.  Outcomes and original
model ranks are isolated from primitive inputs.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from hkjc_rating_matrix_audit import DEFAULT_ARCHIVE, DEFAULT_MANIFEST
from hkjc_zero_one_hit_manifest import result_positions


ROOT = Path(__file__).resolve().parents[1]
REFLECTOR_SCRIPTS = (
    ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
)
sys.path.insert(0, str(REFLECTOR_SCRIPTS))

import build_hkjc_ranking_dataset as builder  # noqa: E402


IDENTITY_COLUMNS = (
    "dataset",
    "split",
    "source_mode",
    "meeting",
    "date",
    "race_number",
    "horse_number",
    "horse_id",
    "horse_name",
    "venue",
    "track",
    "distance_num",
    "race_class_num",
    "field_size",
    "is_debut",
    "is_import",
)

PRIMITIVE_COLUMNS = (
    "weight_carried",
    "days_since_last",
    "starts",
    "wins",
    "hk_starts",
    "card_rating",
    "last6_runs",
    "last6_mean_finish",
    "last6_best_finish",
    "last6_worst_finish",
    "last6_top3_count",
    "last6_top5_count",
    "season_starts",
    "season_wins",
    "season_seconds",
    "season_thirds",
    "same_distance_starts",
    "same_distance_wins",
    "same_distance_seconds",
    "same_distance_thirds",
    "same_venue_distance_starts",
    "same_venue_distance_wins",
    "same_venue_distance_seconds",
    "same_venue_distance_thirds",
    "tw_entries_count",
    "tw_gallop_count",
    "tw_flags_count",
    "tw_confidence_high",
    "tw_confidence_low",
    "tw_jockey_present",
    "raw_formline_higher_win_count",
    "raw_formline_same_win_count",
    "raw_formline_lower_win_count",
    "raw_l400",
    "raw_finish_time_adj",
    "raw_total_starts",
    "raw_total_wins",
    "raw_last_margin",
    "raw_last_finish",
    "raw_weight_trend_span",
    "prior_combo_starts",
    "prior_combo_win_rate",
    "prior_combo_place_rate",
    "prior_jockey_cd_starts",
    "prior_jockey_cd_win_rate",
    "prior_jockey_cd_place_rate",
    "prior_trainer_cd_starts",
    "prior_trainer_cd_win_rate",
    "prior_trainer_cd_place_rate",
    "prior_class_distance_starts",
    "prior_class_distance_win_rate",
    "prior_class_distance_place_rate",
    "prior_weight_class_starts",
    "prior_weight_class_win_rate",
    "prior_weight_class_place_rate",
    "prior_rest_bucket_starts",
    "prior_rest_bucket_win_rate",
    "prior_rest_bucket_place_rate",
)

EVIDENCE_FAMILIES = {
    "form": ("last6_runs", "raw_last_finish", "raw_last_margin", "season_starts"),
    "speed": ("raw_l400", "raw_finish_time_adj"),
    "class_weight": ("card_rating", "weight_carried", "starts"),
    "distance": ("same_distance_starts", "same_venue_distance_starts", "prior_class_distance_starts"),
    "trainer": ("prior_combo_starts", "prior_jockey_cd_starts", "prior_trainer_cd_starts"),
    "readiness": ("days_since_last", "tw_entries_count", "tw_gallop_count", "raw_weight_trend_span"),
    "formline": (
        "raw_formline_higher_win_count",
        "raw_formline_same_win_count",
        "raw_formline_lower_win_count",
    ),
}
EVIDENCE_COLUMNS = tuple(
    column
    for family in EVIDENCE_FAMILIES
    for column in (f"evidence_{family}_count", f"evidence_{family}_coverage")
)

REFERENCE_COLUMNS = (
    "reference_original_rank",
    "reference_original_top2",
    "reference_original_ability",
)
LABEL_COLUMNS = (
    "label_finish_position",
    "label_is_winner",
    "label_is_top3",
)

PRIMITIVE_PROVENANCE_GROUPS = {
    "archive_all": "hkjc_ranking_dataset.csv same-named pre-race materialized columns",
    "current_horse_fields": [
        "days_since_last", "starts", "wins", "hk_starts", "is_debut", "is_import",
    ],
    "current_horse_data": ["weight_carried", "card_rating"],
    "current_last6_parser": [column for column in PRIMITIVE_COLUMNS if column.startswith("last6_")],
    "current_season_stats_parser": [
        column
        for column in PRIMITIVE_COLUMNS
        if column.startswith("season_")
        or column.startswith("same_distance_")
        or column.startswith("same_venue_distance_")
    ],
    "current_trackwork_parser": [column for column in PRIMITIVE_COLUMNS if column.startswith("tw_")],
    "current_structured_forensic": [column for column in PRIMITIVE_COLUMNS if column.startswith("raw_")],
    "current_fixed_2024_25_priors": [column for column in PRIMITIVE_COLUMNS if column.startswith("prior_")],
}

FORBIDDEN_PRIMITIVE_TOKENS = (
    "draw",
    "barrier",
    "going",
    "bias",
    "pace",
    "runstyle",
    "position",
    "odds",
    "market",
    "roi",
    "edge",
    "finish_pos",
    "is_winner",
    "is_top3",
)


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def coerce_int(value: Any) -> int | None:
    number = coerce_float(value)
    return int(round(number)) if number is not None else None


def iso_date(meeting: str) -> str:
    return meeting[:10] if len(meeting) >= 10 else ""


def split_map(manifest: dict[str, Any]) -> dict[tuple[str, int], str]:
    valid = [record for record in manifest["records"] if record.get("valid")]
    archive_meetings = sorted({record["meeting"] for record in valid if record["dataset"] == "archive"})
    cut = math.floor(len(archive_meetings) * 0.70)
    development = set(archive_meetings[:cut])
    mapping = {}
    for record in valid:
        if record["dataset"] == "archive":
            split = "archive_development" if record["meeting"] in development else "archive_temporal_holdout"
        else:
            split = record["dataset"]
        mapping[(record["meeting"], record["race_number"])] = split
    return mapping


def blank_row() -> dict[str, Any]:
    return {column: None for column in (*IDENTITY_COLUMNS, *PRIMITIVE_COLUMNS, *EVIDENCE_COLUMNS, *REFERENCE_COLUMNS, *LABEL_COLUMNS)}


def is_present(value: Any) -> bool:
    return value is not None and value != ""


def add_evidence_counts(row: dict[str, Any]) -> None:
    for family, fields in EVIDENCE_FAMILIES.items():
        count = sum(is_present(row.get(field)) for field in fields)
        row[f"evidence_{family}_count"] = count
        row[f"evidence_{family}_coverage"] = round(count / len(fields), 4)


def safe_prior_record(prefix: str, record: dict[str, float] | None) -> dict[str, float | None]:
    if not record:
        return {
            f"{prefix}_starts": None,
            f"{prefix}_win_rate": None,
            f"{prefix}_place_rate": None,
        }
    return {
        f"{prefix}_starts": float(record.get("starts", 0.0)),
        f"{prefix}_win_rate": float(record.get("win_rate", 0.0)),
        f"{prefix}_place_rate": float(record.get("place_rate", 0.0)),
    }


def safe_priors(
    priors: Any,
    *,
    jockey: str,
    trainer: str,
    venue: str,
    track: str,
    distance_num: int | None,
    race_class_label: str,
    weight_carried: float | None,
    days_since_last: float | None,
) -> dict[str, float | None]:
    distance_key = str(distance_num or "")
    weight_bucket = builder._weight_bucket(weight_carried)
    rest_bucket = builder._rest_bucket(days_since_last)
    output: dict[str, float | None] = {}
    output.update(safe_prior_record("prior_combo", priors.combo.get((jockey, trainer))))
    output.update(
        safe_prior_record("prior_jockey_cd", priors.jockey_cd.get((jockey, venue, track, distance_key)))
    )
    output.update(
        safe_prior_record("prior_trainer_cd", priors.trainer_cd.get((trainer, venue, track, distance_key)))
    )
    output.update(
        safe_prior_record(
            "prior_class_distance",
            priors.class_distance.get((race_class_label, venue, track, distance_key)),
        )
    )
    output.update(
        safe_prior_record("prior_weight_class", priors.weight_class.get((race_class_label, weight_bucket)))
    )
    output.update(safe_prior_record("prior_rest_bucket", priors.rest_bucket.get((rest_bucket,))))
    return output


def archive_rows(
    archive_path: Path,
    manifest: dict[str, Any],
    splits: dict[tuple[str, int], str],
) -> list[dict[str, Any]]:
    valid_keys = {
        (record["meeting"], record["race_number"])
        for record in manifest["records"]
        if record.get("valid") and record["dataset"] == "archive"
    }
    output = []
    with archive_path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            meeting = str(raw.get("meeting_name") or Path(str(raw.get("meeting") or "")).name)
            race_number = coerce_int(raw.get("race_number"))
            finish = coerce_int(raw.get("finish_pos"))
            if race_number is None or finish is None or (meeting, race_number) not in valid_keys:
                continue
            row = blank_row()
            row.update(
                {
                    "dataset": "archive",
                    "split": splits[(meeting, race_number)],
                    "source_mode": "archived_materialized_prerace_snapshot",
                    "meeting": meeting,
                    "date": str(raw.get("date") or iso_date(meeting)),
                    "race_number": race_number,
                    "horse_number": coerce_int(raw.get("horse_number")),
                    "horse_id": str(raw.get("horse_id") or ""),
                    "horse_name": str(raw.get("horse_name") or ""),
                    "venue": str(raw.get("venue") or ""),
                    "track": str(raw.get("track") or ""),
                    "distance_num": coerce_int(raw.get("distance_num")),
                    "race_class_num": coerce_int(raw.get("race_class_num")),
                    "field_size": coerce_int(raw.get("field_size")),
                    "is_debut": coerce_int(raw.get("is_debut")) or 0,
                    "is_import": coerce_int(raw.get("is_import")) or 0,
                    "reference_original_rank": coerce_int(raw.get("current_live_rank")),
                    "reference_original_top2": int((coerce_int(raw.get("current_live_rank")) or 99) <= 2),
                    "reference_original_ability": coerce_float(raw.get("current_live_ability")),
                    "label_finish_position": finish,
                    "label_is_winner": int(finish == 1),
                    "label_is_top3": int(finish <= 3),
                }
            )
            for column in PRIMITIVE_COLUMNS:
                row[column] = coerce_float(raw.get(column))
            add_evidence_counts(row)
            output.append(row)
    return output


def current_logic_rows(
    manifest: dict[str, Any],
    splits: dict[tuple[str, int], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    priors = builder.HistoricalPriors()
    output = []
    errors = []
    result_cache: dict[str, dict[int, dict[int, int]]] = {}
    for record in manifest["records"]:
        if not record.get("valid") or record["dataset"] == "archive":
            continue
        source_parts = str(record["source"]).split(" | ", 1)
        if len(source_parts) != 2:
            errors.append({"meeting": record["meeting"], "race": record["race_number"], "reason": "source_pair_missing"})
            continue
        logic_path = Path(source_parts[0])
        result_path = source_parts[1]
        if result_path not in result_cache:
            result_cache[result_path] = result_positions(Path(result_path))
        positions = result_cache[result_path].get(record["race_number"], {})
        payload = json.loads(logic_path.read_text(encoding="utf-8"))
        race_context = payload.get("race_analysis") if isinstance(payload.get("race_analysis"), dict) else {}
        venue = builder._normalize_venue(
            race_context.get("venue") or record["meeting"]
        )
        track = builder._normalize_track(
            race_context.get("track") or race_context.get("surface")
        )
        distance_num = coerce_int(builder._distance_token(race_context.get("distance")))
        race_class_num = builder._race_class_number(race_context.get("race_class"))
        race_class_label = builder._race_class_label(race_context.get("race_class"))
        horses = payload.get("horses") or {}
        for horse_key, horse in horses.items():
            number = coerce_int(horse_key)
            if number is None or number not in positions:
                continue
            data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
            auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
            horse_id = builder._horse_id_from_name(horse.get("horse_name"))
            last_features = builder._last_finish_features(builder._parse_last_finishes(horse.get("last_6_finishes")))
            season_features = builder._season_stat_features(horse.get("season_stats"))
            trackwork_features = builder._trackwork_features(horse.get("trackwork"))
            forensic = builder._forensic_features(horse)
            weight_carried = coerce_float(data.get("weight_carried"))
            days_since_last = coerce_float(horse.get("days_since_last"))
            prior_features = safe_priors(
                priors,
                jockey=str(horse.get("jockey") or ""),
                trainer=str(horse.get("trainer") or ""),
                venue=venue,
                track=track,
                distance_num=distance_num,
                race_class_label=race_class_label,
                weight_carried=weight_carried,
                days_since_last=days_since_last,
            )
            finish = positions[number]
            original_rank = coerce_int(auto.get("rank"))
            row = blank_row()
            row.update(
                {
                    "dataset": record["dataset"],
                    "split": splits[(record["meeting"], record["race_number"])],
                    "source_mode": "current_logic_reconstructed_primitives",
                    "meeting": record["meeting"],
                    "date": iso_date(record["meeting"]),
                    "race_number": record["race_number"],
                    "horse_number": number,
                    "horse_id": horse_id,
                    "horse_name": str(horse.get("horse_name") or ""),
                    "venue": venue,
                    "track": track,
                    "distance_num": distance_num,
                    "race_class_num": race_class_num,
                    "field_size": len(horses),
                    "is_debut": int(bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT")),
                    "is_import": int(bool(horse.get("is_import"))),
                    "weight_carried": weight_carried,
                    "days_since_last": days_since_last,
                    "starts": coerce_float(horse.get("starts")),
                    "wins": coerce_float(horse.get("wins")),
                    "hk_starts": coerce_float(horse.get("hk_starts")),
                    "card_rating": coerce_float(data.get("current_rating") or horse.get("base_rating")),
                    "reference_original_rank": original_rank,
                    "reference_original_top2": int((original_rank or 99) <= 2),
                    "reference_original_ability": coerce_float(auto.get("ability_score")),
                    "label_finish_position": finish,
                    "label_is_winner": int(finish == 1),
                    "label_is_top3": int(finish <= 3),
                }
            )
            for source in (last_features, season_features, trackwork_features, forensic, prior_features):
                for column in PRIMITIVE_COLUMNS:
                    if column in source:
                        row[column] = coerce_float(source[column])
            add_evidence_counts(row)
            output.append(row)
        race_count = sum(
            row["meeting"] == record["meeting"] and row["race_number"] == record["race_number"]
            for row in output
        )
        if race_count < 3:
            errors.append({"meeting": record["meeting"], "race": record["race_number"], "reason": "fewer_than_3_rows"})
    return output, errors


def availability(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    splits = ["overall", *sorted({row["split"] for row in rows})]
    for split in splits:
        selected = rows if split == "overall" else [row for row in rows if row["split"] == split]
        for column in PRIMITIVE_COLUMNS:
            present = sum(is_present(row.get(column)) for row in selected)
            output.append(
                {
                    "split": split,
                    "primitive": column,
                    "rows": len(selected),
                    "present": present,
                    "availability_rate": round(present / len(selected) * 100, 1) if selected else 0.0,
                }
            )
    return output


def validate_schema(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> list[str]:
    errors = []
    for column in PRIMITIVE_COLUMNS:
        lower = column.lower()
        if any(token in lower for token in FORBIDDEN_PRIMITIVE_TOKENS):
            errors.append(f"forbidden primitive column: {column}")
    if set(PRIMITIVE_COLUMNS) & (set(REFERENCE_COLUMNS) | set(LABEL_COLUMNS)):
        errors.append("primitive/reference/label schema overlap")
    valid_races = sum(record.get("valid", False) for record in manifest["records"])
    race_keys = {(row["dataset"], row["meeting"], row["race_number"]) for row in rows}
    if len(race_keys) != valid_races:
        errors.append(f"race coverage mismatch {len(race_keys)} != {valid_races}")
    duplicates = Counter((row["dataset"], row["meeting"], row["race_number"], row["horse_number"]) for row in rows)
    duplicate_count = sum(count - 1 for count in duplicates.values() if count > 1)
    if duplicate_count:
        errors.append(f"duplicate horse rows: {duplicate_count}")
    return errors


def write_outputs(
    rows: list[dict[str, Any]],
    build_errors: list[dict[str, Any]],
    schema_errors: list[str],
    output_prefix: Path,
) -> None:
    rows = sorted(rows, key=lambda row: (row["date"], row["meeting"], row["race_number"], row["horse_number"] or 99))
    availability_rows = availability(rows)
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    availability_path = output_prefix.with_name(output_prefix.name + "_availability").with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    fields = [*IDENTITY_COLUMNS, *PRIMITIVE_COLUMNS, *EVIDENCE_COLUMNS, *REFERENCE_COLUMNS, *LABEL_COLUMNS]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with availability_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("split", "primitive", "rows", "present", "availability_rate"))
        writer.writeheader()
        writer.writerows(availability_rows)

    coverage = {
        "meetings": len({(row["dataset"], row["meeting"]) for row in rows}),
        "races": len({(row["dataset"], row["meeting"], row["race_number"]) for row in rows}),
        "horses": len(rows),
        "by_split": dict(Counter(row["split"] for row in rows)),
        "by_source_mode": dict(Counter(row["source_mode"] for row in rows)),
    }
    payload = {
        "method": {
            "full_current_engine_replay_possible": False,
            "reason": "archive source Logic files unavailable; common structured pre-race primitive intersection used",
            "primitive_inputs_are_outcome_free": True,
            "labels_isolated": list(LABEL_COLUMNS),
            "original_model_reference_isolated": list(REFERENCE_COLUMNS),
            "excluded": ["going", "draw", "barrier", "track bias", "pace", "run style", "odds", "market", "ROI", "edge", "narrative hidden-form flags"],
            "historical_priors": "fixed 2024/25 pre-race win/place rates and sample counts; ROI excluded",
        },
        "coverage": coverage,
        "primitive_columns": list(PRIMITIVE_COLUMNS),
        "primitive_provenance_groups": PRIMITIVE_PROVENANCE_GROUPS,
        "evidence_families": EVIDENCE_FAMILIES,
        "availability": availability_rows,
        "build_errors": build_errors,
        "schema_errors": schema_errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    availability_index = {(row["split"], row["primitive"]): row for row in availability_rows}
    split_names = ("archive_development", "archive_temporal_holdout", "independent_recent", "external_2026_07_15")
    lines = [
        "# HKJC Dimension重建 Step 2 — 統一賽前Primitive Replay層",
        "",
        "## Replay邊界",
        "",
        "- Archive原始Logic已不存在，因此不能聲稱用現行RacingEngine完整重跑245場。",
        "- 本層採用archive snapshot與近期Logic共同可重建嘅結構化賽前primitive；舊feature／matrix分數不作新dimension輸入。",
        "- 賽果label及原模型rank獨立存放，永不進入primitive白名單。",
        "- 排除going、draw、barrier、track bias、pace、run style、odds、市場、ROI、edge及敘事式hidden-form flags。",
            "- 2024/25 historical priors只保留賽前sample count、win rate、place rate；ROI完全排除。",
            "- 每列保留source mode；JSON另列archive snapshot、Logic direct field、last6／season／trackwork parser及固定prior嘅provenance group。",
        "",
        "## Coverage",
        "",
        f"- {coverage['meetings']}個賽日／{coverage['races']}場／{coverage['horses']}匹完成馬。",
        f"- Split horse rows：{coverage['by_split']}。",
        f"- Source mode：{coverage['by_source_mode']}。",
        f"- Build errors：{len(build_errors)}；schema errors：{len(schema_errors)}。",
        "",
        "## 關鍵primitive可用率",
        "",
        "| Primitive | Development | Temporal | 近期獨立 | 07-15 |",
        "|---|---:|---:|---:|---:|",
    ]
    key_primitives = (
        "last6_runs",
        "raw_last_margin",
        "raw_l400",
        "raw_finish_time_adj",
        "card_rating",
        "weight_carried",
        "same_distance_starts",
        "same_venue_distance_starts",
        "tw_entries_count",
        "raw_formline_higher_win_count",
        "prior_combo_starts",
        "prior_jockey_cd_starts",
        "prior_trainer_cd_starts",
    )
    for primitive in key_primitives:
        values = [availability_index[(split, primitive)]["availability_rate"] for split in split_names]
        lines.append(f"| {primitive} | {values[0]:.1f}% | {values[1]:.1f}% | {values[2]:.1f}% | {values[3]:.1f}% |")
    lines.extend(
        [
            "",
            "## Evidence coverage欄",
            "",
            "| Family | 只計存在性嘅primitive | 用途 |",
            "|---|---|---|",
        ]
    )
    for family, columns in EVIDENCE_FAMILIES.items():
        lines.append(f"| {family} | {', '.join(columns)} | Step 3只用作向中性60收縮，唔直接當能力edge |")
    lines.extend(
        [
            "",
            "## Step 2判斷",
            "",
            "- 245場已可放入同一outcome-free primitive schema，但archive係materialized snapshot，近期係Logic重建，source mode必須保留。",
            "- Step 3只可使用跨development／temporal／近期均有合理覆蓋嘅primitive；版本專屬舊feature分正式淘汰。",
            "- 第三選有效升格需要嘅原模型rank及實際前三label已隔離保存，供Step 6評估，唔會參與dimension建構。",
            "- 本步未定義新分數、未以賽果揀欄位、未改正式Auto engine。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "json": str(json_path),
                "availability": str(availability_path),
                "report": str(report_path),
                "coverage": coverage,
                "build_errors": build_errors,
                "schema_errors": schema_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_prerace_replay",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    splits = split_map(manifest)
    rows = archive_rows(args.archive, manifest, splits)
    recent_rows, build_errors = current_logic_rows(manifest, splits)
    rows.extend(recent_rows)
    schema_errors = validate_schema(rows, manifest)
    write_outputs(rows, build_errors, schema_errors, args.output_prefix)
    return 1 if build_errors or schema_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
