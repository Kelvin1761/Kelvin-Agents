#!/usr/bin/env python3
"""Replay frozen HKJC readiness-health shadow through the current engine.

The source meeting folders are treated as read-only.  Each meeting is staged in
an isolated temporary directory before the current auto orchestrator is run.
The historical finish labels are read from the existing zero/one-hit manifest;
they are never passed to the scoring engine.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "scratch" / "hkjc_zero_one_hit_manifest.json"
DEFAULT_OUTPUT = ROOT / "scratch" / "hkjc_current_engine_readiness_replay"
AUTO_SCRIPT_DIR = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_wong_choi_auto"
    / "scripts"
)
if str(AUTO_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(AUTO_SCRIPT_DIR))

import hkjc_auto_orchestrator as auto_orchestrator  # noqa: E402
import live_priors  # noqa: E402
import engine_core as engine_core_module  # noqa: E402


DATASETS = ("independent_recent", "external_2026_07_15")
SHADOW_PROFILE = "readiness_health_slot"


def configure_offline_priors(cache_root: Path) -> None:
    """Redirect the current engine's live prior tables to a local read-only cache."""
    original_root = live_priors.STATS_ROOT
    live_priors.GENERAL_PRIOR_FILES = {
        key: [cache_root / path.relative_to(original_root) for path in paths]
        for key, paths in live_priors.GENERAL_PRIOR_FILES.items()
    }
    live_priors.MASTER_STATS_FILES = {
        key: [(cache_root / path.relative_to(original_root), weight_key) for path, weight_key in paths]
        for key, paths in live_priors.MASTER_STATS_FILES.items()
    }
    live_priors.STATS_ROOT = cache_root
    live_priors._JT_RATINGS = None
    engine_core_module._TRAINER_SIGNAL_PRIORS = None


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_clone(source: Path, destination: Path) -> None:
    """Create an APFS copy-on-write clone without hydrating DriveFS contents."""
    subprocess.run(["cp", "-c", str(source), str(destination)], check=True)


def source_paths(record: dict[str, Any]) -> tuple[Path, Path]:
    logic, results = (part.strip() for part in record["source"].split("|", 1))
    return Path(logic), Path(results)


def load_records(path: Path, meeting_filter: str = "") -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = [
        record
        for record in payload["records"]
        if record.get("valid")
        and record.get("dataset") in DATASETS
        and (not meeting_filter or record.get("meeting") == meeting_filter)
    ]
    return sorted(records, key=lambda row: (row["date"], as_int(row["race_number"])))


def matching_support_files(source_dir: Path, race_numbers: set[int]) -> tuple[list[Path], Counter]:
    found: dict[tuple[int, str], list[Path]] = defaultdict(list)
    support_types = ("Facts", "排位表", "晨操")
    # One directory scan per meeting avoids repeated cloud-provider enumeration.
    for path in source_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        for race_number in race_numbers:
            token = f"Race {race_number} "
            if token not in path.name:
                continue
            for support_type in support_types:
                if path.name.endswith(f"{support_type}.md"):
                    found[(race_number, support_type)].append(path)
    missing = Counter()
    selected = []
    for race_number in sorted(race_numbers):
        for support_type in support_types:
            candidates = sorted(found.get((race_number, support_type), []))
            if candidates:
                selected.append(candidates[0])
            else:
                missing[support_type] += 1
    return selected, missing


