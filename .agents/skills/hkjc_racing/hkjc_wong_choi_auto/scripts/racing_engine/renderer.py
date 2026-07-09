from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from pathlib import Path

from scoring import clip_score

ABILITY_LABEL = "綜合戰力分"

FEATURE_LABELS = {
    "form_score": "近績分",
    "speed_score": "速度分",
    "class_score": "班次分",
    "jockey_score": "騎師分",
    "trainer_score": "練馬師分",
    "draw_score": "檔位分",
    "distance_score": "路程分",
    "track_going_score": "場地分",
    "weight_score": "負磅分",
    "consistency_score": "穩定性分",
    "risk_score": "風險分",
    "confidence_score": "信心分",
}

# 次序＝報告顯示次序（用戶要求：騎練訊號緊跟狀態與穩定性）
MATRIX_LABELS = {
    "stability": "狀態與穩定性",
    "trainer_signal": "騎練訊號",
    "sectional": "段速",
    "race_shape": "檔位與走位（不含步速）",
    "horse_health": "馬匹健康 / 新鮮感",
    "form_line": "賽績線",
    "class_advantage": "級數優勢",
}

MATRIX_ROLES = {
    "stability": "半核心",
    "sectional": "核心",
    "race_shape": "半核心",
    "trainer_signal": "核心",
    "horse_health": "輔助",
    "form_line": "輔助",
    "class_advantage": "輔助",
}


BAND_LABELS = {
    "✅✅": "極強",
    "✅": "正面",
    "➖": "中性",
    "❌": "偏弱",
    "❌❌": "極弱",
}

PICK_LABELS = {
    "MODEL_TOP_PICK": "模型首選",
    "WATCH": "觀望",
    "NO_PICK": "不選",
}

SHADOW_FLAG_LABELS = {
    "HV_MID_LAST_START_WINNER": "跑馬地中距離上仗交代型",
    "HV_MID_TRACKWORK_REBOUND": "跑馬地中距離備戰回勇型",
}

REPORT_BANS = (
    "tick_count",
    "矩陣算術",
    "步速修正偏差",
    "走位-段速複合",
    "MODEL_TOP_PICK",
    "WATCH",
    "NO_PICK",
    "ability_score",
    "confidence_score",
    "risk_score",
    "odds",
    "賠率",
    "value",
    "值博率",
    "edge",
    "[FILL",
)


def ensure_verdict(logic_data: dict) -> dict:
    horses = logic_data.get("horses", {})
    race_context = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    ranked = sorted(
        [
            {
                "horse_number": str(num),
                "horse_name": horse.get("horse_name", ""),
                "ability_score": float(horse.get("python_auto", {}).get("ability_score", 0)),
                "grade": horse.get("python_auto", {}).get("grade", ""),
                "rank_score": float(horse.get("python_auto", {}).get("ability_score", 0)),
            }
            for num, horse in horses.items()
            if isinstance(horse.get("python_auto"), dict)
        ],
        key=lambda item: (-item["ability_score"], _horse_number_sort_key(item["horse_number"])),
    )
    # We no longer apply artificial tie-breakers or safety swaps.
    # The ML optimizer reached its 30.63% Good Rate peak by purely sorting the 綜合戰力分 (ability_score).
    # Any manual overrides here would corrupt the mathematically proven weights.
    for idx, item in enumerate(ranked, start=1):
        horse = horses[item["horse_number"]]
        auto = horse["python_auto"]
        auto["rank"] = idx
        auto["rank_score"] = round(float(item.get("rank_score", auto.get("ability_score", 0))), 4)
        auto["model_pick_status"] = _pick_status(idx, float(auto.get("ability_score", 0)), auto)
        auto["shadow_flags"] = _shadow_flag_candidates(horse, race_context, auto)
        item["rank"] = idx
        item["model_pick_status"] = auto["model_pick_status"]
        item["shadow_flags"] = [flag.get("label", "") for flag in auto.get("shadow_flags", []) if flag.get("label")]
    verdict = {
        "ranking": ranked,
        "top2": ranked[:2],
        "top4": ranked[:4],
        "model_top_picks": [item for item in ranked if item["model_pick_status"] == "MODEL_TOP_PICK"],
        "watch_list": [item for item in ranked if item["model_pick_status"] == "WATCH"],
        "shadow_watch": [item for item in ranked if item.get("shadow_flags")],
        "no_pick": [item for item in ranked if item["model_pick_status"] == "NO_PICK"],
    }
    logic_data["python_auto_verdict"] = verdict
    return verdict


def _draw_micro_bonus(horse: dict, race_context: dict, auto: dict) -> float:
    bonus = 0.0
    draw = horse.get("barrier") or horse.get("draw")
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return 0.0

    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    fit = str(data.get("draw_position_fit") or "")
    trend = str(data.get("position_pi") or "")
    verdict = str(data.get("draw_verdict") or "")

    if "✅匹配" in fit:
        bonus += 1.5
    elif "❌錯配" in fit:
        bonus -= 2.0
    elif "偏好走外但起步在內" in fit or "偏好走內但被迫走外" in fit:
        bonus -= 1.5
    elif "需主動切入內疊" in fit:
        bonus -= 1.0

    if "上升軌" in trend:
        bonus += 0.8
    elif "衰退中" in trend:
        bonus -= 0.8

    if "✅有利" in verdict:
        bonus += 0.7
    elif "❌不利" in verdict:
        bonus -= 0.7

    bonus += _horse_draw_history_adjustment(horse, draw_num) * 0.5

    venue = _normalize_venue(race_context.get("venue"))
    distance = _normalize_distance(race_context.get("distance"))
    if venue == "跑馬地" and distance == "1650":
        if draw_num in {1, 2, 3, 7, 8}:
            bonus += 0.5
        if draw_num in {11, 12}:
            bonus -= 0.5

    if clip_score(auto.get("feature_scores", {}).get("draw_score", 60.0)) <= 55.0:
        bonus *= 1.15
    return bonus


