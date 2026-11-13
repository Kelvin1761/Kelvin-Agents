"""AU 每匹馬嘅「加分位／扣分位／留意」標籤 —— 純顯示，評分完先做，永遠唔郁分數。

同 HKJC `hkjc_racing_engine/tags.py` 一樣嘅格式（Kelvin 2026-11-13：「AU dashboard 都要有首本路程、騎練黃金組合呢類標籤」）：
每個 chip 係一句具體事實，分清楚：

  * ``scored=True``  —— 引擎真係為呢樣嘢加／扣咗分（``impact`` = 對綜合分嘅影響，原始尺）。
  * ``scored=False`` —— 賽前事實，**冇入分**，只供參考（例如首本路程：AU 路程分唔入排名）。
    dashboard 畫成虛線 chip，tooltip 寫「未入分」。

三種語氣：``good``（有利）、``bad``（不利）、``note``（中性事實）。資料全部係賽前 Facts／Formguide 已有嘅欄位，
同引擎評分用同一份。任何一步出錯都只會少咗標籤（``build`` 包住晒），唔會令評分失敗。
"""
from __future__ import annotations

import re

from .dimensions import MATRIX_FORMULAS
from .scoring import MATRIX_WEIGHTS, parse_placing
from . import track_going as _track

SPECIALIST_MIN_STARTS = 3      # 首本路程／場地專家：最少 3 仗
SPECIALIST_PLACE_RATE = 0.4    # …上名率 ≥ 40% 或者勝出率 ≥ 25%（同 HKJC 一樣）
SPECIALIST_WIN_RATE = 0.25
COMBO_MIN_RUNS = 8             # 騎練黃金組合：同場騎練組合最少 8 次
COMBO_GOOD_RATE = 0.5          # …上名率 ≥ 50%
COMBO_WEAK_RUNS = 10
COMBO_WEAK_RATE = 0.15         # 騎練組合弱：≥ 10 次而上名率 ≤ 15%
DRIVER_FLOOR = 0.5             # 維度影響細過呢個唔寫
OVERLAY_FLOOR = 0.5            # 濕地／檔位 overlay 細過呢個唔寫
LONG_SPELL_DAYS = 90

# 人馬配搭入分項（`jockey_trainer.fit_parts` 嘅因子）→ 標籤
_FIT_TAGS = {
    "沿用歷來最佳人馬配搭": "人馬合拍（沿用最佳配搭）",
    "現役騎師對此駒配合率偏高": "人馬合拍",
    "試閘手接手，備戰線完整": "試閘手接手",
}


def _tag(key, label, tone, *, why="", scored=False, impact=None):
    return {"key": key, "label": label, "tone": tone, "why": why, "scored": scored,
            "impact": None if impact is None else round(float(impact), 2)}


def _record_text(line, label):
    m = re.search(rf"{label}:\s*([^|]+)", str(line or ""))
    return m.group(1).strip() if m else ""


def _good_record(r):
    if not r.get("complete") or r["starts"] < SPECIALIST_MIN_STARTS:
        return False
    return (r["places"] / r["starts"] >= SPECIALIST_PLACE_RATE
            or r["wins"] / r["starts"] >= SPECIALIST_WIN_RATE)


def _rec_text(r):
    return f"{r['starts']}戰{r['wins']}勝{r['places']}上名"


def _dim_impact(matrix_scores, key):
    w = MATRIX_WEIGHTS.get(key)
    if w is None:
        return None
    return (float(matrix_scores.get(key, 60.0)) - 60.0) * float(w)


def _leaf_impact(matrix_scores, dim, leaf, delta):
    """一個 leaf 加減 `delta` 分對綜合分嘅影響 = delta × 維度內份額 × 維度係數。"""
    share = dict(MATRIX_FORMULAS.get(dim) or ()).get(leaf)
    w = MATRIX_WEIGHTS.get(dim)
    if share is None or w is None:
        return None
    return float(delta) * float(share) * float(w)


