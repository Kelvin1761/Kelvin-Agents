#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[5]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING, HK_RACING
SHARED_ROOT = Path(__file__).resolve().parent
AU_REFLECTOR_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_reflector" / "scripts"
HKJC_REFLECTOR_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
HKJC_EXTRACTOR_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts"
AU_RESULTS_EXTRACTOR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "claw_racenet_results.py"
HKJC_RESULTS_EXTRACTOR = HKJC_EXTRACTOR_SCRIPTS / "fast_extract_results.py"


def _add_sys_path(path: Path) -> None:
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


def _import_reflector_auto_stats():
    _add_sys_path(HKJC_REFLECTOR_SCRIPTS)
    from reflector_auto_stats import run_stats

    return run_stats


def _import_au_review():
    _add_sys_path(AU_REFLECTOR_SCRIPTS)
    from au_review_auto_weighting import run_review

    return run_review


def _import_au_shadow_bundle():
    _add_sys_path(AU_REFLECTOR_SCRIPTS)
    from au_shadow_bundle_benchmark import VARIANTS, run_variant

    return VARIANTS, run_variant


def _import_au_class_shadow():
    _add_sys_path(AU_REFLECTOR_SCRIPTS)
    from au_class_normalization_shadow_test import VARIANTS, run_variant

    return VARIANTS, run_variant


def _import_hkjc_review():
    _add_sys_path(HKJC_REFLECTOR_SCRIPTS)
    from hkjc_results_db import (
        find_meeting_results_file,
        get_analysis_archive_root,
        get_season_csvs,
        get_season_results_roots,
    )
    from review_auto_weighting import run_review

    return {
        "find_meeting_results_file": find_meeting_results_file,
        "get_analysis_archive_root": get_analysis_archive_root,
        "get_season_csvs": get_season_csvs,
        "get_season_results_roots": get_season_results_roots,
        "run_review": run_review,
    }


def _import_hkjc_sync():
    _add_sys_path(HKJC_REFLECTOR_SCRIPTS)
    from sync_hkjc_results_database import sync_meeting_results

    return sync_meeting_results


DOMAIN_LABELS = {"au": "AU", "hkjc": "HKJC"}
DOMAIN_ARCHIVES = {
    "au": AU_RACING,
    "hkjc": HK_RACING,
}
DEFAULT_REPORT_NAMES = {
    "au": "{meeting}_Reflector_Report.md",
    "hkjc": "HKJC_Reflection_Report.md",
}


SCORE_LABELS = {
    "form_score": "近況",
    "trial_score": "試閘",
    "sectional_score": "段速",
    "pace_map_score": "步速形勢",
    "speed_score": "速度",
    "class_score": "班次",
    "weight_score": "負磅",
    "distance_score": "路程",
    "track_score": "場地",
    "track_going_score": "場地狀況",
    "draw_score": "檔位",
    "formline_score": "賽績線",
    "consistency_score": "穩定性",
    "health_score": "健康",
    "risk_score": "風險",
    "confidence_score": "信心",
    "trainer_score": "練馬師",
    "jockey_score": "騎師",
    "jockey_horse_fit_score": "人馬配搭",
    "speed_rating_score": "速度評級",
}


SUGGESTION_DESCRIPTIONS = {
    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap08_edge05": "細化 Happy Valley 中距離微檔位 / 形勢 tie-break",
    "candidate_draw_micro_tiebreak_hv_mid_shape60_gap06": "收緊 Happy Valley 中距離檔位 gap 門檻",
    "candidate_draw_tiebreak_ordering": "用檔位 context 做前列排序 tie-break",
    "candidate_outer_weights_retune": "微調 7D 外層權重分配",
    "candidate_trainer_signal_context": "加強騎練部署信號",
    "candidate_class_distance_weight_joint": "聯動班次 / 路程 / 負磅 context",
    "candidate_sectional_context": "加強操練段速 context",
    "candidate_race_sectional_score": "加強實戰 sectional 訊號",
    "candidate_race_sectional_score_non_debut": "只對非初出馬加強實戰 sectional 訊號",
    "candidate_horse_health_context": "加強健康 / 醫療 / freshness context",
    "candidate_horse_health_risk_only": "將健康維度收窄為純 risk context",
    "candidate_draw_hkjc_anchor_no_bleed": "加入 HKJC draw anchor，但限制 bleed-over",
    "candidate_consistency_context": "加強 consistency / form stability context",
    "bundle_recommended": "調整 AU 6D 內部 factor balance（sectional / jockey-fit / class / formline）",
    "bundle_conservative": "保守版 AU factor balance 微調",
    "class_venue_weight_med": "加入 AU class ladder + venue depth + 負磅 context",
    "class_venue_weight_soft": "柔性加入 AU class ladder + venue depth + 負磅 context",
}


INCIDENT_KEYWORDS = {
    "interference": ("interference", "checked", "held up", "blocked", "crowded", "bumped", "hampered", "受擠迫", "受阻", "被碰撞", "碰撞", "勒避", "失去平衡", "收慢避開"),
    "slow_start": ("slow away", "slow to begin", "began awkwardly", "stumbled", "missed the start", "出閘緩慢", "出閘笨拙", "起步時俯首前跪", "起步時發生碰撞"),
    "wide_run": ("wide", "three wide", "without cover", "外疊", "無遮擋", "走三疊"),
    "vet_issue": ("lame", "bled", "cardiac", "fractious", "vet", "injury", "不良於行", "流鼻血", "心律不正常", "獸醫"),
    "ride_issue": ("rider", "apprentice", "tactics", "hung", "poor ride", "騎師", "部署", "催策"),
}


@dataclass
class RacePerformance:
    race_num: int
    label: str
    model_top3: list[dict[str, Any]]
    model_top5: list[dict[str, Any]]
    actual_top3: list[dict[str, Any]]
    actual_rows: list[dict[str, Any]]
    prediction_rows: list[dict[str, Any]]
    top5_actual_top3_hits: int
    top5_actual_top3_covered: list[dict[str, Any]]
    top5_actual_top3_missed: list[dict[str, Any]]
    winner_in_model_top5: bool
    missed_actual_top3: list[dict[str, Any]]
    incident_analysis: dict[str, Any]