def _horse_draw_history_adjustment(horse: dict, draw_num: int) -> float:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    fit = str(data.get("draw_position_fit") or "")
    match = re.search(r"內檔\(1-4\)上名率(\d+)%.*?中檔\(5-8\)上名率(\d+)%.*?外檔\(9\+\)上名率(\d+)%", fit)
    if not match:
        return 0.0
    inner, middle, outer = (float(match.group(i)) for i in range(1, 4))
    if draw_num <= 4:
        current = inner
        best_other = max(middle, outer)
    elif draw_num <= 8:
        current = middle
        best_other = max(inner, outer)
    else:
        current = outer
        best_other = max(inner, middle)
    edge = current - best_other
    if edge >= 10.0:
        return 1.5
    if edge <= -10.0:
        return -1.5
    return 0.0


def _normalize_venue(value) -> str:
    text = str(value or "").strip()
    if text in {"HV", "跑馬地"}:
        return "跑馬地"
    if text in {"ST", "沙田"}:
        return "沙田"
    return text


def _normalize_distance(value) -> str:
    return str(value or "").replace("m", "").strip()


def _is_hv_middle_distance_context(race_context: dict) -> bool:
    return _normalize_venue(race_context.get("venue")) == "跑馬地" and _normalize_distance(race_context.get("distance")) in {"1650", "1800"}


def _shadow_flag_candidates(horse: dict, race_context: dict, auto: dict) -> list[dict]:
    if int(auto.get("rank", 999) or 999) <= 2:
        return []
    if not _is_hv_middle_distance_context(race_context):
        return []

    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    features = auto.get("feature_scores", {}) if isinstance(auto.get("feature_scores"), dict) else {}

    flags: list[dict] = []
    best_distance = str(data.get("best_distance") or "")
    draw_fit = str(data.get("draw_position_fit") or "")
    trackwork_digest = str(data.get("trackwork_digest") or "")
    trackwork_health = str(data.get("trackwork_health") or "")
    position_pi = str(data.get("position_pi") or "")
    same_distance = clip_score(features.get("same_distance_signal_score", 60.0))
    risk_score = clip_score(features.get("risk_score", 60.0))
    last_finish = _safe_int(data.get("last_finish"))

    has_middle_distance_evidence = (
        "今仗 1650m =" in best_distance
        or "今仗 1800m =" in best_distance
        or "相近贏馬經驗" in best_distance
        or "相近上名經驗" in best_distance
    )
    matched_draw = "✅匹配" in draw_fit
    stable_trackwork = "操練放緩" not in trackwork_health and ("加強中" in trackwork_digest or "穩定" in trackwork_digest)
    positive_trackwork = "加強中" in trackwork_digest or clip_score(features.get("trackwork_trend_score", 60.0)) >= 68.0

    if (
        last_finish == 1
        and has_middle_distance_evidence
        and matched_draw
        and stable_trackwork
        and same_distance >= 54.0
        and risk_score >= 60.0
    ):
        flags.append(
            {
                "code": "HV_MID_LAST_START_WINNER",
                "label": SHADOW_FLAG_LABELS["HV_MID_LAST_START_WINNER"],
                "reason": "上仗已有交代，今場仍有中距離證據，排檔匹配而晨操維持穩定。",
            }
        )

    if (
        has_middle_distance_evidence
        and positive_trackwork
        and "上升軌" in position_pi
        and last_finish is not None
        and last_finish <= 5
        and same_distance >= 60.0
        and risk_score >= 58.0
    ):
        flags.append(
            {
                "code": "HV_MID_TRACKWORK_REBOUND",
                "label": SHADOW_FLAG_LABELS["HV_MID_TRACKWORK_REBOUND"],
                "reason": "中距離證據未斷，晨操加強配合走位趨勢回升，屬可跟進的回勇型。",
            }
        )

    seen = set()
    output = []
    for flag in flags:
        code = flag.get("code")
        if not code or code in seen:
            continue
        seen.add(code)
        output.append(flag)
    return output


def _safe_int(value: object) -> int | None:
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def write_race_outputs(logic_path: Path, logic_data: dict) -> tuple[Path, Path]:
    stem = logic_path.stem.replace("_Logic", "")
    md_path = logic_path.with_name(f"{stem}_Auto_Analysis.md")
    csv_path = logic_path.with_name(f"{stem}_Auto_Scoring.csv")
    _atomic_write_text(md_path, render_race_markdown(logic_data))
    _atomic_write_text(csv_path, render_race_csv(logic_data))
    errors = validate_report_text(md_path.read_text(encoding="utf-8"))
    if errors:
        raise ValueError(f"Auto report validation failed for {md_path}:\n" + "\n".join(errors))
    return md_path, csv_path


def render_race_markdown(logic_data: dict) -> str:
    verdict = ensure_verdict(logic_data)
    race = logic_data.get("race_analysis", {})
    horses = logic_data.get("horses", {})
    shadow_verdicts = logic_data.get("python_auto_shadow_verdicts", {}) if isinstance(logic_data.get("python_auto_shadow_verdicts"), dict) else {}
    lines = _render_panorama(race, verdict, horses, shadow_verdicts)
    lines.extend(["", "---", "#### [第二部分] 全場馬匹深度分析", ""])
    for horse_num, horse in _horses_by_rank(horses):
        auto = horse.get("python_auto")
        if isinstance(auto, dict):
            lines.extend(_render_horse_section(horse_num, horse, auto))
    lines.extend(_render_verdict(verdict, horses, shadow_verdicts))
    lines.extend(_render_blind_spots())
    return "\n".join(lines).strip() + "\n"