def _distance_tags(eng):
    out = []
    dist = eng._distance_m()
    line = eng.data.get("track_stats_line")
    same_dist = _track.record(_record_text(line, "同程"))
    if dist and _good_record(same_dist):
        out.append(_tag("specialist", f"首本路程（{dist}米 {_rec_text(same_dist)}）", "good",
                        why=f"同程 {dist}米 {_rec_text(same_dist)}；AU 路程分唔入排名，未入分。"))
    elif dist and same_dist.get("complete") and same_dist["starts"] == 0 and eng._career_starts() >= 3:
        out.append(_tag("first_distance", f"初跑{dist}米", "note", why=f"生涯 {eng._career_starts()} 仗從未跑過 {dist}米；未入分。"))
    trip = ((getattr(eng, "form_quality_detail", {}) or {}).get("trip_change") or {})
    if trip.get("delta"):
        word = "升程" if float(trip["today"]) > float(trip["last"]) else "縮程"
        out.append(_tag("distance_move", f"大幅{word}（{float(trip['last']):.0f}→{float(trip['today']):.0f}米）", "bad",
                        why=f"上仗 {float(trip['last']):.0f}米、今仗 {float(trip['today']):.0f}米，近績質素分扣 {abs(float(trip['delta'])):.0f}。",
                        scored=True, impact=_leaf_impact({}, "stability", "form_quality_score", trip["delta"])))
    return out


def _track_tags(eng, wet_feature):
    out = []
    recs = eng._track_records()
    same = recs["同場"]
    venue = eng._current_venue_name()
    part = _track._same_part(same)
    if venue and _good_record(same):
        impact = _leaf_impact({}, "track", "track_score", part[0]) if part else None
        out.append(_tag("venue_specialist", f"場地專家（{venue} {_rec_text(same)}）", "good",
                        why=f"{venue} {_rec_text(same)}；場地與地況適性有加分。", scored=bool(impact and impact > 0),
                        impact=impact))
    elif venue and same.get("complete") and same["starts"] >= 2 and not same["places"]:
        impact = _leaf_impact({}, "track", "track_score", part[0]) if part else None
        out.append(_tag("venue_poor", f"同場未上過名（{venue} {same['starts']}戰）", "bad",
                        why=f"{venue} 跑過 {same['starts']} 次都未上名；場地與地況適性有扣分。", scored=True, impact=impact))
    wet = float(wet_feature or 0.0)
    if abs(wet) >= OVERLAY_FLOOR:
        detail = _track.wet_overlay_detail(eng._today_going(), eng.data.get("going_stats_line")) or {}
        ev = f"濕地 {detail.get('starts', 0):g} 戰 {detail.get('places', 0):g} 上名（另一種濕地半計）"
        out.append(_tag("wet", "濕地好手" if wet > 0 else "濕地未證明", "good" if wet > 0 else "bad",
                        why=f"今日 {eng._today_going()}：{ev}，濕地往績調整 {wet:+.2f}。", scored=True, impact=wet))
    return out


def _people_tags(eng):
    out = []
    seen = set()
    for adj in (getattr(eng, "jt_fit_detail", {}) or {}).get("adjustments") or []:
        label = _FIT_TAGS.get(adj.get("factor"))
        if label and label.startswith("人馬合拍"):
            if "人馬合拍" in seen:
                continue
            seen.add("人馬合拍")
        if label and float(adj.get("delta") or 0) > 0:
            out.append(_tag(f"fit:{adj['factor']}", label, "good", why=str(adj.get("evidence") or ""),
                            scored=True, impact=_leaf_impact({}, "jockey_trainer", "jockey_horse_fit_score", adj["delta"])))
    combo = eng._current_track_combo_stats() or {}
    runs = int(combo.get("runs") or 0)
    rate = float(combo.get("place_rate") or 0.0)
    venue = eng._current_venue_name()
    if runs >= COMBO_MIN_RUNS and rate >= COMBO_GOOD_RATE:
        out.append(_tag("combo_elite", "騎練黃金組合", "good",
                        why=f"{venue} 同場騎練 {runs} 次、{combo.get('wins', 0)} 勝 {combo.get('places', 0)} 上名（{rate:.0%}）；未入分。"))
    elif runs >= COMBO_WEAK_RUNS and rate <= COMBO_WEAK_RATE:
        out.append(_tag("combo_weak", "騎練組合弱", "bad",
                        why=f"{venue} 同場騎練 {runs} 次只 {combo.get('places', 0)} 次上名（{rate:.0%}）；未入分。"))
    return out