def default_report_path(platform: str, meeting_dir: Path) -> Path:
    pattern = DEFAULT_REPORT_NAMES[platform]
    report_dir = meeting_dir
    if platform == "hkjc":
        archive_root = DOMAIN_ARCHIVES[platform].resolve()
        resolved_meeting_dir = meeting_dir.resolve()
        try:
            resolved_meeting_dir.relative_to(archive_root)
        except ValueError:
            report_dir = archive_root / meeting_dir.name
        else:
            report_dir = resolved_meeting_dir
    return report_dir / pattern.format(meeting=meeting_dir.name)


def run_logged_command(cmd: list[str], label: str, ok_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    print(f"\n{'=' * 72}")
    print(f"🔍 {label}")
    print(" ".join(str(part) for part in cmd))
    print(f"{'=' * 72}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode not in ok_codes:
        raise SystemExit(result.returncode)
    return result


def resolve_meeting_dir(platform: str, meeting_ref: str | None = None, meeting_dir: str | Path | None = None) -> Path:
    if meeting_dir:
        path = Path(meeting_dir).expanduser()
        return path.resolve()

    if not meeting_ref:
        raise SystemExit("❌ meeting_ref / meeting_dir 不能留空。")

    archive_root = DOMAIN_ARCHIVES[platform]
    exact = archive_root / meeting_ref
    if exact.is_dir():
        return exact.resolve()

    needle = meeting_ref.lower()
    matches = [path for path in sorted(archive_root.iterdir()) if path.is_dir() and needle in path.name.lower()]
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise SystemExit(f"❌ 找不到 {DOMAIN_LABELS[platform]} meeting: {meeting_ref}")
    candidates = ", ".join(path.name for path in matches[:5])
    raise SystemExit(f"❌ {DOMAIN_LABELS[platform]} meeting 匹配到多個資料夾，請指定更完整名稱: {candidates}")


def infer_hkjc_date_and_venue(meeting_dir: Path, results_url: str | None) -> tuple[str, str]:
    parsed = urlparse(results_url or "")
    query = parse_qs(parsed.query)
    race_date = query.get("RaceDate", [""])[0].replace("/", "-")
    if not race_date and len(meeting_dir.name) >= 10:
        race_date = meeting_dir.name[:10]

    venue = ""
    lower_name = meeting_dir.name.lower()
    lower_url = (results_url or "").lower()
    if "happyvalley" in lower_name or "跑馬地" in meeting_dir.name or "happyvalley" in lower_url:
        venue = "HappyValley"
    elif "shatin" in lower_name or "sha_tin" in lower_name or "沙田" in meeting_dir.name or "shatin" in lower_url:
        venue = "ShaTin"

    if not race_date:
        raise SystemExit("❌ 無法從 meeting / URL 推斷 HKJC 賽日日期。")
    return race_date, venue or "Unknown"


def find_existing_results_file(platform: str, meeting_dir: Path) -> Path | None:
    if platform == "au":
        json_candidates = sorted(meeting_dir.glob("Race_Results_*.json"))
        if json_candidates:
            return json_candidates[0]
        md_candidates = sorted(meeting_dir.glob("Race_Results_Reflector.md"))
        return md_candidates[0] if md_candidates else None

    local_candidates = sorted(meeting_dir.glob("*全日賽果.json"))
    if local_candidates:
        return local_candidates[0]

    hkjc = _import_hkjc_review()
    return hkjc["find_meeting_results_file"](meeting_dir, hkjc["get_season_results_roots"]())


def ensure_results_file(platform: str, meeting_dir: Path, results_url: str | None, force_extract: bool = False) -> Path:
    if not force_extract:
        existing = find_existing_results_file(platform, meeting_dir)
        if existing and existing.exists():
            return existing.resolve()

    if not results_url:
        raise SystemExit(f"❌ {DOMAIN_LABELS[platform]} 未找到現成賽果，而且未提供 results URL。")

    if platform == "au":
        run_logged_command(
            [
                sys.executable,
                str(AU_RESULTS_EXTRACTOR),
                "--url",
                results_url,
                "--output_dir",
                str(meeting_dir),
                "--json",
            ],
            "Extract AU Results",
        )
    else:
        race_date, venue = infer_hkjc_date_and_venue(meeting_dir, results_url)
        output_json = meeting_dir / f"{race_date}_{venue}_全日賽果.json"
        run_logged_command(
            [
                sys.executable,
                str(HKJC_RESULTS_EXTRACTOR),
                race_date,
                str(output_json),
                venue,
            ],
            "Extract HKJC Results",
        )
        sync_meeting_results = _import_hkjc_sync()
        copies = sync_meeting_results(meeting_dir)
        print(f"✅ HKJC results sync completed: {len(copies)} file copies")

    extracted = find_existing_results_file(platform, meeting_dir)
    if not extracted:
        raise SystemExit(f"❌ {DOMAIN_LABELS[platform]} 賽果擷取完成後仍然找不到輸出檔。")
    return extracted.resolve()


def load_structured_results(platform: str, results_file: Path) -> dict[int, dict[str, Any]]:
    if results_file.suffix.lower() == ".json":
        data = json.loads(results_file.read_text(encoding="utf-8"))
        if platform == "au":
            results: dict[int, dict[str, Any]] = {}
            event_meta = data.get("events") or {}
            event_results = data.get("results") or {}
            for race_key, rows in event_results.items():
                try:
                    race_num = int(race_key)
                except (TypeError, ValueError):
                    continue
                normalized = []
                for row in rows:
                    placing = int(row.get("finish_position") or 99)
                    if placing <= 0 or row.get("is_scratched"):
                        continue
                    normalized.append(
                        {
                            "placing": placing,
                            "horse_no": int(row.get("competitor_number") or 0),
                            "horse_name": str(row.get("horse_name") or "").strip(),
                            "margin": row.get("margin"),
                            "odds": row.get("starting_price"),
                            "race_time": row.get("finish_time"),
                            "comments": str(row.get("comments") or "").strip(),
                            "running_positions": row.get("position_summaries") or [],
                        }
                    )
                normalized.sort(key=lambda item: item["placing"])
                results[race_num] = {
                    "meta": event_meta.get(str(race_num), {}),
                    "incident_report": "",
                    "results": normalized,
                }
            return results

        results = {}
        for race_key, race_data in data.items():
            try:
                race_num = int(race_key)
            except (TypeError, ValueError):
                continue
            rows = []
            for row in race_data.get("results", []):
                try:
                    placing = int(str(row.get("pos", "99")).replace("DH", "").strip() or 99)
                    horse_no = int(row.get("horse_no") or 0)
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "placing": placing,
                        "horse_no": horse_no,
                        "horse_name": str(row.get("horse_name") or "").strip(),
                        "margin": row.get("lbw"),
                        "odds": row.get("win_odds"),
                        "race_time": row.get("finish_time"),
                        "comments": "",
                        "running_positions": str(row.get("running_positions") or "").strip(),
                    }
                )
            rows.sort(key=lambda item: item["placing"])
            results[race_num] = {
                "meta": {
                    "venue": race_data.get("venue"),
                    "sectional_times": race_data.get("sectional_times") or [],
                    "cumulative_times": race_data.get("cumulative_times") or [],
                },
                "incident_report": str(race_data.get("incident_report") or "").strip(),
                "results": rows,
            }
        return results

    results: dict[int, dict[str, Any]] = {}
    current_race: int | None = None
    header_re = re.compile(r"^##\s*(?:Race\s*|第)(\d+)", re.IGNORECASE)
    for raw_line in results_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        match = header_re.match(line)
        if match:
            current_race = int(match.group(1))
            results[current_race] = {"meta": {}, "incident_report": "", "results": []}
            continue
        if current_race is None:
            continue
        result_match = re.match(
            r"(?:(\d+)(?:st|nd|rd|th)|第(\d+)名)[：:.\s]+#?(\d+)\s+(.+?)(?:\s+\(([^)]+)\))?(?:\s+SP\$?([\d.]+))?$",
            line,
            re.IGNORECASE,
        )
        if not result_match:
            continue
        placing = int(result_match.group(1) or result_match.group(2))
        results[current_race]["results"].append(
            {
                "placing": placing,
                "horse_no": int(result_match.group(3)),
                "horse_name": result_match.group(4).strip(),
                "margin": result_match.group(5),
                "odds": result_match.group(6),
                "race_time": "",
                "comments": "",
                "running_positions": [],
            }
        )
    return results


