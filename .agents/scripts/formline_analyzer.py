#!/usr/bin/env python3
"""
formline_analyzer.py — 賽績線 判讀核心邏輯
============================================
Modular engine for generating natural Chinese prose from formline (賽績線) data.

Supports both HKJC and AU racing formats.

賽績線 Python 判讀流程:
  1. 提取曾交手對手
  2. 檢查對手其後有沒有再贏
  3. 判斷對手其後是升班、降班、同班再贏
  4. 判斷對手其後贏的是第幾班
  5. 判斷今馬當時輸幾多個馬位
  6. 判斷輸距屬於哪一個層級
  7. 生成對應的敘述文字

Usage (shared by compile templates):
  from formline_analyzer import analyze_formline
  result = analyze_formline(formline_table, margin_map)
"""

from __future__ import annotations
import re
from typing import Any


# ── 輸距分類 ──────────────────────────────────────────────────────────


def classify_margin(margin_val: float) -> dict:
    """Classify a margin value into a category.

    Args:
        margin_val: Margin in lengths (馬位). Can be negative (meaning beat the opponent).

    Returns:
        dict with 'category', 'level', 'text' keys.
    """
    if margin_val <= 0:
        return {
            "category": "beat_opponent",
            "level": "擊敗對手",
            "text": f"當時以約 {abs(margin_val):.1f} 個馬位擊敗對手",
        }
    if margin_val <= 1.0:
        return {
            "category": "very_close",
            "level": "非常接近",
            "text": f"當時只輸約 {margin_val:.1f} 個馬位，屬非常接近表現",
        }
    if margin_val <= 2.5:
        return {
            "category": "close",
            "level": "貼近",
            "text": f"當時約輸 {margin_val:.1f} 個馬位，仍算貼近",
        }
    if margin_val <= 4.0:
        return {
            "category": "moderate",
            "level": "尚可",
            "text": f"當時約輸 {margin_val:.1f} 個馬位，距離不算太遠，仍有參考價值",
        }
    if margin_val <= 6.0:
        return {
            "category": "noticeable",
            "level": "較明顯",
            "text": f"當時約輸 {margin_val:.1f} 個馬位，差距已經較明顯，但仍可反映曾在有質素賽績線中出現",
        }
    return {
        "category": "large",
        "level": "偏大",
        "text": f"當時約輸 {margin_val:.1f} 個馬位，輸距偏大，不宜解讀為接近表現，只能視為賽績線質素參考",
    }


def classify_margin_raw(margin_str: str) -> dict:
    """Parse a margin string (e.g. '6', '2.5', '3/4', '1-1/4') and classify."""
    margin_val = _parse_margin(margin_str)
    return classify_margin(margin_val)


def _parse_margin(margin_str: str) -> float:
    """Parse HKJC/AU margin string to float in lengths.

    Handles formats: '6', '2.5', '3/4', '1-1/4', 'NOSE', 'SH', 'HD', 'NK', etc.
    """
    if not margin_str or margin_str in ("N/A", "-", ""):
        return 99.0

    margin_str = margin_str.strip().upper()

    try:
        return float(margin_str)
    except ValueError:
        pass

    m = re.match(r"^(\d+)?\s*[-–]?\s*(\d)/(\d)$", margin_str)
    if m:
        whole = float(m.group(1)) if m.group(1) else 0
        num = float(m.group(2))
        den = float(m.group(3))
        return whole + num / den

    text_map = {
        "NOSE": 0.05, "SH": 0.1, "SHT": 0.1, "SHORT HEAD": 0.1,
        "HD": 0.2, "HEAD": 0.2, "NK": 0.3, "NECK": 0.3,
        "頭位": 0.2,  # head position / won by a head
        "1/2": 0.5, "1/2L": 0.5, "3/4": 0.75, "3/4L": 0.75,
        "1": 1.0, "1L": 1.0, "1.5": 1.5, "1.5L": 1.5,
        "2": 2.0, "2L": 2.0, "3": 3.0, "3L": 3.0,
        "4": 4.0, "4L": 4.0, "5": 5.0, "5L": 5.0,
        "6": 6.0, "6L": 6.0, "7": 7.0, "7L": 7.0,
        "8": 8.0, "8L": 8.0, "9": 9.0, "9L": 9.0,
        "10": 10.0, "10L": 10.0,
    }
    return text_map.get(margin_str, 99.0)


