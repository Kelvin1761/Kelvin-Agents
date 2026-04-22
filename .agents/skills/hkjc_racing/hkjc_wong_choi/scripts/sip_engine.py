#!/usr/bin/env python3
"""
SIP Engine — Systemic Improvement Proposals Auto-Evaluator (V2.0)
=================================================================
Streamlined SIP engine after 2026-04-22 audit.

V2.0 Changes:
  - RETIRED: SIP-01 (no structured health data), SIP-06 (dead code),
    SIP-07 (duplicate of MC engine)
  - SIMPLIFIED: SIP-02 → race_context flag (is_straight_1000m)
  - MOVED: SIP-05 → post-analysis verdict guard
  - REFACTORED: SIP-04 → reads Facts.md structured data only
  - KEPT: SIP-08 (MC divergence safety net)

Remaining SIPs:
  Horse-level: SIP-04 (Zero Win Breakout)
  Race-level:  SIP-08 (Divergence Force Review)
  Context:     is_straight_1000m flag (replaces SIP-02)
  Verdict:     class_drop_cluster guard (replaces SIP-05)

Usage:
    from sip_engine import evaluate_horse_sips, evaluate_race_sips
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')

import re


# ============================================================
# SIP-04: Zero Win Breakout Candidate (V2 — Facts.md driven)
# ============================================================

def check_sip04_zero_win_breakout(horse: dict, race_context: dict) -> dict:
    """
    WHEN: wins == 0 AND starts >= 3
      AND positive Facts-based indicators:
        - margin_trend contains 收窄 (closing gap)
        - OR formline_strength contains 強 (strong formline)
        - OR recent_form shows improving positions
      AND barrier <= field_size * 0.5
    THEN: Unlock ceiling to B+, tag ZERO_WIN_BREAKOUT_CANDIDATE

    V2: No longer depends on matrix scores or core_logic keywords.
        Uses pre-filled Facts.md data only (wins, starts, margin_trend,
        formline_strength, recent_form, barrier).
    """
    wins = horse.get('wins', None)
    if wins is None:
        return {}

    if isinstance(wins, str):
        try:
            wins = int(wins)
        except ValueError:
            return {}

    if wins > 0:
        return {}

    starts = horse.get('starts', 0)
    if isinstance(starts, str):
        try:
            starts = int(starts)
        except ValueError:
            starts = 0

    if starts < 3:
        return {}

    # V2: Check positive indicators from Facts.md structured data only
    positive_indicators = 0
    indicator_details = []

    # 1. Margin trend (from Facts.md 頭馬距離趨勢)
    margin_trend = str(horse.get('margin_trend', ''))
    if '收窄' in margin_trend or '📈' in margin_trend:
        positive_indicators += 1
        indicator_details.append('頭馬距離收窄')

    # 2. Formline strength (from Facts.md 綜合評估)
    formline = str(horse.get('formline_strength', ''))
    if '強' in formline or '✅✅' in formline or '✅' in formline:
        positive_indicators += 1
        indicator_details.append(f'賽績線={formline[:20]}')

    # 3. Recent form trend (from Facts.md Last 10)
    recent_form = str(horse.get('recent_form', ''))
    if recent_form and recent_form != 'N/A':
        positions = [int(ch) for ch in recent_form if ch.isdigit()]
        if len(positions) >= 3:
            last3 = positions[-3:]
            # Improving = positions getting smaller (closer to 1st)
            if last3[-1] < last3[-2] < last3[-3]:
                positive_indicators += 1
                indicator_details.append(f'近3仗↗({last3[0]}→{last3[1]}→{last3[2]})')

    if positive_indicators < 1:
        return {}

    # Check barrier (from Facts.md)
    barrier = horse.get('barrier', 99)
    field_size = race_context.get('field_size', 14)
    if isinstance(barrier, int) and barrier > field_size * 0.5:
        return {}

    return {
        'sip': 'SIP-04',
        'name': 'ZERO_WIN_BREAKOUT_CANDIDATE',
        'severity': '🟡',
        'tag': 'ZERO_WIN_BREAKOUT_CANDIDATE',
        'effect': 'Ceiling unlocked to B+ (max)',
        'positive_indicators': positive_indicators,
        'indicator_details': indicator_details,
        'note': '每場最多觸發 2 匹',
    }


# ============================================================
# SIP-08: Divergence Force Review
# ============================================================

def check_sip08_divergence(mc_results: dict, concordance: dict) -> dict:
    """
    WHEN: MC output has FORCE_REVIEW alerts
      OR concordance_level == LOW
    THEN: Marked horses must be mentioned in verdict
    """
    if not concordance:
        return {}

    level = concordance.get('concordance_level', 'HIGH')
    alerts = concordance.get('action_alerts', [])
    divergence = concordance.get('divergence_alerts', [])

    if level != 'LOW' and not alerts and not divergence:
        return {}

    return {
        'sip': 'SIP-08',
        'name': 'DIVERGENCE_FORCE_REVIEW',
        'severity': '🔴',
        'tag': 'MC-LOGIC_DIVERGENCE',
        'concordance_level': level,
        'effects': [
            '被標記馬匹必須在 verdict 中被提及',
            'LOW concordance 時 verdict 必須擴展至 Top6',
        ],
        'alerts': alerts,
        'divergence': divergence,
    }


# ============================================================
# Race Context Flags (replaces SIP-02)
# ============================================================

def get_race_context_flags(race_context: dict) -> dict:
    """
    Generate race-level context flags for work card annotations.
    Replaces SIP-02 (straight course override) with a simple flag.
    MC engine already handles the mechanical adjustments (sigma, barrier reversal).
    """
    flags = {}

    # Straight 1000m detection (was SIP-02)
    distance = race_context.get('distance', 0)
    if isinstance(distance, str):
        m = re.search(r'(\d+)', str(distance))
        distance = int(m.group(1)) if m else 0

    track = str(race_context.get('track', ''))
    is_turf = '草' in track or 'turf' in track.lower() or not track

    if distance <= 1000 and is_turf and distance > 0:
        flags['is_straight_1000m'] = True
        flags['straight_1000m_notes'] = [
            '⚠️ 直路賽：高號碼檔(8-14)統計上有利',
            '⚠️ 直路賽：前領馬≥4匹觸發互燒風險',
            '⚠️ 直路賽：MC 已自動處理 sigma +40% 及檔位反轉',
        ]

    return flags


# ============================================================
# Verdict Guard: Class Drop Cluster (replaces SIP-05)
# ============================================================

def check_class_drop_cluster_guard(ranked_results: list, all_horses: dict) -> dict:
    """
    Post-analysis verdict guard (was SIP-05).
    Call this AFTER rating matrix computation, during verdict generation.

    WHEN: Top4 are all S-Grade AND field has ≥4 class-drop horses
    THEN: Trigger cluster alert, expand to Top6

    Returns guard dict with recommendations, or empty dict if not triggered.
    """
    if len(ranked_results) < 4:
        return {}

    # Count S-grades in top4
    top4_grades = [r.get('final_grade', '') for r in ranked_results[:4]]
    s_count = sum(1 for g in top4_grades if str(g).startswith('S'))

    if s_count < 4:
        return {}

    # Count class-drop horses
    class_drops = 0
    for h_key, h_data in all_horses.items():
        if h_data.get('class_advantage_2bm', False):
            class_drops += 1

    if class_drops < 4:
        return {}

    return {
        'guard': 'CLASS_DROP_CLUSTER',
        'severity': '🔴',
        'effects': [
            '擴大選馬至 Top6',
            '降班馬 class_advantage_bonus 打 7 折 (×0.7)',
            '後上型 (Type B/C) rating +0.3',
        ],
        's_grade_count': s_count,
        'class_drop_count': class_drops,
    }


# ============================================================
# Public API
# ============================================================

def evaluate_horse_sips(horse: dict, race_context: dict) -> list:
    """
    Evaluate per-horse SIP rules.
    V2: Only SIP-04 remains (Facts.md driven).
    Returns list of triggered SIP dicts.
    """
    triggered = []

    sip04 = check_sip04_zero_win_breakout(horse, race_context)
    if sip04:
        triggered.append(sip04)

    return triggered


def evaluate_race_sips(race_context: dict, all_horses: dict,
                       mc_results: dict = None, concordance: dict = None) -> list:
    """
    Evaluate race-level SIP rules.
    V2: Only SIP-08 remains. SIP-02 → context flag, SIP-05 → verdict guard.
    Returns list of triggered SIP dicts.
    """
    triggered = []

    if mc_results and concordance:
        sip08 = check_sip08_divergence(mc_results, concordance)
        if sip08:
            triggered.append(sip08)

    return triggered


def format_sip_summary(horse_sips: list, race_sips: list = None,
                       context_flags: dict = None) -> str:
    """Format triggered SIPs + context flags as a readable work card section."""
    lines = []
    lines.append("## 🛡️ SIP 觸發檢查 [自動]")

    all_sips = (race_sips or []) + horse_sips

    if not all_sips and not context_flags:
        lines.append("- ✅ 無 SIP 規則觸發")
        return '\n'.join(lines)

    # Context flags (e.g. straight 1000m)
    if context_flags:
        for note in context_flags.get('straight_1000m_notes', []):
            lines.append(f"- {note}")

    for sip in all_sips:
        severity = sip.get('severity', '🟡')
        name = sip.get('name', '?')
        tag = sip.get('tag', '')
        effect = sip.get('effect', '')
        effects = sip.get('effects', [])

        lines.append(f"- {severity} **{sip['sip']}** {name}: `{tag}`")
        if effect:
            lines.append(f"  → {effect}")
        for e in effects:
            lines.append(f"  → {e}")

        # V2: Show indicator details for SIP-04
        details = sip.get('indicator_details', [])
        if details:
            lines.append(f"  📊 指標: {', '.join(details)}")

        note = sip.get('note', '')
        if note:
            lines.append(f"  ⚠️ {note}")

    lines.append("")
    return '\n'.join(lines)


if __name__ == '__main__':
    # Quick self-test
    test_horse = {
        'horse_name': '測試馬',
        'wins': 0,
        'starts': 8,
        'weight': 118,
        'barrier': 3,
        'margin_trend': '📈收窄中 — 3L → 1.5L → 0.75L',
        'formline_strength': '✅強組',
        'recent_form': '8-6-5-4-3',
    }

    test_context = {
        'distance': 1000,
        'track': '草地',
        'field_size': 14,
    }

    horse_sips = evaluate_horse_sips(test_horse, test_context)
    race_sips = evaluate_race_sips(test_context, {})
    ctx_flags = get_race_context_flags(test_context)

    print(format_sip_summary(horse_sips, race_sips, ctx_flags))
    print(f"\nTriggered {len(horse_sips)} horse SIPs, {len(race_sips)} race SIPs")
    print(f"Context flags: {ctx_flags}")