def _draw_tag(eng, draw_feature):
    d = float(draw_feature or 0.0)
    if abs(d) < OVERLAY_FLOOR:
        return []
    barrier = str(eng.horse_data.get("barrier") or "").strip()
    label = ("好檔" if d > 0 else "外檔蝕位") + (f"（{barrier}檔）" if barrier else "")
    return [_tag("draw", label, "good" if d > 0 else "bad", why=f"大場次檔位 {d:+.2f}，直接加落綜合分。",
                 scored=True, impact=d)]


def _prep_tags(eng):
    out = []
    spell = eng._spell_days()
    if spell and spell > LONG_SPELL_DAYS and eng._career_starts() > 0:
        out.append(_tag("long_spell", f"久休 {spell} 日復出", "note", why="出賽間隔分只係 ±1，唔影響排名；未入分。"))
    if eng._career_starts() == 0:
        out.append(_tag("debut", "初出馬", "note", why="冇正式賽往績，評分主要靠試閘同騎練；未入分。"))
    if "form_flattered" in set(getattr(eng, "risk_flags", []) or []):
        out.append(_tag("form_flattered", "近績名次好睇過實際", "note",
                        why="有計分近仗名次好睇但實際居後半或輸超過 5 個馬位；只作標示，未入分。"))
    return out


def _driver_label(eng, key, good):
    if key == "stability":
        form = [parse_placing(e.get("placing")) for e in (eng._official_entries() or [])[:3]]
        form = [str(int(x)) for x in form if x]
        # 近績穩定性 = 近 6 仗名次百分位 ＋ 獎金級別，對比同場；贏低班都可以低過同場，所以唔寫「近績好／差」。
        return ("近績質素高過同場" if good else "近績質素低過同場") + (f"（近3仗 {'-'.join(form)}）" if form else "")
    if key == "pace_perf":
        return "末段速度快" if good else "末段速度慢"
    if key == "jockey_trainer":
        jockey = eng._clean_identity(eng.horse_data.get("jockey"))
        return ("騎練實績強" if good else "騎練實績弱") + (f"（{jockey}）" if jockey else "")
    if key == "class_weight":
        return "官方評分佔優" if good else "官方評分蝕底"
    if key == "track":
        return "場地往績好" if good else "場地往績差"
    if key == "preparation":
        return "試閘備戰充足" if good else "試閘備戰弱"
    return ""


def _driver_tags(eng, matrix_scores, covered):
    out = []
    for key in MATRIX_WEIGHTS:
        impact = _dim_impact(matrix_scores, key)
        if impact is None or abs(impact) < DRIVER_FLOOR or key in covered:
            continue
        good = impact > 0
        label = _driver_label(eng, key, good)
        if label:
            out.append(_tag(f"dim:{key}", label, "good" if good else "bad",
                            why=f"呢個維度對綜合分 {impact:+.1f}。", scored=True, impact=impact))
    return out


def build(eng, matrix_scores, *, wet_feature=0.0, draw_feature=0.0):
    """→ {"good": [...], "bad": [...], "note": [...]}；出錯 → {"_error": ...}。永遠唔郁分數。"""
    try:
        special = (_distance_tags(eng) + _track_tags(eng, wet_feature) + _people_tags(eng)
                   + _draw_tag(eng, draw_feature) + _prep_tags(eng))
        covered = set()
        if any(t["key"] in ("venue_specialist", "venue_poor") for t in special):
            covered.add("track")          # 場地維度由「場地專家／同場未上名」講晒
        tags = _driver_tags(eng, matrix_scores, covered) + special
        order = lambda t: (not t["scored"], -abs(t["impact"] or 0))  # noqa: E731
        return {tone: sorted([t for t in tags if t["tone"] == tone], key=order) for tone in ("good", "bad", "note")}
    except Exception as exc:  # 純顯示：出錯就冇標籤
        return {"_error": f"{type(exc).__name__}: {exc}"}