# ── 對手後續表現分析 ────────────────────────────────────────────────────


def _extract_opponent_name(opponent_str: str) -> str:
    """Extract clean horse name from opponent string like '[1] 增強 (頭馬)'."""
    cleaned = re.sub(r'\[\d+\]\s*', '', opponent_str)
    cleaned = re.sub(r'\(.*?\)', '', cleaned)
    return cleaned.strip()


def _parse_class_movement(next_class: str) -> str:
    """Parse class movement from next_class field.

    Returns one of: 'up_class', 'down_class', 'same_class',
                     'up_multiple', 'down_multiple', 'multiple_classes', 'unknown'
    """
    if not next_class or next_class in ("-", "N/A", "未知"):
        return "unknown"

    has_multiple = "及" in next_class or "、" in next_class

    if "升" in next_class:
        return "up_multiple" if has_multiple else "up_class"
    if "降" in next_class:
        return "down_multiple" if has_multiple else "down_class"
    if "同班" in next_class:
        return "same_class"
    if has_multiple:
        return "multiple_classes"

    return "same_class"


def _is_future_winner(next_performance: str) -> bool:
    """Check if the opponent won again (再贏) based on next_performance."""
    if not next_performance:
        return False
    np_text = str(next_performance).lower()
    if "再贏" in np_text or "再胜" in np_text or "win" in np_text or "won" in np_text:
        return True
    # Check for W-P-S format where W > 0
    m = re.search(r'(\d+)-(\d+)-(\d+)', str(next_performance))
    if m and int(m.group(1)) > 0:
        return True
    # Check for Chinese format "X 勝" where X > 0
    m = re.search(r'(\d+)\s*勝', str(next_performance))
    if m and int(m.group(1)) > 0:
        return True
    # Check for "頭馬" / "first" which implies a win
    if "頭馬" in str(next_performance) or "first" in np_text:
        return True
    return False


def _parse_class_text(next_class: str) -> str:
    """Extract clean class text from next_class field.

    Examples:
      '升班於第三班' → '第三班'
      '同班' → '同班'
      '降班於第四班' → '第四班'
      '第三班及第二班' → '第三班及第二班'
    """
    if not next_class or next_class in ("-", "N/A", "未知"):
        return "未知班次"

    cleaned = next_class.strip()
    cleaned = re.sub(r'^(?:升班於|降班於|同班於|於)', '', cleaned)
    return cleaned.strip()


def _class_movement_text(movement: str) -> str:
    """Convert class movement to Chinese text for inline use."""
    mapping = {
        "up_class": "升班於",
        "down_class": "降班於",
        "same_class": "於同班",
        "multiple_classes": "升班於",
        "unknown": "",
    }
    return mapping.get(movement, "")


def _class_movement_prefix(movement: str, class_text: str) -> str:
    """Build the class-movement prefix for sentences like '其後升班於第三班再贏'."""
    ct = class_text.strip()
    if movement == "same_class" or (ct in ("同班", "")):
        return "於同班"
    if movement in ("up_class", "up_multiple"):
        return f"升班於{ct}"
    if movement in ("down_class", "down_multiple"):
        return f"降班於{ct}"
    if movement == "multiple_classes":
        return f"於{ct}"
    if ct and ct not in ("未知班次", ""):
        return f"於{ct}"
    return "再贏"


