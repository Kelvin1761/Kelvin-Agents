#!/usr/bin/env python3
"""Step-1 source-contract audit for the HKJC dimension rebuild.

This script inventories pre-race feature and matrix values only.  Finish
positions are used solely to keep the same strict manifest population; they do
not influence any formula, threshold or rebuild decision in this step.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from hkjc_rating_matrix_audit import DEFAULT_ARCHIVE, DEFAULT_MANIFEST
from hkjc_zero_one_hit_manifest import result_positions


ROOT = Path(__file__).resolve().parents[1]

PUBLIC_FEATURES = (
    "form_score",
    "speed_score",
    "class_score",
    "jockey_score",
    "trainer_score",
    "draw_score",
    "distance_score",
    "track_going_score",
    "weight_score",
    "consistency_score",
    "risk_score",
    "confidence_score",
)
DERIVED_SIGNALS = (
    "formline_strength_score",
    "margin_trend_score",
    "same_distance_signal_score",
    "trackwork_trend_score",
    "race_shape_context_score",
)
MATRIX_DIMENSIONS = (
    "stability",
    "sectional",
    "race_shape",
    "trainer_signal",
    "horse_health",
    "form_line",
    "class_advantage",
)
SIGNALS = PUBLIC_FEATURES + DERIVED_SIGNALS + tuple(f"matrix_{key}" for key in MATRIX_DIMENSIONS)
DRIFT_SIGNALS = (
    "speed_score",
    "distance_score",
    "track_going_score",
    "confidence_score",
    "formline_strength_score",
    "race_shape_context_score",
)

SOURCE_CONTRACT = {
    "stability": {
        "formula": "form_score 50% + consistency_score 40% + trackwork_trend_score 10%",
        "post_adjustment": "feature context may replace consistency_score before mapping",
        "contamination": "form與consistency同樣大量源自近期賽績，可能重複計分",
        "decision": "REBUILD_DISTINCT",
    },
    "sectional": {
        "formula": "speed_score 65% + track_going_score 35%",
        "post_adjustment": "finish-time trend nudge after matrix mapping",
        "contamination": "track_going_score屬已排除going；同時有post-matrix時間修正",
        "decision": "REBUILD_SPEED_ONLY_WITH_RELIABILITY",
    },
    "race_shape": {
        "formula": "race_shape_context_score 100%",
        "post_adjustment": "Sha Tin: draw 55% + draw-position fit 25% + trip consumption 20%; other venue: draw + context delta",
        "contamination": "draw係主要基底，屬重建排除項；位置訊號亦同draw文字混合",
        "decision": "REPLACE_WITH_DRAW_FREE_CONTEXT",
    },
    "trainer_signal": {
        "formula": "jockey_score 55% + trainer_score 45%",
        "post_adjustment": "trainer-signal V3 priors after matrix mapping",
        "contamination": "prior樣本量未直接成為統一可靠度收縮",
        "decision": "KEEP_CORE_ADD_RELIABILITY",
    },
    "horse_health": {
        "formula": "risk_score 55% + weight_score 35% + confidence_score 10%",
        "post_adjustment": "health-only V2 after matrix mapping",
        "contamination": "weight同class重複；confidence係資料覆蓋卻被當正向能力分",
        "decision": "REBUILD_READINESS_RISK_ONLY",
    },
    "form_line": {
        "formula": "formline_strength_score 100%",
        "post_adjustment": "none after mapping",
        "contamination": "離散bucket且對手後續樣本量未做統一收縮；margin trend已排除避免同stability重複",
        "decision": "KEEP_MEANING_ADD_RELIABILITY",
    },
    "class_advantage": {
        "formula": "class_score 75% + weight_score 25%",
        "post_adjustment": "none after mapping",
        "contamination": "weight同horse_health重複；distance_score及same-distance signal仍在矩陣外",
        "decision": "REBUILD_CLASS_WEIGHT_AND_SEPARATE_DISTANCE",
    },
}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 60.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def row_record(
    *,
    dataset: str,
    meeting: str,
    race_number: int,
    horse_number: int,
    is_debut: bool,
    features: dict[str, Any],
    derived: dict[str, Any],
    matrix: dict[str, Any],
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "dataset": dataset,
        "meeting": meeting,
        "race_number": race_number,
        "horse_number": horse_number,
        "is_debut": is_debut,
        "provenance": provenance or {},
    }
    for key in PUBLIC_FEATURES:
        record[key] = as_float(features.get(key))
    for key in DERIVED_SIGNALS:
        if key == "race_shape_context_score":
            record[key] = as_float(derived.get(key), as_float(matrix.get("race_shape")))
        else:
            record[key] = as_float(derived.get(key))
    for key in MATRIX_DIMENSIONS:
        record[f"matrix_{key}"] = as_float(matrix.get(key))
    return record


def load_archive(path: Path, valid_keys: set[tuple[str, int]]) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            meeting = str(raw.get("meeting_name") or Path(str(raw.get("meeting") or "")).name)
            race_number = as_int(raw.get("race_number"))
            if (meeting, race_number) not in valid_keys or as_int(raw.get("finish_pos")) <= 0:
                continue
            features = {key: raw.get(f"feat_{key}") for key in PUBLIC_FEATURES}
            derived = {key: raw.get(f"feat_{key}") for key in DERIVED_SIGNALS}
            matrix = {key: raw.get(f"matrix_{key}") for key in MATRIX_DIMENSIONS}
            rows.append(
                row_record(
                    dataset="archive",
                    meeting=meeting,
                    race_number=race_number,
                    horse_number=as_int(raw.get("horse_number")),
                    is_debut=bool(as_int(raw.get("is_debut"))),
                    features=features,
                    derived=derived,
                    matrix=matrix,
                )
            )
    return rows


def load_logic_rows(record: dict[str, Any], positions: dict[int, int]) -> list[dict[str, Any]]:
    logic_path = Path(str(record["source"]).split(" | ", 1)[0])
    payload = json.loads(logic_path.read_text(encoding="utf-8"))
    rows = []
    for horse_key, horse in (payload.get("horses") or {}).items():
        number = as_int(horse_key)
        if number not in positions:
            continue
        auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
        if not auto:
            continue
        features = auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {}
        derived = auto.get("derived_feature_scores") if isinstance(auto.get("derived_feature_scores"), dict) else {}
        matrix = auto.get("matrix_scores") if isinstance(auto.get("matrix_scores"), dict) else {}
        provenance = auto.get("score_provenance") if isinstance(auto.get("score_provenance"), dict) else {}
        reasons = auto.get("reason_codes") if isinstance(auto.get("reason_codes"), list) else []
        is_debut = bool(horse.get("is_debut")) or any(str(reason).startswith("debut_") for reason in reasons)
        rows.append(
            row_record(
                dataset=record["dataset"],
                meeting=record["meeting"],
                race_number=record["race_number"],
                horse_number=number,
                is_debut=is_debut,
                features=features,
                derived=derived,
                matrix=matrix,
                provenance=provenance,
            )
        )
    return rows


def build_rows(manifest: dict[str, Any], archive_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [record for record in manifest["records"] if record.get("valid")]
    archive_keys = {
        (record["meeting"], record["race_number"])
        for record in valid
        if record["dataset"] == "archive"
    }
    rows = load_archive(archive_path, archive_keys)
    errors = []
    result_cache: dict[str, dict[int, dict[int, int]]] = {}
    for record in valid:
        if record["dataset"] == "archive":
            continue
        parts = str(record["source"]).split(" | ", 1)
        if len(parts) != 2:
            errors.append({"meeting": record["meeting"], "race": record["race_number"], "reason": "missing_results_path"})
            continue
        result_path = parts[1]
        if result_path not in result_cache:
            result_cache[result_path] = result_positions(Path(result_path))
        positions = result_cache[result_path].get(record["race_number"], {})
        race_rows = load_logic_rows(record, positions)
        if len(race_rows) < 3:
            errors.append({"meeting": record["meeting"], "race": record["race_number"], "reason": "fewer_than_3_rows"})
            continue
        rows.extend(race_rows)
    return rows, errors


def signal_stats(rows: list[dict[str, Any]], signal: str) -> dict[str, Any]:
    values = [float(row[signal]) for row in rows]
    neutral = sum(abs(value - 60.0) < 1e-9 for value in values)
    recent_with_provenance = [row for row in rows if row["dataset"] != "archive" and row["provenance"]]
    missing_neutral = sum(
        str(row["provenance"].get(signal, "")) == "missing_neutral"
        for row in recent_with_provenance
    )
    return {
        "signal": signal,
        "rows": len(values),
        "mean": round(statistics.mean(values), 3) if values else 60.0,
        "stdev": round(statistics.pstdev(values), 3) if len(values) > 1 else 0.0,
        "minimum": round(min(values), 3) if values else 60.0,
        "maximum": round(max(values), 3) if values else 60.0,
        "neutral_60": neutral,
        "neutral_60_rate": round(neutral / len(values) * 100, 1) if values else 0.0,
        "recent_provenance_rows": len(recent_with_provenance),
        "recent_missing_neutral": missing_neutral,
        "recent_missing_neutral_rate": round(missing_neutral / len(recent_with_provenance) * 100, 1)
        if recent_with_provenance
        else None,
    }


def pearson(rows: list[dict[str, Any]], left: str, right: str) -> float:
    xs = [float(row[left]) for row in rows]
    ys = [float(row[right]) for row in rows]
    if len(xs) < 2:
        return 0.0
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return round(numerator / (denom_x * denom_y), 4)


def correlation_audit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_signals = PUBLIC_FEATURES + DERIVED_SIGNALS
    pairs = []
    for index, left in enumerate(base_signals):
        for right in base_signals[index + 1 :]:
            correlation = pearson(rows, left, right)
            pairs.append({"left": left, "right": right, "correlation": correlation, "absolute": abs(correlation)})
    return sorted(pairs, key=lambda row: (-row["absolute"], row["left"], row["right"]))


def provenance_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counters: dict[str, Counter[str]] = {key: Counter() for key in PUBLIC_FEATURES + DERIVED_SIGNALS}
    for row in rows:
        if row["dataset"] == "archive":
            continue
        provenance = row["provenance"]
        for key in counters:
            counters[key][str(provenance.get(key) or "not_persisted")] += 1
    return {key: dict(counter.most_common()) for key, counter in counters.items()}


def write_outputs(
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    output_prefix: Path,
) -> None:
    datasets = sorted({row["dataset"] for row in rows})
    stats = {
        dataset: {
            signal: signal_stats([row for row in rows if dataset == "overall" or row["dataset"] == dataset], signal)
            for signal in SIGNALS
        }
        for dataset in ["overall", *datasets]
    }
    correlations = correlation_audit(rows)
    meetings = len({(row["dataset"], row["meeting"]) for row in rows})
    races = len({(row["dataset"], row["meeting"], row["race_number"]) for row in rows})
    payload = {
        "method": {
            "uses_results_for_formula_design": False,
            "result_use": "strict population membership only",
            "public_feature_schema_changes": False,
            "excluded_rebuild_inputs": ["going", "draw", "odds", "market", "pace", "micro_tiebreak"],
        },
        "coverage": {
            "meetings": meetings,
            "races": races,
            "horses": len(rows),
            "debut_horses": sum(row["is_debut"] for row in rows),
            "by_dataset": dict(Counter(row["dataset"] for row in rows)),
        },
        "source_contract": SOURCE_CONTRACT,
        "signal_stats": stats,
        "provenance_recent": provenance_audit(rows),
        "correlations": correlations,
        "errors": errors,
    }
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "dataset", "signal", "rows", "mean", "stdev", "minimum", "maximum", "neutral_60",
        "neutral_60_rate", "recent_provenance_rows", "recent_missing_neutral", "recent_missing_neutral_rate",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for dataset, dataset_stats in stats.items():
            for signal in SIGNALS:
                writer.writerow({"dataset": dataset, **dataset_stats[signal]})

    coverage = payload["coverage"]
    lines = [
        "# HKJC Dimension重建 Step 1 — 來源契約與污染盤點",
        "",
        "## 方法",
        "",
        "- 使用既有strict manifest相同245場；賽果只用嚟鎖定完成馬population，完全無參與本步公式或閾值判斷。",
        "- 公開12-feature schema保持不變；盤點另包括5項derived signal及7個matrix dimension。",
        "- going、draw、賠率、市場、pace及micro tie-break列為重建排除輸入。",
        "",
        "## Coverage",
        "",
        f"- {coverage['meetings']}個賽日／{coverage['races']}場／{coverage['horses']}匹完成馬；初出馬{coverage['debut_horses']}匹。",
        f"- Dataset horse rows：{coverage['by_dataset']}。",
        f"- 資料錯誤：{len(errors)}。",
        "",
        "## 現行dimension來源契約",
        "",
        "| Dimension | 現行公式 | Mapping後調整 | 污染／重疊 | Step 3方向 |",
        "|---|---|---|---|---|",
    ]
    for dimension, contract in SOURCE_CONTRACT.items():
        lines.append(
            f"| {dimension} | {contract['formula']} | {contract['post_adjustment']} | "
            f"{contract['contamination']} | {contract['decision']} |"
        )
    lines.extend(
        [
            "",
            "## 全體中性60與分布",
            "",
            "| Signal | Mean | SD | 中性60 | Min–Max |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for signal in SIGNALS:
        row = stats["overall"][signal]
        lines.append(
            f"| {signal} | {row['mean']:.2f} | {row['stdev']:.2f} | {row['neutral_60_rate']:.1f}% | "
            f"{row['minimum']:.1f}–{row['maximum']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Dataset版本漂移警報",
            "",
            "| Signal | Archive中性60 | 近期獨立中性60 | 07-15中性60 |",
            "|---|---:|---:|---:|",
        ]
    )
    for signal in DRIFT_SIGNALS:
        lines.append(
            f"| {signal} | {stats['archive'][signal]['neutral_60_rate']:.1f}% | "
            f"{stats['independent_recent'][signal]['neutral_60_rate']:.1f}% | "
            f"{stats['external_2026_07_15'][signal]['neutral_60_rate']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## 高重疊訊號",
            "",
            "以下列出絕對相關最高15組；相關只係重疊警報，唔等同因果或自動刪除。",
            "",
            "| Signal A | Signal B | Correlation |",
            "|---|---|---:|",
        ]
    )
    for row in correlations[:15]:
        lines.append(f"| {row['left']} | {row['right']} | {row['correlation']:+.3f} |")
    lines.extend(
        [
            "",
            "## Step 1判斷",
            "",
            "- 必須移除：sectional內track-going；race-shape內draw基底。",
            "- 必須拆重：weight不可同時在horse-health及class重複當能力；confidence只可控制可靠度，唔應作正向能力edge。",
            "- 必須補可靠度：speed、distance、form-line、騎練及冷門馬上限需由evidence count向中性60收縮。",
            "- 必須統一replay：speed中性率由archive 55.4%跌至近期4.0%，form-line則由7.8%升至52.2%，證明現存跨時段分數混有engine版本漂移；Step 2要用同一版賽前資料重算先可公平驗證新dimension。",
            "- 可保留語義但重算：stability、trainer signal、form-line、class/weight；distance維持獨立context，避免偷塞入form-line。",
            "- 本步只完成來源契約，尚未定義新公式、跑賽果性能或改正式Auto engine。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "report": str(report_path),
                "coverage": coverage,
                "errors": errors,
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
        default=ROOT / "scratch" / "hkjc_dimension_source_audit",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows, errors = build_rows(manifest, args.archive)
    write_outputs(rows, errors, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
