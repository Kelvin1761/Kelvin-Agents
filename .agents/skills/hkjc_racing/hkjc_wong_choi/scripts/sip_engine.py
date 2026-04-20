#!/usr/bin/env python3
"""
SIP Engine — Systemic Improvement Proposals Auto-Evaluator
==========================================================
Evaluates all 8 HKJC SIP rules against horse/race data.
Returns triggered SIPs with tags, adjustments, and alerts.

Based on: 2026-04-19 Sha Tin Reflector Audit (SIP V1.0)

Usage:
    from sip_engine import evaluate_horse_sips, evaluate_race_sips
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')

import json
import re


# ============================================================
# SIP-01: Health Recovery Discount
# ============================================================

def check_sip01_health_recovery(horse: dict) -> dict:
    """
    WHEN: Horse has health record (roaring, EIPH, abnormal breathing)
      AND last race was normal finish (not DNF, not last 3)
    THEN: Floor rating at B-, tag HEALTH_RECOVERY
    """
    health_issues = horse.get('health_issues', [])
    if isinstance(health_issues, str):
        health_issues = [health_issues] if health_issues else []
    
    health_keywords = ['喘鳴', '氣管', '出血', 'roaring', 'EIPH', '異常呼吸', 'bleed']
    has_health = any(
        any(kw in str(issue) for kw in health_keywords)
        for issue in health_issues
    )
    
    if not has_health:
        # Also check core_logic for mentions
        core_logic = str(horse.get('core_logic', ''))
        has_health = any(kw in core_logic for kw in health_keywords)
    
    if not has_health:
        return {}
    
    # Check last race wasn't a disaster
    last_dnf = horse.get('last_race_dnf', False)
    last_position = horse.get('last_position')
    field_size = horse.get('_field_size', 14)
    
    if last_dnf:
        return {}
    
    if last_position and isinstance(last_position, int):
        if last_position >= field_size - 2:  # Last 3
            return {}
    
    return {
        'sip': 'SIP-01',
        'name': 'HEALTH_RECOVERY_DISCOUNT',
        'severity': '🟡',
        'tag': '健康復甦折扣啟動',
        'effect': 'Floor at B-, health as RISK FACTOR only',
        'max_upgrade': '+1 grade',
    }


# ============================================================
# SIP-02: Straight Course 1000m Override
# ============================================================

def check_sip02_straight_course(race_context: dict) -> dict:
    """
    WHEN: distance == 1000m AND turf
    THEN: Multiple adjustments (barrier reversal, burn index, etc.)
    Note: MC engine already handles sigma boost (+40%) and barrier reversal.
          This SIP flags for LLM analysis layer adjustments.
    """
    distance = race_context.get('distance', 0)
    if isinstance(distance, str):
        m = re.search(r'(\d+)', str(distance))
        distance = int(m.group(1)) if m else 0
    
    track = str(race_context.get('track', ''))
    is_turf = '草' in track or 'turf' in track.lower() or not track
    
    if distance > 1000 or not is_turf:
        return {}
    
    return {
        'sip': 'SIP-02',
        'name': 'STRAIGHT_COURSE_1000M',
        'severity': '🔴',
        'tag': '直路賽特殊模型',
        'effects': [
            '高號碼檔(8-14)加分，低號碼檔(1-4)唔自動加分',
            'Type A ≥4 匹觸發互燒指數',
            '減磅效應加強 (每磅 PI boost 0.25)',
            '選馬範圍擴展至 Top6',
        ],
        'note': 'MC 引擎已自動處理 sigma +40% 及檔位反轉',
    }


# ============================================================
# SIP-04: Zero Win Breakout Candidate
# ============================================================

def check_sip04_zero_win_breakout(horse: dict, race_context: dict) -> dict:
    """
    WHEN: wins == 0 AND starts >= 3
      AND positive indicators (strong formline OR rising PI)
      AND barrier <= field_size * 0.5
    THEN: Unlock ceiling to B+, tag ZERO_WIN_BREAKOUT_CANDIDATE
    """
    wins = horse.get('wins', None)
    if wins is None:
        # Try to parse from recent_form
        recent_form = str(horse.get('recent_form', ''))
        wins = recent_form.count('1') if recent_form else None
    
    if wins is None or wins > 0:
        return {}
    
    starts = horse.get('starts', 0)
    if isinstance(starts, str):
        try:
            starts = int(starts)
        except ValueError:
            starts = 0
    
    if starts < 3:
        return {}
    
    # Check positive indicators
    positive_indicators = 0
    core_logic = str(horse.get('core_logic', ''))
    matrix = horse.get('matrix', {})
    
    # Check formline strength
    formline = matrix.get('賽績線', matrix.get('formline', {}))
    if isinstance(formline, dict):
        score = formline.get('score', '')
        if score in ('✅✅', '✅'):
            positive_indicators += 1
    
    # Check stability (rising form)
    stability = matrix.get('狀態與穩定性', matrix.get('stability', {}))
    if isinstance(stability, dict):
        score = stability.get('score', '')
        if score in ('✅✅', '✅'):
            positive_indicators += 1
    
    # Check for positive keywords in core_logic
    positive_keywords = ['進步', '上升', '漸入佳境', '突破', 'improving', '強組']
    if any(kw in core_logic for kw in positive_keywords):
        positive_indicators += 1
    
    if positive_indicators < 1:
        return {}
    
    # Check barrier
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
        'note': '每場最多觸發 2 匹',
    }


# ============================================================
# SIP-05: Class Drop Cluster Alert
# ============================================================

def check_sip05_class_drop_cluster(race_context: dict, all_horses: dict) -> dict:
    """
    WHEN: Top4 verdict has 4 S-Grade horses
      AND field has ≥4 class-drop horses
    THEN: Trigger cluster alert, expand to Top6
    """
    # Count S-grades in top4
    verdict = race_context.get('verdict', {})
    top4 = verdict.get('top4', [])
    s_count = sum(1 for h in top4 if isinstance(h, dict) and str(h.get('grade', '')).startswith('S'))
    
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
        'sip': 'SIP-05',
        'name': 'CLASS_DROP_CLUSTER',
        'severity': '🔴',
        'tag': 'CLASS_DROP_CLUSTER',
        'effects': [
            '擴大選馬至 Top6',
            '降班馬 class_advantage_bonus 打 7 折 (×0.7)',
            '後上型 (Type B/C) rating +0.3',
            '初出馬 floor 從 D 提升至 C',
        ],
        's_grade_count': s_count,
        'class_drop_count': class_drops,
    }


# ============================================================
# SIP-06: Hot Combo Boost
# ============================================================

def check_sip06_hot_combo(horse: dict) -> dict:
    """
    WHEN: jockey_trainer combo this season >= 3 wins
      AND combo_strike_rate > league average × 1.3
    THEN: Rating boost +0.3, tag HOT_COMBO
    """
    combo_wins = horse.get('jockey_trainer_combo_wins', 0)
    if isinstance(combo_wins, str):
        try:
            combo_wins = int(combo_wins)
        except ValueError:
            combo_wins = 0
    
    if combo_wins < 3:
        return {}
    
    combo_sr = horse.get('jockey_trainer_combo_sr', 0)
    league_avg_sr = 0.08  # ~8% average HK strike rate
    
    if isinstance(combo_sr, (int, float)) and combo_sr > league_avg_sr * 1.3:
        return {
            'sip': 'SIP-06',
            'name': 'HOT_COMBO_BOOST',
            'severity': '🟡',
            'tag': 'HOT_COMBO',
            'effect': 'Rating +0.3',
            'combo_wins': combo_wins,
            'combo_sr': combo_sr,
            'note': '騎練因子加總最多 +1 級',
        }
    
    # Even without explicit SR data, flag if combo_wins >= 3
    return {
        'sip': 'SIP-06',
        'name': 'HOT_COMBO_BOOST',
        'severity': '🟡',
        'tag': 'HOT_COMBO (待驗證 SR)',
        'effect': 'Rating +0.3 (需驗證 strike rate)',
        'combo_wins': combo_wins,
    }


# ============================================================
# SIP-07: Significant Claim Discount
# ============================================================

def check_sip07_claim_discount(horse: dict) -> dict:
    """
    WHEN: Apprentice jockey claim >= 7 lbs
    THEN: Enhanced weight reduction effect, tag SIGNIFICANT_CLAIM
    Note: MC engine already handles non-linear model (>=7lbs coeff 0.22)
    """
    weight = horse.get('weight', 126)
    if not isinstance(weight, (int, float)):
        return {}
    
    claim = 126 - weight
    if claim < 7:
        return {}
    
    return {
        'sip': 'SIP-07',
        'name': 'SIGNIFICANT_CLAIM_DISCOUNT',
        'severity': '🟡',
        'tag': 'SIGNIFICANT_CLAIM_DISCOUNT',
        'effect': f'減磅 {claim} 磅，加強效應 (coeff 0.22)',
        'claim_lbs': claim,
        'note': 'MC 引擎已自動處理非線性減磅模型',
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
# Public API
# ============================================================

def evaluate_horse_sips(horse: dict, race_context: dict) -> list:
    """
    Evaluate all per-horse SIP rules.
    Returns list of triggered SIP dicts.
    """
    triggered = []
    
    sip01 = check_sip01_health_recovery(horse)
    if sip01:
        triggered.append(sip01)
    
    sip04 = check_sip04_zero_win_breakout(horse, race_context)
    if sip04:
        triggered.append(sip04)
    
    sip06 = check_sip06_hot_combo(horse)
    if sip06:
        triggered.append(sip06)
    
    sip07 = check_sip07_claim_discount(horse)
    if sip07:
        triggered.append(sip07)
    
    return triggered


def evaluate_race_sips(race_context: dict, all_horses: dict,
                       mc_results: dict = None, concordance: dict = None) -> list:
    """
    Evaluate all race-level SIP rules.
    Returns list of triggered SIP dicts.
    """
    triggered = []
    
    sip02 = check_sip02_straight_course(race_context)
    if sip02:
        triggered.append(sip02)
    
    sip05 = check_sip05_class_drop_cluster(race_context, all_horses)
    if sip05:
        triggered.append(sip05)
    
    if mc_results and concordance:
        sip08 = check_sip08_divergence(mc_results, concordance)
        if sip08:
            triggered.append(sip08)
    
    return triggered


def format_sip_summary(horse_sips: list, race_sips: list = None) -> str:
    """Format triggered SIPs as a readable work card section."""
    lines = []
    lines.append("## 🛡️ SIP 觸發檢查 [自動]")
    
    all_sips = (race_sips or []) + horse_sips
    
    if not all_sips:
        lines.append("- ✅ 無 SIP 規則觸發")
        return '\n'.join(lines)
    
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
        'matrix': {
            '賽績線': {'score': '✅'},
            '狀態與穩定性': {'score': '✅'},
        },
        'core_logic': '近績線漸入佳境，PI 持續上升',
    }
    
    test_context = {
        'distance': 1000,
        'track': '草地',
        'field_size': 14,
    }
    
    horse_sips = evaluate_horse_sips(test_horse, test_context)
    race_sips = evaluate_race_sips(test_context, {})
    
    print(format_sip_summary(horse_sips, race_sips))
    print(f"\nTriggered {len(horse_sips)} horse SIPs, {len(race_sips)} race SIPs")
