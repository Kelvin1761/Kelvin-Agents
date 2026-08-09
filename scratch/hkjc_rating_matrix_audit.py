#!/usr/bin/env python3
"""Step-5 time-stratified audit of the HKJC rating matrix.

The audit evaluates pure matrix scores and their dimensions.  It excludes live
rank_score, micro tie-breaks and blind rank-2/rank-3 swaps.  Stored sectional
and race-shape dimensions are shown for structural audit only because they
contain going and draw evidence; speed-only is the eligible sectional proxy.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hkjc_zero_one_hit_manifest import result_positions


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "scratch" / "hkjc_zero_one_hit_manifest.json"
DEFAULT_ARCHIVE = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_ranking_dataset.csv"
)

MATRIX_WEIGHTS = {
    "sectional": 0.1849,
    "trainer_signal": 0.2209,
    "stability": 0.0919,
    "race_shape": 0.2560,
    "class_advantage": 0.1335,
    "horse_health": 0.0378,
    "form_line": 0.0749,
}
DEBUT_MATRIX_WEIGHTS = {
    "trainer_signal": 0.30,
    "horse_health": 0.30,
    "race_shape": 0.20,
    "stability": 0.15,
    "class_advantage": 0.05,
}
DIMENSIONS = (
    "pure_matrix_total",
    "sectional",
    "speed_only",
    "trainer_signal",
    "stability",
    "race_shape",
    "class_advantage",
    "horse_health",
    "form_line",
    "distance_context",
)
LABELS = {
    "pure_matrix_total": "純矩陣總分",
    "sectional": "Stored段速矩陣（含going；只審核）",
    "speed_only": "Speed-only段速代理",
    "trainer_signal": "騎練訊號",
    "stability": "狀態與穩定性",
    "race_shape": "走位矩陣（含檔位；只審核）",
    "class_advantage": "級數優勢",
    "horse_health": "健康／新鮮感",
    "form_line": "賽績線",
    "distance_context": "路程context（矩陣外診斷）",
}
ELIGIBILITY = {
    "pure_matrix_total": "總分審核",
    "sectional": "只審核",
    "speed_only": "可研究",
    "trainer_signal": "可研究",
    "stability": "可研究",
    "race_shape": "只審核",
    "class_advantage": "可研究",
    "horse_health": "可研究",
    "form_line": "可研究",
    "distance_context": "矩陣外context",
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


def pure_total(matrix: dict[str, float], is_debut: bool) -> float:
    weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS
    return round(sum(matrix.get(key, 60.0) * weight for key, weight in weights.items()), 4)


def horse_record(
    *,
    dataset: str,
    meeting: str,
    race_number: int,
    number: int,
    name: str,
    finish: int,
    stored_ability: float,
    is_debut: bool,
    matrix: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    matrix_values = {key: as_float(matrix.get(key)) for key in MATRIX_WEIGHTS}
    pure = pure_total(matrix_values, is_debut)
    return {
        "dataset": dataset,
        "meeting": meeting,
        "race_number": race_number,
        "horse_number": number,
        "horse_name": name,
        "finish": finish,
        "is_top3": finish <= 3,
        "is_winner": finish == 1,
        "is_debut": is_debut,
        "stored_ability": round(stored_ability, 4),
        "pure_matrix_total": pure,
        "post_matrix_delta": round(stored_ability - pure, 4),
        "sectional": matrix_values["sectional"],
        "speed_only": as_float(features.get("speed_score")),
        "trainer_signal": matrix_values["trainer_signal"],
        "stability": matrix_values["stability"],
        "race_shape": matrix_values["race_shape"],
        "class_advantage": matrix_values["class_advantage"],
        "horse_health": matrix_values["horse_health"],
        "form_line": matrix_values["form_line"],
        "distance_context": as_float(features.get("distance_score")),
    }


def load_archive(path: Path, valid_keys: set[tuple[str, int]]) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            meeting = str(raw.get("meeting_name") or Path(str(raw.get("meeting") or "")).name)
            race_number = as_int(raw.get("race_number"))
            finish = as_int(raw.get("finish_pos"))
            if (meeting, race_number) not in valid_keys or finish <= 0:
                continue
            matrix = {
                key: raw.get(f"matrix_{key}")
                for key in MATRIX_WEIGHTS
            }
            features = {
                "speed_score": raw.get("feat_speed_score"),
                "distance_score": raw.get("feat_distance_score"),
            }
            rows.append(
                horse_record(
                    dataset="archive",
                    meeting=meeting,
                    race_number=race_number,
                    number=as_int(raw.get("horse_number")),
                    name=str(raw.get("horse_name") or ""),
                    finish=finish,
                    stored_ability=as_float(
                        raw.get("current_live_recomputed_ability"),
                        as_float(raw.get("current_live_ability")),
                    ),
                    is_debut=bool(as_int(raw.get("is_debut"))),
                    matrix=matrix,
                    features=features,
                )
            )
    return rows


def load_logic_race(
    record: dict[str, Any],
    positions: dict[int, int],
) -> list[dict[str, Any]]:
    logic_path = Path(str(record["source"]).split(" | ", 1)[0])
    payload = json.loads(logic_path.read_text(encoding="utf-8"))
    rows = []
    for horse_key, raw in (payload.get("horses") or {}).items():
        number = as_int(horse_key)
        if number not in positions:
            continue
        auto = raw.get("python_auto") if isinstance(raw.get("python_auto"), dict) else {}
        if not auto:
            continue
        matrix = auto.get("matrix_scores") if isinstance(auto.get("matrix_scores"), dict) else {}
        features = auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {}
        reasons = auto.get("reason_codes") if isinstance(auto.get("reason_codes"), list) else []
        is_debut = bool(raw.get("is_debut")) or any(str(reason).startswith("debut_") for reason in reasons)
        rows.append(
            horse_record(
                dataset=record["dataset"],
                meeting=record["meeting"],
                race_number=record["race_number"],
                number=number,
                name=str(raw.get("horse_name") or ""),
                finish=positions[number],
                stored_ability=as_float(auto.get("ability_score")),
                is_debut=is_debut,
                matrix=matrix,
                features=features,
            )
        )
    return rows


def build_horse_rows(manifest: dict[str, Any], archive_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [row for row in manifest["records"] if row.get("valid")]
    archive_keys = {
        (row["meeting"], row["race_number"])
        for row in valid if row["dataset"] == "archive"
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
        race_rows = load_logic_race(record, positions)
        if len(race_rows) < 3:
            errors.append({"meeting": record["meeting"], "race": record["race_number"], "reason": "fewer_than_3_scored_finishers"})
            continue
        rows.extend(race_rows)
    return rows, errors


def group_races(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["dataset"], row["meeting"], row["race_number"])].append(row)
    return dict(grouped)


def within_race_auc(races: dict[tuple[str, str, int], list[dict[str, Any]]], dimension: str, target: str) -> float:
    wins = 0.0
    pairs = 0
    for race_rows in races.values():
        positives = [row for row in race_rows if row[target]]
        negatives = [row for row in race_rows if not row[target]]
        for positive in positives:
            for negative in negatives:
                pairs += 1
                if positive[dimension] > negative[dimension]:
                    wins += 1.0
                elif positive[dimension] == negative[dimension]:
                    wins += 0.5
    return round(wins / pairs, 4) if pairs else 0.5


def mean_race_delta(races: dict[tuple[str, str, int], list[dict[str, Any]]], dimension: str, target: str) -> float:
    deltas = []
    for race_rows in races.values():
        positives = [row[dimension] for row in race_rows if row[target]]
        negatives = [row[dimension] for row in race_rows if not row[target]]
        if positives and negatives:
            deltas.append(statistics.mean(positives) - statistics.mean(negatives))
    return round(statistics.mean(deltas), 4) if deltas else 0.0


def top2_capture(races: dict[tuple[str, str, int], list[dict[str, Any]]], dimension: str) -> dict[str, Any]:
    hits = 0
    winners = 0
    total = len(races)
    for race_rows in races.values():
        selected = sorted(race_rows, key=lambda row: (-row[dimension], row["horse_number"]))[:2]
        hits += sum(row["is_top3"] for row in selected)
        winners += int(any(row["is_winner"] for row in selected))
    return {
        "top2_actual_top3_hits": hits,
        "hits_per_race": round(hits / total, 3) if total else 0.0,
        "winner_top2_rate": round(winners / total * 100, 1) if total else 0.0,
    }


def dimension_metrics(rows: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    races = group_races(rows)
    capture = top2_capture(races, dimension)
    return {
        "dimension": dimension,
        "label": LABELS[dimension],
        "eligibility": ELIGIBILITY[dimension],
        "weight": MATRIX_WEIGHTS.get(dimension),
        "horses": len(rows),
        "races": len(races),
        "top3_auc": within_race_auc(races, dimension, "is_top3"),
        "winner_auc": within_race_auc(races, dimension, "is_winner"),
        "top3_mean_race_delta": mean_race_delta(races, dimension, "is_top3"),
        "winner_mean_race_delta": mean_race_delta(races, dimension, "is_winner"),
        "neutral_60_rate": round(sum(abs(row[dimension] - 60.0) < 1e-9 for row in rows) / len(rows) * 100, 1) if rows else 0.0,
        **capture,
    }


def consistency_label(archive_auc: float, recent_auc: float) -> str:
    if archive_auc >= 0.52 and recent_auc >= 0.52:
        return "跨時段正向"
    if archive_auc <= 0.48 and recent_auc <= 0.48:
        return "跨時段反向"
    if (archive_auc >= 0.52 and recent_auc <= 0.48) or (archive_auc <= 0.48 and recent_auc >= 0.52):
        return "方向反轉"
    return "弱／不穩定"


def pure_top2_performance(
    rows: list[dict[str, Any]],
    manifest_records: list[dict[str, Any]],
    dataset: str | None = None,
) -> dict[str, Any]:
    if dataset is not None:
        rows = [row for row in rows if row["dataset"] == dataset]
        manifest_records = [row for row in manifest_records if row.get("dataset") == dataset]
    races = group_races(rows)
    distribution = Counter()
    winner_top2 = 0
    selected_by_key = {}
    for key, race_rows in races.items():
        selected = sorted(race_rows, key=lambda row: (-row["pure_matrix_total"], row["horse_number"]))[:2]
        distribution[sum(row["is_top3"] for row in selected)] += 1
        winner_top2 += int(any(row["is_winner"] for row in selected))
        selected_by_key[(key[1], key[2])] = {row["horse_number"] for row in selected}
    valid_manifest = [row for row in manifest_records if row.get("valid")]
    current_distribution = Counter(row["top2_hits"] for row in valid_manifest)
    current_winner = sum(row["winner_in_top2"] for row in valid_manifest)
    different = sum(
        selected_by_key.get((row["meeting"], row["race_number"]), set())
        != {pick["number"] for pick in row["picks"][:2]}
        for row in valid_manifest
    )
    total = len(races)
    return {
        "races": total,
        "pure_matrix_top2_hit_distribution": dict(distribution),
        "current_top2_hit_distribution": dict(current_distribution),
        "pure_matrix_winner_top2": winner_top2,
        "current_winner_top2": current_winner,
        "pure_matrix_winner_top2_rate": round(winner_top2 / total * 100, 1) if total else 0.0,
        "current_winner_top2_rate": round(current_winner / total * 100, 1) if total else 0.0,
        "top2_set_different_races": different,
    }


def build_audit(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    datasets = sorted({row["dataset"] for row in rows})
    metrics_by_dataset = {
        dataset: {
            dimension: dimension_metrics([row for row in rows if row["dataset"] == dataset], dimension)
            for dimension in DIMENSIONS
        }
        for dataset in datasets
    }
    overall = {dimension: dimension_metrics(rows, dimension) for dimension in DIMENSIONS}
    consistency = {}
    for dimension in DIMENSIONS:
        archive_auc = metrics_by_dataset["archive"][dimension]["top3_auc"]
        recent_auc = metrics_by_dataset["independent_recent"][dimension]["top3_auc"]
        consistency[dimension] = {
            "archive_top3_auc": archive_auc,
            "recent_top3_auc": recent_auc,
            "label": consistency_label(archive_auc, recent_auc),
        }
    post_deltas = [row["post_matrix_delta"] for row in rows]
    non_debut_deltas = [row["post_matrix_delta"] for row in rows if not row["is_debut"]]
    debut_deltas = [row["post_matrix_delta"] for row in rows if row["is_debut"]]
    def delta_stats(values: list[float]) -> dict[str, Any]:
        return {
            "horses": len(values),
            "nonzero_horses": sum(abs(value) > 1e-6 for value in values),
            "absolute_gt_0_05": sum(abs(value) > 0.05 for value in values),
            "absolute_ge_0_5": sum(abs(value) >= 0.5 for value in values),
            "mean": round(statistics.mean(values), 4) if values else 0.0,
            "max": round(max(values), 4) if values else 0.0,
            "min": round(min(values), 4) if values else 0.0,
        }
    return {
        "coverage": {
            "horses": len(rows),
            "races": len(group_races(rows)),
            "meetings": len({(row["dataset"], row["meeting"]) for row in rows}),
            "debut_horses": sum(row["is_debut"] for row in rows),
        },
        "post_matrix_delta": {
            "all": delta_stats(post_deltas),
            "non_debut": delta_stats(non_debut_deltas),
            "debut_formula_difference": delta_stats(debut_deltas),
        },
        "overall": overall,
        "by_dataset": metrics_by_dataset,
        "time_consistency": consistency,
        "pure_matrix_top2": pure_top2_performance(rows, manifest["records"]),
        "pure_matrix_top2_by_dataset": {
            dataset: pure_top2_performance(rows, manifest["records"], dataset)
            for dataset in sorted({row["dataset"] for row in rows})
        },
    }


def write_outputs(rows: list[dict[str, Any]], audit: dict[str, Any], errors: list[dict[str, Any]], output_prefix: Path) -> None:
    payload = {
        "method": {
            "race_stratified_auc": True,
            "uses_pure_matrix_total": True,
            "uses_rank_score": False,
            "uses_micro_tiebreak": False,
            "blind_swap": False,
            "audit_only_dimensions": ["sectional", "race_shape"],
            "eligible_sectional_proxy": "speed_only",
            "excluded_from_tuning": ["going", "draw", "odds", "market"],
        },
        "audit": audit,
        "errors": errors,
    }
    json_path = output_prefix.with_suffix(".json")
    csv_path = output_prefix.with_suffix(".csv")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "dataset", "dimension", "label", "eligibility", "weight", "horses", "races",
            "top3_auc", "winner_auc", "top3_mean_race_delta", "winner_mean_race_delta",
            "neutral_60_rate", "top2_actual_top3_hits", "hits_per_race", "winner_top2_rate",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for dataset, metrics in [("overall", audit["overall"]), *audit["by_dataset"].items()]:
            for dimension in DIMENSIONS:
                writer.writerow({"dataset": dataset, **metrics[dimension]})

    coverage = audit["coverage"]
    pure = audit["pure_matrix_top2"]
    lines = [
        "# HKJC Wong Choi Step 5 — Rating Matrix跨時段審核",
        "",
        "## 方法鎖定",
        "",
        "- 使用純矩陣總分及matrix dimension；不使用live rank_score、micro tie-break或第二／第三選盲換。",
        "- AUC為同場pairwise分辨力：0.50等同無分辨力，越高越好。",
        "- Stored段速矩陣含going、走位矩陣含檔位，只作結構審核；可研究段速用speed-only代理。",
        "- 不使用賠率、市場，亦不由going／draw產生候選調整。",
        "",
        "## Coverage",
        "",
        f"- {coverage['meetings']}個賽日／{coverage['races']}場／{coverage['horses']}匹完成馬",
        f"- 初出馬：{coverage['debut_horses']}匹",
        f"- 資料錯誤：{len(errors)}",
        "",
        "## 全體矩陣分辨力",
        "",
        "| Dimension | 權重 | 實際前三AUC | 頭馬AUC | 實際前三平均差 | 單項Top2每場包馬 | 中性60 | 資格 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for dimension in DIMENSIONS:
        row = audit["overall"][dimension]
        weight = "—" if row["weight"] is None else f"{row['weight'] * 100:.2f}%"
        lines.append(
            f"| {row['label']} | {weight} | {row['top3_auc']:.3f} | {row['winner_auc']:.3f} | "
            f"{row['top3_mean_race_delta']:+.2f} | {row['hits_per_race']:.3f} | {row['neutral_60_rate']:.1f}% | {row['eligibility']} |"
        )
    lines.extend(["", "## 跨時段一致性", "", "| Dimension | Archive AUC | 近期AUC | 判斷 |", "|---|---:|---:|---|"])
    for dimension in DIMENSIONS:
        row = audit["time_consistency"][dimension]
        lines.append(
            f"| {LABELS[dimension]} | {row['archive_top3_auc']:.3f} | {row['recent_top3_auc']:.3f} | {row['label']} |"
        )
    lines.extend(
        [
            "",
            "## 純矩陣Top 2校準",
            "",
            f"- 純矩陣Top 2 hit分布：{pure['pure_matrix_top2_hit_distribution']}",
            f"- 現行Top 2 hit分布：{pure['current_top2_hit_distribution']}",
            f"- 純矩陣Top 2包頭馬：{pure['pure_matrix_winner_top2']}/{pure['races']}（{pure['pure_matrix_winner_top2_rate']}%）",
            f"- 現行Top 2包頭馬：{pure['current_winner_top2']}/{pure['races']}（{pure['current_winner_top2_rate']}%）",
            f"- 純矩陣與現行Top 2名單不同：{pure['top2_set_different_races']}場",
            "",
            "| 時段 | 純矩陣0／1／2 hit | 現行0／1／2 hit | 純矩陣頭馬Top 2 | 現行頭馬Top 2 | 名單不同 |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for dataset, row in audit["pure_matrix_top2_by_dataset"].items():
        lines.append(
            f"| {dataset} | {row['pure_matrix_top2_hit_distribution']} | {row['current_top2_hit_distribution']} | "
            f"{row['pure_matrix_winner_top2_rate']}% | {row['current_winner_top2_rate']}% | {row['top2_set_different_races']} |"
        )
    lines.extend(
        [
            "",
            "## Post-matrix差值核對",
            "",
            f"- 非初出馬：{audit['post_matrix_delta']['non_debut']['horses']}匹；｜差值｜>0.05有{audit['post_matrix_delta']['non_debut']['absolute_gt_0_05']}匹，≥0.5有{audit['post_matrix_delta']['non_debut']['absolute_ge_0_5']}匹",
            f"- 非初出馬平均／最低／最高差：{audit['post_matrix_delta']['non_debut']['mean']:+.3f}／{audit['post_matrix_delta']['non_debut']['min']:+.3f}／{audit['post_matrix_delta']['non_debut']['max']:+.3f}",
            f"- 初出馬：{audit['post_matrix_delta']['debut_formula_difference']['horses']}匹；平均差{audit['post_matrix_delta']['debut_formula_difference']['mean']:+.3f}，另列為debut公式差異，唔當micro。",
            "- 本報告所有性能結論採用純矩陣總分；差值只用嚟確認post-matrix影響已被隔離。",
            "",
            "## Step 5狀態",
            "",
            "Rating matrix跨時段審核完成；尚未提出新權重、跑候選shadow或改正式模型。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "report": str(report_path), "coverage": coverage, "pure_matrix_top2": pure, "errors": errors}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "scratch" / "hkjc_rating_matrix_audit")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    rows, errors = build_horse_rows(manifest, args.archive)
    audit = build_audit(rows, manifest)
    write_outputs(rows, audit, errors, args.output_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
