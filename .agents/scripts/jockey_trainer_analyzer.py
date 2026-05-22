#!/usr/bin/env python3
"""
jockey_trainer_analyzer.py — 騎練訊號 判讀核心邏輯
====================================================
Modular engine for generating natural Chinese prose from jockey/trainer data.

Produces analysis in four blocks:
1. 騎師安排 (Jockey change analysis)
2. 人馬配搭 (Horse-jockey partnership history)
3. 馬房近態 (Trainer recent form)
4. Final conclusion combining all three

騎練訊號 Python 輸出結構 (每次輸出順序):
  騎練訊號
  - {jockey_change_sentence}
  - {horse_jockey_record_sentence}
  - {trainer_form_sentence}
  - {final_jockey_trainer_conclusion}

Usage:
  from jockey_trainer_analyzer import analyze_jockey_trainer
  result = analyze_jockey_trainer(...)
"""

from __future__ import annotations
import re
from typing import Any


# ── 騎師安排 ──────────────────────────────────────────────────────────


def analyze_jockey_change(jockey: str, last_jockey: str | None,
                          first_time: bool = False) -> dict:
    """Analyze the jockey change situation.

    Args:
        jockey: Current race jockey name.
        last_jockey: Jockey from last start (None if unknown).
        first_time: True if this is first time jockey rides this horse.

    Returns:
        dict with 'text' and 'type' keys.
        type: 'same', 'change', 'first_time', 'unknown'
    """
    if not last_jockey or last_jockey in ("N/A", "未知", ""):
        return {"text": f"今場由 {jockey} 策騎，上仗騎師資料未明。", "type": "unknown"}

    if first_time:
        return {
            "text": f"今場換上 {jockey} 策騎。{jockey} 與此馬屬首次合作，未有實戰配搭數據支持，騎師因素暫時只能作中性處理。",
            "type": "first_time",
        }

    if jockey == last_jockey:
        return {
            "text": f"今場繼續由 {jockey} 策騎，人馬配搭保持不變，穩定性較高。",
            "type": "same",
        }

    return {
        "text": f"今場換上 {jockey} 策騎，上仗由 {last_jockey} 執韁，屬換騎安排。",
        "type": "change",
    }


# ── 人馬配搭 ──────────────────────────────────────────────────────────


def analyze_partnership(jockey: str, horse_name: str,
                        rides: int, wins: int, places: int,
                        avg_finish: float | None = None,
                        last_placing: int | None = None) -> dict:
    """Analyze the jockey-horse partnership history.

    Case A: First time partnership
    Case B: 1 previous ride, poor result
    Case C: 1 previous ride, placed
    Case D: Multiple rides, no win, some placings
    Case E: Multiple rides, with wins
    Case F: Multiple rides, poor record
    Case G: Changed jockey, new jockey has better record (handled separately)

    Returns:
        dict with 'text' and 'verdict' keys.
        verdict: 'positive', 'slightly_positive', 'neutral', 'slightly_negative', 'negative'
    """
    if rides == 0:
        return {
            "text": f"{jockey} 與此馬屬首次合作，未有過往配搭紀錄，暫時難以判斷是否合拍。今場騎師安排屬新配搭，訊號偏中性。",
            "verdict": "neutral",
        }

    if rides == 1:
        if last_placing is not None and last_placing <= 3:
            return {
                "text": f"{jockey} 與此馬過往合作 1 次，該次跑入第 {last_placing} 名，雖然樣本不多，但至少有入位紀錄支持。今場再度合作，配搭可視為中性偏正面。",
                "verdict": "slightly_positive",
            }
        elif last_placing is not None:
            return {
                "text": f"{jockey} 與此馬過往合作 1 次，該次只跑第 {last_placing} 名，未勝亦未入位，暫時未見明確合拍證據。今場雖然換上 {jockey}，但人馬配搭層面未算明顯加分。",
                "verdict": "slightly_negative",
            }
        else:
            return {
                "text": f"{jockey} 與此馬過往合作 1 次，但具體成績未明，暫難判斷配搭默契。",
                "verdict": "neutral",
            }

    # rides >= 2
    if wins > 0:
        avg_str = f"，平均名次第 {avg_finish:.1f}" if avg_finish else ""
        return {
            "text": f"{jockey} 與此馬過往合作 {rides} 次，錄得 {wins} 勝 {places} 入位{avg_str}，人馬配搭有實績支持。今場再度合作，騎師安排屬正面訊號。",
            "verdict": "positive",
        }

    if places > 0:
        avg_str = f"，平均名次第 {avg_finish:.1f}" if avg_finish else ""
        return {
            "text": f"{jockey} 與此馬過往合作 {rides} 次，未有勝仗，但曾經 {places} 次入位{avg_str}，反映配搭有一定穩定性，但贏馬說服力未算強。",
            "verdict": "neutral",
        }

    # rides >= 2, no wins, no placings
    avg_str = f"，平均名次第 {avg_finish:.1f}" if avg_finish else ""
    return {
        "text": f"{jockey} 與此馬過往合作 {rides} 次，未勝未入位{avg_str}，配搭數據偏弱。今場即使再由 {jockey} 策騎，亦難以視為明顯加分。",
        "verdict": "negative",
    }


