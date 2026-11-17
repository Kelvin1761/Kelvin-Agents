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
    # 「今仗換騎」唔再寫：換騎 chip 已經寫明前→今騎師（Kelvin 2026-11-17 話重複）。
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


_BATTLEFIELD: dict | None = None
SCORED_HIGHLIGHT_KEYS = ("surface_move", "distance_up", "incident_wide", "incident_medical", "draw_style_misfit")


def load_battlefield(path=None) -> dict:
    """HKJC_Sections/battlefield.json（hkjc_pit_sections_build 每晚重建）；冇就空。"""
    global _BATTLEFIELD
    if path is None and _BATTLEFIELD is not None:
        return _BATTLEFIELD
    import json
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / "HKJC_Sections" / "battlefield.json"
    p = Path(path)
    try:
        _BATTLEFIELD = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        _BATTLEFIELD = {}
    return _BATTLEFIELD


def _nos(items) -> str:
    return "、".join(f"{n} 號" for n in items)


def battlefield(logic_data: dict, table: dict | None = None) -> dict | None:
    """戰場全景（Kelvin 2026-11-17）：呢個場地路程 2019 起歷史上邊種跑法／檔位段上名多，加今場邊幾匹屬於邊類。"""
    from .surface_move import SURFACE_NAME, today_surface
    from .run_style import classify  # noqa: F401  (標準嚟自 run_style.py，表都係用佢計)
    ra = logic_data.get("race_analysis") or {}
    surface = today_surface(ra)
    m = re.search(r"\d{3,4}", str(ra.get("distance") or ""))
    if not surface or not m:
        return None
    dist = int(m.group())
    table = table if table is not None else load_battlefield()
    cell = ((table or {}).get("cells") or {}).get(f"{surface}|{dist}")
    horses = logic_data.get("horses") or {}
    styles: dict[str, list] = {"放頭": [], "守中": [], "後上": [], "未明": []}
    draws: dict[str, list] = {"內檔": [], "中檔": [], "外檔": []}
    for no, h in horses.items():
        auto = (h or {}).get("python_auto") if isinstance(h, dict) else None
        if not isinstance(auto, dict):
            continue
        rs = auto.get("run_style") or {}
        styles[rs.get("label") or "未明"].append(no)
        try:
            d = int(str(h.get("barrier") or h.get("draw") or "0").split(".")[0])
        except ValueError:
            d = 0
        if d > 0:
            draws["內檔" if d <= 4 else ("中檔" if d <= 9 else "外檔")].append(no)
    key = lambda n: int(n) if str(n).isdigit() else 999
    return {"surface": SURFACE_NAME.get(surface, surface), "distance": dist, "scenario": scenario_constants(),
            "date": str(ra.get("race_date") or "")[:10], "venue": str(ra.get("venue") or ""),
            "history": cell, "since": (table or {}).get("since"),
            "today_styles": {k: sorted(v, key=key) for k, v in styles.items()},
            "today_draws": {k: sorted(v, key=key) for k, v in draws.items()}}


# 情境（Kelvin 2026-11-17「利咩跑法／利咩欄」；EXP-20261117-08）：純顯示，唔改正式排名同 ROI 頭兩選。
#   上名率 1pp ≈ 0.87 顯示分：校準斜率 b ≈ 0.139 logit／原始分（回放 2020–26 逐季 0.137–0.15），p = 25% 時 1pp = 0.0533 logit，
#   × 顯示尺 DISPLAY_SLOPE。預設幅度 = 「強偏差日」（回放每日每類殘差 90 百分位 ≈ ±10pp）。
#   即場：今日已跑場次每類上名率 − 當日平均，× 0.2（回放：頭半場偏差喺下半場只剩約兩成），上限 ±3pp，每類 ≥ 8 匹先計。
SCENARIO_LOGIT_PER_RAW = 0.139
SCENARIO_STYLE_PP = {"放頭": {"放頭": 10, "守中": 0, "後上": -10}, "守中": {"放頭": -5, "守中": 10, "後上": -5},
                     "後上": {"放頭": -10, "守中": 0, "後上": 10}}