def analyze_opponent_future(opponent_name: str, next_class: str,
                             next_performance: str) -> dict:
    """Analyze a single opponent's future performance.

    Returns:
        dict with 'text', 'movement', 'is_winner', 'class_text' keys.
    """
    is_winner = _is_future_winner(next_performance)
    movement = _parse_class_movement(next_class)
    class_text = _parse_class_text(next_class)

    if not is_winner:
        return {
            "text": "",
            "movement": movement,
            "is_winner": False,
            "class_text": class_text,
        }

    if movement in ("multiple_classes", "up_multiple", "down_multiple"):
        if movement == "up_multiple":
            prefix = f"升班於{class_text}"
        elif movement == "down_multiple":
            prefix = f"降班於{class_text}"
        else:
            prefix = f"於{class_text}"
        text = f"{opponent_name}其後{prefix}再贏，後續表現有延續性，令該場賽績線更具參考價值"
    elif movement == "up_class":
        text = f"{opponent_name}其後升班於{class_text}再贏，反映該場賽績線含金量較高"
    elif movement == "down_class":
        text = f"{opponent_name}其後降班於{class_text}再贏，雖然支持力度不及升班再勝，但仍反映該駒本身具備一定贏馬能力"
    elif movement == "same_class":
        text = f"{opponent_name}其後於同班再贏，反映該場賽績線有後續支持"
    else:
        text = f"{opponent_name}其後再贏，反映該場賽績線有後續支持"

    return {
        "text": text,
        "movement": movement,
        "is_winner": True,
        "class_text": class_text,
        "opponent_name": opponent_name,
    }


# ── 輸距文字生成 ──────────────────────────────────────────────────────


def _get_margin_sentence(margin_val: float) -> str:
    """Generate standalone margin sentence based on margin value.

    輸距 | Python 判讀文字
    0-1馬位   | 當時只輸約 {margin} 個馬位，屬非常接近表現
    1.1-2.5   | 當時約輸 {margin} 個馬位，仍算貼近
    2.6-4     | 當時約輸 {margin} 個馬位，距離不算太遠，仍有參考價值
    4.1-6     | 當時約輸 {margin} 個馬位，差距已經較明顯，但仍可反映曾在有質素賽績線中出現
    6+        | 當時約輸 {margin} 個馬位，輸距偏大，不宜解讀為接近表現，只能視為賽績線質素參考
    """
    if margin_val <= 0:
        return f"當時以約 {abs(margin_val):.1f} 個馬位跑先對手"
    if margin_val <= 1.0:
        return f"當時只輸約 {margin_val:.1f} 個馬位，屬非常接近表現"
    if margin_val <= 2.5:
        return f"當時約輸 {margin_val:.1f} 個馬位，仍算貼近"
    if margin_val <= 4.0:
        return f"當時約輸 {margin_val:.1f} 個馬位，距離不算太遠，仍有參考價值"
    if margin_val <= 6.0:
        return f"當時約輸 {margin_val:.1f} 個馬位，差距已經較明顯，但仍可反映曾在有質素賽績線中出現"
    return f"當時約輸 {margin_val:.1f} 個馬位，輸距偏大，不宜解讀為接近表現，只能視為賽績線質素參考"


def _get_margin_sentence_short(margin_val: float) -> str:
    """Short margin sentence (no qualifier), for use inside combination text."""
    if margin_val <= 0:
        return f"當時以約 {abs(margin_val):.1f} 個馬位跑先對手"
    if margin_val <= 1.0:
        return f"當時只輸約 {margin_val:.1f} 個馬位"
    if margin_val <= 2.5:
        return f"當時約輸 {margin_val:.1f} 個馬位"
    if margin_val <= 4.0:
        return f"當時約輸 {margin_val:.1f} 個馬位"
    if margin_val <= 6.0:
        return f"當時約輸 {margin_val:.1f} 個馬位，差距已經較明顯"
    return f"當時約輸 {margin_val:.1f} 個馬位，輸距偏大"


def _format_margins(margins: list[float]) -> str:
    """Format multiple margins for display."""
    formatted = [f"{m:.1f}" for m in margins]
    if len(formatted) == 1:
        return formatted[0]
    return "、".join(formatted)


def _estimate_margin_from_entry(entry: dict) -> float:
    """Estimate margin from formline entry data (fallback)."""
    return 99.0