def render_race_csv(logic_data: dict) -> str:
    ensure_verdict(logic_data)
    output = io.StringIO()
    fields = [
        "race_number",
        "horse_number",
        "horse_name",
        "jockey",
        "trainer",
        "rank",
        "ability_score",
        "grade",
        "model_pick_status",
        "shadow_flag_labels",
        "shadow_flag_reasons",
        "shadow_consistency_rank",
        "shadow_consistency_ability",
        "shadow_consistency_delta",
        "shadow_consistency_reason",
        *FEATURE_LABELS.keys(),
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    race_number = logic_data.get("race_analysis", {}).get("race_number", "")
    for horse_num, horse in _sorted_horses(logic_data.get("horses", {})):
        auto = horse.get("python_auto", {})
        row = {
            "race_number": race_number,
            "horse_number": horse_num,
            "horse_name": horse.get("horse_name", ""),
            "jockey": horse.get("jockey", ""),
            "trainer": horse.get("trainer", ""),
            "rank": auto.get("rank", ""),
            "ability_score": auto.get("ability_score", ""),
            "grade": auto.get("grade", ""),
            "model_pick_status": auto.get("model_pick_status", ""),
            "shadow_flag_labels": _shadow_flag_labels(auto),
            "shadow_flag_reasons": _shadow_flag_reasons(auto),
            "shadow_consistency_rank": _shadow_profile_value(auto, "consistency_context", "rank"),
            "shadow_consistency_ability": _shadow_profile_value(auto, "consistency_context", "ability_score"),
            "shadow_consistency_delta": _shadow_profile_value(auto, "consistency_context", "rank_delta"),
            "shadow_consistency_reason": _shadow_profile_value(auto, "consistency_context", "reason"),
        }
        row.update(auto.get("feature_scores", {}))
        writer.writerow(row)
    return output.getvalue()


def render_meeting_csv(results: list[dict]) -> str:
    rows = []
    for logic_data in results:
        reader = csv.DictReader(render_race_csv(logic_data).splitlines())
        rows.extend(dict(row) for row in reader)
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def validate_report_text(text: str) -> list[str]:
    return [f"REPORT-001 contains banned term: {term}" for term in REPORT_BANS if term in text]


def _render_panorama(race: dict, verdict: dict, horses: dict, shadow_verdicts: dict | None = None) -> list[str]:
    race_class = _fmt(race.get("race_class"))
    distance = _fmt(race.get("distance"))
    race_number = _fmt(race.get("race_number"))
    shadow_verdicts = shadow_verdicts or {}
    return [
        "## [第一部分] 🗺️ 戰場全景",
        "",
        "| 項目 | 內容 |",
        "|:---|:---|",
        f"| 賽事格局 | {race_class} / {distance}m / HKJC |",
        "| **賽事類型** | **`[HKJC Wong Choi Auto Python 7D]`** |",
        "| 天氣 / 場地 | 以本地已抽取資料為準；缺資料以中性分處理 |",
        "| 分析邊界 | 12項分數 + 7D；不使用即場市場資料、主觀補寫或外部模型 |",
        "",
        "**📍 Auto 走位與檔位摘要（不含節奏預測）:**",
        f"- 場次: 第 {race_number} 場",
        f"- 出馬數: {len(horses)}",
        f"- 檔位分較高: {_top_feature_horses(horses, 'draw_score')}",
        f"- 信心分較高: {_top_feature_horses(horses, 'confidence_score')}",
        f"- 影子觀察: {_shadow_watch_summary(verdict)}",
        f"- Consistency Shadow: {_consistency_shadow_summary(shadow_verdicts.get('consistency_context'))}",
        "",
        "**📊 全場綜合戰力排名**",
        "",
        f"| 排名 | 馬號 | 馬名 | {ABILITY_LABEL} | Grade | 信心分 | 風險分 | 情境標記 |",
        "|---:|---:|---|---:|---|---:|---:|---|",
        *[_ranking_row(item, horses) for item in verdict.get("ranking", [])],
    ]


def _render_horse_section(horse_num: str, horse: dict, auto: dict) -> list[str]:
    # 版面次序（一個總分區，唔重覆）：
    #   1. 標題＋一行核心分數（總分／評級／信心／風險／情境標記）
    #   2. 評分總覽 — 唯一嘅 7D 加權計算表（貢獻、評級定義、參考分、風險標記）
    #   3. 數據判讀 → Facts → 近績 → 晨操解讀
    #   4. 7D 逐項拆解（構成、sub分點解、實證調整、判讀、數據）
    #   5. 最終判讀（核心判讀／優勢／風險）
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    features = auto.get("feature_scores", {})
    head = [
        f"**【No.{horse_num}】 {horse.get('horse_name', '')}** | 騎師:{horse.get('jockey', '')} | 練馬師:{horse.get('trainer', '')} | 負磅:{_fmt(horse.get('weight'))} | 檔位:{_fmt(horse.get('barrier'))}",
        _summary_banner(auto, features),
    ]
    for optional in (_shadow_flag_line(auto), _consistency_shadow_line(auto)):
        if optional:
            head.append(optional)
    return head + [
        "",
        _matrix_grade_section(auto, features),
        "",
        *_data_readout_lines(auto),
        "#### ⏱️ 近績解構",
        f"- **近六場:** {_fmt(horse.get('last_6_finishes'))} (左=剛戰 → 右=最舊)",
        f"- **休後復出:** {_fmt(horse.get('days_since_last') or data.get('days_since_last'))} 日",
        f"- **統計:** {_fmt(horse.get('season_stats') or data.get('season_stats_line'))}",
        f"- **近績分 / 穩定性分:** {float(features.get('form_score', 60)):.1f} / {float(features.get('consistency_score', 60)):.1f}",
        "",
        "#### 🧮 7D 評分矩陣逐項拆解",
        "> 每個維度：**評分構成**（sub分 × 權重點砌出嚟）→ 每個 sub分嘅來源 → **實證調整** → **判讀** → **數據**。",
        "",
        *_matrix_lines(horse, auto),
        "",
        "#### 💡 最終判讀 (Analyst View)",
        f"> - **核心判讀:** {_core_logic(auto, horse)}",
        f"> - **主要優勢:** {_advantage_text(features)}",
        f"> - **主要風險:** {_risk_text(auto)}",
        "",
        "---",
        "",
    ]


def _render_verdict(verdict: dict, horses: dict, shadow_verdicts: dict | None = None) -> list[str]:
    shadow_verdicts = shadow_verdicts or {}
    lines = [
        "#### [第三部分] 最終預測 (The Verdict)",
        "",
        f"- **全場信心指數:** `{_race_confidence(verdict.get('top4', []), horses)}`",
        "- **關鍵變數:** 檔位轉化、路程證明、晨操趨勢（歸狀態與穩定性）、資料完整度",
        "",
        "**🏆 Top 4 位置精選**",
        "",
    ]
    for idx, item in enumerate(verdict.get("top4", []), start=1):
        auto = horses[str(item["horse_number"])]["python_auto"]
        lines.extend([
            f"**第{idx}選**",
            f"- **馬號及馬名:** [{item['horse_number']}] {item['horse_name']}",
            f"- **評級與{ABILITY_LABEL}:** `[{auto.get('grade', '')}]` | {ABILITY_LABEL} {float(auto.get('ability_score', 0)):.1f}",
            *_verdict_pick_line(auto),
            f"- **核心理據:** {_short(_core_logic(auto, horses[str(item['horse_number'])]), 420)}",
            f"- **最大風險:** {_risk_text(auto)}",
            "",
        ])
    lines.extend([
        "**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**",
        *_top2_lines(verdict.get("top2", []), horses),
        "",
    ])
    shadow_watch = verdict.get("shadow_watch", [])
    if shadow_watch:
        lines.extend([
            "**🧭 影子觀察名單 (不改排名)**",
            *[
                f"- [{item['horse_number']}] {item['horse_name']}: {_shadow_flag_labels(horses[str(item['horse_number'])]['python_auto'])} — {_shadow_flag_reasons(horses[str(item['horse_number'])]['python_auto'])}"
                for item in shadow_watch
            ],
            "",
        ])
    consistency_shadow = shadow_verdicts.get("consistency_context")
    if consistency_shadow:
        lines.extend([
            "**🧪 Consistency Shadow Top 4 (不改主排名)**",
            *[
                f"- [{item['horse_number']}] {item['horse_name']}: 影子排名第{item['rank']}位，較主線提升{item.get('rank_delta', 0)}位"
                for item in consistency_shadow.get("top4", [])
            ],
            "",
        ])
        promoted = consistency_shadow.get("promoted", [])
        if promoted:
            lines.extend([
                "**🧭 Consistency Shadow 值得跟進名單**",
                *[
                    f"- [{item['horse_number']}] {item['horse_name']}: 影子排名第{item['rank']}位，較主線提升{item.get('rank_delta', 0)}位"
                    for item in promoted[:4]
                ],
                "",
            ])
    lines.extend([
        "**🚨 緊急重跑檢查 (Emergency Brake Protocol):**",
        "- 若出馬名單、場地資料、負磅、檔位或本地抽取資料更新，需重跑 Auto orchestrator。",
        "",
    ])
    return lines


def _render_blind_spots() -> list[str]:
    return [
        "---",
        "#### [第四部分] 分析盲區(緊隨第三部分)",
        "",
        "**1. 資料完整度:** 缺失欄位以中性 60 處理，並透過信心分反映不確定性。",
        "**2. 段速含金量:** 段速由本地已抽取資料與矩陣綜合，未以單一數字直接定勝負。",
        f"**3. 排名邏輯:** 只按{ABILITY_LABEL}由高至低排序；檔位、健康、騎練、段速等訊號已在 7D 矩陣內反映，不再另設排序 tie-break。Grade 只作閱讀標籤。",
        "**4. 騎練樣本:** 人馬、騎練或海外騎師資料不足時，不會單靠名氣加分。",
        "**5. 重跑條件:** 任何本地來源更新後，應重新執行 Python Auto pipeline。",
        "",
    ]


def _matrix_lines(horse: dict, auto: dict) -> list[str]:
    matrix = auto.get("matrix", {})
    matrix_scores = auto.get("matrix_scores", {})
    matrix_reasoning = auto.get("matrix_reasoning", {})
    lines = []
    for key, label in MATRIX_LABELS.items():
        score = matrix_scores.get(key)
        reasoning = matrix_reasoning.get(key, {}) if isinstance(matrix_reasoning, dict) else {}
        text = reasoning.get("text") if isinstance(reasoning, dict) else None
        components = reasoning.get("components", []) if isinstance(reasoning, dict) else []
        if not text:
            if isinstance(score, (int, float)):
                text = f"{label} {float(score):.1f}分；相關來源不足，以保守分處理。"
            else:
                text = f"{label} 暫缺可用分數；相關來源不足，以中性處理。"
        component_line = _matrix_component_line(components)
        if isinstance(score, (int, float)):
            band = BAND_LABELS.get(matrix.get(key, "➖"), "")
            header = f"##### {label}：`{float(score):.1f}分`　{matrix.get(key, '')} {band}".rstrip()
        else:
            header = f"##### {label}：`N/A`"
        lines.append(header)
        lines.append(f"  - **評分構成:** {component_line}")
        # 逐個 sub分點解：用 leaf scorer 自己嘅 note 解釋『點解係呢個分』。
        for comp in components:
            clbl = comp.get("label", "分項")
            csc = float(comp.get("score", 60))
            cnote = _clean_subscore_note(comp.get("note", ""))
            lines.append(f"    - {clbl} {csc:.0f} ← {cnote}" if cnote else f"    - {clbl} {csc:.0f}")
        adjustment = reasoning.get("adjustment") if isinstance(reasoning, dict) else None
        if adjustment:
            lines.append(f"    - {adjustment}")
        if key == "trainer_signal":
            lines.extend(_trainer_signal_adjustment_lines(auto))
        if key == "sectional":
            lines.extend(_speed_detail_lines(auto))
        lines.append(f"  - **判讀:** {_sanitize_text(text)}")
        if key == "stability":
            # 晨操分析＋海外往績直接住喺狀態與穩定性維度入面（用戶要求，唔另開 section）
            data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
            tw_lines = _trackwork_lines(auto, data)
            if tw_lines:
                lines.append("  - **晨操分析:**")
                lines.extend(f"    {item}" for item in tw_lines)
            overseas = auto.get("overseas_form_read")
            if isinstance(overseas, dict):
                lines.append("  - **海外往績:**")
                lines.extend(f"    - {item}" for item in overseas.get("lines", []))
                if overseas.get("verdict"):
                    lines.append(f"    - **判讀:** {overseas['verdict']}")
        fact_lines = _matrix_fact_lines(key, horse)
        if key == "form_line":
            fact_lines = _formline_table_lines(horse) + fact_lines
        if fact_lines:
            lines.append("  - **數據:**")
            for fact in fact_lines:
                lines.extend(_expand_fact_lines(fact))
    return lines


def _speed_detail_lines(auto: dict) -> list[str]:
    """速度分逐項訊號：每個 factor / 原始值 / ±分 / 白話，令 65% 速度分完全透明。
    速度分 = 基準60 + 各訊號加減。"""
    detail = auto.get("speed_detail")
    if not isinstance(detail, list) or not detail:
        return []
    lines = ["    - 速度分＝基準60 + 以下逐項訊號："]
    for d in detail:
        delta = float(d.get("delta", 0) or 0)
        dtxt = f"{delta:+.1f}" if delta else "0"
        val = str(d.get("value", "")).strip()
        why = str(d.get("why", "")).strip()
        val_part = f"（{val}）" if val else ""
        lines.append(f"      · {d.get('factor', '訊號')}{val_part} {dtxt}　{why}")
    return lines


def _trainer_signal_adjustment_lines(auto: dict) -> list[str]:
    """騎練訊號完整追溯：基礎層級分 → 每項實證調整（因子＋原始統計）→ 最終分。"""
    detail = auto.get("trainer_signal_detail")
    if not isinstance(detail, dict):
        return []
    lines: list[str] = []
    adjustments = detail.get("adjustments") or []
    # 每項因子有數據就顯示（±0都寫）；直接用因子名做標題（用戶要求）
    for adj in adjustments:
        delta = float(adj.get("delta", 0) or 0)
        delta_txt = f"{delta:+.1f}" if delta else "0"
        lines.append(f"    - {adj.get('factor', '調整')}（{adj.get('target', '')}）{delta_txt} ← {adj.get('evidence', '')}")
    if not adjustments:
        lines.append("    - 統計調整: 人馬歷史／騎練組合／同程均無可用統計")
    return lines


def _formline_table_lines(horse: dict) -> list[str]:
    """賽績線全表：每場過往賽事 — 強度組別、本駒名次、對手、對手之後戰績（franking）。"""
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    table = data.get("formline_table")
    if not isinstance(table, list) or not table:
        return []
    lines: list[str] = []
    validated = 0
    for row in table:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or "").strip()
        strength = str(row.get("strength") or "").strip()
        if strength in {"-", "--", "N/A"}:
            strength = ""
        my_finish = str(row.get("my_finish") or "").strip()
        opponents = " ".join(str(row.get("opponents") or "").split())
        next_class = " ".join(str(row.get("next_class") or "").split())
        next_perf = " ".join(str(row.get("next_performance") or "").split())
        wm = re.search(r"(\d+)\s*勝", next_perf)
        wins = int(wm.group(1)) if wm else 0
        if wins >= 1:
            validated += 1
        if next_class and next_class != "-" and next_perf and next_perf != "-":
            frank = f"對手其後{next_class} {next_perf}"
        elif next_perf and next_perf != "-":
            frank = f"對手其後{next_perf}"
        else:
            frank = "對手後續未有資料"
        bits = [b for b in (date, strength, f"本駒名次 {my_finish}" if my_finish else "", f"對手 {opponents}" if opponents else "", frank) if b]
        # 用「；」相連令每場保持一行（_expand_fact_lines 只會拆「 | 」或超長段落）
        lines.append("賽績線明細: " + "；".join(bits))
    if lines:
        n = len(lines)
        verdict = ("已受賽果驗證（franked）" if validated >= 2 else
                   ("有基本背書" if validated == 1 else "暫未有對手後續勝出背書"))
        lines.insert(0, f"賽績線兌現度: {validated}/{n} 場嘅對手其後再勝 → {verdict}")
    return lines