SCENARIO_DRAW_PP = {"利內欄": {"內檔": 10, "中檔": 0, "外檔": -10}, "利中內": {"內檔": 5, "中檔": 5, "外檔": -10},
                    "利中欄": {"內檔": -5, "中檔": 10, "外檔": -5}, "利中外": {"內檔": -10, "中檔": 5, "外檔": 5},
                    "利外欄": {"內檔": -10, "中檔": 0, "外檔": 10}}
SCENARIO_INRACE = {"shrink": 0.2, "cap_pp": 3, "min_starts": 8}


def scenario_constants() -> dict:
    from .scoring import DISPLAY_SLOPE
    p0 = 0.25
    pp = 0.01 / (p0 * (1 - p0)) / SCENARIO_LOGIT_PER_RAW * DISPLAY_SLOPE
    return {"pp_to_display": round(pp, 3), "style": SCENARIO_STYLE_PP, "draw": SCENARIO_DRAW_PP, "inrace": SCENARIO_INRACE}


def _horse_ref(horses: dict, no) -> dict:
    h = horses.get(str(no)) or {}
    return {"no": str(no), "name": str(h.get("horse_name") or "").strip()}


def _refs_text(refs: list[dict], suffix=None) -> str:
    return "、".join(f"{r['no']} {r['name']}".strip() + (suffix(r) if suffix else "") for r in refs)


def _items(logic_data: dict, ranking: list[dict], bf: dict | None) -> list[dict]:
    """全場重點（Kelvin 2026-11-17「唔好淨係講號碼，要講馬名」）：每項 = 分類、標題、內容、涉及嘅馬（號＋名）。"""
    horses = logic_data.get("horses") or {}
    key = lambda n: int(n) if str(n).isdigit() else 999
    items = []
    if ranking:
        top = horses.get(str(ranking[0].get("horse_number"))) or {}
        tags = ((top.get("python_auto") or {}).get("summary") or {}).get("tags") or {}
        good = [t["label"] for t in tags.get("good") or [] if t.get("scored")][:3]
        bad = [t["label"] for t in tags.get("bad") or []][:2]
        if good or bad:
            items.append({"kind": "reasons", "title": "首選理由", "horses": [_horse_ref(horses, ranking[0].get("horse_number"))],
                          "good": good, "bad": bad})
    if bf and bf.get("history"):
        h = bf["history"]
        base = (h.get("base") or {}).get("place") or 0
        st = {k: v["place"] for k, v in (h.get("style") or {}).items() if v}
        dr = {k: v["place"] for k, v in (h.get("draw") or {}).items() if v}
        if st:
            best = max(st, key=st.get)
            fronts = [_horse_ref(horses, n) for n in bf["today_styles"].get("放頭") or []]
            items.append({"kind": "style", "title": "跑法形勢",
                          "text": f"{bf['surface']} {bf['distance']}米歷史（{h.get('races')} 場）{best}最著數：上名率 {st[best]:.0%}（平均 {base:.0%}）",
                          "sub": "今場慣性放頭" if fronts else "今場冇慣性放頭馬", "horses": fronts})
        if dr:
            best, worst = max(dr, key=dr.get), min(dr, key=dr.get)
            refs = [dict(_horse_ref(horses, n), draw=str((horses.get(n) or {}).get("barrier") or "").split(".")[0])
                    for n in bf["today_draws"].get(best) or []]
            items.append({"kind": "draw", "title": "檔位形勢",
                          "text": f"{best}上名率 {dr[best]:.0%}，{worst}只有 {dr[worst]:.0%}",
                          "sub": f"今場{best}", "horses": refs})
    field = sum(1 for h in horses.values() if isinstance(h, dict) and isinstance(h.get("python_auto"), dict))
    groups: dict[tuple, list] = {}
    for no, h in horses.items():
        tags = (((h or {}).get("python_auto") or {}).get("summary") or {}).get("tags") or {} if isinstance(h, dict) else {}
        for tone in ("good", "bad"):
            for t in tags.get(tone) or []:
                if t.get("key") in SCORED_HIGHLIGHT_KEYS:
                    groups.setdefault((t["label"].split("（")[0], tone), []).append(no)
    # 超過半場都有嘅因素唔列（例如全場大部分馬增程）：場內置中之後對排名冇分別
    shown = [(k, v) for k, v in groups.items() if field and len(v) * 2 <= field]
    for (label, tone), nos in sorted(shown, key=lambda kv: len(kv[1]))[:4]:
        items.append({"kind": "factor", "title": label, "tone": tone,
                      "horses": [_horse_ref(horses, n) for n in sorted(nos, key=key)]})
    return items