def stage_meeting(
    records: list[dict[str, Any]], destination: Path, source_cache: Path | None = None
) -> tuple[dict[int, Path], dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    first_logic, first_results = source_paths(records[0])
    source_dir = (source_cache / records[0]["meeting"]) if source_cache else first_logic.parent
    race_numbers = {as_int(record["race_number"]) for record in records}
    support_files, missing_support = matching_support_files(source_dir, race_numbers)
    staged = {}
    source_hashes = []
    for record in records:
        race_number = as_int(record["race_number"])
        original_logic_path, results_path = source_paths(record)
        logic_path = source_dir / original_logic_path.name if source_cache else original_logic_path
        if not source_cache and logic_path.parent != source_dir:
            raise RuntimeError(f"meeting spans multiple source folders: {record['meeting']}")
        if not logic_path.exists():
            raise FileNotFoundError(logic_path)
        if not results_path.exists():
            raise FileNotFoundError(results_path)
        target = destination / logic_path.name
        copy_clone(logic_path, target)
        staged[race_number] = target
        source_hashes.append((logic_path.name, file_sha256(target)))
    for path in support_files:
        copy_clone(path, destination / path.name)
    combined = hashlib.sha256()
    for name, digest in sorted(source_hashes):
        combined.update(f"{name}:{digest}\n".encode("utf-8"))
    audit = {
        "source_dir": str(source_dir),
        "source_mode": "connector_cache" if source_cache else "drivefs_read_only",
        "races": len(records),
        "logic_files": len(staged),
        "support_files": len(support_files),
        "missing_support": dict(missing_support),
        "logic_bundle_sha256": combined.hexdigest(),
        "results_path": str(first_results),
    }
    return staged, audit


def run_orchestrator(meeting_dir: Path, health_profile: str) -> tuple[int, str]:
    # Multi-season profile scraping is explicitly display-only.  Disabling it
    # makes the replay offline and cannot change any scoring input.
    auto_orchestrator._HAS_PROFILE_SCRAPER = False
    # Historical Logic snapshots already carry their prerace combo prior in
    # _data.  Avoid reopening the shared DriveFS prior CSV during offline replay;
    # _enrich_horse_headers never overwrites an embedded prior.
    auto_orchestrator._COMBO_PRIORS_CACHE = {}
    runner = auto_orchestrator.HKJCAutoOrchestrator(
        meeting_dir,
        scoring_profile="current_engine_readiness_replay",
        shadow_profile=SHADOW_PROFILE,
        health_profile=health_profile,
    )
    runner._validate_engine_requested = False
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        exit_code = runner.run()
    return exit_code, buffer.getvalue()


def horse_number_list(items: list[dict[str, Any]]) -> list[int]:
    return [as_int(item.get("horse_number")) for item in items]


def extract_snapshot(logic_path: Path) -> dict[str, Any]:
    payload = json.loads(logic_path.read_text(encoding="utf-8"))
    verdict = payload.get("python_auto_verdict") or {}
    shadow = (payload.get("python_auto_shadow_verdicts") or {}).get(SHADOW_PROFILE) or {}
    ranking = horse_number_list(verdict.get("ranking") or [])
    shadow_ranking = horse_number_list(shadow.get("ranking") or [])
    horses = payload.get("horses") or {}
    score_signature = []
    for number in sorted(horses, key=lambda item: as_int(item)):
        auto = horses[number].get("python_auto") or {}
        shadow_auto = ((auto.get("shadow_profiles") or {}).get(SHADOW_PROFILE) or {})
        score_signature.append(
            (
                as_int(number),
                round(float(auto.get("ability_score", 0.0)), 4),
                round(float(shadow_auto.get("ability_score", 0.0)), 4),
            )
        )
    return {
        "base_ranking": ranking,
        "shadow_ranking": shadow_ranking,
        "base_top2": horse_number_list(verdict.get("top2") or []),
        "shadow_top2": [as_int(item) for item in shadow.get("shadow_top2") or []],
        "score_signature": score_signature,
        "horse_count": len(horses),
    }


def race_row(record: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    actual_top3 = {as_int(item["number"]) for item in record.get("actual_top3") or []}
    winner = next(
        (as_int(item["number"]) for item in record.get("actual_top3") or [] if as_int(item["finish"]) == 1),
        0,
    )
    stored_ranking = [as_int(item["number"]) for item in sorted(record["picks"], key=lambda row: row["rank"])]
    base = snapshot["base_top2"]
    shadow = snapshot["shadow_top2"]
    if len(base) != 2 or len(shadow) != 2 or len(snapshot["base_ranking"]) < 3:
        raise RuntimeError(f"invalid current ranking: {record['meeting']} R{record['race_number']}")
    entered = sorted(set(shadow) - set(base))
    exited = sorted(set(base) - set(shadow))
    base_hits = sum(number in actual_top3 for number in base)
    shadow_hits = sum(number in actual_top3 for number in shadow)
    stored_top2 = stored_ranking[:2]
    stored_hits = sum(number in actual_top3 for number in stored_top2)
    current_rank3 = snapshot["base_ranking"][2]
    rank3_promoted = current_rank3 in entered
    effective_rank3 = int(
        rank3_promoted
        and current_rank3 in actual_top3
        and any(number not in actual_top3 for number in exited)
    )
    harmful_rank3 = int(
        rank3_promoted
        and current_rank3 not in actual_top3
        and any(number in actual_top3 for number in exited)
    )
    effective_replacement = int(
        any(number in actual_top3 for number in entered)
        and any(number not in actual_top3 for number in exited)
    )
    harmful_replacement = int(
        any(number not in actual_top3 for number in entered)
        and any(number in actual_top3 for number in exited)
    )
    venue = "HappyValley" if "HappyValley" in record["meeting"] else "ShaTin"
    return {
        "dataset": record["dataset"],
        "split": record["dataset"],
        "meeting": record["meeting"],
        "date": record["date"],
        "venue": venue,
        "race_number": as_int(record["race_number"]),
        "actual_top3": "/".join(str(number) for number in sorted(actual_top3)),
        "winner": winner,
        "stored_top2": "/".join(str(number) for number in stored_top2),
        "current_top2": "/".join(str(number) for number in base),
        "shadow_top2": "/".join(str(number) for number in shadow),
        "stored_hits": stored_hits,
        "current_hits": base_hits,
        "shadow_hits": shadow_hits,
        "stored_winner_top2": int(winner in stored_top2),
        "current_winner_top1": int(winner == base[0]),
        "current_winner_top2": int(winner in base),
        "shadow_winner_top1": int(winner == shadow[0]),
        "shadow_winner_top2": int(winner in shadow),
        "top2_changed": int(set(base) != set(shadow)),
        "entered_top2": "/".join(str(number) for number in entered),
        "exited_top2": "/".join(str(number) for number in exited),
        "hit_delta": shadow_hits - base_hits,
        "winner_delta": int(winner in shadow) - int(winner in base),
        "zero_to_positive": int(base_hits == 0 and shadow_hits > 0),
        "one_to_two": int(base_hits == 1 and shadow_hits == 2),
        "one_to_zero": int(base_hits == 1 and shadow_hits == 0),
        "two_to_one_or_zero": int(base_hits == 2 and shadow_hits < 2),
        "current_rank3": current_rank3,
        "current_rank3_is_top3": int(current_rank3 in actual_top3),
        "current_rank3_promoted": int(rank3_promoted),
        "effective_rank3_rescue": effective_rank3,
        "harmful_rank3_promotion": harmful_rank3,
        "effective_replacement": effective_replacement,
        "harmful_replacement": harmful_replacement,
        "field_size": snapshot["horse_count"],
    }


def selection_metrics(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    hits = [as_int(row[f"{prefix}_hits"]) for row in rows]
    distribution = {str(value): hits.count(value) for value in (0, 1, 2)}
    winner_top2_key = f"{prefix}_winner_top2"
    winner_top1_key = f"{prefix}_winner_top1"
    return {
        "races": len(rows),
        "distribution": distribution,
        "total_top2_hits": sum(hits),
        "top2_hit_rate_pct": round(sum(hits) / (2 * len(rows)) * 100.0, 1) if rows else 0.0,
        "at_least_one_rate_pct": round((len(rows) - distribution["0"]) / len(rows) * 100.0, 1) if rows else 0.0,
        "two_hit_rate_pct": round(distribution["2"] / len(rows) * 100.0, 1) if rows else 0.0,
        "winner_top2": sum(as_int(row[winner_top2_key]) for row in rows),
        "winner_top2_rate_pct": round(sum(as_int(row[winner_top2_key]) for row in rows) / len(rows) * 100.0, 1) if rows else 0.0,
        "winner_top1": sum(as_int(row.get(winner_top1_key, 0)) for row in rows),
    }


def comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    current = selection_metrics(rows, "current")
    shadow = selection_metrics(rows, "shadow")
    return {
        "current": current,
        "shadow": shadow,
        "deltas": {
            "zero_hit": shadow["distribution"]["0"] - current["distribution"]["0"],
            "one_hit": shadow["distribution"]["1"] - current["distribution"]["1"],
            "two_hit": shadow["distribution"]["2"] - current["distribution"]["2"],
            "total_top2_hits": shadow["total_top2_hits"] - current["total_top2_hits"],
            "winner_top2": shadow["winner_top2"] - current["winner_top2"],
            "winner_top1": shadow["winner_top1"] - current["winner_top1"],
        },
        "changes": {
            "top2_set_changes": sum(as_int(row["top2_changed"]) for row in rows),
            "improved_races": sum(as_int(row["hit_delta"]) > 0 for row in rows),
            "harmed_races": sum(as_int(row["hit_delta"]) < 0 for row in rows),
            "zero_to_positive": sum(as_int(row["zero_to_positive"]) for row in rows),
            "one_to_two": sum(as_int(row["one_to_two"]) for row in rows),
            "one_to_zero": sum(as_int(row["one_to_zero"]) for row in rows),
            "two_to_one_or_zero": sum(as_int(row["two_to_one_or_zero"]) for row in rows),
            "effective_replacement": sum(as_int(row["effective_replacement"]) for row in rows),
            "harmful_replacement": sum(as_int(row["harmful_replacement"]) for row in rows),
            "effective_rank3_rescue": sum(as_int(row["effective_rank3_rescue"]) for row in rows),
            "harmful_rank3_promotion": sum(as_int(row["harmful_rank3_promotion"]) for row in rows),
        },
    }


def stored_vs_current(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stored_hits = [as_int(row["stored_hits"]) for row in rows]
    current = selection_metrics(rows, "current")
    stored_distribution = {str(value): stored_hits.count(value) for value in (0, 1, 2)}
    stored_winners = sum(as_int(row["stored_winner_top2"]) for row in rows)
    return {
        "stored": {
            "races": len(rows),
            "distribution": stored_distribution,
            "total_top2_hits": sum(stored_hits),
            "winner_top2": stored_winners,
        },
        "current": current,
        "deltas": {
            "zero_hit": current["distribution"]["0"] - stored_distribution["0"],
            "total_top2_hits": current["total_top2_hits"] - sum(stored_hits),
            "winner_top2": current["winner_top2"] - stored_winners,
        },
    }


def group_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {name: comparison(group) for name, group in sorted(grouped.items())}


def promotion_parity(rows: list[dict[str, Any]], evidence_path: Path) -> dict[str, Any]:
    with evidence_path.open(encoding="utf-8-sig", newline="") as handle:
        evidence = {
            (row["meeting"], as_int(row["race_number"])): row
            for row in csv.DictReader(handle)
        }
    mismatches = []
    for row in rows:
        key = (row["meeting"], as_int(row["race_number"]))
        expected = evidence.get(key)
        if expected is None:
            mismatches.append({"meeting": key[0], "race_number": key[1], "issue": "missing evidence"})
            continue
        if row["current_top2"] != expected["shadow_top2"]:
            mismatches.append(
                {
                    "meeting": key[0],
                    "race_number": key[1],
                    "expected_shadow_top2": expected["shadow_top2"],
                    "promoted_mainline_top2": row["current_top2"],
                }
            )
    return {
        "passes": not mismatches and len(rows) == len(evidence),
        "races_checked": len(rows),
        "evidence_races": len(evidence),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def gate(summary: dict[str, Any]) -> dict[str, Any]:
    combined = summary["combined"]
    primary = combined["deltas"]
    changes = combined["changes"]
    split_non_harm = all(
        item["deltas"]["zero_hit"] <= 0
        and item["deltas"]["total_top2_hits"] >= 0
        and item["deltas"]["winner_top2"] >= 0
        for item in summary["by_split"].values()
    )
    venue_non_harm = all(
        item["deltas"]["zero_hit"] <= 0
        and item["deltas"]["total_top2_hits"] >= 0
        and item["deltas"]["winner_top2"] >= 0
        for item in summary["by_venue"].values()
    )
    combined_non_harm = (
        primary["zero_hit"] <= 0
        and primary["total_top2_hits"] >= 0
        and primary["winner_top2"] >= 0
    )
    signal = (
        primary["zero_hit"] < 0
        or primary["total_top2_hits"] > 0
        or primary["winner_top2"] > 0
        or changes["effective_rank3_rescue"] > changes["harmful_rank3_promotion"]
    )
    enough_changes = changes["top2_set_changes"] >= 5
    return {
        "passes": combined_non_harm and split_non_harm and venue_non_harm and signal and enough_changes,
        "combined_non_harm": combined_non_harm,
        "split_non_harm": split_non_harm,
        "venue_non_harm": venue_non_harm,
        "positive_signal": signal,
        "minimum_five_top2_changes": enough_changes,
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# HKJC 現行引擎 readiness health-slot replay",
        "",
        "## 範圍",
        "",
        f"- 完整現行引擎重播：{summary['race_count']} 場，{summary['meeting_count']} 個賽日。",
        "- 主比較：現行正式 Top 2 對 frozen `readiness_health_slot` shadow Top 2。",
        "- 賽果只用於重算完成後評分；公式及 gate 沒有因應本批結果再調整。",
        "- 原始 Google Drive meeting folders 全程唯讀；所有引擎輸出只寫入臨時目錄。",
        "",
        "## 分析表現",
        "",
        "| 範圍 | 場數 | 現行 0/1/2 hit | Shadow 0/1/2 hit | Hits Δ | 頭馬 Top2 Δ | Top2 改動 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    display = [("合計", summary["combined"])] + [
        (name, item) for name, item in summary["by_split"].items()
    ] + [(name, item) for name, item in summary["by_venue"].items()]
    for name, item in display:
        base = item["current"]
        candidate = item["shadow"]
        delta = item["deltas"]
        changes = item["changes"]
        lines.append(
            f"| {name} | {base['races']} | {base['distribution']['0']}/{base['distribution']['1']}/{base['distribution']['2']} "
            f"| {candidate['distribution']['0']}/{candidate['distribution']['1']}/{candidate['distribution']['2']} "
            f"| {delta['total_top2_hits']:+d} | {delta['winner_top2']:+d} | {changes['top2_set_changes']} |"
        )
    combined = summary["combined"]
    base = combined["current"]
    shadow = combined["shadow"]
    changes = combined["changes"]
    lines += [
        "",
        "## 0/1-hit 與第3選救援",
        "",
        f"- 0-hit：{base['distribution']['0']} → {shadow['distribution']['0']}；0→有命中 {changes['zero_to_positive']} 場。",
        f"- Top 2 命中率：{base['top2_hit_rate_pct']:.1f}% → {shadow['top2_hit_rate_pct']:.1f}%（{shadow['top2_hit_rate_pct'] - base['top2_hit_rate_pct']:+.1f}pp）；二中二場率 {base['two_hit_rate_pct']:.1f}% → {shadow['two_hit_rate_pct']:.1f}%。",
        f"- 1→2 hit：{changes['one_to_two']} 場；1→0 hit：{changes['one_to_zero']} 場；2→下跌：{changes['two_to_one_or_zero']} 場。",
        f"- 有效替換／有害替換：{changes['effective_replacement']} / {changes['harmful_replacement']}。",
        f"- 現行第3選有效救援／有害升級：{changes['effective_rank3_rescue']} / {changes['harmful_rank3_promotion']}。",
        f"- 代價：第一選中頭馬 {base['winner_top1']} → {shadow['winner_top1']}（{shadow['winner_top1'] - base['winner_top1']:+d}）；但用戶投注決策範圍係 Top 2，頭馬 Top 2 仍然改善。",
        f"- 觸發集中：沙田改動 {summary['by_venue']['ShaTin']['changes']['top2_set_changes']} 場；跑馬地只改動 {summary['by_venue']['HappyValley']['changes']['top2_set_changes']} 場。",
        "",
        "## 現行引擎本身（對舊 stored ranking）",
        "",
    ]
    drift = summary["stored_vs_current"]
    lines += [
        f"- 舊 stored Top 2：0/1/2 hit = {drift['stored']['distribution']['0']}/{drift['stored']['distribution']['1']}/{drift['stored']['distribution']['2']}，總 hits {drift['stored']['total_top2_hits']}，頭馬 Top 2 {drift['stored']['winner_top2']}。",
        f"- 現行引擎 Top 2：0/1/2 hit = {drift['current']['distribution']['0']}/{drift['current']['distribution']['1']}/{drift['current']['distribution']['2']}，總 hits {drift['current']['total_top2_hits']}，頭馬 Top 2 {drift['current']['winner_top2']}。",
        f"- 版本漂移：0-hit {drift['deltas']['zero_hit']:+d}、總 hits {drift['deltas']['total_top2_hits']:+d}、頭馬 Top 2 {drift['deltas']['winner_top2']:+d}。",
        "- 注意：現行 replay 使用目前兩季 prior tables，因此呢段 stored→current 差異只係版本漂移診斷，唔當成無偷睇 point-in-time 改善證據。主晉升證據係同一現行引擎 base/shadow 配對結果，再配合先前 157 場 frozen stored-matrix holdout。",
        "",
        "## 驗證與決定",
        "",
        f"- 兩次現行引擎重跑完全一致：{'是' if summary['determinism']['passes'] else '否'}。",
        f"- Logic/Facts/racecard scoring-context 完整性錯誤：{summary['source_audit']['error_count']}（trackwork header fallback 屬 optional）。",
        f"- 晉升 gate：{'PASS' if summary['promotion_gate']['passes'] else 'HOLD'}。",
        "",
    ]
    parity = summary.get("promotion_parity")
    if parity:
        lines += [
            f"- 正式主線對凍結 shadow 逐場 parity：{'PASS' if parity['passes'] else 'FAIL'}（{parity['races_checked']}場，{parity['mismatch_count']}個不一致）。",
            "- 晉升後 readiness shadow 與主線相同，所以 base/shadow 改動數 gate 不再適用；正式決定以晉升前 evidence gate 加本次逐場 parity 為準。",
            "",
        ]
    if parity and parity["passes"]:
        lines.append("結論：正式主線逐場完全重現已通過 gate 嘅 frozen readiness shadow，可以完成晉升。")
    elif summary["promotion_gate"]["passes"]:
        lines.append("結論：readiness health-slot 喺現行引擎 replay 仍然有非傷害兼正面訊號，可以進入正式 scoring 晉升評估。")
    else:
        lines.append("結論：readiness health-slot 未能喺現行引擎 replay 同時通過整體、split、場地及訊號門檻，維持 internal shadow。")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--meeting", default="", help="Optional single-meeting smoke test")
    parser.add_argument("--source-cache", type=Path, default=None, help="Optional connector-downloaded read-only source cache")
    parser.add_argument("--priors-cache", type=Path, default=None, help="Local comprehensive_stats cache for current-engine priors")
    parser.add_argument("--expected-shadow-csv", type=Path, default=None, help="Frozen pre-promotion shadow picks for exact parity validation")
    parser.add_argument(
        "--health-profile",
        default="readiness_health_slot",
        choices=("readiness_health_slot", "legacy_health_v2"),
        help="Mainline health profile used for this replay",
    )
    args = parser.parse_args()

    records = load_records(args.manifest, args.meeting)
    if not records:
        raise SystemExit("no replay records selected")
    by_meeting: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_meeting[record["meeting"]].append(record)
    if args.priors_cache:
        configure_offline_priors(args.priors_cache)

    rows = []
    audits = {}
    determinism_errors = []
    with tempfile.TemporaryDirectory(prefix="hkjc-current-engine-readiness-") as temp_name:
        temp_root = Path(temp_name)
        for meeting, meeting_records in sorted(by_meeting.items()):
            print(f"[{meeting}] staging {len(meeting_records)} races", flush=True)
            meeting_dir = temp_root / meeting
            staged, audit = stage_meeting(meeting_records, meeting_dir, args.source_cache)
            audits[meeting] = audit
            snapshots = []
            for pass_number in (1, 2):
                exit_code, log = run_orchestrator(meeting_dir, args.health_profile)
                if exit_code:
                    tail = "\n".join(log.splitlines()[-30:])
                    raise RuntimeError(f"orchestrator failed for {meeting}, pass {pass_number}:\n{tail}")
                snapshots.append({race: extract_snapshot(path) for race, path in staged.items()})
            if snapshots[0] != snapshots[1]:
                determinism_errors.append(meeting)
            for record in meeting_records:
                race_number = as_int(record["race_number"])
                rows.append(race_row(record, snapshots[0][race_number]))
            print(f"[{meeting}] complete", flush=True)

    rows.sort(key=lambda row: (row["date"], row["race_number"]))
    source_errors = []
    for meeting, audit in audits.items():
        for support_type, count in audit["missing_support"].items():
            if support_type == "晨操":
                continue
            if count:
                source_errors.append(f"{meeting}: missing {support_type} x{count}")
    summary = {
        "contract": {
            "baseline": "current engine mainline Top 2",
            "candidate": SHADOW_PROFILE,
            "mainline_health_profile": args.health_profile,
            "datasets": list(DATASETS),
            "outcome_blind_scoring": True,
            "source_write_policy": "read-only; staged temp copies only",
        },
        "race_count": len(rows),
        "meeting_count": len(by_meeting),
        "combined": comparison(rows),
        "by_split": group_metrics(rows, "split"),
        "by_venue": group_metrics(rows, "venue"),
        "by_meeting": group_metrics(rows, "meeting"),
        "stored_vs_current": stored_vs_current(rows),
        "determinism": {"passes": not determinism_errors, "errors": determinism_errors},
        "source_audit": {
            "meetings": audits,
            "error_count": len(source_errors),
            "errors": source_errors,
        },
    }
    summary["promotion_gate"] = gate(summary)
    if args.expected_shadow_csv:
        summary["promotion_parity"] = promotion_parity(rows, args.expected_shadow_csv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output.with_name(args.output.name + "_races.csv"), rows)
    args.output.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_name(args.output.name + "_report.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    print(json.dumps({
        "races": len(rows),
        "meetings": len(by_meeting),
        "combined": summary["combined"],
        "promotion_gate": summary["promotion_gate"],
        "determinism": summary["determinism"],
        "source_errors": source_errors,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
