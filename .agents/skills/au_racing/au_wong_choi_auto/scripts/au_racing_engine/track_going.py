"""AU 場地與地況適性（維度 `track`）＋ 濕地 overlay —— 唯一計算位置。

輸入只有三樣（全部賽前 Facts）：
    track_stats_line   `3:1-0-1 | 同程: … | 同場同程: …`   → 第一段 = 同場
    going_stats_line   `12:2-1-3 | 軟地: 7:1-2-0 | 重地: 3:0-0-1` → 第一段 = 好地（冇標籤）
    今日掛牌地況       → bucket 好地／軟地／重地

場地分 = clip(60 + 同場 + 今日濕地, 0, 100)：

    同場     有上名 → min(9, 5.0 × 上名 + 2.4 × 贏)；≥2 戰 0 上名 → −8.81；1 戰 0 上名 → −0.81
    今日濕地 （今日軟地／重地先計，用返嗰個 bucket 嘅往績）
             有上名 → min(10, 0.8 × 上名)，曾贏再 +3.77；≥2 戰 0 上名 → −4.75；1 戰 0 上名 → −4.14
    好地日   唔計地況段。好地往績只做報告：2026-08 A/B（`39155166d`）同 EXP-20261103-01 SPG 都過唔到閘。

截斷紀錄（2026-08 Sportsbet 舊 Facts，例如 `7:`，連生涯都冇贏亞季）：場地分同濕地 overlay 都當冇紀錄。
以前 overlay 當「7 戰 0 上名」（最多 −5 分）。改正喺 3,302 場 good_positional −0.12pp [−0.25, −0.03]，
過唔到 §7；**USER-ACCEPTED**（Kelvin 2026-11-03：「main aim is to have wong choi reflects true ability」），
見 EXP-20261103-03。2026-09 起 live 冇截斷紀錄，所以只改歷史語料。

濕地 overlay（直接加落綜合分，唔改呢個維度分）：今日 soft／heavy 先開；
    今日嗰個濕地 bucket 全份、另一個半份；率 = (上名 + 4 × 0.3758) ÷ (出賽 + 4)；
    14.852 × (率 − 0.3758)，封頂 ±6.1818。冇濕地出賽 = 0。常數同歷史喺 `scoring.py`。

歷史：EXP-20261102-10 逐條消融 —— 同場兩個 0 上名扣分有訊號（剷走 Gold −0.18pp，CI 全負）；
「爛地未經驗證 −6.4」同「重地專項三條」剷走冇代價，已剷。EXP-20261103-02 簡化：剷走由來冇觸發過嘅
乾地扣分（−3.46／−3.0：好地 bucket 永遠冇紀錄）同重複嘅紀錄 parser。
"""
from __future__ import annotations

import re

from .scoring import (WET_FORM_FEATURE_SCALE, WET_FORM_MAX_ABS, WET_FORM_PRIOR, WET_FORM_SHRINK_A,
                      WET_OTHER_BUCKET_WEIGHT, clip_score, parse_record_line)

NEUTRAL = 60.0
# 一個 dict：`au_runtime_micro_ablation` 喺 runtime 逐個 key 改做 0 嚟消融，所以計分時先讀。
WEIGHTS = {
    "same_place": 5.0, "same_win": 2.4, "same_cap": 9.0, "same_nil_many": -8.81, "same_nil_one": -0.81,
    "wet_place": 0.8, "wet_place_cap": 10.0, "wet_win": 3.77, "wet_nil_many": -4.75, "wet_nil_one": -4.14,
}

_FULL_RECORD = re.compile(r"\d+\s*:\s*\d+\s*-\s*\d+\s*-\s*\d+")


def wet_state(going):
    """Heavy → heavy；Soft 7+ → soft7plus；Soft 5–6 → soft56；其他（包括冇數字）→ ""。"""
    m = re.search(r"(Soft|Heavy)\s*([0-9]+)", str(going or ""), re.I)
    if not m:
        return ""
    if m.group(1).lower() == "heavy":
        return "heavy"
    level = int(m.group(2))
    return "soft7plus" if level >= 7 else "soft56" if level >= 5 else ""


def going_bucket(going):
    g = str(going or "")
    if "Heavy" in g or "重" in g:
        return "重地"
    if "Soft" in g or "軟" in g:
        return "軟地"
    return "好地"


def record(text):
    """`3:1-0-1` → {starts, wins, seconds, thirds, places, complete}。
    截斷 `7:` → starts 7、其餘 0、complete False；`N/A`／空 → 全 0。"""
    text = str(text or "").strip()
    if _FULL_RECORD.search(text):
        return {**parse_record_line(text), "complete": True}
    m = re.match(r"(\d+)\s*:", text)
    return {**parse_record_line(""), "starts": int(m.group(1)) if m else 0, "complete": False}