def _item_line(item: dict) -> str:
    if item["kind"] == "reasons":
        r = item["horses"][0]
        return (f"首選 {r['no']} {r['name']} 主要靠：{'、'.join(item['good']) or '綜合分'}"
                + (f"；要留意：{'、'.join(item['bad'])}" if item["bad"] else ""))
    if item["kind"] == "style":
        return f"{item['text']}；{item['sub']}" + (f"：{_refs_text(item['horses'])}" if item["horses"] else "")
    if item["kind"] == "draw":
        return f"檔位：{item['text']}；{item['sub']}：" + (_refs_text(item["horses"], lambda r: f"（{r['draw']} 檔）") or "冇馬")
    if item["kind"] == "factor":
        return f"{item['title']}（{'加分' if item['tone'] == 'good' else '扣分'}）：{_refs_text(item['horses'])}"
    return item.get("text", "")


def race_summary(ranking: list[dict], logic_data: dict | None = None) -> dict:
    """Field-level read: how clear the top pick is, with its historical hit rate."""
    if len(ranking) < 2:
        return {"lines": [], "items": []}
    scores = [float(item.get("ability_score", 0)) for item in ranking]
    gap = round(scores[0] - scores[1], 1)
    top = ranking[0]
    items = []
    if gap >= CLEAR_GAP:
        tightness = "clear"
        items.append({"kind": "top", "title": "首選", "horses": [{"no": str(top["horse_number"]), "name": top["horse_name"]}],
                      "text": f"拋離第二名 {gap:.1f} 分", "sub": f"呢類場次歷史上首選上名約 {TOP_PICK_PLACE_RATE['clear']:.0%}"})
    else:
        tightness = "close"
        second = ranking[1]
        items.append({"kind": "top", "title": "頭兩名", "horses": [{"no": str(top["horse_number"]), "name": top["horse_name"]},
                                                                {"no": str(second["horse_number"]), "name": second["horse_name"]}],
                      "text": f"只差 {gap:.1f} 分", "sub": f"呢類場次歷史上首選上名約 {TOP_PICK_PLACE_RATE['close']:.0%}"})
    if len(scores) >= 4:
        spread = round(scores[0] - scores[3], 1)
        if spread < 6:
            items.append({"kind": "mix", "title": "混戰", "text": f"頭四名相差 {spread:.1f} 分以內",
                          "horses": [{"no": str(r["horse_number"]), "name": r["horse_name"]} for r in ranking[:4]]})
        if len(scores) >= 5:
            cliff = round(scores[3] - scores[4], 1)
            if cliff >= 4:
                items.append({"kind": "mix", "title": "斷層", "text": f"第四同第五名之間差 {cliff:.1f} 分，頭四名以外較難入位",
                              "horses": [{"no": str(r["horse_number"]), "name": r["horse_name"]} for r in ranking[:4]]})
    bf = battlefield(logic_data) if logic_data else None
    if logic_data:
        items += _items(logic_data, ranking, bf)
    lines = []
    for it in items:
        if it["kind"] == "top":
            names = "、".join(f"[{r['no']}] {r['name']}" for r in it["horses"])
            lines.append(f"{it['title']} {names} {it['text']}（{it['sub']}）")
        elif it["kind"] == "mix":
            lines.append(f"{it['title']}：{it['text']}")
        else:
            lines.append(_item_line(it))
    return {"gap_1_2": gap, "tightness": tightness, "lines": lines, "items": items, "battlefield": bf}


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
    logic_data["python_auto_race_summary"] = race_summary(ranking, logic_data)