# ── 賽績線組合模板 ──────────────────────────────────────────────────────
# All combinations follow the 7-spec from the standard.
# Each is a self-contained paragraph builder.


def _build_combination_1(winners, best_margin):
    """Combination 1: Two strong opponents, both won again, margin close (≤4.0).

    Example output:
    呢條賽績線有明顯份量。巴基之勝其後升班於第三班及第二班再贏，閃耀天河其後亦升班
    於第三班及第二班再贏，兩匹曾交手對手其後都有實質延續，反映當日賽事水準不低。
    今馬當時分別約輸 3.0 及 6.0 個馬位，距離仍算有參考價值，代表牠曾經喺一條
    後續證明有質素嘅賽績線中交出可取表現。
    """
    parts = ["呢條賽績線有明顯份量"]
    for opp in winners:
        parts.append(opp["text"])
    parts.append("兩匹曾交手對手其後都有實質延續，反映當日賽事水準不低")
    parts.append(
        f"今馬當時分別約輸 {_format_margins([o['margin'] for o in winners])} "
        f"個馬位，距離仍算有參考價值，代表牠曾經喺一條後續證明有質素嘅賽績線中交出可取表現"
    )
    return "。".join(parts) + "。"


def _build_combination_2(winners, best_margin):
    """Combination 2: Two strong opponents, but margin large (>4.0).

    Example output:
    呢條賽績線本身有份量。巴基之勝其後升班於第三班及第二班再贏，閃耀天河其後亦升班
    於第三班及第二班再贏，兩匹對手其後都能夠延續贏馬表現，證明該場賽事並非普通弱組。
    今馬當時約輸 6 個馬位，輸距已經偏大，不宜解讀為貼近強手。不過，因為對手其後在
    更高層次仍能交出成績，該場賽績線仍然可以作為質素參考。
    """
    parts = ["呢條賽績線本身有份量"]
    for opp in winners:
        parts.append(opp["text"])
    parts.append("兩匹對手其後都能夠延續贏馬表現，證明該場賽事並非普通弱組")
    parts.append(f"今馬當時約輸 {best_margin:.1f} 個馬位，輸距已經偏大，不宜解讀為貼近強手")
    parts.append(
        "不過，因為對手其後在更高層次仍能交出成績，"
        "該場賽績線仍然可以作為質素參考"
    )
    return "。".join(parts) + "。"


def _build_combination_3(winners, best_margin):
    """Combination 3: One opponent won again, margin close (≤4.0).

    Example output:
    賽績線有一定支持。巴基之勝其後升班於第三班及第二班再贏，反映該場對手質素其後
    有延續。今馬當時約輸 2.0 個馬位，距離仍算接近，因此該仗表現具備一定參考價值。
    """
    winner = winners[0]
    class_prefix = _class_movement_prefix(
        winner.get("movement", "same_class"),
        winner.get("class_text", "同班")
    )
    parts = [
        "賽績線有一定支持",
        f"{winner['opponent_name']}其後{class_prefix}再贏，反映該場對手質素其後有延續",
    ]
    if best_margin <= 1.0:
        parts.append(
            f"今馬{_get_margin_sentence_short(best_margin)}，屬非常接近表現，"
            f"因此該仗表現具備一定參考價值"
        )
    elif best_margin <= 4.0:
        parts.append(
            f"今馬當時約輸 {best_margin:.1f} 個馬位，距離仍算接近，"
            f"因此該仗表現具備一定參考價值"
        )
    else:
        parts.append(
            f"今馬當時約輸 {best_margin:.1f} 個馬位，差距已經較明顯，"
            f"因此不能單純解讀為貼近高質對手，只能視為曾經出現在一條有份量賽績線之中"
        )
    return "。".join(parts) + "。"