def _to_float(value: Any) -> float | None:
    if value in (None, "", "nan"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_prediction_rows(meeting_dir: Path, platform: str) -> dict[int, list[dict[str, Any]]]:
    meeting_csv = {
        "au": meeting_dir / "Meeting_Auto_Scoring.csv",
        "hkjc": meeting_dir / "HKJC_Auto_Scoring.csv",
    }[platform]
    csv_paths = [meeting_csv] if meeting_csv.exists() else sorted(meeting_dir.glob("Race_*_Auto_Scoring.csv"))
    by_race: dict[int, list[dict[str, Any]]] = defaultdict(list)
    score_key = "ability_score"

    for csv_path in csv_paths:
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    race_num = int(float(row.get("race_number") or 0))
                    horse_no = int(float(row.get("horse_number") or 0))
                except (TypeError, ValueError):
                    continue
                composite_score = _to_float(row.get(score_key))
                if composite_score is None:
                    composite_score = _to_float(row.get("ability_score")) or _to_float(row.get("rank_score")) or 0.0
                factor_scores = {
                    key: _to_float(value)
                    for key, value in row.items()
                    if key.endswith("_score") and key not in {"ability_score", "rank_score"}
                }
                by_race[race_num].append(
                    {
                        "race_num": race_num,
                        "horse_no": horse_no,
                        "horse_name": str(row.get("horse_name") or "").strip(),
                        "rank": int(float(row.get("rank") or 999)),
                        "grade": str(row.get("grade") or "").strip(),
                        "model_pick_status": str(row.get("model_pick_status") or "").strip(),
                        "composite_score": composite_score,
                        "ability_score": _to_float(row.get("ability_score")),
                        "rank_score": _to_float(row.get("rank_score")),
                        "factor_scores": factor_scores,
                    }
                )

    for race_num, rows in by_race.items():
        rows.sort(key=lambda item: (-float(item["composite_score"] or 0.0), item["rank"], item["horse_no"]))
        for idx, row in enumerate(rows, start=1):
            row["derived_rank"] = idx
    return dict(by_race)


def performance_label_from_rows(model_top3: list[dict[str, Any]], actual_top3: list[dict[str, Any]]) -> str:
    # Delegates to the canonical shared ruler so reflector labels can never
    # drift from backtest/calibration labels.
    _add_sys_path(SHARED_ROOT.parents[1])
    from eval_metrics import exclusive_label

    actual_set = {row["horse_no"] for row in actual_top3}
    pick_nums = [row["horse_no"] for row in model_top3[:3]]
    top3_hits = sum(1 for horse_no in pick_nums if horse_no in actual_set)
    top2_hits = sum(1 for horse_no in pick_nums[:2] if horse_no in actual_set)
    return exclusive_label(top3_hits, top2_hits)


def label_rank(label: str) -> int:
    order = {"Miss": 0, "1 Hit": 1, "Pass": 2, "Good": 3, "Gold": 4}
    return order.get(label, 0)


def summarize_factors(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    factors = [(name, score) for name, score in row.get("factor_scores", {}).items() if score is not None]
    if not factors:
        return [], []
    factors.sort(key=lambda item: item[1], reverse=True)
    strengths = [SCORE_LABELS.get(name, name) for name, _score in factors[:3]]
    weaknesses = [SCORE_LABELS.get(name, name) for name, _score in sorted(factors, key=lambda item: item[1])[:3]]
    return strengths, weaknesses


def derive_improvement_theme(row: dict[str, Any]) -> tuple[str, str]:
    factors = row.get("factor_scores", {})
    ranked = sorted(
        ((name, score) for name, score in factors.items() if score is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    keys = [name for name, _score in ranked[:4]]
    if any(name in keys for name in ("class_score", "distance_score", "weight_score", "formline_score")):
        return "class_distance", "加強班次 / 路程 / form line interpretation"
    if any(name in keys for name in ("draw_score", "pace_map_score", "track_score", "track_going_score")):
        return "draw_pace", "細化檔位 / 步速 / 場地偏差 context"
    if any(name in keys for name in ("trainer_score", "jockey_score", "jockey_horse_fit_score")):
        return "jockey_trainer", "加強騎師 / 練馬師 / 人馬配搭權重"
    if any(name in keys for name in ("sectional_score", "speed_score", "trial_score", "speed_rating_score")):
        return "sectional", "加強段速 / 試閘 / 速度訊號"
    if any(name in keys for name in ("consistency_score", "form_score", "health_score", "risk_score")):
        return "stability", "改善近況 / 穩定性 / 風險寬恕"
    return "general", "微調綜合戰力分矩陣權重"


def extract_incident_signals(text: str) -> list[str]:
    lower = text.lower()
    hits = []
    for label, keywords in INCIDENT_KEYWORDS.items():
        if any(keyword.lower() in lower for keyword in keywords):
            hits.append(label)
    return hits


def incident_excerpt(text: str, horse_name: str) -> str:
    if not text:
        return ""
    match = re.search(re.escape(horse_name), text, re.IGNORECASE)
    if not match:
        return text[:180].strip()
    start = max(0, match.start() - 60)
    end = min(len(text), match.end() + 120)
    return text[start:end].strip()


def analyse_missed_horse(
    actual_row: dict[str, Any],
    prediction_rows: list[dict[str, Any]],
    incident_text: str,
) -> dict[str, Any]:
    prediction_map = {row["horse_no"]: row for row in prediction_rows}
    candidate = prediction_map.get(actual_row["horse_no"])
    if not candidate:
        return {
            "horse_no": actual_row["horse_no"],
            "horse_name": actual_row["horse_name"],
            "placing": actual_row["placing"],
            "verdict": "資料不足",
            "reason": "現有 scoring CSV 找不到此馬，代表 archive / analysis 輸出不完整。",
            "suggestion_theme": "general",
            "suggestion_text": "先補齊 scoring / archive artifacts，再評估是否屬模型問題。",
        }

    strengths, weaknesses = summarize_factors(candidate)
    theme, theme_text = derive_improvement_theme(candidate)
    third_score = prediction_rows[2]["composite_score"] if len(prediction_rows) >= 3 else None
    gap = None if third_score is None else round(float(third_score) - float(candidate["composite_score"] or 0.0), 3)
    incident = incident_excerpt(incident_text, actual_row["horse_name"])
    incident_signals = extract_incident_signals(incident)

    if incident_signals:
        verdict = "可寬恕 / 需保留"
        reason = f"官方 / 可用備註見到 {', '.join(incident_signals)} 訊號，呢類偏向賽事事故，未必應直接當成純模型失誤。"
    elif candidate["derived_rank"] <= 6 and (gap is None or gap <= 3.0):
        verdict = "模型有訊號但低估"
        reason = "其實模型已經將呢匹馬放喺前列邊緣，只係未能推入 Top 3，較似權重排序問題多過完全 miss。"
    else:
        verdict = "模型失誤"
        reason = "現有綜合戰力分未有足夠把呢匹馬推上前列，較似矩陣權重或 context factor 漏捉。"

    evidence = "有" if strengths else "有限"
    hidden_signals = " / ".join(strengths[:2]) if strengths else "未見明顯隱藏訊號"
    weakness_text = " / ".join(weaknesses[:2]) if weaknesses else "未見清晰短板"

    return {
        "horse_no": actual_row["horse_no"],
        "horse_name": actual_row["horse_name"],
        "placing": actual_row["placing"],
        "predicted_rank": candidate["derived_rank"],
        "grade": candidate["grade"],
        "composite_score": candidate["composite_score"],
        "gap_to_model_top3": gap,
        "verdict": verdict,
        "reason": reason,
        "evidence_level": evidence,
        "hidden_signals": hidden_signals,
        "weaknesses": weakness_text,
        "suggestion_theme": theme,
        "suggestion_text": theme_text,
        "incident_excerpt": incident,
    }


def analyse_race_incidents(
    platform: str,
    model_top3: list[dict[str, Any]],
    actual_top3: list[dict[str, Any]],
    incident_text: str,
) -> dict[str, Any]:
    if not incident_text:
        if platform == "au":
            return {
                "classification": "資料不足",
                "summary": "AU source 未抽到官方 stewards / incident note，今場只可用賽果同原分析檔覆盤。",
                "signals": [],
            }
        return {
            "classification": "無明顯事故",
            "summary": "今場未見可用 競賽事件報告內容。",
            "signals": [],
        }

    relevant_names = [row["horse_name"] for row in model_top3 + actual_top3]
    matched_excerpts = [incident_excerpt(incident_text, name) for name in relevant_names if name and name in incident_text]
    signal_counter = Counter(extract_incident_signals(" ".join(matched_excerpts) or incident_text))
    if not signal_counter:
        return {
            "classification": "無明顯事故",
            "summary": "有 incident text，但未見明確干擾 / 慢閘 / 外疊 / 獸醫等可直接歸因訊號。",
            "signals": [],
            "excerpt": matched_excerpts[:2],
        }

    top_signal = signal_counter.most_common(1)[0][0]
    mapping = {
        "interference": "可寬恕事故",
        "slow_start": "起步問題",
        "wide_run": "走位 / 位置消耗",
        "vet_issue": "健康 / 獸醫風險",
        "ride_issue": "部署 / 騎乘因素",
    }
    return {
        "classification": mapping.get(top_signal, "可寬恕事故"),
        "summary": f"可用 incident notes 指向 {top_signal}，今場部份失手可視為具備寬恕基礎。",
        "signals": list(signal_counter.elements()),
        "excerpt": matched_excerpts[:2],
    }


def build_race_performances(
    platform: str,
    meeting_stats: dict[str, Any],
    structured_results: dict[int, dict[str, Any]],
    prediction_rows: dict[int, list[dict[str, Any]]],
    target_races: set[int] | None = None,
) -> list[RacePerformance]:
    performances = []
    for race in meeting_stats.get("races", []):
        race_num = int(race["race_num"])
        if target_races and race_num not in target_races:
            continue

        actual_rows = structured_results.get(race_num, {}).get("results", [])
        actual_top3 = actual_rows[:3]
        prediction_list = prediction_rows.get(race_num, [])
        prediction_map = {row["horse_no"]: row for row in prediction_list}
        if actual_rows and prediction_list:
            final_starters = {row["horse_no"] for row in actual_rows}
            prediction_list = [
                dict(row)
                for row in prediction_list
                if row["horse_no"] in final_starters
            ]
            for idx, row in enumerate(prediction_list, start=1):
                row["derived_rank"] = idx
            prediction_map = {row["horse_no"]: row for row in prediction_list}
        model_top5 = [
            {
                "rank": row.get("derived_rank") or row.get("rank"),
                "horse_no": row["horse_no"],
                "horse_name": row["horse_name"],
                "grade": row.get("grade", ""),
                "composite_score": row.get("composite_score"),
            }
            for row in prediction_list[:5]
        ]
        model_top3 = []
        if prediction_list:
            model_top3 = [
                {
                    "rank": row.get("derived_rank") or row.get("rank"),
                    "horse_no": row["horse_no"],
                    "horse_name": row["horse_name"],
                    "grade": row.get("grade", ""),
                    "composite_score": row.get("composite_score"),
                }
                for row in prediction_list[:3]
            ]
        else:
            for rank, horse_no, horse_name in race.get("top_picks", [])[:3]:
                row = prediction_map.get(horse_no, {})
                model_top3.append(
                    {
                        "rank": rank,
                        "horse_no": horse_no,
                        "horse_name": horse_name,
                        "grade": row.get("grade", ""),
                        "composite_score": row.get("composite_score"),
                    }
                )
        actual_top3_view = [
            {
                "placing": row["placing"],
                "horse_no": row["horse_no"],
                "horse_name": row["horse_name"],
                "margin": row.get("margin"),
                "odds": row.get("odds"),
            }
            for row in actual_top3
        ]
        top5_nums = {row["horse_no"] for row in model_top5}
        top5_actual_top3_covered = [
            row for row in actual_top3_view if row["horse_no"] in top5_nums
        ]
        top5_actual_top3_missed = [
            row for row in actual_top3_view if row["horse_no"] not in top5_nums
        ]

        label = performance_label_from_rows(model_top3, actual_top3_view)
        incident_text = structured_results.get(race_num, {}).get("incident_report", "")
        incident_analysis = analyse_race_incidents(platform, model_top3, actual_top3_view, incident_text)
        missed_horses = [
            analyse_missed_horse(row, prediction_list, incident_text)
            for row in actual_top3
            if row["horse_no"] not in {pick["horse_no"] for pick in model_top3}
        ]
        performances.append(
            RacePerformance(
                race_num=race_num,
                label=label,
                model_top3=model_top3,
                model_top5=model_top5,
                actual_top3=actual_top3_view,
                actual_rows=actual_rows,
                prediction_rows=prediction_list,
                top5_actual_top3_hits=len(top5_actual_top3_covered),
                top5_actual_top3_covered=top5_actual_top3_covered,
                top5_actual_top3_missed=top5_actual_top3_missed,
                winner_in_model_top5=bool(actual_top3_view and actual_top3_view[0]["horse_no"] in top5_nums),
                missed_actual_top3=missed_horses,
                incident_analysis=incident_analysis,
            )
        )
    return performances


def summarize_label_distribution(races: list[RacePerformance]) -> dict[str, int]:
    counts = Counter(race.label for race in races)
    return {label: counts.get(label, 0) for label in ("Gold", "Good", "Pass", "1 Hit", "Miss")}


def summarize_shortlist_metrics(races: list[RacePerformance]) -> dict[str, Any]:
    total = len(races)
    if not total:
        return {
            "races": 0,
            "top5_3plus": 0,
            "top5_2plus": 0,
            "winner_in_top5": 0,
            "avg_actual_top3_in_top5": 0.0,
            "top5_3plus_rate": 0.0,
            "top5_2plus_rate": 0.0,
            "winner_in_top5_rate": 0.0,
        }

    top5_3plus = sum(1 for race in races if race.top5_actual_top3_hits >= 3)
    top5_2plus = sum(1 for race in races if race.top5_actual_top3_hits >= 2)
    winner_in_top5 = sum(1 for race in races if race.winner_in_model_top5)
    avg_hits = sum(race.top5_actual_top3_hits for race in races) / total
    return {
        "races": total,
        "top5_3plus": top5_3plus,
        "top5_2plus": top5_2plus,
        "winner_in_top5": winner_in_top5,
        "avg_actual_top3_in_top5": round(avg_hits, 3),
        "top5_3plus_rate": round(top5_3plus / total * 100, 1),
        "top5_2plus_rate": round(top5_2plus / total * 100, 1),
        "winner_in_top5_rate": round(winner_in_top5 / total * 100, 1),
    }


def normalize_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    if "Champion" in raw:
        return {
            "meetings": raw.get("meetings", 0),
            "races": raw.get("races", 0),
            "champion": raw.get("Champion", 0),
            "gold": raw.get("Gold", 0),
            "good": raw.get("Good", 0),
            "pass": raw.get("Minimum", 0),
            "order_issue": raw.get("Order Issue", 0),
            "mrr": raw.get("MRR", 0.0),
            "avg_top4_hits": raw.get("Avg Top4 Hits", 0.0),
        }
    return {
        "meetings": raw.get("meetings", 0),
        "races": raw.get("races", 0),
        "champion": raw.get("champion", 0),
        "gold": raw.get("gold", 0),
        "good": raw.get("good", 0),
        "pass": raw.get("min_threshold", 0),
        "order_issue": raw.get("order_issue", 0),
        "mrr": raw.get("mrr", 0.0),
        "avg_top4_hits": raw.get("avg_top4_hits", 0.0),
    }


def diff_metrics(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(float(candidate.get(key, 0)) - float(baseline.get(key, 0)), 4)
        for key in ("champion", "gold", "good", "pass", "order_issue", "mrr", "avg_top4_hits")
    }


def extract_au_race_labels(details: list[dict[str, Any]]) -> dict[str, str]:
    labels = {}
    for meeting in details:
        meeting_name = meeting.get("meeting", "")
        for race in meeting.get("races_detail", []):
            key = f"{meeting_name} / R{race.get('race_num')}"
            label = performance_label_from_rows(
                [{"horse_no": pick[1]} for pick in race.get("top_picks", [])[:3]],
                [{"horse_no": row[1]} for row in race.get("actual_top3", [])[:3]],
            )
            labels[key] = label
    return labels


def extract_hkjc_race_labels(race_records: list[dict[str, Any]], model_name: str) -> dict[str, str]:
    labels = {}
    for record in race_records:
        model = (record.get("models") or {}).get(model_name)
        if not model:
            continue
        top3 = [{"horse_no": horse_no} for horse_no in model.get("picks", [])[:3]]
        actual_top3 = [{"horse_no": horse_no} for horse_no, _pos in sorted((record.get("actual_pos") or {}).items(), key=lambda item: item[1])[:3]]
        label = performance_label_from_rows(top3, actual_top3)
        labels[f"{Path(record.get('meeting', '')).name} / R{record.get('race')}"] = label
    return labels


def compare_label_maps(baseline: dict[str, str], candidate: dict[str, str]) -> tuple[list[str], list[str]]:
    helped = []
    worsened = []
    for key, baseline_label in baseline.items():
        candidate_label = candidate.get(key)
        if candidate_label is None:
            continue
        delta = label_rank(candidate_label) - label_rank(baseline_label)
        if delta > 0:
            helped.append(key)
        elif delta < 0:
            worsened.append(key)
    return helped[:3], worsened[:3]


def pick_best_candidate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            item["delta"]["pass"],
            item["delta"]["good"],
            item["delta"]["champion"],
            -item["delta"]["order_issue"],
            item["delta"]["mrr"],
            item["delta"]["avg_top4_hits"],
        ),
        reverse=True,
    )


def meaningful_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["helped_examples"]
        or any(float(row["delta"].get(key, 0.0)) > 0 for key in ("champion", "gold", "good", "pass", "mrr", "avg_top4_hits"))
        or float(row["delta"].get("order_issue", 0.0)) < 0
    ]


def run_au_backtests(meeting_dir: Path) -> list[dict[str, Any]]:
    archive_root = DOMAIN_ARCHIVES["au"]
    overall_started = time.perf_counter()
    print(f"🔍 AU backtests: scanning archive candidates for {meeting_dir.name}", flush=True)
    baseline_run_review = _import_au_review()
    baseline_started = time.perf_counter()
    baseline_report = baseline_run_review(archive_root, mode="recomputed")
    baseline = normalize_metrics(baseline_report["current_live"])
    baseline_labels = extract_au_race_labels(baseline_report["details"])
    print(
        "✅ AU backtests: recomputed baseline ready "
        f"({baseline['races']} races, {time.perf_counter() - baseline_started:.2f}s)",
        flush=True,
    )

    suggestions = []
    class_variants, class_runner = _import_au_class_shadow()
    for variant_name in ("class_venue_weight_soft",):
        stage_started = time.perf_counter()
        print(f"🔍 AU backtests: running {variant_name}", flush=True)
        result = class_runner(archive_root, variant_name, class_variants[variant_name])
        metrics = normalize_metrics(result["current_live"])
        delta = diff_metrics(metrics, baseline)
        candidate_labels = extract_au_race_labels(result["details"])
        helped, worsened = compare_label_maps(baseline_labels, candidate_labels)
        print(f"✅ AU backtests: {variant_name} finished ({time.perf_counter() - stage_started:.2f}s)", flush=True)
        suggestions.append(
            {
                "name": result["variant"],
                "description": SUGGESTION_DESCRIPTIONS.get(result["variant"], result["variant"]),
                "metrics": metrics,
                "delta": delta,
                "helped_examples": helped,
                "worsened_examples": worsened,
                "source": "au_class_normalization_shadow_test",
            }
        )

    bundle_variants, bundle_runner = _import_au_shadow_bundle()
    stage_started = time.perf_counter()
    print("🔍 AU backtests: running bundle_recommended", flush=True)
    result = bundle_runner(archive_root, "bundle_recommended", bundle_variants["bundle_recommended"])
    metrics = normalize_metrics(result["current_live"])
    delta = diff_metrics(metrics, baseline)
    candidate_labels = extract_au_race_labels(result["details"])
    helped, worsened = compare_label_maps(baseline_labels, candidate_labels)
    print(f"✅ AU backtests: bundle_recommended finished ({time.perf_counter() - stage_started:.2f}s)", flush=True)
    suggestions.append(
        {
            "name": result["variant"],
            "description": SUGGESTION_DESCRIPTIONS.get(result["variant"], result["variant"]),
            "metrics": metrics,
            "delta": delta,
            "helped_examples": helped,
            "worsened_examples": worsened,
            "source": "au_shadow_bundle_benchmark",
        }
    )

    print(f"✅ AU backtests complete ({time.perf_counter() - overall_started:.2f}s)", flush=True)
    return pick_best_candidate(meaningful_candidates(suggestions))[:3]


def run_hkjc_backtests(meeting_dir: Path) -> list[dict[str, Any]]:
    hkjc = _import_hkjc_review()
    review = hkjc["run_review"](
        [hkjc["get_analysis_archive_root"]()],
        hkjc["get_season_results_roots"](),
        hkjc["get_season_csvs"](),
        include_races=True,
    )
    race_records = review.get("race_records") or []
    model_roles = review.get("model_roles") or {}
    model_summary = review.get("model_summary") or {}
    meeting_name = meeting_dir.name
    meeting_summary = (review.get("meeting_summary") or {}).get(meeting_name) or {}
    meeting_models = meeting_summary.get("models") or {}
    baseline_name = "published_mainline" if meeting_models.get("published_mainline") and model_summary.get("published_mainline") else "current_live"
    baseline_metrics = normalize_metrics(model_summary.get(baseline_name) or {})
    baseline_labels = extract_hkjc_race_labels(race_records, baseline_name)

    suggestions = []
    for model_name, metrics_raw in model_summary.items():
        if model_name in {"current_live", "published_mainline", "previous_calibrated"}:
            continue
        if model_roles.get(model_name) != "experimental":
            continue
        metrics = normalize_metrics(metrics_raw)
        delta = diff_metrics(metrics, baseline_metrics)
        candidate_labels = extract_hkjc_race_labels(race_records, model_name)
        helped, worsened = compare_label_maps(baseline_labels, candidate_labels)
        meeting_delta = {}
        if meeting_models.get(model_name):
            meeting_metrics = normalize_metrics(meeting_models[model_name])
            baseline_meeting_metrics = normalize_metrics(meeting_models.get(baseline_name) or {})
            meeting_delta = diff_metrics(meeting_metrics, baseline_meeting_metrics)
        suggestions.append(
            {
                "name": model_name,
                "description": SUGGESTION_DESCRIPTIONS.get(model_name, model_name),
                "metrics": metrics,
                "delta": delta,
                "meeting_delta": meeting_delta,
                "helped_examples": helped,
                "worsened_examples": worsened,
                "source": "review_auto_weighting",
            }
        )

    return pick_best_candidate(meaningful_candidates(suggestions))[:3]


def summarize_meeting_strengths(races: list[RacePerformance]) -> list[str]:
    if not races:
        return ["未有可反映場次。"]
    counts = summarize_label_distribution(races)
    shortlist = summarize_shortlist_metrics(races)
    strengths = []
    if counts["Gold"] or counts["Good"]:
        strengths.append(f"前列排序有一定命中力，Gold/Good 合共有 {counts['Gold'] + counts['Good']} 場。")
    if counts["Pass"]:
        strengths.append(f"至少 2/3 Top picks 入實際前三的場次有 {counts['Pass']} 場。")
    if shortlist["top5_2plus"]:
        strengths.append(
            f"Top 5 shortlist 有 {shortlist['top5_2plus']}/{shortlist['races']} 場包到至少兩匹實際前三，"
            f"平均每場包 {shortlist['avg_actual_top3_in_top5']} 匹。"
        )
    if not strengths:
        strengths.append("今次 meeting 幾乎冇明顯命中優勢，強項主要只剩個別單場細節。")
    return strengths


def summarize_meeting_failures(races: list[RacePerformance]) -> list[str]:
    misses = [race for race in races if race.label == "Miss"]
    one_hits = [race for race in races if race.label == "1 Hit"]
    lines = []
    if misses:
        lines.append(f"完全 Miss 場次有 {len(misses)} 場，代表綜合戰力分前列排序仍有結構性落差。")
    if one_hits:
        lines.append(f"只有 1 Hit 的場次有 {len(one_hits)} 場，通常屬排序未夠準而唔係完全冇訊號。")
    if not lines:
        lines.append("今次未見大規模崩盤，主要係零碎排序微誤差。")
    return lines


def render_markdown_report(
    platform: str,
    meeting_dir: Path,
    results_file: Path,
    race_performances: list[RacePerformance],
    backtests: list[dict[str, Any]],
) -> str:
    distribution = summarize_label_distribution(race_performances)
    shortlist = summarize_shortlist_metrics(race_performances)
    reflected_races = ", ".join(str(race.race_num) for race in race_performances) or "N/A"
    lines = [
        f"# Unified {DOMAIN_LABELS[platform]} Race Reflector Report",
        "",
        "## Workflow Summary",
        f"- Domain: `{DOMAIN_LABELS[platform]}`",
        f"- Meeting: `{meeting_dir.name}`",
        f"- Reflected races: `{reflected_races}`",
        f"- Results file: `{results_file.name}`",
        f"- Approval gate: **任何 improvement suggestion 只供審批，不會自動改 code / matrix。**",
        "",
        "## Meeting Performance Summary",
        f"- Gold: {distribution['Gold']}",
        f"- Good: {distribution['Good']}",
        f"- Pass: {distribution['Pass']}",
        f"- 1 Hit: {distribution['1 Hit']}",
        f"- Miss: {distribution['Miss']}",
        f"- Top 5 包齊實際前三: {shortlist['top5_3plus']}/{shortlist['races']} ({shortlist['top5_3plus_rate']}%)",
        f"- Top 5 包至少兩匹實際前三: {shortlist['top5_2plus']}/{shortlist['races']} ({shortlist['top5_2plus_rate']}%)",
        f"- 冠軍在模型 Top 5: {shortlist['winner_in_top5']}/{shortlist['races']} ({shortlist['winner_in_top5_rate']}%)",
        f"- 平均每場 Top 5 包實際前三匹數: {shortlist['avg_actual_top3_in_top5']}",
        "",
        "## What The Model Did Well",
    ]
    lines.extend(f"- {item}" for item in summarize_meeting_strengths(race_performances))
    lines.extend(["", "## What The Model Missed"])
    lines.extend(f"- {item}" for item in summarize_meeting_failures(race_performances))

    for race in race_performances:
        model_top3_text = ", ".join(
            f"#{row['horse_no']} {row['horse_name']}" for row in race.model_top3
        ) or "N/A"
        model_top5_text = ", ".join(
            f"#{row['horse_no']} {row['horse_name']}" for row in race.model_top5
        ) or "N/A"
        actual_top3_text = ", ".join(
            f"{row['placing']}. #{row['horse_no']} {row['horse_name']}" for row in race.actual_top3
        ) or "N/A"
        lines.extend(
            [
                "",
                f"## Race {race.race_num}",
                f"- Performance label: **{race.label}**",
                f"- Model Top 3: {model_top3_text}",
                f"- Model Top 5 shortlist: {model_top5_text}",
                f"- Actual Top 3: {actual_top3_text}",
                f"- Top 5 shortlist coverage: {race.top5_actual_top3_hits}/3 actual Top 3; winner in Top 5: {'Yes' if race.winner_in_model_top5 else 'No'}",
                f"- Incident / forgiveness: **{race.incident_analysis.get('classification', 'N/A')}** — {race.incident_analysis.get('summary', 'N/A')}",
            ]
        )
        if race.top5_actual_top3_missed:
            missed_top5_text = ", ".join(
                f"#{row['horse_no']} {row['horse_name']}" for row in race.top5_actual_top3_missed
            )
            lines.append(f"- Actual Top 3 outside model Top 5: {missed_top5_text}")
        if race.incident_analysis.get("excerpt"):
            for excerpt in race.incident_analysis["excerpt"]:
                lines.append(f"- Incident excerpt: {excerpt}")
        if not race.missed_actual_top3:
            lines.append("- Missed Top 3 horses: 無。模型 Top 3 已全中實際前三。")
        else:
            lines.append("- Missed Top 3 horses:")
            for missed in race.missed_actual_top3:
                lines.append(
                    f"  - #{missed['horse_no']} {missed['horse_name']}: {missed['verdict']}。"
                    f" 原模型排第 {missed.get('predicted_rank', 'N/A')}，"
                    f" 隱藏訊號 `{missed.get('hidden_signals', 'N/A')}`，"
                    f" 短板 `{missed.get('weaknesses', 'N/A')}`。"
                )
                lines.append(f"  - 原因: {missed['reason']}")
                lines.append(f"  - 是否有足夠歷史證據: {missed.get('evidence_level', '有限')}")
                lines.append(f"  - 建議測試方向: {missed.get('suggestion_text', 'N/A')}")
                if missed.get("incident_excerpt"):
                    lines.append(f"  - Incident / notes excerpt: {missed['incident_excerpt']}")
        race_clean_fail = race.incident_analysis.get("classification") in {"無明顯事故", "資料不足"}
        lines.append(
            f"- Race verdict: {'偏向 clean model failure' if race_clean_fail and race.label in {'Miss', '1 Hit'} else '帶有可寬恕元素或非純模型錯誤'}"
        )

    lines.extend(["", "## Backtested Improvement Suggestions"])
    if not backtests:
        lines.append("- 今次未有可用 backtest candidate。")
    else:
        for candidate in backtests:
            metrics = candidate["metrics"]
            delta = candidate["delta"]
            meeting_delta = candidate.get("meeting_delta") or {}
            consistency = "較一致" if len(candidate["helped_examples"]) >= len(candidate["worsened_examples"]) else "有 overfit 風險"
            lines.append(f"- **{candidate['name']}**: {candidate['description']}")
            lines.append(
                f"  - 全庫: Champion {metrics['champion']} ({delta['champion']:+.0f}), Gold {metrics['gold']} ({delta['gold']:+.0f}), "
                f"Good {metrics['good']} ({delta['good']:+.0f}), Pass {metrics['pass']} ({delta['pass']:+.0f}), "
                f"Order Issue {metrics['order_issue']} ({delta['order_issue']:+.0f}), MRR {metrics['mrr']:.4f} ({delta['mrr']:+.4f})"
            )
            if meeting_delta:
                lines.append(
                    f"  - 今場 / meeting replay: Champion {meeting_delta.get('champion', 0):+.0f}, Good {meeting_delta.get('good', 0):+.0f}, "
                    f"Pass {meeting_delta.get('pass', 0):+.0f}, Order Issue {meeting_delta.get('order_issue', 0):+.0f}, "
                    f"MRR {meeting_delta.get('mrr', 0):+.4f}"
                )
            lines.append(f"  - Consistency: {consistency}")
            lines.append(
                f"  - Helped examples: {', '.join(candidate['helped_examples']) if candidate['helped_examples'] else '未見明顯改善例子'}"
            )
            lines.append(
                f"  - Worse examples: {', '.join(candidate['worsened_examples']) if candidate['worsened_examples'] else '未見明顯轉差例子'}"
            )
            lines.append("  - Status: **只供審批，未實裝。**")

    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "- 先審核今份反射報告與 backtest evidence。",
            "- 如你批准某個 suggestion，我哋先會再做 code / matrix 更新。",
            "- 無批准之前，最終排名仍以現行 `綜合戰力分` 排序結果為準，唔會有任何 override。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_json_summary(
    platform: str,
    meeting_dir: Path,
    results_file: Path,
    races: list[RacePerformance],
    backtests: list[dict[str, Any]],
    report_path: Path,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "meeting_dir": str(meeting_dir),
        "results_file": str(results_file),
        "report_path": str(report_path),
        "meeting_summary": summarize_label_distribution(races),
        "shortlist_summary": summarize_shortlist_metrics(races),
        "races": [
            {
                "race_num": race.race_num,
                "label": race.label,
                "model_top3": race.model_top3,
                "model_top5": race.model_top5,
                "actual_top3": race.actual_top3,
                "top5_actual_top3_hits": race.top5_actual_top3_hits,
                "top5_actual_top3_covered": race.top5_actual_top3_covered,
                "top5_actual_top3_missed": race.top5_actual_top3_missed,
                "winner_in_model_top5": race.winner_in_model_top5,
                "missed_actual_top3": race.missed_actual_top3,
                "incident_analysis": race.incident_analysis,
            }
            for race in races
        ],
        "backtests": backtests,
    }


