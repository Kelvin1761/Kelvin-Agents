from __future__ import annotations

import csv
import io
import os
import re
from pathlib import Path

from hidden_signal_rescue import apply_report_only_hidden_signal
from scoring import clip_score


ABILITY_LABEL = "綜合戰力分"

FEATURE_LABELS = {
    "form_score": "近績分",
    "trial_score": "試閘分",
    "sectional_score": "段速分",
    "pace_map_score": "形勢分",
    "jockey_score": "騎師分",
    "trainer_score": "練馬師分",
    "jockey_horse_fit_score": "人馬配搭分",
    "class_score": "級數分",
    "rating_score": "Rating 分",
    "weight_score": "負磅分",
    "distance_score": "路程分",
    "track_score": "場地分",
    "formline_score": "賽績線分",
    "consistency_score": "穩定性分",
    "health_score": "備戰完整度分",
    "confidence_score": "信心分",
}

MATRIX_LABELS = {
    "stability": "狀態與穩定性",
    "sectional": "段速與引擎",
    "race_shape": "檔位形勢",
    "jockey_trainer": "騎練訊號",
    "class_weight": "級數與負重",
    "track": "場地適性",
    "form_line": "賽績線",
}

REPORT_BANS = ("[FILL]", "PLACEHOLDER", "待補", "分析中")
HIDDEN_SIGNAL_REPORT_ONLY_ENABLED = False


def ensure_verdict(logic_data: dict) -> dict:
    horses = logic_data.get("horses", {})
    ranked = sorted(
        [
            {
                "horse_number": str(num),
                "horse_name": horse.get("horse_name", ""),
                "ability_score": float(horse.get("python_auto", {}).get("ability_score", 0)),
                "grade": horse.get("python_auto", {}).get("grade", ""),
            }
            for num, horse in horses.items()
            if isinstance(horse.get("python_auto"), dict)
        ],
        key=lambda item: (
            -item["ability_score"],
            _horse_number_sort_key(item["horse_number"]),
        ),
    )
    for idx, item in enumerate(ranked, start=1):
        auto = horses[item["horse_number"]]["python_auto"]
        auto["rank"] = idx
        auto["model_pick_status"] = "MODEL_TOP_PICK" if idx <= 2 else ("WATCH" if idx <= 4 else "NO_PICK")
        item["rank"] = idx
        item["model_pick_status"] = auto["model_pick_status"]
    _apply_hidden_signal_report_only(ranked, horses)
    watchlist = _build_rank_4_6_watchlist(ranked, horses)
    verdict = {
        "ranking": ranked,
        "top2": ranked[:2],
        "top4": ranked[:4],
        "rank_4_6_watchlist": watchlist,
    }
    logic_data["python_auto_verdict"] = verdict
    return verdict


def render_race_markdown(logic_data: dict) -> str:
    verdict = ensure_verdict(logic_data)
    race = logic_data.get("race_analysis", {})
    horses = logic_data.get("horses", {})
    lines = [
        _panorama(race, verdict, horses),
        "",
        "## [第二部分] 🛡️ 戰馬矩陣剖析",
        "",
    ]
    for horse_num, horse in _horses_by_rank(horses):
        lines.extend(_render_horse_section(horse_num, horse, horse["python_auto"]))
    lines.extend(_render_verdict(verdict, horses, race))
    return "\n".join(lines).strip() + "\n"


def render_race_csv(logic_data: dict) -> str:
    ensure_verdict(logic_data)
    output = io.StringIO()
    from scoring import FEATURE_KEYS
    fields = [
        "race_number",
        "horse_number",
        "horse_name",
        "jockey",
        "trainer",
        "rank",
        "pure_7d_score",
        "base_7d_score",
        "final_rank_score",
        "ability_score",
        "wet_form_feature",
        "grade",
        "model_pick_status",
        "watchlist_level",
        "watchlist_reasons",
        "hidden_signal_rescue_modifier",
        "hidden_signal_reasons",
        "shadow_rank_score",
        *FEATURE_KEYS,
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
            "pure_7d_score": auto.get("pure_7d_score", ""),
            "base_7d_score": auto.get("base_7d_score", ""),
            "final_rank_score": auto.get("final_rank_score", ""),
            "ability_score": auto.get("ability_score", ""),
            "wet_form_feature": auto.get("wet_form_feature", ""),
            "grade": auto.get("grade", ""),
            "model_pick_status": auto.get("model_pick_status", ""),
            "watchlist_level": auto.get("watchlist_level", ""),
            "watchlist_reasons": ";".join(auto.get("watchlist_reasons", []) or []),
            "hidden_signal_rescue_modifier": auto.get("hidden_signal_rescue_modifier", ""),
            "hidden_signal_reasons": ";".join(auto.get("hidden_signal_reasons", []) or []),
            "shadow_rank_score": auto.get("shadow_rank_score", ""),
        }
        row.update(auto.get("feature_scores", {}))
        writer.writerow(row)
    return output.getvalue()