def _build_combination_4(winners, best_margin):
    """Combination 4: One opponent won again, but margin large (>4.0).

    Example output:
    賽績線有一定質素支持。巴基之勝其後升班於第三班及第二班再贏，證明該對手實力其後
    得到確認。不過，今馬當時約輸 6 個馬位，差距較明顯，因此不能單純解讀為貼近高質
    對手，只能視為曾經出現在一條有份量賽績線之中。
    """
    winner = winners[0]
    class_prefix = _class_movement_prefix(
        winner.get("movement", "same_class"),
        winner.get("class_text", "同班")
    )
    parts = [
        "賽績線有一定質素支持",
        f"{winner['opponent_name']}其後{class_prefix}再贏，證明該對手實力其後得到確認",
        f"不過，今馬當時約輸 {best_margin:.1f} 個馬位，差距較明顯，"
        f"因此不能單純解讀為貼近高質對手，只能視為曾經出現在一條有份量賽績線之中",
    ]
    return "。".join(parts) + "。"


def _build_combination_5(winners, best_margin):
    """Combination 5: Opponent won again after dropping class.

    Example output:
    巴基之勝其後降班於第四班再贏，反映其本身仍有一定贏馬能力。不過，由於後續勝仗
    來自降班，對原賽績線的加分力度較有限。今馬當時約輸 3.0 個馬位，整體只能視為
    一般參考，未足以大幅提升今場評價。
    """
    parts = []
    for opp in winners:
        parts.append(
            f"{opp['opponent_name']}其後降班於 {opp['class_text']} 再贏，"
            f"反映其本身仍有一定贏馬能力"
        )
    parts.append("不過，由於後續勝仗來自降班，對原賽績線的加分力度較有限")
    if best_margin < 99.0:
        parts.append(f"今馬{_get_margin_sentence_short(best_margin)}")
    parts.append("整體只能視為一般參考，未足以大幅提升今場評價")
    return "。".join(parts) + "。"


def _build_combination_6(total_winner_count, best_margin):
    """Combination 6: No meaningful follow-up winner.

    Example output:
    呢條賽績線暫時未見太多後續支持，曾交手對手其後未有明顯再勝表現。今馬當時約輸
    3.0 個馬位，參考價值主要來自自身走勢，而非該場對手其後證明特別有質素。
    """
    parts = [
        "呢條賽績線暫時未見太多後續支持，曾交手對手其後未有明顯再勝表現"
    ]
    if best_margin < 99.0:
        parts.append(f"今馬{_get_margin_sentence_short(best_margin)}")
    parts.append("參考價值主要來自自身走勢，而非該場對手其後證明特別有質素")
    return "。".join(parts) + "。"


def _build_combination_7(best_margin):
    """Combination 7: Multiple future winners, but current horse beaten badly.

    Example output:
    該場賽績線有一定份量，因為當中多匹對手其後再贏，反映整體組別質素不差。不過，
    今馬當時約輸 8.0 個馬位，輸距偏大，代表牠未能真正貼近該組主力馬。呢條線可以
    證明牠曾經面對有質素對手，但不應過度解讀成直接加分。
    """
    parts = [
        "該場賽績線有一定份量，因為當中多匹對手其後再贏，反映整體組別質素不差",
        f"不過，今馬{_get_margin_sentence_short(best_margin)}，代表牠未能真正貼近該組主力馬",
        "呢條線可以證明牠曾經面對有質素對手，但不應過度解讀成直接加分",
    ]
    return "。".join(parts) + "。"


def _build_better_final_sample(winners, best_margin):
    """Better final sample: 2+ strong opponents, margin ~6, with full detail.

    This matches the user's "Better final sample" specification for cases where
    there are strong opponents who went on to win at higher classes, but the
    current horse's margin was notable.

    Example output:
    呢條賽績線有實質份量。巴基之勝其後升班於第三班及第二班再贏，閃耀天河其後亦升班
    於第三班及第二班再贏，反映該場曾交手對手其後有明顯延續，賽事水準得到後續支持。
    今馬當時約輸 6 個馬位，差距已經較明顯，不宜解讀為接近表現。不過，因為對手其後
    能夠在更高班次繼續贏馬，該場賽績線仍可視為有質素參考。
    """
    parts = ["呢條賽績線有實質份量"]
    for opp in winners:
        parts.append(opp["text"])
    parts.append("反映該場曾交手對手其後有明顯延續，賽事水準得到後續支持")
    parts.append(
        f"今馬當時約輸 {best_margin:.1f} 個馬位，差距已經較明顯，不宜解讀為接近表現"
    )
    parts.append(
        "不過，因為對手其後能夠在更高班次繼續贏馬，"
        "該場賽績線仍可視為有質素參考"
    )
    return "。".join(parts) + "。"


