#!/usr/bin/env python3
"""
hkjc_schema.py — HKJC V4.2 Central Schema Constants
=====================================================
Single source of truth for all HKJC Logic JSON schema
definitions, matrix structure, valid scores, legacy key
blacklists, and content-quality word lists.

ALL pipeline modules must import from here:
  - hkjc_orchestrator.py
  - compile_analysis_template_hkjc.py
  - create_hkjc_logic_skeleton.py
  - validate_hkjc_logic_schema.py
  - racing_graph_nodes.py

Do NOT duplicate these constants inline.
"""

# ═══════════════════════════════════════════════════════════════
# VERSION & PLATFORM
# ═══════════════════════════════════════════════════════════════

HKJC_SCHEMA_VERSION = "HKJC_LOGIC_V4_2"
HKJC_PLATFORM = "HKJC"

# ═══════════════════════════════════════════════════════════════
# 7-DIMENSION MATRIX SCHEMA (V4.2)
# ═══════════════════════════════════════════════════════════════

HKJC_MATRIX_SCHEMA = {
    "stability":       "semi",
    "sectional":       "core",
    "race_shape":      "semi",
    "trainer_signal":  "core",
    "horse_health":    "aux",
    "form_line":       "aux",
    "class_advantage": "aux",
}

HKJC_MATRIX_EXPECTED_KEYS = frozenset(HKJC_MATRIX_SCHEMA)

# Ordered render list: (canonical_key, chinese_label, tier_label)
HKJC_MATRIX_RENDER = [
    ("stability",       "狀態與穩定性",         "半核心"),
    ("sectional",       "🔬 段速質量 (包含段速法醫)", "核心"),
    ("race_shape",      "⚡ 形勢與走位",        "半核心"),
    ("trainer_signal",  "🧭 騎練訊號",          "核心"),
    ("horse_health",    "⚠️ 馬匹健康 / 新鮮感", "輔助"),
    ("form_line",       "🔗 賽績線",            "輔助"),
    ("class_advantage", "級數優勢",             "輔助"),
]

# Quick lookup: canonical_key → (chinese_label, tier_label)
HKJC_MATRIX_LABELS = {key: (zh, tier) for key, zh, tier in HKJC_MATRIX_RENDER}

# Resource files each dimension must cite in reasoning
HKJC_MATRIX_RESOURCE_REQUIREMENTS = {
    "stability":       ("05_forensic_analysis.md",),
    "sectional":       ("03_engine_pace_context.md", "04_engine_corrections.md"),
    "race_shape":      ("05_forensic_analysis.md",),
    "trainer_signal":  ("07b_trainer_signals.md", "07c_jockey_profiles.md"),
    "horse_health":    ("05_forensic_analysis.md",),
    "form_line":       ("Facts.md",),
    "class_advantage": ("06_rating_engine.md",),
}

# ═══════════════════════════════════════════════════════════════
# VALID SCORES
# ═══════════════════════════════════════════════════════════════

HKJC_VALID_SCORES = frozenset({"✅✅", "✅", "➖", "❌", "❌❌"})
HKJC_VALID_SCORES_WITH_NA = frozenset(HKJC_VALID_SCORES | {"N/A"})

# Scores allowed for core/semi dimensions (full 5-tier)
HKJC_CORE_SEMI_SCORES = frozenset({"✅✅", "✅", "➖", "❌", "❌❌"})
# Scores allowed for auxiliary dimensions (3-tier)
HKJC_AUX_SCORES = frozenset({"✅", "➖", "❌"})

# ═══════════════════════════════════════════════════════════════
# LEGACY KEY BLACKLISTS (fail-fast rejection)
# ═══════════════════════════════════════════════════════════════

HKJC_LEGACY_8D_KEYS = frozenset({
    "裝備與距離", "Gear & Distance", "gear_distance", "gear_dist",
    "gearDistance", "gear_and_distance",
    "場地適性", "情境適配", "scenario",
    "路程/新鮮度", "distance_freshness", "freshness", "distance",
    # Legacy English key variants that should now fail
    "speed_mass", "trainer_jockey",
})

HKJC_LEGACY_TOP_LEVEL_FIELDS = frozenset({
    "analytical_breakdown", "sectional_forensic", "race_shape",
})

# ═══════════════════════════════════════════════════════════════
# CHINESE → CANONICAL ENGLISH NORMALIZATION MAP
# Used by orchestrator grade computation when LLM uses Chinese
# dimension names. This is the exhaustive mapping.
# ═══════════════════════════════════════════════════════════════

ZH_EN_MATRIX_MAP = {
    # Chinese key variants
    "狀態與穩定性":         "stability",
    "位置穩定性":           "stability",
    "段速與引擎":           "sectional",
    "段速質量":             "sectional",
    "形勢與走位":           "race_shape",
    "形勢與走位(舊)":       "race_shape",
    "騎練訊號":             "trainer_signal",
    "練馬師訊號":           "trainer_signal",
    "級數與負重":           "class_advantage",
    "級數優勢":             "class_advantage",
    "賽績線":               "form_line",
    "馬匹健康 / 新鮮感":    "horse_health",
    "馬匹健康":             "horse_health",
    "新鮮度/場地":          "horse_health",
    "路程/新鮮度":          "horse_health",
    # Legacy English aliases (for backward-compatibility normalization)
    "formline":             "form_line",
    "trainer":              "trainer_signal",
    "class":                "class_advantage",
}

# ═══════════════════════════════════════════════════════════════
# DUMMY / FLUFF PHRASE LISTS (content quality)
# ═══════════════════════════════════════════════════════════════

DUMMY_PHRASES = [
    '自動法醫分析', '自動匹配系統法則', '分析中', '待分析',
    '自動生成', '批量填充', 'auto_fill', 'auto_expert',
]

FLUFF_PHRASES = [
    '具備一定競爭力', '狀態有待觀察', '近期走勢', '值得留意',
    '有望爭勝', '不容忽視', '實力不俗', '表現平穩',
]

# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def normalize_matrix_keys(m_data: dict) -> dict:
    """Normalize matrix keys from Chinese/variant English to canonical schema keys.

    Returns a new dict with canonical keys. Drops unknown keys silently
    (they will be caught by the validator).
    """
    if not m_data:
        return m_data
    needs_norm = any(k in ZH_EN_MATRIX_MAP for k in m_data)
    if not needs_norm:
        return m_data
    return {ZH_EN_MATRIX_MAP.get(k, k): v for k, v in m_data.items()}
