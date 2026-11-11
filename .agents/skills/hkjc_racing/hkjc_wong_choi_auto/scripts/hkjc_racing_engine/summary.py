"""Plain-language summary of one race: why each horse ranks where it does.

Display only — runs after the official ranking and never touches a score.

Every reason is ranked by its **impact on the final raw score**:
``impact = weight × (dimension raw − dimension typical)`` where *typical* is the
dimension's measured median (its display centre).  This is the number the
dashboard bar already shows (``grade_transparency.rows[].impact``), so the text
and the bar can no longer disagree.  The old verdict ranked dimensions by their
raw 0–100 score, and 賽績線 (raw median 80) was "the strongest link" for almost
every horse; it also listed 資料完整度 — not part of the model — as an advantage.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import tags as tag_builder

# 只講影響綜合分 ≥ 呢個數（原始尺）嘅維度。0.5 ≈ 顯示尺 1.1 分 —— 細過呢個唔值得寫。
IMPACT_FLOOR = 0.5

# 分差（顯示尺）同首選上名率：2026-04-12 → 2026-11-08 回放 431 場（PIT priors）。
#   首選拋離 ≥3 分：上名 58%（199 場）｜頭兩名 <3 分：上名 48%（232 場）
# 全體首選上名 52.7%、第二 44.2%、第三 36.4%、第四 31.4%。
CLEAR_GAP = 3.0
TOP_PICK_PLACE_RATE = {"clear": 0.58, "close": 0.48}
RANK_PLACE_RATE = {1: 0.527, 2: 0.442, 3: 0.364, 4: 0.314}

LONG_LAYOFF_DAYS = 75   # 同健康分嘅 days_gt_75_pen 一致
_AGE_CHECK = re.compile(r"年屆\S*歲")  # 賽會年齡例行檢查，唔係傷患


def _evidence(reasoning: dict) -> str:
    """Per-dimension 判讀 sentence without its trailing「→ 72分，加分位。」."""
    text = str((reasoning or {}).get("text") or "").strip()
    if " → " in text:
        text = text.rsplit(" → ", 1)[0]
    return text.rstrip("。；; ")


def _short(text: str, limit: int = 70) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _drivers(auto: dict) -> tuple[list[dict], list[dict]]:
    rows = (auto.get("grade_transparency") or {}).get("rows") or []
    reasoning = auto.get("matrix_reasoning") or {}
    items = []
    for row in rows:
        try:
            impact = float(row.get("impact"))
        except (TypeError, ValueError):
            continue
        if abs(impact) < IMPACT_FLOOR:
            continue
        items.append({
            "key": row.get("key"),
            "label": row.get("label"),
            "impact": round(impact, 2),
            "why": _short(_evidence(reasoning.get(row.get("key")))),
        })
    plus = sorted((i for i in items if i["impact"] > 0), key=lambda i: -i["impact"])[:3]
    minus = sorted((i for i in items if i["impact"] < 0), key=lambda i: i["impact"])[:2]
    return plus, minus


def _watch(horse: dict, auto: dict) -> list[str]:
    """Pre-race facts a reader must not miss, whether or not they are scored."""
    out = []
    days = auto.get("days_since_last")
    if isinstance(days, (int, float)) and days > LONG_LAYOFF_DAYS:
        out.append(f"休賽 {int(days)} 日後復出")
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    for record in data.get("official_injury_records") or []:
        if not isinstance(record, dict) or record.get("performance_only"):
            continue
        detail = str(record.get("detail") or "")
        if _AGE_CHECK.search(detail):
            continue
        out.append(_short(f"賽會傷患記錄 {record.get('incident_date') or ''} {detail}（未入分）", 60))
        break
    medical = str(data.get("medical_flags") or horse.get("medical_flags") or "")
    if medical and "無醫療事故" not in medical and medical not in ("N/A", "-"):
        out.append("賽事短評有醫療事故紀錄")
    for adj in (auto.get("trainer_signal_detail") or {}).get("adjustments") or []:
        if adj.get("factor") == "換騎" and adj.get("delta"):
            out.append("今仗換騎")
            break
    if any("debut" in str(code).lower() for code in auto.get("reason_codes") or []):
        out.append("初出馬，冇正式賽績")
    return out


def _gaps(auto: dict) -> list[str]:
    """Inputs that fell back to neutral 60 because the data was missing."""
    out = []
    if any(d.get("factor") == "資料不足" for d in auto.get("speed_detail") or []):
        out.append("段速")
    provenance = auto.get("score_provenance") or {}
    if provenance.get("form_score") == "missing_neutral" or provenance.get("consistency_score") == "missing_neutral":
        out.append("近績")
    derived = auto.get("derived_feature_scores") or {}
    if derived.get("formline_strength_score") == 60.0:
        out.append("賽績線")
    return out


def horse_summary(horse: dict, auto: dict, field_size: int) -> dict:
    plus, minus = _drivers(auto)
    rank = int(auto.get("rank") or 0)
    head = f"第{rank}／{field_size}｜{float(auto.get('ability_score', 0)):.1f} {auto.get('grade', '')}"
    if plus:
        head += "｜靠" + "、".join(p["label"] for p in plus[:2])
    if minus:
        head += "；" + "、".join(m["label"] for m in minus[:1]) + "拖低"
    if not plus and not minus:
        head += "｜各維度都接近中游，冇明顯強項或弱項"
    return {
        "headline": head,
        "plus": plus,
        "minus": minus,
        "watch": _watch(horse, auto),
        "gaps": _gaps(auto),
    }


def race_summary(ranking: list[dict]) -> dict:
    """Field-level read: how clear the top pick is, with its historical hit rate."""
    if len(ranking) < 2:
        return {"lines": []}
    scores = [float(item.get("ability_score", 0)) for item in ranking]
    gap = round(scores[0] - scores[1], 1)
    top = ranking[0]
    lines = []
    if gap >= CLEAR_GAP:
        tightness = "clear"
        lines.append(f"首選 [{top['horse_number']}] {top['horse_name']} 拋離第二名 {gap:.1f} 分"
                     f"（呢類場次歷史上首選上名約 {TOP_PICK_PLACE_RATE['clear']:.0%}）")
    else:
        tightness = "close"
        second = ranking[1]
        lines.append(f"頭兩名 [{top['horse_number']}] {top['horse_name']}、[{second['horse_number']}] "
                     f"{second['horse_name']} 只差 {gap:.1f} 分（呢類場次歷史上首選上名約 "
                     f"{TOP_PICK_PLACE_RATE['close']:.0%}）")
    if len(scores) >= 4:
        spread = round(scores[0] - scores[3], 1)
        if spread < 6:
            lines.append(f"頭四名相差 {spread:.1f} 分以內，屬混戰")
        if len(scores) >= 5:
            cliff = round(scores[3] - scores[4], 1)
            if cliff >= 4:
                lines.append(f"第四名同第五名之間有 {cliff:.1f} 分斷層，頭四名以外較難入位")
    return {"gap_1_2": gap, "tightness": tightness, "lines": lines}


def attach(logic_data: dict, meeting_dir: Path | None = None) -> None:
    """Write `python_auto.summary` per horse and `python_auto_race_summary`.

    `meeting_dir` lets the tag builder read the horse-profile cache and the racecard
    (潘頓棄騎、初跑、王牌…). Without it the tags fall back to what the Logic file holds.
    """
    horses = logic_data.get("horses") or {}
    scored = {num: h for num, h in horses.items() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict)}
    tags = tag_builder.race_tags(logic_data, meeting_dir)
    for num, horse in scored.items():
        horse["python_auto"]["summary"] = horse_summary(horse, horse["python_auto"], len(scored))
        horse["python_auto"]["summary"]["tags"] = tags.get(str(num)) or {"good": [], "bad": [], "note": []}
    ranking = (logic_data.get("python_auto_verdict") or {}).get("ranking") or []
    if not ranking:
        ranking = sorted(
            ({"horse_number": num, "horse_name": h.get("horse_name", ""),
              "ability_score": h["python_auto"].get("ability_score", 0), "rank": h["python_auto"].get("rank", 999)}
             for num, h in scored.items()),
            key=lambda item: item["rank"],
        )
    logic_data["python_auto_race_summary"] = race_summary(ranking)