def records(track_stats_line, going_stats_line):
    """→ {同場, 好地, 軟地, 重地: record}。"""
    going = str(going_stats_line or "")
    out = {"同場": record(str(track_stats_line or "").split("|", 1)[0]),
           "好地": record(going.split("|", 1)[0])}
    for label in ("軟地", "重地"):
        m = re.search(rf"{label}:\s*([^|]+)", going)
        out[label] = record(m.group(1) if m else "")
    return out


def _same_part(r):
    w = WEIGHTS
    if not r["complete"]:
        return None
    if r["places"]:
        return min(w["same_cap"], w["same_place"] * r["places"] + w["same_win"] * r["wins"]), "同場有實際上名支持"
    if r["starts"] >= 2:
        return w["same_nil_many"], "同場已有多次出賽但仍未交到成績"
    if r["starts"]:
        return w["same_nil_one"], "有同場出賽紀錄但仍未交到成績"
    return None


def _wet_parts(r, bucket):
    w = WEIGHTS
    if not r["complete"]:
        return []
    if r["places"]:
        parts = [(min(w["wet_place_cap"], w["wet_place"] * r["places"]), f"{bucket}有上名（{r['places']}／{r['starts']}）")]
        if r["wins"]:
            parts.append((w["wet_win"], f"{bucket}曾贏"))
        return parts
    if r["starts"] >= 2:
        return [(w["wet_nil_many"], f"{bucket} {r['starts']} 戰未有前列")]
    if r["starts"]:
        return [(w["wet_nil_one"], f"{bucket} 1 戰未有成績")]
    return []


def track_score(recs, going):
    """recs = `records(...)` → (分數, 同場 parts, 地況 parts)；parts = [(加減, 說明)]。"""
    same = _same_part(recs["同場"])
    same_parts = [same] if same else []
    bucket = going_bucket(going)
    going_parts = _wet_parts(recs[bucket], bucket) if bucket != "好地" else []
    score = NEUTRAL
    for delta, _ in same_parts + going_parts:
        score += delta
    return clip_score(score), same_parts, going_parts


def has_wet_place(recs):
    return bool(recs["軟地"]["places"] or recs["重地"]["places"])


def _wet_buckets(going, going_stats_line):
    """→ ((今日 bucket, 紀錄), (另一個, 紀錄))；今日唔係重地就當軟地。"""
    recs = {k: r if r["complete"] else record("") for k, r in records("", going_stats_line).items()}
    order = ("重地", "軟地") if "heavy" in str(going or "").lower() else ("軟地", "重地")
    return tuple((label, recs[label]) for label in order)


def wet_overlay(going, going_stats_line):
    """濕地往績調整（綜合分加減）；乾地 → 0。"""
    detail = wet_overlay_detail(going, going_stats_line)
    return detail["value"] if detail else 0.0


def wet_overlay_detail(going, going_stats_line):
    """濕地 overlay 嘅明細；乾地 → None。"""
    g = str(going or "")
    if "soft" not in g.lower() and "heavy" not in g.lower():
        return None
    (today, t), (other, o) = _wet_buckets(going, going_stats_line)
    w = WET_OTHER_BUCKET_WEIGHT
    starts = t["starts"] + w * o["starts"]
    places = t["places"] + w * o["places"]
    rate = (places + WET_FORM_SHRINK_A * WET_FORM_PRIOR) / (starts + WET_FORM_SHRINK_A)
    value = max(-WET_FORM_MAX_ABS, min(WET_FORM_MAX_ABS, WET_FORM_FEATURE_SCALE * (rate - WET_FORM_PRIOR)))
    return {"going": g, "starts": round(starts, 1), "places": round(places, 1),
            "today_bucket": today, "other_bucket": other,
            "today_record": [t["starts"], t["places"]], "other_record": [o["starts"], o["places"]],
            "rate": round(rate, 4), "prior": WET_FORM_PRIOR, "value": round(value, 4)}


def wet_overlay_line(detail):
    """→ 一句人話；None → ""。"""
    if not detail:
        return ""
    if not detail["starts"]:
        return f"今日 {detail['going']}，本駒未有濕地出賽，濕地往績調整 +0.00（中性）。"
    (ts, tp), (os_, op) = detail["today_record"], detail["other_record"]
    return (f"今日 {detail['going']}：{detail['today_bucket']} {ts} 戰 {tp} 上名（全計）、"
            f"{detail['other_bucket']} {os_} 戰 {op} 上名（半計），收縮後上名率 {detail['rate']:.1%} 對比"
            f"平均 {detail['prior']:.1%} → 濕地往績調整 {detail['value']:+.2f}，直接加落綜合戰力分。")