def _matrix_fact_lines(key: str, horse: dict) -> list[str]:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    if key == "stability":
        return _compact_fact_lines(
            ("近6場數據", data.get("recent_6_detail"), 320),
            ("頭馬距離趨勢", data.get("margin_trend"), 180),
        )
    if key == "sectional":
        finish_time = " | ".join(
            part for part in (data.get("finish_time_adj"), data.get("finish_time_adj_level")) if part
        )
        # 純速度錨點。場地偏差（track_bias）唔喺度顯示：佢係 draw/course 訊號，
        # 已於「檔位與走位」維度嘅數據錨點顯示，唔重複。
        return _compact_fact_lines(
            ("引擎分佈", data.get("engine_type"), 220),
            ("最佳路程", data.get("best_distance"), 160),
            ("L400 / 能量趨勢", _join_nonempty(data.get("raw_l400"), data.get("l400_trend"), data.get("energy_trend"), sep=" | "), 320),
            ("步速修正", finish_time, 260),
        )
    if key == "race_shape":
        draw_running = _join_nonempty(
            data.get("draw_verdict"),
            data.get("running_style"),
            f"走位PI={data.get('position_pi')}" if data.get("position_pi") else "",
            sep=" | ",
        )
        return _compact_fact_lines(
            ("近3-5仗走位窗口", data.get("position_window"), 360),
            ("檔位 / 跑法", draw_running, 360),
            ("檔位-走位匹配度", data.get("draw_position_fit"), 320),
            ("場地偏差", data.get("track_bias"), 180),
        )
    if key == "trainer_signal":
        combo_lines = _jockey_combo_snapshot(data.get("jockey_combo_block"))
        # 晨操部署已搬去狀態與穩定性嘅晨操分析（晨操嘢一律住嗰度）
        return _compact_fact_lines(
            ("配備變動", data.get("gear_change"), 180),
            *[(label, value, limit) for label, value, limit in combo_lines],
        )
    if key == "horse_health":
        rest_weight = _join_nonempty(
            f"休賽: {horse.get('days_since_last') or data.get('days_since_last')}日" if (horse.get("days_since_last") or data.get("days_since_last")) else "",
            f"體重趨勢: {data.get('weight_trend')}" if data.get("weight_trend") else "",
            sep=", ",
        )
        return _compact_fact_lines(
            ("休賽 / 體重趨勢", rest_weight, 260),
            ("健康掃描", data.get("medical_flags"), 120),
        )
    if key == "form_line":
        last_result = _join_nonempty(
            f"上仗名次={data.get('last_finish')}" if data.get("last_finish") else "",
            f"距離差={data.get('last_margin')}" if data.get("last_margin") else "",
            sep=" | ",
        )
        # 對手逐場明細已由 _formline_table_lines 提供，呢度只補強度標籤同上仗結果。
        return _compact_fact_lines(
            ("賽績線強度", data.get("formline_strength"), 160),
            ("上仗結果", last_result, 140),
        )
    if key == "class_advantage":
        record = _join_nonempty(
            f"{data.get('total_starts')}戰{data.get('total_wins')}勝" if data.get("total_starts") is not None and data.get("total_wins") is not None else "",
            f"評分趨勢={data.get('rating_trend')}" if data.get("rating_trend") else "",
            f"負磅={data.get('weight_carried')}" if data.get("weight_carried") not in (None, "") else "",
            sep=", ",
        )
        return _compact_fact_lines(
            ("班次 / 評分背景", record, 220),
            ("場地轉換", data.get("venue_transfer"), 80),
        )
    return []


