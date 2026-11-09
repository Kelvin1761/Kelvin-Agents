"""RacingEngine: one horse → leaf scores → 9D matrix → composite.

The class is assembled from four mixins (facts, leaves, shadows, explanations);
this module owns only the orchestration in `analyze_horse`.
"""

from .features.draw import DrawScorer
from .features.form import FormScorer
from .features.jockey import JockeyScorer
from .features.speed import SpeedScorer
from .features.trainer import TrainerScorer
from .live_priors import (
    TrainerSignalPriors,
    empty_trainer_signal_priors,
    prior_source_manifest,
    temporal_source_is_safe,
)
from .matrix_mapper import (
    map_features_to_matrix_scores,
    matrix_formula_manifest,
)
from . import scoring
from .scoring import (CENTRED_MATRIX_WEIGHTS, DEBUT_MATRIX_WEIGHTS, FEATURE_KEYS, MATRIX_WEIGHTS, clip_score, compute_grade,
                      score_band, to_dimension_display,
                      to_display_scale)


_TRAINER_SIGNAL_PRIORS = None


def scoring_run_contract():
    """JSON-safe fingerprint for the exact production scoring contract."""
    return {
        "version": scoring.SCORING_CONTRACT_VERSION,
        "standard_matrix_weights": dict(MATRIX_WEIGHTS),
        "debut_matrix_weights": dict(DEBUT_MATRIX_WEIGHTS),
        "matrix_formulas": matrix_formula_manifest(),
        "race_shape_formula": scoring.race_shape_contract_manifest(),
        "distance_suitability": scoring.distance_suitability_contract_manifest(),
        "dimension_evidence_blends": {},
        "grade_thresholds": [
            {"minimum": minimum, "grade": grade}
            for minimum, grade in scoring.GRADE_THRESHOLDS
        ],
        # 顯示尺入契約：改咗個 anchor／slope 就等於改咗每份報告嘅數字同評級，
        # 唔可以靜靜改。validation.py 會對；golden 亦會逐匹馬印出分別。
        "display_scale": dict(scoring.DISPLAY_SCALE),
        "dimension_display_scale": scoring.dimension_display_manifest(),
        "prior_sources": prior_source_manifest(),
        "prior_temporal_contract": {
            "historical": "matching_point_in_time_required",
            "live_or_future": "latest_materialized_snapshot_allowed",
        },
    }


from ._facts import HorseFacts
from ._leaves import LeafScores, _consumption_label  # noqa: F401  (re-export)
from ._shadows import ShadowProfiles
from ._explain import Explanations