def _apply_hidden_signal_report_only(ranked: list[dict], horses: dict) -> None:
    if not HIDDEN_SIGNAL_REPORT_ONLY_ENABLED:
        for item in ranked:
            horse = horses[str(item["horse_number"])]
            auto = horse.get("python_auto", {})
            auto["hidden_signal_rescue_modifier"] = 0.0
            auto["hidden_signal_reasons"] = []
            auto["shadow_rank_score"] = round(float(auto.get("rank_score") or auto.get("ability_score") or 0.0), 4)
        return

    rows = []
    for item in ranked:
        horse = horses[str(item["horse_number"])]
        auto = horse.get("python_auto", {})
        rows.append(
            {
                "horse_number": int(item["horse_number"]),
                "horse_name": item.get("horse_name") or horse.get("horse_name", ""),
                "rank_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                "ability_score": float(auto.get("ability_score") or 0.0),
                "feature_scores": dict(auto.get("feature_scores") or {}),
                "matrix_scores": dict(auto.get("matrix_scores") or {}),
                "risk_flags": list(auto.get("risk_flags") or []),
            }
        )

    shadow_rows = apply_report_only_hidden_signal(rows)
    shadow_lookup = {int(row["horse_number"]): row for row in shadow_rows}
    for item in ranked:
        horse = horses[str(item["horse_number"])]
        auto = horse.get("python_auto", {})
        shadow = shadow_lookup.get(int(item["horse_number"]), {})
        auto["hidden_signal_rescue_modifier"] = round(float(shadow.get("hidden_signal_rescue_modifier") or 0.0), 4)
        auto["hidden_signal_reasons"] = list(shadow.get("hidden_signal_reasons") or [])
        auto["shadow_rank_score"] = round(float(shadow.get("shadow_score") or auto.get("rank_score") or auto.get("ability_score") or 0.0), 4)


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


def write_race_outputs(logic_path: Path, logic_data: dict) -> tuple[Path, Path]:
    stem = logic_path.stem.replace("_Logic", "")
    md_path = logic_path.with_name(f"{stem}_Auto_Analysis.md")
    csv_path = logic_path.with_name(f"{stem}_Auto_Scoring.csv")
    _atomic_write_text(md_path, render_race_markdown(logic_data))
    _atomic_write_text(csv_path, render_race_csv(logic_data))
    return md_path, csv_path


def validate_report_text(text: str) -> list[str]:
    return [f"REPORT-001 contains banned term: {term}" for term in REPORT_BANS if term in text]


def _going_box_advisory(race):
    """Report-only track-condition confidence flag for box-trifecta staking.
    Does NOT affect ranking / 綜合戰力分. Grounded in the archive box-trifecta
    (all 3 placers within top-4) hit-rate by going over 616 races:
    Good/Firm 16.2%, Soft 13.8%, Heavy 8.9%. Wet (esp. Heavy) finds the winner
    fine but 2nd/3rd go chaotic, so widen the box / size down rather than trust top-4."""
    going = str(race.get("going") or "").strip()
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)?", going, re.I)
    if not m:
        return []
    kind = m.group(1).lower()
    level = int(m.group(2)) if m.group(2) else 0
    if kind == "heavy":
        conf = "🔴 低"
        advice = ("Heavy 場位次高度混亂：歷史 box-trifecta 命中率 ≈ 8.9%，約為好/快地 (16.2%) 一半。"
                  "冠軍仍具參考性，惟 2/3 名隨機性大。建議：box 由 4 匹擴至 5–6 匹，或減注。")
    elif kind == "soft" and level >= 7:
        conf = "🟠 中低"
        advice = "Soft 7+ 偏濕：位次穩定性下降 (box ≈ 13–14%)。建議：box 適度擴至 5 匹或減注。"
    elif kind == "soft":
        conf = "🟡 中"
        advice = "Soft 5–6：輕微濕地影響 (box ≈ 13.8%)，可正常注碼，惟留意位次波動。"
    else:
        return []
    return [
        f"> **⚠️ 場地位置信心：{conf}**（{going}）",
        f"> {advice}",
        "> _綜合戰力分已計入濕地往績（going suitability feature）；上述為落注 box 闊度建議。_",
        "",
    ]


def _panorama(race, verdict, horses):
    race_number = race.get("race_number", "")
    distance = race.get("distance", "")
    race_class = race.get("race_class", "")
    speed_map = race.get("speed_map", {}) if isinstance(race.get("speed_map"), dict) else {}
    track_bias = _meeting_track_bias_text(race, speed_map)
    return "\n".join([
        "## [第一部分] 🗺️ 戰場全景",
        "",
        "| 項目 | 內容 |",
        "|:---|:---|",
        f"| 賽事格局 | Race {race_number} / {distance} / {race_class} |",
        "| **賽事類型** | **`[AU Wong Choi Auto Python 7D]`** |",
        f"| 出馬數 | {len(horses)} |",
        f"| 跑道偏差 | {track_bias} |",
        "",
        *_going_box_advisory(race),
        "**🏃 形勢推演**",
        "",
        *_shape_overview_lines(speed_map),
        "",
        "**📊 全場綜合戰力排名**",
        "",
        f"| 排名 | 馬號 | 馬名 | {ABILITY_LABEL} | Grade | 定位 |",
        "|---:|---:|---|---:|---|---|",
        *[
            f"| {item['rank']} | {item['horse_number']} | {item['horse_name']} | {item['ability_score']:.1f} | {item['grade']} | {_horse_positioning(horses[str(item['horse_number'])], horses[str(item['horse_number'])].get('python_auto', {}))} |"
            for item in verdict.get("ranking", [])
        ],
    ])