def run_unified_reflector(
    platform: str,
    meeting_ref: str | None = None,
    meeting_dir: str | Path | None = None,
    results_file: str | Path | None = None,
    results_url: str | None = None,
    target_races: list[int] | None = None,
    report_path: str | Path | None = None,
    force_extract: bool = False,
    skip_backtest: bool = False,
) -> dict[str, Any]:
    if platform not in {"au", "hkjc"}:
        raise SystemExit("❌ platform 必須係 `au` 或 `hkjc`。")

    resolved_meeting_dir = resolve_meeting_dir(platform, meeting_ref=meeting_ref, meeting_dir=meeting_dir)
    resolved_results_file = Path(results_file).resolve() if results_file else ensure_results_file(
        platform,
        resolved_meeting_dir,
        results_url,
        force_extract=force_extract,
    )

    print(f"✅ Using meeting dir: {resolved_meeting_dir}")
    print(f"✅ Using results file: {resolved_results_file}")

    run_stats = _import_reflector_auto_stats()
    meeting_stats = run_stats(str(resolved_meeting_dir), str(resolved_results_file))
    if meeting_stats.get("error"):
        raise SystemExit(f"❌ reflector_auto_stats 失敗: {meeting_stats['error']}")

    structured_results = load_structured_results(platform, resolved_results_file)
    prediction_rows = load_prediction_rows(resolved_meeting_dir, platform)
    race_filter = set(target_races) if target_races else None
    races = build_race_performances(
        platform,
        meeting_stats,
        structured_results,
        prediction_rows,
        target_races=race_filter,
    )
    backtests = [] if skip_backtest else (run_au_backtests(resolved_meeting_dir) if platform == "au" else run_hkjc_backtests(resolved_meeting_dir))

    final_report_path = Path(report_path).resolve() if report_path else default_report_path(platform, resolved_meeting_dir)
    final_report_path.parent.mkdir(parents=True, exist_ok=True)
    final_report_path.write_text(
        render_markdown_report(platform, resolved_meeting_dir, resolved_results_file, races, backtests),
        encoding="utf-8",
    )
    print(f"✅ Unified reflector report written: {final_report_path}")

    return build_json_summary(
        platform,
        resolved_meeting_dir,
        resolved_results_file,
        races,
        backtests,
        final_report_path,
    )