def analyze_partnership_changed_jockey(jockey: str, last_jockey: str,
                                        horse_name: str,
                                        rides: int, wins: int, places: int,
                                        avg_finish: float | None = None) -> dict:
    """Case G: Changed jockey, but new jockey has better horse record.

    Only use this when the jockey actually has decent record (wins > 0 or places > 0).
    Do NOT use when the only record is 1 ride, 10th place.
    """
    if wins == 0 and places == 0:
        return {"text": "", "verdict": "neutral"}

    avg_str = f"，平均名次第 {avg_finish:.1f}" if avg_finish else ""
    return {
        "text": f"今場換上 {jockey} 策騎，上仗由 {last_jockey} 執韁。從過往紀錄睇，{jockey} 與此馬已有 {rides} 次合作，成績為 {wins} 勝 {places} 入位{avg_str}，屬此馬相對較有依據的配搭之一。",
        "verdict": "positive",
    }


# ── 馬房近態 ──────────────────────────────────────────────────────────


def analyze_trainer_form(trainer: str,
                          recent_win_rate: float | None = None,
                          recent_place_rate: float | None = None,
                          recent_starts: int = 0) -> dict:
    """Analyze trainer's recent form.

    Args:
        trainer: Trainer name.
        recent_win_rate: Win rate in recent period (0.0-1.0).
        recent_place_rate: Place rate in recent period (0.0-1.0).
        recent_starts: Number of starts in recent period.

    Returns:
        dict with 'text' and 'level' keys.
        level: 'strong', 'stable', 'average', 'weak'
    """
    if recent_win_rate is None or recent_place_rate is None or recent_starts < 3:
        return {
            "text": f"{trainer}馬房近期表現尚算平穩，代表馬房狀態未算差，但未見特別強勢。",
            "level": "stable",
        }

    # Strong: win rate >= 20%
    if recent_win_rate >= 0.20:
        return {
            "text": f"{trainer}馬房近期勝率及上名率都有支持，反映馬房狀態正處於較理想水平。",
            "level": "strong",
        }

    # Stable but not explosive: place rate >= 25%
    if recent_place_rate >= 0.25:
        return {
            "text": f"{trainer}馬房近期上名率尚算穩定，反映馬房整體狀態不差。不過勝出率未算突出，因此更多屬穩定性支持，而非強烈贏馬訊號。",
            "level": "stable",
        }

    # Average: place rate >= 15%
    if recent_place_rate >= 0.15:
        return {
            "text": f"{trainer}馬房近期表現中規中矩，未見明顯強勢。今場馬房因素只能作一般支持，未足以單靠此點推高評分。",
            "level": "average",
        }

    # Weak
    return {
        "text": f"{trainer}馬房近期勝率及上名率偏低，整體狀態未見突出。即使今場騎師安排合理，馬房近態仍未能提供太大加分。",
        "level": "weak",
    }


# ── 最終騎練訊號組合 ──────────────────────────────────────────────────