def _render_horse_section(horse_num, horse, auto):
    jockey = _display_text(horse.get("jockey"))
    trainer = _display_text(horse.get("trainer"))
    weight = _display_weight(horse.get("weight"))
    barrier = _display_text(horse.get("barrier"))
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    lines = [
        f"### 【No.{horse_num}】 {horse.get('horse_name', '')} | 騎師: {jockey} | 練馬師: {trainer} | 負重: {weight} | 檔位: {barrier}",
        "",
        f"⭐ 最終評級: **{auto.get('grade', '')}** | {ABILITY_LABEL}: **{float(auto.get('ability_score', 0)):.1f}** | 排名: **{auto.get('rank', '')}**",
        "",
        "#### ⏱️ 近績解構",
        f"- **近績序列:** `{_display_text(data.get('recent_form') or horse.get('recent_form'))}`",
        f"- **狀態週期:** `{_humanize_text(horse.get('status_cycle')) or '-'}`",
        f"- **趨勢總評:** {_trend_summary(horse) or '-'}",
        f"- **預計走法:** {_humanize_text(_tactical_position(horse)) or '-'}",
        f"- **戰術劇本:** {_humanize_text(_tactical_scenario(horse)) or '-'}",
        "",
        "#### 📋 完整賽績檔案",
        *_complete_record_lines(data),
        "",
        "#### 🧠 核心分析",
        f"- {_render_core_logic(horse, auto)}",
        "",
        "#### 📊 7D 評分矩陣",
    ]
    for key, label in MATRIX_LABELS.items():
        score = auto.get("matrix_scores", {}).get(key, 60)
        reason_bundle = auto.get("matrix_reasoning", {}).get(key, {})
        reason = reason_bundle.get("text", "")
        lines.append(f"- **{label}:** {score:.1f}")
        lines.append(f"  - Python 判讀: {_humanize_text(reason)}")
        fact_lines = reason_bundle.get("anchors") or _matrix_fact_lines(key, horse, auto)
        if fact_lines:
            lines.append(f"  - **資料錨點:** {fact_lines[0]}")
            for fact in fact_lines[1:]:
                lines.append(f"  - {fact}")
    # 加入 Python 計算透明度
    grade_trans = auto.get("grade_transparency", {})
    grade_summary = grade_trans.get("summary", "") if isinstance(grade_trans, dict) else ""
    core_trans = auto.get("core_logic_transparency", "")
    
    if grade_summary:
        lines.extend([
            "",
            "**🔢 7D 矩陣加權總分計算 (Python Auto 引擎):**",
            "",
            grade_summary,
        ])
    if core_trans:
        lines.extend([
            "",
            core_trans,
        ])
    
    lines.extend([
        "",
        "#### 主要優勢",
        *[f"- {_humanize_text(item)}" for item in auto.get("advantages", [])],
        "",
        "#### 主要風險",
        *[f"- {_humanize_text(item)}" for item in auto.get("disadvantages", [])],
        "",
        "#### 16 項分數",
        f"- " + " | ".join(f"{FEATURE_LABELS[key]} {clip_score(auto.get('feature_scores', {}).get(key, 60)):.1f}" for key in FEATURE_LABELS),
        "",
    ])
    return lines


def _render_verdict(verdict, horses, race=None):
    lines = [
        "## [第三部分] 🏆 Top 4 位置精選",
        "",
        *(_going_box_advisory(race) if race else []),
    ]
    labels = ("🥇", "🥈", "🥉", "🏅")
    text_labels = ("第一選", "第二選", "第三選", "第四選")
    for idx, item in enumerate(verdict.get("top4", [])):
        horse = horses[str(item["horse_number"])]
        auto = horse["python_auto"]
        lines.extend([
            f"{labels[idx]} **{text_labels[idx]}**",
            f"- **馬號及馬名:** [{item['horse_number']}] {item['horse_name']}",
            f"- **定位:** {_horse_positioning(horse, auto)}",
            f"- **核心理據:** {_top4_summary(horse, auto)}",
            f"- **最大風險:** {_risk_summary(auto)}",
            f"- **評級 / 戰力分:** {auto.get('grade', '')} / {float(auto.get('ability_score', 0)):.1f}",
            "",
        ])
    watchlist = verdict.get("rank_4_6_watchlist") or []
    if watchlist:
        lines.extend([
            "## Rank 4-6 Danger Watchlist (Report-only)",
            "",
            "| Rank | 馬號 | 馬名 | Level | Gap | 理由 |",
            "|---:|---:|---|---|---:|---|",
        ])
        for item in watchlist:
            reasons = "；".join(_watchlist_reason_label(reason) for reason in item.get("reasons", []))
            lines.append(
                f"| {item['rank']} | {item['horse_number']} | {item['horse_name']} | "
                f"{item['level']} | {item['gap_to_top3']:.2f} | {reasons} |"
            )
        lines.append("")
    lines.extend([
        "## [第四部分] 分析盲區(緊隨第三部分)",
        "",
        "- ranking 以 `ability_score`（綜合戰力分）排序；`base_7d_score` 只作 7D 基礎分解釋。",
        "- 單一評分：`綜合戰力分` = `ability_score` = `final_rank_score` = `pure_7d_score`（乾地）或 `pure_7d_score + wet_form_feature`（濕地）；已退役所有 report-only 微調。",
        "- Rank 4-6 danger watchlist 只係提醒候選，不會交換 Top3 或 Top4 排名。",
        "- 初出馬若正式賽績空白，會較依賴試閘、馬房、走位結構與路程投影，信心不會無上限放大。",
        "- 如 Facts / Logic 更新，應重新執行 AU Auto orchestrator。",
        "",
    ])
    return lines