# ── 賽績線分析主入口 ──────────────────────────────────────────────────


def analyze_formline(formline_table: list[dict],
                     margin_map: dict[str, float] | None = None,
                     horse_name: str = "此馬",
                     format_style: str = "detailed") -> str:
    """Main entry point: analyze formline data and generate complete analysis text.

    Args:
        formline_table: List of formline entry dicts.
            Each entry should have: opponent_name/opponents, next_class,
            next_performance, strength, margin
        margin_map: Optional dict mapping opponent name → margin in lengths.
        horse_name: Name of the horse being analyzed (used in prose).
        format_style: "detailed" for full analysis, "compact" for summary.

    Returns:
        Complete formline analysis text in Chinese.
    """
    if not formline_table:
        return "未有賽績線數據，無法進行賽績線分析。"

    all_opponents = []
    total_winner_count = 0

    for entry in formline_table:
        opponent_str = entry.get("opponents", entry.get("opponent_name", entry.get("opponent", "")))
        next_class = entry.get("next_class", "")
        next_performance = entry.get("next_performance", "")

        if not opponent_str or str(opponent_str).strip() in ("未知", "-", ""):
            continue

        opponent_name = _extract_opponent_name(str(opponent_str))
        if not opponent_name:
            continue

        opp_result = analyze_opponent_future(opponent_name, next_class, next_performance)

        if opp_result["is_winner"]:
            total_winner_count += 1

        margin_val = 99.0
        if "margin" in entry and isinstance(entry["margin"], (int, float)):
            margin_val = float(entry["margin"])
        elif margin_map and opponent_name in margin_map:
            margin_val = margin_map[opponent_name]
        else:
            margin_val = _estimate_margin_from_entry(entry)

        opp_result["margin"] = margin_val
        all_opponents.append(opp_result)

    winners = [o for o in all_opponents if o.get("is_winner")]

    margins = [o["margin"] for o in winners if o["margin"] < 99.0]
    best_margin = min(margins) if margins else 99.0
    worst_margin = max(margins) if margins else 99.0

    # Triage: down-class-only winners
    down_class_winners = [o for o in winners if o.get("movement") == "down_class"]
    if down_class_winners and total_winner_count == len(down_class_winners):
        return _build_combination_5(down_class_winners, best_margin)

    # Route based on winner count and margin
    if total_winner_count == 0:
        return _build_combination_6(total_winner_count, best_margin)

    if total_winner_count >= 3 and worst_margin > 6.0:
        return _build_combination_7(worst_margin)

    if total_winner_count >= 2:
        if worst_margin <= 4.0:
            # All opponents were within close range
            return _build_combination_1(winners, best_margin)
        if worst_margin <= 6.0:
            # At least one margin is in the 4.1-6 range
            return _build_better_final_sample(winners, worst_margin)
        # Max margin > 6.0: strong opponents but horse was well beaten
        return _build_combination_2(winners, worst_margin)

    # total_winner_count == 1
    if best_margin <= 4.0:
        return _build_combination_3(winners, best_margin)
    return _build_combination_4(winners, best_margin)


def analyze_formline_from_facts(facts_text: str, horse_block: str) -> str:
    """Convenience wrapper that parses Facts text and generates formline analysis."""
    try:
        from create_hkjc_logic_skeleton import parse_formline_table
    except ImportError:
        return "無法載入賽績線解析工具。"

    formline_table = parse_formline_table(horse_block)
    if not formline_table:
        return "未有賽績線數據。"
    return analyze_formline(formline_table)