def _compact_fact_lines(*items: tuple[str, object, int]) -> list[str]:
    lines = []
    for label, value, limit in items:
        text = _inline_text(value)
        if not text or text in {"N/A", "未知"}:
            continue
        lines.append(f"{label}: {_short(text, limit)}")
    return lines


def _strip_digest_directive(text: object) -> str:
    """去除晨操 digest 內部指令句（「判讀指令：…」係俾引擎用，唔係俾人讀）。"""
    return re.sub(r"判讀指令[:：].*$", "", str(text or ""), flags=re.S).strip()




def _trackwork_lines(auto: dict, data: dict) -> list[str]:
    """晨操分析：優先用引擎嘅逐項判讀（trackwork_read），冇先fallback原文摘要。
    晨操部署（操練者身份／配備／部署旗標）一併住呢度——晨操嘢唔分家。"""
    lines: list[str] = []
    read = auto.get("trackwork_read")
    if isinstance(read, dict) and read.get("lines"):
        lines.extend(f"- {item}" for item in read["lines"])
    else:
        digest = _strip_digest_directive(data.get("trackwork_digest"))
        lines.append(f"- **摘要:** {_short(digest or '未有完整晨操摘要，中性處理', 360)}")
    deployment = _inline_text(data.get("trackwork_trainer"))
    if deployment and deployment not in {"N/A", "未知"}:
        lines.append(f"- 部署：{_short(deployment, 260)}")
    if isinstance(read, dict) and read.get("verdict"):
        lines.append(f"- **判讀:** {read['verdict']}")
    return lines