def _build_rank_4_6_watchlist(ranked, horses):
    if len(ranked) < 4:
        return []
    top3_cutoff = float(ranked[2]["ability_score"]) if len(ranked) >= 3 else 0.0
    watchlist = []
    for item in ranked[3:6]:
        horse = horses[str(item["horse_number"])]
        auto = horse.get("python_auto", {})
        level, reasons, gap = _watchlist_signal(horse, auto, top3_cutoff)
        auto["watchlist_level"] = level
        auto["watchlist_reasons"] = reasons
        auto["watchlist_report_only"] = bool(level)
        if level:
            watchlist.append({
                "rank": item["rank"],
                "horse_number": item["horse_number"],
                "horse_name": item["horse_name"],
                "level": level,
                "gap_to_top3": gap,
                "reasons": reasons,
            })
    return watchlist


def _watchlist_signal(horse: dict, auto: dict, top3_cutoff: float) -> tuple[str, list[str], float]:
    score = float(auto.get("ability_score") or 0.0)
    gap = max(0.0, top3_cutoff - score)
    matrix = auto.get("matrix_scores") or {}
    features = auto.get("feature_scores") or {}
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    reasons = []
    if gap <= 2.5:
        reasons.append("near_top3_score")
    if _as_float(matrix.get("stability"), 60.0) >= 66.0:
        reasons.append("stable_enough")
    if _as_float(matrix.get("class_weight"), 60.0) >= 61.5:
        reasons.append("class_weight_ok")
    if _as_float(matrix.get("jockey_trainer"), 60.0) >= 64.0 or _as_float(features.get("trial_score"), 60.0) >= 66.0:
        reasons.append("jt_or_trial_support")
    if _as_float(features.get("distance_score"), 60.0) >= 60.0:
        reasons.append("distance_ok")
    market_low = _as_float(data.get("current_market_low"), None)
    if market_low is not None and market_low <= 15.0:
        reasons.append("market_context")
    timing_recent = _as_float(data.get("timing_600m_recent_speed"), None)
    if timing_recent is not None and timing_recent >= 17.0:
        reasons.append("timing_context")
    if _as_float(data.get("recent_shape_wide_no_cover_count"), 0.0) or _as_float(data.get("recent_shape_early_work_count"), 0.0):
        reasons.append("excuse_shape_context")
    gear_changes = str(data.get("gear_changes") or "").strip().lower()
    if gear_changes and gear_changes != "none":
        reasons.append("gear_context")
    count = len(reasons)
    level = "High" if count >= 5 else "Medium" if count >= 3 else "Low" if count >= 1 else ""
    return level, reasons, round(gap, 4)


def _watchlist_reason_label(reason: str) -> str:
    labels = {
        "near_top3_score": "分差接近 Top3",
        "stable_enough": "穩定性夠",
        "class_weight_ok": "級數/負磅合理",
        "jt_or_trial_support": "騎練或試閘支持",
        "distance_ok": "路程無明顯扣分",
        "market_context": "市場只作背景支持",
        "timing_context": "時間/段速背景支持",
        "excuse_shape_context": "近仗有走位/形勢藉口",
        "gear_context": "配備變動背景",
    }
    return labels.get(reason, reason)


def _as_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        return float(match.group(0)) if match else default


def _horses_by_rank(horses):
    ranked = []
    for num, horse in horses.items():
        auto = horse.get("python_auto", {})
        ranked.append((auto.get("rank", 999), _horse_number_sort_key(num), num, horse))
    ranked.sort()
    return [(num, horse) for _, _, num, horse in ranked]


def _sorted_horses(horses):
    return sorted(((str(num), horse) for num, horse in horses.items()), key=lambda item: _horse_number_sort_key(item[0]))


