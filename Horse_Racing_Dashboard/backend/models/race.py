"""
Pydantic models for race analysis data.
"""
from pydantic import BaseModel
from typing import Optional, List
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


class DimensionDetail(BaseModel):
    """One row of the AU engine's per-dimension breakdown.

    The analysis markdown carries far more than the ✅/➖ symbol the dashboard
    used to surface: the score, its ranking weight, the weighted contribution,
    the engine's own verdict, and -- the part that matters for reading -- how
    many starts/trials each judgement actually rests on. Measured 2026-09-02:
    477 of 477 horses had all of it in the file and 0% reached the payload.

    `ranking_weighted` is False for the two dimensions the engine prints but
    explicitly marks 「參考·不入排名」(檔位形勢, 賽績線). They are kept rather
    than dropped so the UI can show them as non-scoring instead of silently
    hiding them.
    """
    name: str
    score: Optional[float] = None
    weight_pct: Optional[float] = None
    contribution: Optional[float] = None
    symbol: Optional[str] = None       # ✅✅ / ✅ / ➖ / ❌ / ❌❌
    category: Optional[str] = None     # 偏強 / 中性 / 偏弱 / 很弱
    verdict: Optional[str] = None      # 判讀
    evidence: list[str] = []           # 數據 lines
    sample_counts: list[str] = []      # "9 場", "1 次試閘" -- evidence thickness
    ranking_weighted: bool = True


class RatingMatrix(BaseModel):
    dimensions: list[RatingDimension]
    base_rating: Optional[str] = None
    adjustment: Optional[str] = None
    override: Optional[str] = None


class HorseAnalysis(BaseModel):
    horse_number: int
    horse_name: str
    horse_name_en: Optional[str] = None
    horse_code: Optional[str] = None  # HKJC brand number, e.g. K178
    hkjc_horse_id: Optional[str] = None  # Exact HKJC id, e.g. HK_2024_K178
    horse_profile_url: Optional[str] = None  # Official HKJC horse profile
    silk_url: Optional[str] = None  # HKJC racing colour image
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
    eem_energy: Optional[str] = None  # ⚡ 形勢與走位 (legacy field name kept for compat)
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
    ability_score: Optional[float] = None
    # 賽前**市場**盤（2026-08-26）。同下面 `predicted_place_odds` 唔同 ——
    # 嗰個係模型推算嘅合理賠率，呢個係 Sportsbet 抓取嗰刻嘅實際市場價。
    # **唔入任何評分。** 抽佢淨係為咗喺 dashboard 預填落注輸入格。
    # 見 EXP-20260826-08：市場價加落排名雖然過閘，但最佳混合比重 w=0.0
    # （純市場），即係模型貢獻為零，而排名等於市場排名就冇 edge。
    market_win_odds: Optional[float] = None
    market_place_odds: Optional[float] = None
    confidence_score: Optional[float] = None
    risk_score: Optional[float] = None
    model_pick_status: Optional[str] = None
    rank: Optional[int] = None

    # Evidence thickness. The engine's own 數據信心 counts dimensions that have
    # measured data (X of Y); it is near-constant in practice -- 93.9% of 477
    # horses read 5/5 on 2026-09-02 -- so it separates almost nothing on its
    # own. The per-dimension `sample_counts` in dimension_details are the
    # signal worth reading; this pair is kept because it is cheap and does
    # discriminate at the thin tail (29 horses below 5/5 that day).
    evidence_dimensions: Optional[int] = None
    evidence_dimensions_total: Optional[int] = None
    dimension_details: Optional[list[DimensionDetail]] = None
    
    # Conclusion
    conclusion: Optional[str] = None  # 💡 結論
    core_logic: Optional[str] = None  # 核心邏輯
    data_readout: Optional[List[dict]] = None  # 📊 數據判讀 rows: {label,value,trend,band,reason}
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
    analysis_type: Optional[str] = None  # classic / auto
    scoring_file: Optional[str] = None
    
    # Monte Carlo simulation results
    monte_carlo_simulation: Optional[list['MonteCarloPick']] = None


class Meeting(BaseModel):
    date: str  # YYYY-MM-DD
    venue: str
    region: Region
    analysts: list[AnalystName] = []
    races: list[RaceAnalysis] = []
    folder_paths: dict[str, str] = {}  # analyst_name -> folder_path