def _inline_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return " ".join(text.split())


def _join_nonempty(*parts: object, sep: str = " ") -> str:
    values = [str(part).strip() for part in parts if str(part or "").strip()]
    return sep.join(values)


def _jockey_combo_snapshot(block: object) -> list[tuple[str, str, int]]:
    text = str(block or "").strip()
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    output: list[tuple[str, str, int]] = []
    current_row = next((line for line in lines if line.startswith("|") and "← 今場" in line), "")
    if current_row:
        cols = _table_cols(current_row)
        if len(cols) >= 8:
            jockey = cols[0].replace("← 今場", "").strip()
            output.append(
                (
                    "人馬組合統計",
                    f"{jockey}×此馬 {cols[1]}場 {cols[2]}勝 {cols[4]}上名 平均名次{cols[5]} 勝率{cols[6]} 位率{cols[7]}",
                    220,
                )
            )
    recent_names: list[str] = []
    in_recent_history = False
    for line in lines:
        if line.startswith("| # | 日期 | 騎師 |"):
            in_recent_history = True
            continue
        if not in_recent_history or not line.startswith("|"):
            continue
        cols = _table_cols(line)
        if len(cols) < 4 or cols[0] in {"---", "#"}:
            continue
        recent_names.append(cols[2])
    if recent_names:
        counts = Counter(recent_names)
        summary = "、".join(f"{name}{count}次" for name, count in counts.items())
        output.append(("近6場騎師分佈", summary, 180))
    return output


def _table_cols(line: str) -> list[str]:
    return [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]


def _ranking_row(item: dict, horses: dict) -> str:
    auto = horses[str(item["horse_number"])]["python_auto"]
    features = auto.get("feature_scores", {})
    return (
        f"| {auto.get('rank', '')} | {item['horse_number']} | {item['horse_name']} | "
        f"{float(auto.get('ability_score', 0)):.1f} | {auto.get('grade', '')} | "
        f"{float(features.get('confidence_score', 60)):.1f} | {float(features.get('risk_score', 60)):.1f} | "
        f"{_context_tags_display(auto)} |"
    )


def _pick_status(rank: int, ability: float, auto: dict) -> str:
    confidence = float(auto.get("feature_scores", {}).get("confidence_score", 60))
    if rank <= 2 and ability >= 70 and confidence >= 55:
        return "MODEL_TOP_PICK"
    if ability >= 70:
        return "WATCH"
    return "NO_PICK"


def _sorted_horses(horses: dict) -> list[tuple[str, dict]]:
    return sorted(horses.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 999)


def _top_feature_horses(horses: dict, feature_key: str, limit: int = 3) -> str:
    ranked = []
    for num, horse in _sorted_horses(horses):
        score = horse.get("python_auto", {}).get("feature_scores", {}).get(feature_key)
        if isinstance(score, (int, float)):
            ranked.append((float(score), num, horse.get("horse_name", "")))
    ranked.sort(key=lambda item: (-item[0], _horse_number_sort_key(item[1])))
    return "、".join(f"[{num}] {name} {score:.1f}" for score, num, name in ranked[:limit]) or "資料不足"


def _horses_by_rank(horses: dict) -> list[tuple[str, dict]]:
    return sorted(
        horses.items(),
        key=lambda item: (
            int(item[1].get("python_auto", {}).get("rank", 999)),
            _horse_number_sort_key(item[0]),
        ),
    )


def _horse_number_sort_key(value: object) -> int:
    return int(value) if str(value).isdigit() else 999