def _horse_number_sort_key(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _display_text(value):
    text = str(value or "").strip()
    return text if text else "-"


def _display_weight(value):
    if value in (None, "", "-"):
        return "-"
    try:
        return f"{float(value):.1f}kg"
    except (TypeError, ValueError):
        text = str(value).strip()
        return text if text.endswith("kg") else f"{text}kg"


def _complete_record_lines(data: dict) -> list[str]:
    facts_section = str(data.get("facts_section") or "")
    rows = _record_rows(facts_section, limit=6)
    if not rows:
        return ["- 可用紀錄不足。"]
    return rows


def _recent_record_excerpt(facts_section: str) -> str:
    lines = [line.strip() for line in facts_section.splitlines() if line.strip().startswith("|") and "| 類型 |" not in line and "|---" not in line]
    if not lines:
        return ""
    rows = []
    for line in lines[:3]:
        cols = [col.strip() for col in line.strip("|").split("|")]
        if len(cols) < 9:
            continue
        kind = cols[1]
        date = cols[2]
        venue = cols[3]
        distance = cols[4]
        placing = cols[7]
        trajectory = cols[9] if len(cols) > 9 else ""
        row = " / ".join(part for part in (kind, date, venue, distance, f"名次{placing}", trajectory) if part and part != "-")
        if row:
            rows.append(row)
    return "；".join(rows)


def _record_rows(facts_section: str, limit: int = 6) -> list[str]:
    lines = [line.strip() for line in facts_section.splitlines() if line.strip().startswith("|") and "| 類型 |" not in line and "|---" not in line]
    rows = []
    for line in lines[:limit]:
        cols = [col.strip() for col in line.strip("|").split("|")]
        if len(cols) < 10:
            continue
        kind = cols[1]
        date = cols[2]
        venue = cols[3]
        distance = cols[4]
        going = cols[5]
        barrier = cols[6]
        placing = cols[7]
        trajectory = cols[9]
        label = "正式" if "試閘" not in kind else "試閘"
        rows.append(
            f"- `{label}` {date} | {venue} | {distance} | 場地 {going} | 檔位 {barrier} | 名次 {placing} | 走勢 {trajectory}"
        )
    return rows


def _latest_formal_result(facts_section: str) -> str:
    for line in _record_rows(facts_section, limit=6):
        if line.startswith("- `正式`"):
            return line.replace("- `正式` ", "", 1)
    if "共 0 正式" in facts_section:
        return "未有正式賽果可供引用。"
    return ""


def _latest_public_result(facts_section: str) -> str:
    for line in _record_rows(facts_section, limit=6):
        if line.startswith("- `試閘`"):
            return line.replace("- `試閘` ", "", 1)
    racecard = re.search(r"上仗結果\(Racecard\): ([^\n]+)", facts_section)
    if racecard:
        return f"最近公開紀錄顯示 {racecard.group(1).strip()}。"
    return ""


def _fact_block_excerpt(facts_section: str, title: str) -> str:
    if not facts_section or title not in facts_section:
        return ""
    lines = facts_section.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if title in line:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""
    collected = []
    for line in lines[start_idx:]:
        if line.startswith("- **") and title not in line:
            break
        if line.startswith("### "):
            break
        text = line.strip()
        if not text:
            continue
        if text.startswith("|") and ("日期" in text or "---" in text):
            continue
        if text.startswith(">"):
            continue
        if text.startswith("- "):
            text = text[2:]
        collected.append(text)
        if len(collected) >= 3:
            break
    return " ".join(collected)


def _formline_summary(facts_section: str) -> str:
    headline = ""
    headline_match = re.search(r"\*\*綜合評估:\*\* ([^\n]+)", facts_section)
    if headline_match:
        headline = headline_match.group(1).strip()
    rows = []
    for line in facts_section.splitlines():
        text = line.strip()
        if not text.startswith("|") or "頭馬" not in text and "亞軍" not in text and "季軍" not in text:
            continue
        if "日期" in text or "---" in text:
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        if len(cols) < 8:
            continue
        opponent = cols[4]
        next_class = cols[5]
        result = cols[6]
        grade = cols[7]
        if opponent:
            rows.append(" / ".join(part for part in (opponent, next_class, result, grade) if part and part != "-"))
        if len(rows) >= 2:
            break
    pieces = []
    text = "；".join(rows)
    headline_lower = headline or ""
    if "無資料" in headline_lower and rows:
        return f"對手後續暫未有足夠實績承接，賽績線現階段只可視為中性偏正面。代表對手包括 {text}。"
    if "強" in headline_lower:
        if rows:
            return f"對手線有一定支撐，唔係普通水位跑返嚟。代表對手包括 {text}。"
        return "對手線有一定支撐，賽績線可信度屬正面。"
    if rows:
        return f"對手後續證明未算厚，但亦唔係完全冇參考。代表對手包括 {text}。"
    return headline


def _fact_bullets(facts_section: str) -> list[tuple[str, str]]:
    labels = ("班次負重", "引擎距離", "步態場地", "配備意圖", "人馬組合")
    output = []
    for label in labels:
        match = re.search(rf"- \*\*{re.escape(label)}:\*\* ([^\n]+)", facts_section)
        if match:
            output.append((label, _shorten_fact(match.group(1), 220)))
    return output


def _energy_summary(facts_section: str) -> str:
    block = _fact_block_excerpt(facts_section, "⚡ 走位消耗摘要")
    clean = block.replace("  ", " ")
    if "極高" in clean:
        return "近仗曾有外疊或蝕位情況，消耗偏重，今次若能跑得更順會有反彈空間。"
    if "中等" in clean:
        return "近仗消耗屬可控範圍，未見特別傷腳程。"
    if "輕微" in clean or "中低" in clean:
        return "近仗走位成本唔高，體力保留算合理。"
    return clean


def _trial_anchor(data: dict, facts_section: str) -> str:
    trial_count = int(float(data.get("trial_count") or 0))
    trial_top3 = int(float(data.get("trial_top3_count") or 0))
    latest = _latest_public_result(facts_section)
    if trial_count > 0:
        base = f"共 {trial_count} 次試閘，其中 {trial_top3} 次前三"
        return f"{base}；最近一課為 {latest}" if latest else base
    return latest


def _l400_anchor(horse: dict, data: dict) -> str:
    value = horse.get("raw_l400") or data.get("raw_l400")
    if value in (None, "", "-"):
        return ""
    try:
        return f"{float(value):.2f} 秒"
    except (TypeError, ValueError):
        return str(value).strip()


def _matrix_fact_lines(key: str, horse: dict, auto: dict) -> list[str]:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    facts_section = str(data.get("facts_section") or "")
    if key == "stability":
        return _compact_fact_lines(
            ("近況總覽", _recent_record_summary(horse, data, facts_section), 320),
            ("狀態週期", _humanize_text(horse.get("status_cycle")), 120),
            ("趨勢總評", _humanize_text(horse.get("trend_summary")), 140),
            ("最近正式賽果", _latest_formal_result(facts_section), 220),
            ("試閘交代", _trial_anchor(data, facts_section), 180),
            ("走位消耗", _energy_summary(facts_section), 180),
        )
    if key == "sectional":
        return _compact_fact_lines(
            ("引擎與路程", _engine_distance_summary(data), 320),
            ("L400", _l400_anchor(horse, data), 80),
            ("試閘交代", _trial_anchor(data, facts_section), 180),
            ("最近試閘 / 公開紀錄", _latest_public_result(facts_section), 220),
        )
    if key == "race_shape":
        return _compact_fact_lines(
            ("跑法信心", _inline_text(data.get("style_confidence_line")), 80),
            ("預計走法", _humanize_text(_tactical_position(horse)), 120),
            ("跑法摘要", _inline_text(data.get("running_style_line")), 120),
            ("戰術劇本", _humanize_text(_tactical_scenario(horse)), 260),
            ("走位消耗", _energy_summary(facts_section), 180),
        )
    if key == "jockey_trainer":
        return _compact_fact_lines(
            ("騎師 / 練馬師", " / ".join(part for part in (_inline_text(horse.get("jockey")), _inline_text(horse.get("trainer"))) if part and part != "-"), 180),
            ("試閘交代", _trial_anchor(data, facts_section), 180),
            ("狀態週期", _humanize_text(horse.get("status_cycle")), 120),
            ("跑法摘要", _inline_text(data.get("running_style_line")), 120),
            ("戰術劇本", _humanize_text(_tactical_scenario(horse)), 260),
        )
    if key == "class_weight":
        return _compact_fact_lines(
            ("生涯背景", _career_background(facts_section), 220),
            ("班次變動", data.get("class_move"), 80),
            ("負磅", _display_weight(horse.get("weight")), 80),
        )
    if key == "track":
        race_context = auto.get("race_context", {}) if isinstance(auto.get("race_context"), dict) else {}
        return _compact_fact_lines(
            ("場地背景", _track_summary(facts_section), 220),
            ("今場掛牌", race_context.get("going"), 80),
            ("Meeting bias", race_context.get("meeting_bias"), 220),
            ("賽道幾何", race_context.get("track_geometry"), 220),
            ("最近正式賽果", _latest_formal_result(facts_section), 220),
        )
    if key == "form_line":
        return _compact_fact_lines(
            ("賽績線", _formline_summary(facts_section), 320),
            ("最近正式賽果", _latest_formal_result(facts_section), 220),
        )
    return []


def _compact_fact_lines(*items: tuple[str, object, int]) -> list[str]:
    lines = []
    for label, value, limit in items:
        text = _inline_text(value)
        if not text or text in {"-", "N/A", "未知"}:
            continue
        lines.append(f"{label}: {_shorten_fact(text, limit)}")
    return lines


def _shape_overview_lines(speed_map: dict) -> list[str]:
    leaders = len(speed_map.get("leaders") or [])
    pressers = len(speed_map.get("pressers") or [])
    on_pace = len(speed_map.get("on_pace") or [])
    mid_pack = len(speed_map.get("mid_pack") or [])
    closers = len(speed_map.get("closers") or [])
    lines = ["- 形勢推演暫時以跑法分佈、檔位同戰術劇本為主，未納入步速預測。"]
    if leaders + pressers + on_pace <= 2:
        lines.append("- 前置馬唔多，邊匹願意主動搶位會直接影響前中段落位。")
    elif leaders + pressers + on_pace >= 5:
        lines.append("- 前面有幾匹都想搶位，出閘後搶位成本會係關鍵。")
    else:
        lines.append("- 前後分佈尚算平均，臨場誰先搵到舒服位置會更重要。")
    if closers >= 2 or mid_pack >= 5:
        lines.append("- 留後馬若入直路前未開始移位，末段未必追得切。")
    else:
        lines.append("- 若前列馬順利搵到遮擋，後面想一氣追過會有一定難度。")
    return lines


def _track_bias_text(track_bias: object, speed_map: dict) -> str:
    raw = _inline_text(track_bias)
    clean = _humanize_text(raw)
    if clean and clean not in {"按 facts / intelligence 判斷", "未明"} and "using barriers" not in raw:
        return clean
    inside = len(speed_map.get("inside_draws") or [])
    outside = len(speed_map.get("outside_draws") or [])
    if inside and outside:
        if inside > outside:
            return "內檔略有幫助，但未到非常鮮明。"
        if outside > inside:
            return "外檔未算絕對輸蝕，轉彎後落位先係關鍵。"
    return "今場未見特別鮮明檔位偏差，仍以臨場落位為主。"


def _meeting_track_bias_text(race: dict, speed_map: dict) -> str:
    meeting = race.get("meeting_intelligence", {}) if isinstance(race.get("meeting_intelligence"), dict) else {}
    profile = race.get("track_profile", {}) if isinstance(race.get("track_profile"), dict) else {}
    bias = _humanize_text(meeting.get("bias_summary"))
    if bias:
        straight = profile.get("straight_m")
        try:
            straight_text = f" 直路僅約 {int(float(straight))}m。" if straight else ""
        except (TypeError, ValueError):
            straight_text = ""
        return (bias + straight_text).strip()
    return _track_bias_text(race.get("track_bias") or speed_map.get("track_bias"), speed_map)


def _career_background(facts_section: str) -> str:
    match = re.search(r"生涯:\s*([^\n]+)", facts_section)
    stage = re.search(r"生涯標記:\s*`?([^`\n]+)`?", facts_section)
    parts = []
    if match:
        parts.append(match.group(1).strip())
    if stage:
        parts.append(stage.group(1).strip())
    return " | ".join(parts)


def _track_summary(facts_section: str) -> str:
    track = re.search(r"同場:\s*([^\n]+)", facts_section)
    going = re.search(r"好地:\s*([^\n]+)", facts_section)
    parts = []
    if track:
        parts.append("同場/同程 " + track.group(1).strip())
    if going:
        parts.append("場地紀錄 " + going.group(1).strip())
    return " | ".join(parts)


def _trend_summary(horse: dict) -> str:
    trend = _humanize_text(horse.get("trend_summary"))
    status = _humanize_text(horse.get("status_cycle"))
    if not trend:
        return ""
    compact_trend = trend.replace("休後復出", "久休復出").replace("長休復出", "久休復出")
    if status and (compact_trend == status or compact_trend in status or status in compact_trend):
        return ""
    return trend


def _tactical_position(horse: dict) -> str:
    plan = horse.get("tactical_plan")
    if isinstance(plan, dict):
        return str(plan.get("expected_position") or "").strip()
    return ""


def _tactical_scenario(horse: dict) -> str:
    plan = horse.get("tactical_plan")
    if isinstance(plan, dict):
        text = str(plan.get("race_scenario") or "").strip()
        for src, dst in (
            ("於偏慢場面下，", "入直路前，"),
            ("在偏慢場面下，", "入直路前，"),
            ("於偏慢場面下", "入直路前"),
            ("在偏慢場面下", "入直路前"),
            ("偏慢場面下", "入直路前"),
            ("於極慢步速下，", "入直路前，"),
            ("在極慢步速下，", "入直路前，"),
            ("於極慢步速下", "入直路前"),
            ("在極慢步速下", "入直路前"),
            ("極慢步速下", "入直路前"),
            ("因應偏慢場面而", "視乎落位而"),
            ("因應偏慢場面", "視乎落位"),
            ("能從容控制場面節奏並", "若能順利放出並"),
            ("控制場面節奏", "控制走位主動權"),
            ("控制步速", "控制走位主動權"),
            ("以騎功彌補場面節奏劣勢", "以騎功修正走位成本"),
            ("場面節奏劣勢", "走位成本劣勢"),
        ):
            text = text.replace(src, dst)
        return text
    return ""


def _recent_record_summary(horse: dict, data: dict, facts_section: str) -> str:
    recent = str(data.get("recent_form") or horse.get("recent_form") or "").strip()
    status_cycle = _humanize_text(horse.get("status_cycle")) or "-"
    trend = _humanize_text(horse.get("trend_summary")) or "-"
    excerpt = _recent_record_excerpt(facts_section)
    if recent and recent not in {"-", "N/A"}:
        base = f"近績序列 {recent}，現時屬 {status_cycle} 階段，走勢大致可概括為「{trend}」。"
    else:
        base = f"現時屬 {status_cycle} 階段，走勢大致可概括為「{trend}」。"
    if excerpt:
        return f"{base} 最近賽績重點為 {excerpt}。"
    return base


def _engine_distance_summary(data: dict) -> str:
    line = _inline_text(data.get("engine_line"))
    if not line:
        return ""
    distance_match = re.search(r"今仗\s+([0-9]+m)\s+\(([^)]+)\):\s*([0-9場()\-0-9]+)", line)
    engine_match = re.search(r"引擎:\s*([^|]+)", line)
    confidence_match = re.search(r"信心:\s*([^|]+)", line)
    pieces = []
    if engine_match:
        pieces.append(f"現階段引擎輪廓偏向 {engine_match.group(1).strip()}")
    if distance_match:
        pieces.append(f"今次 {distance_match.group(1)} 暫以上 {distance_match.group(2).strip()} 系列作參考")
    if confidence_match and confidence_match.group(1).strip() in {"低", "中"}:
        pieces.append(f"距離投射信心屬{confidence_match.group(1).strip()}，仍要靠臨場表現補證")
    return "，".join(pieces) + "。" if pieces else line


def _horse_positioning(horse: dict, auto: dict) -> str:
    rank = int(auto.get("rank", 99) or 99)
    ability = float(auto.get("ability_score", 0) or 0)
    race_shape = float(auto.get("matrix_scores", {}).get("race_shape", 60) or 60)
    stability = float(auto.get("matrix_scores", {}).get("stability", 60) or 60)
    if rank <= 2 and ability >= 66:
        return "爭勝"
    if rank <= 4 and stability >= 66:
        return "爭位"
    if race_shape >= 66:
        return "形勢型"
    return "保留"


def _render_core_logic(horse: dict, auto: dict) -> str:
    base = _humanize_text(str(auto.get("core_logic") or "").strip())
    barrier = _display_text(horse.get("barrier"))
    expected_position = _humanize_text(_tactical_position(horse))
    scenario = _humanize_text(_tactical_scenario(horse))
    positioning = _horse_positioning(horse, auto)
    risk = _risk_summary(auto)
    pieces = []
    if base:
        pieces.append(base)
    if expected_position not in {"", "-"}:
        pieces.append(f"配合今次 {barrier} 檔，同埋預計以「{expected_position}」方式應戰，跑法上有相應劇本。")
    if scenario not in {"", "-"}:
        pieces.append(f"如果能夠照住呢個場面劇本落位，{scenario}")
    if positioning == "爭勝":
        pieces.append("整體屬於有條件主動爭勝嗰類。")
    elif positioning == "爭位":
        pieces.append("整體較似穩紮穩打嘅爭位份子。")
    elif positioning == "形勢型":
        pieces.append("整體更似要靠場面幫手先最易兌現。")
    else:
        pieces.append(f"現階段仍有保留，尤其要留意 {risk}。")
    return " ".join(piece for piece in pieces if piece)


def _top4_summary(horse: dict, auto: dict) -> str:
    position = _horse_positioning(horse, auto)
    expected_position = _humanize_text(_tactical_position(horse))
    summary = _humanize_text(str(auto.get("core_logic") or "").strip())
    if position == "爭勝":
        prefix = "今場最主要係睇佢能否將自身條件順利兌現。"
    elif position == "爭位":
        prefix = "今場贏馬把握未必最硬，但放入前列範圍相對合理。"
    elif position == "形勢型":
        prefix = "今場更似場面啱先會特別突出嘅一匹。"
    else:
        prefix = "今場仍要靠幾方面同時配合，先較易跑出預期。"
    if expected_position not in {"", "-"}:
        prefix += f" 若能以「{expected_position}」姿態順利入局，會較容易交代。"
    return f"{prefix} {summary}"


def _risk_summary(auto: dict) -> str:
    risks = [_humanize_text(item) for item in auto.get("disadvantages", []) if str(item).strip()]
    if not risks:
        return "暫未見特別鮮明紅旗"
    if len(risks) == 1:
        return risks[0]
    return "；".join(risks[:2])


def _humanize_text(text: object) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = " ".join(value.split())
    value = re.sub(r"(?<!段)步速", "場面節奏", value)
    value = re.sub(r"\bpace\b", "節奏", value, flags=re.I)
    value = value.replace("FACTS_SPEED_MODEL", "")
    value = value.replace("FACTS_SHAPE_MODEL", "")
    value = re.sub(r"Warwick Farm Race \d+(?:-\d+)? \d+m; using barriers, EEM/settled weighted recent run style, and engine cross-check\.?", "", value)
    value = re.sub(r"using barriers, EEM/settled weighted recent run style, and engine cross-check\.?", "", value, flags=re.I)
    value = re.sub(r"Warwick Farm Race \d+(?:-\d+)? \d+m; using barriers, video/settled weighted recent run style, and engine cross-check\.?", "", value)
    value = re.sub(r"using barriers, video/settled weighted recent run style, and engine cross-check\.?", "", value, flags=re.I)
    replacements = {
        "Leader/On-Pace": "前領跟前",
        "On-節奏 BIAS": "前置偏差",
        "On-節奏": "前領跟前",
        "Lead": "領放",
        "On-Pace": "前領跟前",
        "Tight-turning": "急彎賽道",
        "Handy/On Pace": "跟前前置",
        "Mid-pack to Closer": "中後跟跑",
        "Midfield/WTMF": "居中跟跑",
        "Box Seat/Midfield": "守中靠欄",
        "Back/Tail": "居後包尾",
        "Midfield": "居中",
        "Closer": "後上",
        "Tail": "包尾",
        "Back": "後追",
        "Third-up": "第三仗",
        "Second-up": "第二仗",
        "First-up": "久休復出",
        "Fourth-up": "第四仗",
        "Deep Prep": "長期作戰期",
        "Unknown": "未明",
        "前領 / 跟前": "前領跟前",
        "跟前 / 前置": "跟前前置",
        "居中 / 中後": "居中稍後",
        "居後 / 包尾": "居後包尾",
        "偏慢的起場面節奏度": "起步未算快",
        "起場面節奏度": "起步反應",
        "整場賽事節奏": "場面主導權",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    value = value.replace("極慢場面節奏", "偏慢場面")
    value = value.replace("慢場面節奏", "偏慢場面")
    value = value.replace("極快場面節奏", "偏快場面")
    value = value.replace("快場面節奏", "偏快場面")
    value = value.replace("臨場場面節奏", "臨場節奏")
    value = re.sub(r"\b(?:leaders|pressers|closers|mid|on_節奏|predicted|confidence)\b\s*=?\s*[\w.\-]+", "", value, flags=re.I)
    value = re.sub(r"\s*\([^)]*\)", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" ;,:")
    return value


def _shorten_fact(text: object, limit: int) -> str:
    clean = _inline_text(text)
    if not clean:
        return ""
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _inline_text(value: object) -> str:
    text = str(value or "").strip()
    return " ".join(text.split()) if text else ""


def _forgiveness_digest(horse: dict, data: dict) -> str:
    facts_section = str(data.get("facts_section") or "")
    rows = [line.strip() for line in facts_section.splitlines() if line.strip().startswith("|") and "| 類型 |" not in line and "|---" not in line]
    reasons = []
    for line in rows[:4]:
        cols = [col.strip() for col in line.strip("|").split("|")]
        if len(cols) < 18 or "試閘" in cols[1]:
            continue
        forgiveness = cols[17]
        notes = cols[16]
        if forgiveness and forgiveness not in {"[-]", "[需判定]"}:
            reasons.append(forgiveness)
        elif any(token in notes for token in ("Crowded", "Bumped", "Steadied", "Looking for run", "Worked early", "Too much start")):
            reasons.append(notes)
    if not reasons:
        return "未見鮮明寬恕背景"
    text = "；".join(reasons[:2])
    return _shorten_fact(_humanize_text(text), 120)
