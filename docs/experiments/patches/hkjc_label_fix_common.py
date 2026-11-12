"""EXP-20261112-16／-17／-18 共用：三個「名不副實」標籤嘅修正版計法（跑 A/B 之前寫死）。

16 引擎型態：每仗分段先減馬會標準分段（同場地、路程、班次），再用原本嘅分類同門檻。
    原版（`inject_hkjc_fact_anchors._classify_pace_shape`）3 段或以下嘅賽事連短頭段一齊比，所以由路程決定
    （1000m 一律快開慢收、1200m 一律漸進加速）。減咗標準之後，頭段長短唔再影響。
    標準：今仗班次優先，搵唔到用嗰仗自己班次（同 past_runs.std_pace）；冇標準嘅仗唔計。
    聚合（近 6 仗、≥ 50% 主導、≥ 70% 高信心、< 4 仗低信心）同字串格式同原版一模一樣。
17 對手後續更高班再贏：同**嗰場對碰時嘅班次**比（唔係今仗班次）。賽績線表只列對手之後跑過嘅班次、唔話贏喺邊班，
    所以只喺確定嘅情況先分類：之後跑過嘅班次**全部**高過原場 → 更高班；**全部**低過 → 較低班；其餘 → 同班；
    原場班次搵唔到 → unknown（唔加減分）。
18 體重微增／微減 +1：上游「微增／微減」其實係波幅 > 5 磅、「穩定」係 ≤ 5 磅（方向調轉）。
    修正：+1 改畀「穩定」；「微增／微減」唔再加分。
"""
from __future__ import annotations

import re
from datetime import datetime

PACE_LABELS = ("均速型", "漸進加速", "快開慢收", "慢開快收", "波動型")


def classify_pace_shape(diffs):
    """同原版 `_classify_pace_shape` 一樣嘅門檻，但輸入係「分段 − 標準分段」，唔使跳頭段。"""
    if len(diffs) < 2:
        return "未知"
    mid = len(diffs) // 2
    first = sum(diffs[:mid]) / max(mid, 1)
    second = sum(diffs[mid:]) / max(len(diffs) - mid, 1)
    diff = second - first
    if abs(diff) < 0.3:
        return "均速型 ✅"
    if diff < -0.3:
        return "漸進加速 ✅"
    if diff > 0.5:
        return "快開慢收 ⚠️"
    return "波動型 ➖"


def engine_type_vs_standard(runs, today_class, run_classes):
    """runs = past_runs.parse_formguide 嘅仗（新到舊、已過濾賽日之前）。返回同上游一樣格式嘅字串，或者 None。"""
    from hkjc_racing_engine import past_runs

    counts = {k: 0 for k in PACE_LABELS}
    valid = 0
    for run in runs[:6]:
        splits = run.get("splits") or []
        if len(splits) < 3:
            continue
        std = past_runs.standard_sections(run["venue"], run["awt"], run["distance"], today_class) or \
            past_runs.standard_sections(run["venue"], run["awt"], run["distance"], run_classes.get(run["date"]))
        if not std or len(std) != len(splits):
            continue
        shape = classify_pace_shape([a - b for a, b in zip(splits, std)])
        valid += 1
        for key in counts:
            if key in shape:
                counts[key] += 1
                break
    if valid < 2:
        return f"混合型 | 信心: 低 | 依據: 段速數據不足 ({valid} 場有標準可比)"
    accel = counts["漸進加速"] + counts["慢開快收"]
    dominant = max([("均速型", counts["均速型"]), ("漸進加速型", accel), ("快開慢收型", counts["快開慢收"])], key=lambda x: x[1])
    if dominant[1] >= valid * 0.5 and dominant[1] >= 2:
        kind, conf = dominant[0], ("高" if dominant[1] >= valid * 0.7 else "中")
        evidence = [f"近{valid}場對標準段速剖面 {dominant[1]}/{valid} 場{dominant[0]}"]
    else:
        kind, conf = "混合型", "低"
        evidence = [f"均速{counts['均速型']}/加速{accel}/快開慢收{counts['快開慢收']} (共{valid}場，對標準)"]
    if valid < 4:
        conf = "低"
        evidence.append(f"樣本量少 ({valid} 場)")
    return f"{kind} | 信心: {conf} | 依據: {'; '.join(evidence)}"


def run_classes_from_recent(recent_6_detail):
    out = {}
    for d, cls in re.findall(r"第\d仗\((\d{2}/\d{2}/\d{4})\s+([^)]*?)\)", str(recent_6_detail or "")):
        try:
            out[datetime.strptime(d, "%d/%m/%Y").date()] = cls.strip()
        except ValueError:
            continue
    return out


def formline_rows_with_dates(section_text):
    """賽績線表（Facts）逐行，連日期（續行繼承上一行日期）。"""
    marker = "🔗 **賽績線:**"
    start = section_text.find(marker)
    if start < 0:
        return []
    rows, in_table, cur_date = [], False, None
    for line in section_text[start:].splitlines():
        if line.startswith("| # | 日期 | 賽事 |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if set(line.replace("|", "").strip()) == {"-"}:
            continue
        cols = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cols) < 8:
            continue
        if cols[1]:
            try:
                cur_date = datetime.strptime(cols[1], "%d/%m/%y").date()
            except ValueError:
                cur_date = None
        rows.append({"date": cur_date, "opponent": cols[4], "class_text": cols[5], "result_text": cols[6]})
    return rows


def formline_counts_vs_original(section_text, recent_6_detail, class_rank, rank_tokens):
    """{higher, same, lower} 對手數（每個對手攞最好嗰行），同原場班次比。class_rank = orchestrator._class_rank。"""
    by_date = run_classes_from_recent(recent_6_detail)
    best = {}
    order = {"higher": 0, "same": 1, "lower": 2, "unknown": 3}
    for row in formline_rows_with_dates(section_text):
        m = re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", row["result_text"])
        if not m or int(m.group(1)) <= 0:
            continue
        nm = re.search(r"\]\s*([^(]+)", row["opponent"])
        name = (nm.group(1) if nm else row["opponent"]).strip()
        if not name:
            continue
        orig = class_rank(by_date.get(row["date"])) if row["date"] else None
        later = [rank for token, rank in rank_tokens.items() if token in row["class_text"]]
        if orig is None or not later:
            bucket = "unknown"
        elif max(later) < orig:          # 數字細 = 班次高；最低嗰班都高過原場
            bucket = "higher"
        elif min(later) > orig:          # 最高嗰班都低過原場
            bucket = "lower"
        else:
            bucket = "same"
        if name not in best or order[bucket] < order[best[name]]:
            best[name] = bucket
    vals = list(best.values())
    return {"higher": vals.count("higher"), "same": vals.count("same"), "lower": vals.count("lower"),
            "unknown": vals.count("unknown")}


def weight_trend_tail(text):
    t = str(text or "")
    return t.split(" → ")[-1] if " → " in t else t
