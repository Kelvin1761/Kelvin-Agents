"""
Pydantic models for race analysis data.
"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class Region(str, Enum):
    HKJC = "hkjc"
    AU = "au"


class AnalystName(str, Enum):
    KELVIN = "Kelvin"
    HEISON = "Heison"


class RatingDimension(BaseModel):
    name: str
    category: str  # 核心 / 半核心 / 輔助
    value: str      # ✅ / ➖ / ❌
    rationale: str


class RatingMatrix(BaseModel):
    dimensions: list[RatingDimension]
    base_rating: Optional[str] = None
    adjustment: Optional[str] = None
    override: Optional[str] = None


class HorseAnalysis(BaseModel):
    horse_number: int
    horse_name: str
    jockey: Optional[str] = None
    trainer: Optional[str] = None
    weight: Optional[str] = None
    barrier: Optional[int] = None
    rating: Optional[int] = None  # Official rating number
    
    # Context
    situation_tag: Optional[str] = None  # 情境標記
    
    # Performance
    recent_form: Optional[str] = None  # 近六場序列
    form_cycle: Optional[str] = None  # 狀態週期
    statistics: Optional[str] = None
    key_runs: Optional[list[str]] = None  # 關鍵場次法醫
    trend_summary: Optional[str] = None  # 趨勢總評
    
    # HKJC-specific sections
    speed_forensics: Optional[str] = None  # 🔬 段速法醫
    eem_energy: Optional[str] = None  # ⚡ EEM 能量
    forgiveness_file: Optional[str] = None  # 📋 寬恕檔案
    form_line: Optional[str] = None  # 🔗 賽績線
    
    # AU-specific sections
    horse_profile: Optional[str] = None  # 🐴 馬匹剖析
    core_analysis: Optional[str] = None  # 🧠 核心分析推演
    
    # Engine & Distance classification (AU + HKJC)
    engine_type: Optional[str] = None  # Type A / Type B / Type C / Type A/B
    engine_type_label: Optional[str] = None  # 前領均速型 / 末段爆發型 etc.
    engine_distance_summary: Optional[str] = None  # Full engine distance text
    
    # Rating
    rating_matrix: Optional[RatingMatrix] = None
    final_grade: Optional[str] = None  # A+, A, B+, etc.
    
    # Conclusion
    conclusion: Optional[str] = None  # 💡 結論
    core_logic: Optional[str] = None  # 核心邏輯
    advantage: Optional[str] = None  # 最大競爭優勢
    risk: Optional[str] = None  # 最大失敗原因
    
    # Underhorse Signal (3-tier: light/moderate/strong)
    underhorse_triggered: bool = False
    underhorse_level: Optional[str] = None  # 'light' (🟢), 'moderate' (🟡), 'strong' (🔴)
    underhorse_condition: Optional[str] = None
    underhorse_reason: Optional[str] = None
    
    # Raw text for full display
    raw_text: Optional[str] = None


class TopPick(BaseModel):
    rank: int  # 1-4
    rank_label: Optional[str] = None  # 🥇, 🥈, 🥉, 🏅
    horse_number: int
    horse_name: str
    grade: Optional[str] = None
    checkmarks: Optional[int] = None
    core_rationale: Optional[str] = None
    max_risk: Optional[str] = None
    scenario: Optional[str] = None  # e.g. "Good 4", "Soft 5", "Heavy 8" — from SIP-RR01


class MonteCarloPick(BaseModel):
    mc_rank: int                          # 1, 2, 3 ...
    horse_number: Optional[str] = None    # e.g. "5", "11"
    horse_name: str
    win_pct: float                        # e.g. 19.7
    predicted_odds: Optional[str] = None  # e.g. "$5.07"
    predicted_place_odds: Optional[str] = None  # e.g. "$2.40"
    top3_pct: Optional[float] = None
    top4_pct: Optional[float] = None
    forensic_rank: Optional[str] = None   # e.g. "🥇 #1", "#6"
    divergence: Optional[str] = None      # e.g. "✅ 一致", "❌ ⬆️5"


class RaceAnalysis(BaseModel):
    race_number: int
    distance: Optional[str] = None
    race_class: Optional[str] = None
    track: Optional[str] = None
    venue: Optional[str] = None
    race_name: Optional[str] = None
    race_type: Optional[str] = None
    going: Optional[str] = None

    # Pace prediction
    pace_prediction: Optional[str] = None
    speed_map: Optional[str] = None
    
    # Horses
    horses: list[HorseAnalysis] = []
    
    # Verdict
    top_picks: list[TopPick] = []
    # SIP-RR01: dual-scenario top picks. Keys are track conditions, e.g. {"Good 4": [...], "Soft 5": [...]}
    scenario_top_picks: Optional[dict[str, list[TopPick]]] = None
    confidence: Optional[str] = None
    key_variable: Optional[str] = None
    
    # Pace flip insurance
    pace_flip: Optional[str] = None
    
    # Underhorse signals summary
    underhorse_signals: Optional[list[str]] = None
    
    # Raw sections
    battlefield_overview: Optional[str] = None  # 第一部分
    verdict_text: Optional[str] = None  # 第三部分
    blind_spots: Optional[str] = None  # 第四部分
    
    # Monte Carlo simulation results
    monte_carlo_simulation: Optional[list['MonteCarloPick']] = None


class Meeting(BaseModel):
    date: str  # YYYY-MM-DD
    venue: str
    region: Region
    analysts: list[AnalystName] = []
    races: list[RaceAnalysis] = []
    folder_paths: dict[str, str] = {}  # analyst_name -> folder_path