def analyze_jockey_trainer(
    jockey: str,
    last_jockey: str | None,
    horse_name: str,
    trainer: str,
    partnership_rides: int = 0,
    partnership_wins: int = 0,
    partnership_places: int = 0,
    partnership_avg_finish: float | None = None,
    partnership_last_placing: int | None = None,
    trainer_win_rate: float | None = None,
    trainer_place_rate: float | None = None,
    trainer_recent_starts: int = 0,
) -> dict:
    """Main entry point: full jockey-trainer analysis producing four blocks.

    Returns:
        dict with keys:
        - 'jockey_change': 騎師安排 sentence
        - 'partnership': 人馬配搭 sentence
        - 'trainer_form': 馬房近態 sentence
        - 'conclusion': Final combined verdict
        - 'blocks': Ordered list of all four blocks
    """
    # Block 1: 騎師安排
    first_time = (partnership_rides == 0)
    same_jockey = bool(last_jockey and jockey == last_jockey)

    jockey_change = analyze_jockey_change(jockey, last_jockey, first_time)

    # Block 2: 人馬配搭
    if first_time:
        partnership = analyze_partnership(
            jockey, horse_name, 0, 0, 0, None, None
        )
    elif same_jockey:
        partnership = analyze_partnership(
            jockey, horse_name,
            partnership_rides, partnership_wins, partnership_places,
            partnership_avg_finish, partnership_last_placing,
        )
    elif partnership_wins > 0 or partnership_places > 0:
        # Changed jockey but new jockey has some record — check if meaningful
        partnership = analyze_partnership_changed_jockey(
            jockey, last_jockey or "", horse_name,
            partnership_rides, partnership_wins, partnership_places,
            partnership_avg_finish,
        )
        if not partnership["text"]:
            # Fallback to standard partnership analysis if not meaningful
            partnership = analyze_partnership(
                jockey, horse_name,
                partnership_rides, partnership_wins, partnership_places,
                partnership_avg_finish, partnership_last_placing,
            )
    else:
        partnership = analyze_partnership(
            jockey, horse_name,
            partnership_rides, partnership_wins, partnership_places,
            partnership_avg_finish, partnership_last_placing,
        )

    # Block 3: 馬房近態
    trainer_form = analyze_trainer_form(
        trainer,
        recent_win_rate=trainer_win_rate,
        recent_place_rate=trainer_place_rate,
        recent_starts=trainer_recent_starts,
    )

    # Block 4: Conclusion
    conclusion = _build_conclusion(
        jockey, last_jockey, horse_name, trainer,
        jockey_change, partnership, trainer_form,
        partnership_rides, partnership_wins, partnership_places,
        partnership_avg_finish, partnership_last_placing,
        same_jockey, first_time,
    )

    blocks = [
        jockey_change["text"],
        partnership["text"],
        trainer_form["text"],
        conclusion,
    ]
    blocks = [b for b in blocks if b]

    return {
        "jockey_change": jockey_change["text"],
        "partnership": partnership["text"],
        "trainer_form": trainer_form["text"],
        "conclusion": conclusion,
        "blocks": blocks,
    }


def _build_conclusion(
    jockey: str, last_jockey: str | None, horse_name: str, trainer: str,
    jockey_change: dict, partnership: dict, trainer_form: dict,
    partnership_rides: int, partnership_wins: int, partnership_places: int,
    partnership_avg_finish: float | None,
    partnership_last_placing: int | None,
    same_jockey: bool, first_time: bool,
) -> str:
    """Build the final conclusion combining all three blocks.

    Uses 7 combination templates from the standard.
    """
    t_level = trainer_form.get("level", "stable")
    p_verdict = partnership.get("verdict", "neutral")
    t_text = trainer_form.get("text", "")

    # ── Combination 1: Change jockey, first time partnership, stable/average trainer ──
    if not same_jockey and first_time and t_level in ("stable", "average"):
        return (
            f"整體騎練訊號只屬中性偏穩。{t_text} 不過，由於人馬配搭未有實績支持，"
            f"整體騎練訊號只屬中性偏穩。"
        )

    # ── Combination 2: Change jockey, one bad previous ride ──
    if not same_jockey and p_verdict == "slightly_negative" and t_level in ("stable", "average"):
        return (
            f"整體而言，今場騎練配置算正常，"
            f"但 {jockey} 與此馬過往實績有限，暫時未足以構成明顯加分。"
        )

    # ── Combination 3: Same jockey, strong partnership ──
    if same_jockey and p_verdict in ("positive", "slightly_positive"):
        return (
            f"整體騎練訊號偏正面，屬今場其中一項加分位。"
        )

    # ── Combination 4: Same jockey, poor partnership ──
    if same_jockey and p_verdict == "negative":
        return (
            f"整體而言，{jockey} 與此馬過往數據偏弱，"
            f"騎練組合本身仍未算有明顯加分。"
        )

    # ── Combination 5: Changed to a strong jockey, no horse-specific record ──
    if not same_jockey and first_time and t_level == "strong":
        return (
            f"整體騎練訊號合理，騎師安排可視為中性偏正面，"
            f"但仍需要賽事形勢配合。"
        )

    # ── Combination 6: Strong trainer, weak jockey partnership ──
    if t_level == "strong" and p_verdict in ("negative", "slightly_negative"):
        return (
            f"整體騎練訊號有馬房支持，但騎師配搭未能進一步推高評價。"
        )

    # ── Combination 7: Weak trainer, decent jockey partnership ──
    if t_level == "weak" and p_verdict in ("positive", "slightly_positive"):
        return (
            f"今場騎師安排有支持，但馬房近態會削弱整體騎練訊號。"
        )

    # ── Default: neutral ──
    if not same_jockey:
        return (
            f"整體騎練訊號屬中性，配置合理，但不足以單靠騎練組合推高評分。"
        )

    return "整體騎練訊號屬中性偏穩。"