class RacingEngine(HorseFacts, LeafScores, ShadowProfiles, Explanations):
    def __init__(self, horse_data, race_context):
        self.horse_data = horse_data
        self.race_context = race_context
        self.data = horse_data.get("_data", {}) if isinstance(horse_data.get("_data"), dict) else {}
        self.reason_codes = []
        self.risk_flags = []
        self.provenance = {}
        # 騎練訊號逐項調整紀錄（因子、加減分、原始數據）— 供報告完整追溯
        self.trainer_signal_detail = None
        # 速度分逐項訊號明細（L400／步速修正／能量／引擎／路程）— 供報告完整追溯
        self.speed_detail = None
        # 檔位與走位逐項明細（檔位分／走位匹配分／近仗消耗分 或 跑馬地情境修正）
        self.race_shape_detail = None

    def analyze_horse(self):
        feature_scores = {}
        feature_notes = {}

        for name, scorer_class in {
            "jockey_score": JockeyScorer,
            "trainer_score": TrainerScorer,
            "draw_score": DrawScorer,
            "form_score": FormScorer,
            "speed_score": SpeedScorer,
        }.items():
            scorer = scorer_class(self.horse_data, self.race_context)
            score, note = scorer.compute()
            feature_scores[name] = clip_score(score)
            feature_notes[name] = self._normalize_reason(name, note)
            self.provenance[name] = self._source_for(name)
            if name == "speed_score":
                self.speed_detail = getattr(scorer, "detail", None)

        for name, func in {
            "class_score": self._class_score,
            "distance_score": self._distance_score,
            "track_going_score": self._track_going_score,
            "weight_score": self._weight_score,
            "consistency_score": self._consistency_score,
            "risk_score": self._risk_score,
            "confidence_score": self._confidence_score,
        }.items():
            score, note, source = func(feature_scores)
            feature_scores[name] = clip_score(score)
            feature_notes[name] = note
            self.provenance[name] = source

        derived_scores = {
            "formline_strength_score": self._formline_strength_score(),
            "margin_trend_score": self._margin_trend_score(),
            "same_distance_signal_score": self._same_distance_signal_score(),
            "trackwork_trend_score": self._trackwork_trend_score(),
            "race_shape_context_score": self._race_shape_context_score(feature_scores),
        }
        for name, (score, note, source) in derived_scores.items():
            feature_scores[name] = clip_score(score)
            feature_notes[name] = note
            self.provenance[name] = source

        feature_scores, context_notes, context_sources = self._apply_mainline_context(feature_scores, feature_notes)
        feature_notes.update(context_notes)
        self.provenance.update(context_sources)

        for key in FEATURE_KEYS:
            feature_scores[key] = clip_score(feature_scores.get(key, 60))
            feature_notes.setdefault(key, "資料不足，中性60分。")
            self.provenance.setdefault(key, "missing_neutral")

        matrix_scores = map_features_to_matrix_scores(feature_scores, debut=self._is_debut())
        # 同程表現（9D，2026-10-10）：之前係 7D 以外嘅獨立 raw 調整，而家係一個
        # centred 維度。leaf = 60 + 調整 ÷ 權重，所以 權重 × (leaf − 60) 等於原本嘅調整。
        distance_suitability = self._distance_suitability_adjustment(feature_scores, matrix_scores)
        self.distance_suitability_adjustment = distance_suitability
        distance_weight = CENTRED_MATRIX_WEIGHTS.get("distance_fit")
        if distance_weight:
            distance_leaf = 60.0 + float(distance_suitability["raw_adjustment"]) / distance_weight
            feature_scores["distance_fit_score"] = distance_leaf
            matrix_scores["distance_fit"] = round(distance_leaf, 4)
            # 呢個 leaf 唔喺 FEATURE_KEYS，之前冇人寫說明，「評分構成」就跌落預設
            # 「資料不足」—— 即使匹馬明明有同程紀錄（2026-11-04 跑馬地 83% 馬有）。
            feature_notes["distance_fit_score"] = self._distance_fit_note(distance_suitability)
            self.provenance["distance_fit_score"] = (
                "same_distance_record"
                if int(distance_suitability.get("same_distance_starts", 0) or 0) > 0
                else "missing_neutral"
            )
        # 維度 band 一律由**顯示尺**判。原始尺上面七個維度有五個永遠出唔到 ✅✅，
        # `馬匹健康` 連 ❌ 都出唔到（原始全距只有 55.2–73.7），所以同一套門檻
        # （✅✅ 85 / ✅ 70 / ➖ 55 / ❌ 40）套落七把唔同嘅尺 = 個符號冇意義。
        # 見 scoring.MATRIX_DISPLAY_CENTRES / MATRIX_DISPLAY_GAINS。
        matrix_scores_display = {
            key: round(to_dimension_display(key, value), 2)
            for key, value in matrix_scores.items()
        }
        matrix = {key: score_band(value) for key, value in matrix_scores_display.items()}
        # 加權總分係原始尺（維度加權平均，實測全距 50–77）；`ability_score` 印出
        # 嚟嘅係顯示尺。仿射、單調，所以排序 bit-identical——見 scoring.DISPLAY_SCALE。
        ability_raw = round(self._ability_score(matrix_scores), 2)
        ability_score = round(to_display_scale(ability_raw), 2)
        grade = compute_grade(ability_score)
        matrix_reasoning = self._matrix_reasoning(matrix_scores, matrix, feature_scores, feature_notes,
                                                  matrix_scores_display)
        score_breakdown = self._score_breakdown(feature_scores, feature_notes)
        grade_transparency = self._grade_computation_transparency(matrix_scores, ability_score, grade, feature_scores)

        return {
            "version": "HKJC_AUTO_SCORE_V2",
            "scoring_contract_id": scoring.SCORING_CONTRACT_VERSION,
            "ability_score": ability_score,
            "ability_score_raw": ability_raw,
            "grade": grade,
            "matrix": matrix,
            # 原始尺 = 綜合分嘅輸入，同所有權重／消融工具讀嘅嘢，唔可以動。
            "matrix_scores": matrix_scores,
            # 顯示尺 = 報告同 band 讀嘅嘢（見 scoring.to_dimension_display）。
            "matrix_scores_display": matrix_scores_display,
            "matrix_reasoning": matrix_reasoning,
            "core_logic": self._core_logic(feature_scores, matrix_scores, matrix_reasoning),
            "data_readout": self._data_readout(feature_scores, matrix_scores),
            "grade_transparency": grade_transparency,
            "trainer_signal_detail": self.trainer_signal_detail,
            "speed_detail": getattr(self, "speed_detail", None),
            "race_shape_detail": getattr(self, "race_shape_detail", None),
            "distance_suitability_adjustment": distance_suitability,
            "trackwork_read": self._trackwork_interpretation(),
            "trackwork_timeline": self._trackwork_timeline(),
            "overseas_form_read": self._overseas_form_interpretation(),
            "health_readout": self._health_readout(),
            # 引擎重算嘅距今日數（見 _days_since_last）。Logic 個同名欄位帶住
            # 舊生成器嘅錯值，renderer 一律要讀呢個，唔好讀原欄位。
            "days_since_last": self._days_since_last(),
            # 重算過嘅「頭馬距離趨勢」（舊 Logic 個字串符號錯，見 _margin_trend_display）
            "margin_trend": self._margin_trend_display(),
            "feature_scores": {key: round(feature_scores[key], 2) for key in FEATURE_KEYS},
            # Persist the derived sub-features that feed form_line/stability so the
            # backtest harness can faithfully reproduce production scoring (these
            # are NOT in the 12 FEATURE_KEYS but matrix formulas depend on them).
            "derived_feature_scores": {
                key: round(feature_scores.get(key, 60.0), 2)
                for key in ("formline_strength_score", "margin_trend_score",
                            "same_distance_signal_score", "trackwork_trend_score",
                            "race_shape_context_score")
            },
            "score_breakdown": score_breakdown,
            "reason_codes": sorted(set(self.reason_codes)),
            "risk_flags": sorted(set(self.risk_flags)),
            "score_provenance": self.provenance,
        }

    def _trainer_signal_priors(self):
        global _TRAINER_SIGNAL_PRIORS
        if _TRAINER_SIGNAL_PRIORS is None:
            _TRAINER_SIGNAL_PRIORS = TrainerSignalPriors()
        # A latest/full-season snapshot is valid for a live card but leaks
        # future results when an archived race is replayed. Keep historical
        # scoring neutral unless the PIT harness injects a matching source.
        as_of_date = (self.race_context or {}).get("race_date")
        if not temporal_source_is_safe(_TRAINER_SIGNAL_PRIORS, as_of_date):
            return empty_trainer_signal_priors()
        return _TRAINER_SIGNAL_PRIORS