def _data_readout_lines(auto: dict) -> list[str]:
    """Render the structured 數據判讀 rows as a scannable markdown block."""
    rows = auto.get("data_readout") or []
    if not rows:
        return []
    lines = ["#### 📊 數據判讀", ""]
    for r in rows:
        val = f" {r['value']}" if r.get("value") else ""
        trend = f" — {r['trend']}" if r.get("trend") else ""
        reason = f"（{r['reason']}）" if r.get("reason") else ""
        lines.append(f"- {r.get('band', '➖')} **{r['label']}**{val}{trend}{reason}")
    lines.append("")
    return lines


def _core_logic(auto: dict, horse: dict) -> str:
    text = str(auto.get("core_logic") or "").strip()
    if text:
        return _sanitize_text(text)
    return f"{horse.get('horse_name', '')} 目前{ABILITY_LABEL} {float(auto.get('ability_score', 0)):.1f}，由 12 項分數及 7D 矩陣產生。"




def _advantage_text(features: dict) -> str:
    ranked = sorted(features.items(), key=lambda item: item[1], reverse=True)[:3]
    return "、".join(_advantage_phrase(key, float(score)) for key, score in ranked) or "資料不足"


def _risk_text(auto: dict) -> str:
    features = auto.get("feature_scores", {})
    flags = list(auto.get("risk_flags", []))
    weak = sorted(
        [
            (key, float(score))
            for key, score in features.items()
            if isinstance(score, (int, float)) and float(score) < 55
        ],
        key=lambda item: item[1],
    )
    pieces = []
    if weak:
        pieces.extend(_risk_phrase(key, score) for key, score in weak[:2])
    if "trackwork_slowing" in flags:
        pieces.append("備戰節奏亦略慢")
    elif "draw_pressure" in flags:
        pieces.append("排檔形勢亦帶來額外走位壓力")
    elif "distance_unproven" in flags:
        pieces.append("今場路程亦仍待驗證")
    pieces = _dedupe_phrases(pieces)
    if pieces:
        if len(pieces) == 1:
            return pieces[0]
        if len(pieces) == 2:
            return f"{pieces[0]}，{pieces[1]}"
        return "；".join(["，".join(pieces[:2]), "另外" + pieces[2]])
    return "無重大風險標記"


def _advantage_phrase(key: str, score: float) -> str:
    mapping = {
        "form_score": "近績走勢",
        "speed_score": "末段反應",
        "class_score": "班底硬度",
        "jockey_score": "騎師配置",
        "trainer_score": "馬房支持",
        "draw_score": "排檔形勢",
        "distance_score": "路程適配",
        "track_going_score": "場地配合",
        "weight_score": "負磅條件",
        "consistency_score": "穩定度",
        "risk_score": "健康銜接",
        "confidence_score": "資料完整度",
    }
    return f"{mapping.get(key, FEATURE_LABELS.get(key, key))} {score:.1f}"


def _risk_phrase(key: str, score: float) -> str:
    mapping = {
        "form_score": "近況未算完全企穩",
        "speed_score": "末段爆發力仍有保留",
        "class_score": "班底硬度未算夠硬",
        "jockey_score": "騎師層面未見額外加成",
        "trainer_score": "馬房助力未算突出",
        "draw_score": "排檔走位成本偏高",
        "distance_score": "今場路程證明仍然不足",
        "track_going_score": "場地適配仍未夠清晰",
        "weight_score": "負磅條件略為吃力",
        "consistency_score": "表現延續性未算穩陣",
        "risk_score": "健康銜接仍要再觀察",
        "confidence_score": "資料完整度未算特別高",
    }
    return mapping.get(key, FEATURE_LABELS.get(key, key))


def _dedupe_phrases(items: list[str]) -> list[str]:
    seen = set()
    output = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _race_confidence(top4: list[dict], horses: dict) -> str:
    scores = []
    for item in top4:
        horse = horses.get(str(item.get("horse_number")), {})
        score = horse.get("python_auto", {}).get("feature_scores", {}).get("confidence_score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    avg = sum(scores) / len(scores) if scores else 60
    if avg >= 80:
        return "高"
    if avg >= 68:
        return "中高"
    if avg >= 55:
        return "中"
    return "偏低"


def _top2_lines(top2: list[dict], horses: dict) -> list[str]:
    lines = []
    for item in top2:
        horse = horses[str(item["horse_number"])]
        auto = horse["python_auto"]
        lines.append(f"- [{item['horse_number']}] {item['horse_name']}: `{_race_confidence([item], horses)}` — {ABILITY_LABEL} {float(auto.get('ability_score', 0)):.1f}")
    return lines


def _fmt(value: object, fallback: str = "N/A") -> str:
    text = str(value or "").strip()
    if not text or _is_placeholder(text):
        return fallback
    return _sanitize_text(text)


def _short(value: object, limit: int) -> str:
    text = _sanitize_text(" ".join(str(value or "").split()))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _is_placeholder(text: str) -> bool:
    upper = text.upper()
    return "[FILL" in upper or "FILL]" in upper or upper == "FILL"


def _sanitize_text(text: str) -> str:
    if _is_placeholder(text):
        return "資料未完成，中性處理"
    return text


def _expand_fact_lines(fact: object) -> list[str]:
    """Make a dense 數據 anchor scannable: a『標籤: a | b | c』pipe-list becomes the
    label then one bullet per item; a long paragraph (e.g. 晨操 digest) is split into
    sentence bullets. Short single-value facts stay on one line."""
    fact = str(fact or "").strip()
    if not fact:
        return []
    m = re.match(r"^\s*([^:：]{1,24}[:：])\s*(.*)$", fact, re.S)
    label, rest = (m.group(1).strip(), m.group(2).strip()) if m else ("", fact)
    items = []
    if re.search(r"\s[|｜]\s", rest):
        items = [x.strip() for x in re.split(r"\s*[|｜]\s*", rest) if x.strip()]
    elif len(rest) > 110:
        items = [x.strip() for x in re.split(r"(?<=[。；])\s*", rest) if x.strip()]
    if len(items) > 1:
        head = f"    - {label}" if label else "    - 明細:"
        return [head] + [f"      - {it}" for it in items]
    return [f"    - {fact}"]


def _clean_subscore_note(note: object) -> str:
    """去掉 sub分 note 尾巴重覆嘅自述分數（個分我哋已喺前面顯示）。只剝最尾一段，
    要有分隔符 boundary，唔可以跨過逗號食埋真內容。兩種格式：『… 93.0 分。』『…近績分 54.2』。"""
    note = str(note or "").strip().rstrip("。 ")
    note = re.sub(r"[，,、；;。]\s*[^，,、；;。]*?\d+(?:\.\d+)?\s*分。?\s*$", "", note)
    note = re.sub(r"[，,、；;。]\s*[^，,、；;。]*?分\s*\d+(?:\.\d+)?。?\s*$", "", note)
    return note.strip(" ，,、；;。")


def _matrix_component_line(components: list[dict]) -> str:
    if not components:
        return "相關來源不足，以中性拆分處理。"
    return "、".join(
        f"{item.get('label', '分項')} {float(item.get('score', 60)):.1f} x {float(item.get('weight', 0)) * 100:.0f}%"
        for item in components
    )


def _pick_status_display(auto: dict, include_no_pick: bool = True) -> str:
    status = str(auto.get("model_pick_status") or "")
    if status == "NO_PICK" and not include_no_pick:
        return ""
    return PICK_LABELS.get(status, "不選")


def _shadow_flag_labels(auto: dict) -> str:
    flags = auto.get("shadow_flags", []) if isinstance(auto.get("shadow_flags"), list) else []
    labels = [str(flag.get("label") or "").strip() for flag in flags if isinstance(flag, dict)]
    labels = [label for label in labels if label]
    return "、".join(labels)


def _shadow_flag_reasons(auto: dict) -> str:
    flags = auto.get("shadow_flags", []) if isinstance(auto.get("shadow_flags"), list) else []
    reasons = [str(flag.get("reason") or "").strip() for flag in flags if isinstance(flag, dict)]
    reasons = [reason for reason in reasons if reason]
    return "；".join(reasons)


def _context_tags_display(auto: dict) -> str:
    tags = []
    pick_text = _pick_status_display(auto, include_no_pick=False)
    shadow_text = _shadow_flag_labels(auto)
    if pick_text:
        tags.append(pick_text)
    if shadow_text:
        tags.append(f"影子觀察: {shadow_text}")
    consistency_text = _consistency_shadow_tag(auto)
    if consistency_text:
        tags.append(consistency_text)
    return " / ".join(tags)


def _summary_banner(auto: dict, features: dict) -> str:
    """The ONE core-score line: total / grade / rank / confidence / risk (+tags)."""
    parts = [
        f"**📌 {ABILITY_LABEL} `{float(auto.get('ability_score', 0)):.1f}` → 評級 `{auto.get('grade', '')}`**",
    ]
    rank = auto.get("rank")
    if rank not in (None, ""):
        parts.append(f"全場排名 `{rank}`")
    parts.extend(
        [
            f"信心分 `{float(features.get('confidence_score', 60)):.1f}`",
            f"風險分 `{float(features.get('risk_score', 60)):.1f}`",
        ]
    )
    tags = _context_tags_display(auto)
    if tags:
        parts.append(f"情境標記 `{tags}`")
    return " | ".join(parts)


def _shadow_flag_line(auto: dict) -> str:
    labels = _shadow_flag_labels(auto)
    reasons = _shadow_flag_reasons(auto)
    if not labels:
        return ""
    return f"- **影子觀察:** {labels} — {reasons}"


def _consistency_shadow_line(auto: dict) -> str:
    profile = _shadow_profile(auto, "consistency_context")
    if not profile:
        return ""
    rank = profile.get("rank")
    rank_delta = profile.get("rank_delta")
    reason = str(profile.get("reason") or "").strip()
    if rank in (None, ""):
        return ""
    return f"- **Consistency Shadow:** 影子排名第{rank}位，較主線提升{rank_delta}位 — {reason}"


def _verdict_pick_line(auto: dict) -> list[str]:
    tags = _context_tags_display(auto)
    return [f"- **情境標記:** {tags}"] if tags else []


def _shadow_watch_summary(verdict: dict) -> str:
    shadow_watch = verdict.get("shadow_watch", []) if isinstance(verdict, dict) else []
    if not shadow_watch:
        return "暫無"
    parts = []
    for item in shadow_watch[:3]:
        labels = item.get("shadow_flags", [])
        if labels:
            parts.append(f"[{item['horse_number']}] {item['horse_name']} {_short('、'.join(labels), 32)}")
    return "；".join(parts) if parts else "暫無"


def _shadow_profile(auto: dict, profile_name: str) -> dict:
    profiles = auto.get("shadow_profiles", {}) if isinstance(auto.get("shadow_profiles"), dict) else {}
    profile = profiles.get(profile_name)
    return profile if isinstance(profile, dict) else {}


def _shadow_profile_value(auto: dict, profile_name: str, key: str):
    value = _shadow_profile(auto, profile_name).get(key, "")
    if isinstance(value, float):
        return round(value, 2)
    return value


def _consistency_shadow_tag(auto: dict) -> str:
    profile = _shadow_profile(auto, "consistency_context")
    if not profile:
        return ""
    rank_delta = int(profile.get("rank_delta", 0) or 0)
    if rank_delta >= 2:
        return f"Consistency影子升{rank_delta}位"
    if bool(profile.get("entered_top4")):
        return "Consistency影子入前四"
    return ""


def _consistency_shadow_summary(verdict: dict | None) -> str:
    if not verdict:
        return "未啟用"
    promoted = verdict.get("promoted", [])
    if not promoted:
        return "已啟用，但未見明顯升位馬"
    parts = []
    for item in promoted[:3]:
        parts.append(f"[{item['horse_number']}] {item['horse_name']} 升{item.get('rank_delta', 0)}位")
    return "；".join(parts)


def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)




def _matrix_grade_section(auto: dict, features: dict) -> str:
    """The single scoring-summary section (contribution table + grade + risk flags)."""
    parts = []

    grade_trans = auto.get("grade_transparency", {})
    if isinstance(grade_trans, dict) and grade_trans.get("summary"):
        parts.append("#### 🔢 評分總覽（7D 加權計算 · Python Auto 引擎）")
        parts.append("")
        parts.append(grade_trans["summary"])

    if not parts:
        return ""
    
    return "\n".join(parts)
