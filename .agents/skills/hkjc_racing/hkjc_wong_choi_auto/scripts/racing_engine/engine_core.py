import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR / "features"))

from draw import DrawScorer
from form import FormScorer
from jockey import JockeyScorer
from speed import SpeedScorer
from trainer import TrainerScorer
from live_priors import TrainerSignalPriors
from matrix_mapper import MATRIX_FORMULAS, map_features_to_matrix, map_features_to_matrix_scores
import scoring
from scoring import FEATURE_KEYS, MATRIX_WEIGHTS, clip_score, compute_grade, parse_float, parse_record, score_band

_TRAINER_SIGNAL_PRIORS = None


class RacingEngine:
    def __init__(self, horse_data, race_context):
        self.horse_data = horse_data
        self.race_context = race_context
        self.data = horse_data.get("_data", {}) if isinstance(horse_data.get("_data"), dict) else {}
        self.reason_codes = []
        self.risk_flags = []
        self.provenance = {}

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
            score, note = scorer_class(self.horse_data, self.race_context).compute()
            feature_scores[name] = clip_score(score)
            feature_notes[name] = self._normalize_reason(name, note)
            self.provenance[name] = self._source_for(name)

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

        matrix_scores = map_features_to_matrix_scores(feature_scores)
        matrix_scores["trainer_signal"] = self._apply_trainer_signal_v3(matrix_scores["trainer_signal"])
        matrix_scores["horse_health"] = self._apply_health_only_v2(matrix_scores["horse_health"])
        matrix = map_features_to_matrix(feature_scores)
        matrix["trainer_signal"] = score_band(matrix_scores["trainer_signal"])
        matrix["horse_health"] = score_band(matrix_scores["horse_health"])
        ability_score = round(self._ability_score(matrix_scores), 2)
        grade = compute_grade(ability_score)
        matrix_reasoning = self._matrix_reasoning(matrix_scores, matrix, feature_scores, feature_notes)
        score_breakdown = self._score_breakdown(feature_scores, feature_notes)
        grade_transparency = self._grade_computation_transparency(matrix_scores, ability_score, grade)

        return {
            "version": "HKJC_AUTO_SCORE_V2",
            "ability_score": ability_score,
            "grade": grade,
            "matrix": matrix,
            "matrix_scores": matrix_scores,
            "matrix_reasoning": matrix_reasoning,
            "core_logic": self._core_logic(feature_scores, matrix_scores, matrix_reasoning),
            "grade_transparency": grade_transparency,
            "core_logic_transparency": self._core_logic_transparency(feature_scores, matrix_scores, matrix, ability_score, grade),
            "feature_scores": {key: round(feature_scores[key], 2) for key in FEATURE_KEYS},
            # Persist the derived sub-features that feed form_line/stability so the
            # backtest harness can faithfully reproduce production scoring (these
            # are NOT in the 12 FEATURE_KEYS but matrix formulas depend on them).
            "derived_feature_scores": {
                key: round(feature_scores.get(key, 60.0), 2)
                for key in ("formline_strength_score", "margin_trend_score",
                            "same_distance_signal_score", "trackwork_trend_score")
            },
            "score_breakdown": score_breakdown,
            "reason_codes": sorted(set(self.reason_codes)),
            "risk_flags": sorted(set(self.risk_flags)),
            "score_provenance": self.provenance,
        }

    def _class_score(self, _features):
        if self._is_debut():
            self.reason_codes.append("debut_class_unknown")
            return 60, "初出馬未有正式班際賽績，級數優勢暫按中性60分。", "career_tag"
        score = 60
        notes = []
        starts = parse_float(self._value("career_race_starts") or self.horse_data.get("career_race_starts"))
        season = self._season_record()
        same_distance = self._same_distance_record()
        career_tag = self._clean(self._value("career_tag") or self.horse_data.get("career_tag") or "")
        if career_tag == "ESTABLISHED":
            score += scoring.CLASS_MICRO_WEIGHTS.get("established_bonus", 4.0)
            notes.append("屬已建立賽駒")
        if starts is not None:
            if starts >= 20:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_20_bonus", 4.0)
                notes.append("正式賽經驗充足")
            elif starts <= 8:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_8_pen", -2.0)
                notes.append("正式賽樣本較薄")
        if season:
            if season["places"] >= 3:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_3_bonus", 4.0)
                notes.append("季內有基本交代")
            elif season["places"] == 0:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_0_pen", -4.0)
                self.risk_flags.append("class_edge_unproven")
                notes.append("季內未見上名")
        if same_distance and same_distance["places"] > 0:
            score += scoring.CLASS_MICRO_WEIGHTS.get("same_dist_place_bonus", 4.0)
            notes.append("同程有實績")
        elif same_distance and same_distance["starts"] > 0 and same_distance["places"] == 0:
            score += scoring.CLASS_MICRO_WEIGHTS.get("same_dist_unplaced_pen", -2.0)
            notes.append("同程未有實績")
        note = "班次優勢按實戰經驗、季內交代與同程適應評估"
        if notes:
            note += "，" + "、".join(notes)
        note += f"，班次分{clip_score(score):.1f}。"
        return clip_score(score), note, "career_context"

    def _distance_score(self, _features):
        best_distance = self._value("best_distance")
        distance = str(self.race_context.get("distance") or "")
        text = self._text("best_distance", "season_stats", "course_record")
        record = parse_record(text)
        best_text = self._clean(best_distance or "")
        distance_token = distance.replace("m", "").strip()
        direct_match = best_text.startswith(f"{distance_token}m") or best_text.startswith(distance)
        if "未跑過" in best_text:
            if "相近上名經驗" in best_text:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("similar_place_base", 62.0), "今場路程未有直接實績，但相近路程有上名旁證，路程分62分。", "best_distance"
            if self._is_debut():
                self.reason_codes.append("debut_distance_unproven")
                return scoring.DISTANCE_MICRO_WEIGHTS.get("debut_base", 58.0), "初出馬未經今仗路程實戰驗證，路程分保守58分。", "career_tag"
            self.risk_flags.append("distance_unproven")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("unproven_base", 56.0), "今場路程未有直接實績，路程分56分。", "best_distance"
        if best_distance and distance and direct_match:
            starts = record["starts"] if record else None
            if starts and record["places"] > 0:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_place_base", 72.0), f"路程資料見今仗距離及上名紀錄，路程適性評為72分。", "best_distance"
            return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_small_sample_base", 66.0), "最佳路程欄與今仗距離吻合，但樣本有限，路程分66分。", "best_distance"
        if self._is_debut():
            self.reason_codes.append("debut_distance_unproven")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("debut_base", 58.0), "初出馬未經今仗路程實戰驗證，路程分保守58分。", "career_tag"
        if "同程" in text and record and record["starts"] > 0 and record["places"] == 0:
            self.risk_flags.append("distance_record_weak")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("same_dist_unplaced_base", 54.0), "同程有樣本但未見上名支持，路程分54分。", "season_stats"
        return scoring.DISTANCE_MICRO_WEIGHTS.get("neutral_base", 60.0), "路程證據不足，按中性60分。", "missing_neutral"

    def _track_going_score(self, _features):
        text = self._text("good_record", "soft_record", "course_record", "track_bias", "draw_verdict")
        if "✅有利" in text or ("同場同程" in text and "(0-0-0-0)" not in text):
            return scoring.TRACK_MICRO_WEIGHTS.get("favorable_base", 66.0), "場地/跑道資料有明確支持，場地分66分。", "draw_verdict"
        if any(token in text for token in ("❌不利", "不利", "差", "無資料")):
            return scoring.TRACK_MICRO_WEIGHTS.get("unfavorable_base", 58.0), "場地或場地紀錄支持不足，場地分58分。", "course_record"
        return scoring.TRACK_MICRO_WEIGHTS.get("neutral_base", 60.0), "未有明確場地適性證據，場地分60分。", "missing_neutral"

    def _weight_score(self, _features):
        weight = parse_float(self._value("weight_carried") or self._value("weight"))
        text = self._text("weight_trend")
        if weight is None:
            return 60, "負磅資料不足，負磅分60分。", "missing_neutral"
        score = scoring.WEIGHT_MICRO_WEIGHTS.get("base", 64.0)
        note = f"今仗負磅{weight:.0f}磅，屬可處理範圍，負磅分64分。"
        if weight <= 120:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("light_weight_base", 70.0)
            note = f"今仗負磅{weight:.0f}磅較輕，負磅分70分。"
        elif weight >= 132:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("heavy_weight_base", 54.0)
            note = f"今仗負磅{weight:.0f}磅偏重，負磅分54分。"
        if "轉輕" in text:
            score += scoring.WEIGHT_MICRO_WEIGHTS.get("trend_lighter_bonus", 4.0)
            note += " 體重趨勢顯示轉輕，略加支持。"
        if "轉重" in text:
            score += scoring.WEIGHT_MICRO_WEIGHTS.get("trend_heavier_pen", -4.0)
            note += " 體重趨勢偏重，略扣。"
        return clip_score(score), note, "weight_carried"

    def _consistency_score(self, features):
        form = str(self.horse_data.get("last_6_finishes") or "")
        finishes = [int(item) for item in re.findall(r"\b\d+\b", form)[:6]]
        if self._is_debut():
            prep = self._prep_score()
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_base", 58.0) + (prep - 60) * scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_prep_mult", 0.35)
            note = f"初出馬以晨操備戰穩定性代替正式近績，備戰分{prep:.0f}，穩定性分{score:.1f}。"
            return score, note, "trackwork_digest"
        if len(finishes) >= 3:
            places = sum(1 for rank in finishes if rank <= 3)
            poor = sum(1 for rank in finishes if rank >= 8)
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("base", 58.0) + places * scoring.CONSISTENCY_MICRO_WEIGHTS.get("place_mult", 7.0) - poor * scoring.CONSISTENCY_MICRO_WEIGHTS.get("poor_mult", 5.0)
            note = f"近{len(finishes)}仗有{places}次前三、{poor}次八名或以後，穩定性分{clip_score(score):.1f}。"
            return score, note, "last_6_finishes"
        if features.get("form_score", 60) >= 70:
            return scoring.CONSISTENCY_MICRO_WEIGHTS.get("good_form_base", 66.0), "近績樣本少但名次訊號正面，穩定性分66分。", "last_6_finishes"
        return scoring.CONSISTENCY_MICRO_WEIGHTS.get("neutral_base", 60.0), "近績樣本不足，穩定性分60分。", "missing_neutral"

    def _risk_score(self, features):
        score = scoring.RISK_MICRO_WEIGHTS.get("base", 68.0)
        notes = []
        medical = self._text("medical_flags")
        trackwork = self._text("trackwork_health", "trackwork_digest")
        if "無醫療事故" in medical:
            notes.append("醫療欄未見事故")
        else:
            score += scoring.RISK_MICRO_WEIGHTS.get("medical_unknown_pen", -8.0)
            self.risk_flags.append("medical_record_unknown")
            notes.append("醫療欄資料不足")
        if "操練放緩" in trackwork:
            score += scoring.RISK_MICRO_WEIGHTS.get("trackwork_slowing_pen", -6.0)
            self.risk_flags.append("trackwork_slowing")
            notes.append("晨操趨勢放緩")
        if self._is_debut():
            score += scoring.RISK_MICRO_WEIGHTS.get("debut_pen", -5.0)
            self.risk_flags.append("debut_race_experience_unknown")
            notes.append("初出缺正式賽經驗")
        if features.get("draw_score", 60) < 55:
            score += scoring.RISK_MICRO_WEIGHTS.get("draw_pressure_pen", -5.0)
            self.risk_flags.append("draw_pressure")
            notes.append("檔位分偏低")
        if features.get("distance_score", 60) < 58:
            score += scoring.RISK_MICRO_WEIGHTS.get("distance_unproven_pen", -4.0)
            self.risk_flags.append("distance_unproven")
            notes.append("路程證明不足")
        return clip_score(score), "、".join(notes) + f"，風險分{clip_score(score):.1f}。", "medical_flags"

    def _confidence_score(self, features):
        present = 0
        important_sources = ("trackwork_digest", "draw_verdict", "weight_carried", "last_6_finishes", "season_stats")
        for key in important_sources:
            if self._value(key) not in (None, "", "N/A"):
                present += 1
        score = scoring.CONFIDENCE_MICRO_WEIGHTS.get("base", 48.0) + present * scoring.CONFIDENCE_MICRO_WEIGHTS.get("present_mult", 6.0)
        if self._value("jockey_combo_block"):
            score += scoring.CONFIDENCE_MICRO_WEIGHTS.get("jockey_combo_bonus", 5.0)
        if self._is_debut():
            score += scoring.CONFIDENCE_MICRO_WEIGHTS.get("debut_pen", -4.0)
        if features.get("risk_score", 60) < 55:
            score += scoring.CONFIDENCE_MICRO_WEIGHTS.get("high_risk_pen", -5.0)
        note = f"可用資料覆蓋{present}/{len(important_sources)}項，信心分{clip_score(score):.1f}。"
        return clip_score(score), note, "data_coverage"

    def _formline_strength_score(self):
        signal = self._formline_strength_signal()
        mapping = {
            "elite": 88,
            "strong": 78,
            "weak": 54,
            "neutral": 64,
            "unknown": 60,
        }
        note_map = {
            "elite": "之前對手質量高，賽績線強度屬高含金量。",
            "strong": "之前對手組合有基本強度，賽績線含金量屬正面。",
            "weak": "之前對手強度支持不足，賽績線含金量偏弱。",
            "neutral": "對手強度中性，賽績線含金量一般。",
            "unknown": "未有清晰對手強度資料，賽績線強度按中性處理。",
        }
        score = mapping[signal]
        higher = self._value("formline_higher_win_count")
        same = self._value("formline_same_win_count")
        lower = self._value("formline_lower_win_count")
        higher_count = int(parse_float(higher) or 0)
        same_count = int(parse_float(same) or 0)
        lower_count = int(parse_float(lower) or 0)
        bonus = min(8, higher_count * 3 + same_count * 1 - lower_count * 1)
        if higher_count:
            note_map[signal] += f" 對手後續有{higher_count}匹於更高班再贏，含金量可再上調。"
        elif same_count and not lower_count:
            note_map[signal] += f" 對手後續有{same_count}匹於同班再贏，證明基本線索有兌現。"
        elif lower_count and not higher_count:
            note_map[signal] += f" 對手後續主要在較低班再贏，提升幅度只宜保守。"
        return clip_score(score + bonus), note_map[signal], "formline_strength"

    def _margin_trend_score(self):
        signal = self._margin_trend_signal()
        mapping = {
            "improving": 76,
            "worsening": 48,
            "flat": 60,
        }
        note_map = {
            "improving": "近仗輸距有收窄跡象，代表面對同類對手時有追近訊號。",
            "worsening": "近仗輸距有擴大跡象，代表近期對同類對手的抵抗力下滑。",
            "flat": "近仗輸距走勢未見鮮明改善或惡化，暫按中性理解。",
        }
        return mapping[signal], note_map[signal], "margin_trend"

    def _same_distance_signal_score(self):
        same_distance = self._same_distance_record()
        best_distance = self._clean(self._value("best_distance") or "")
        if same_distance and same_distance["starts"] > 0 and same_distance["places"] > 0:
            return 72, "同程有接近或上名證據，賽績線放返今場路程唔算失焦。", "season_stats_line"
        if same_distance and same_distance["starts"] > 0:
            return 54, "同程已有樣本但未見成果，賽績線搬返今場路程仍有保留。", "season_stats_line"
        if "相近上名經驗" in best_distance:
            return 64, "雖然未跑同程，但有相近路程上名經驗，可提供少量旁證。", "best_distance"
        if "未跑過" in best_distance:
            return 58, "今場路程未有直接實績，賽績線只可作有限度轉化。", "best_distance"
        return 60, "同程證據未算清晰，按中性處理。", "best_distance"

    def _trackwork_trend_score(self):
        trackwork = self._trackwork_markers()
        classification = trackwork["classification"]
        trend = trackwork["trend"]
        
        # 1. Text-based trend base score
        if classification == "翻案復刻":
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("rebound_base", 66.0)
            note = "晨操摘要屬翻案復刻，顯示團隊正嘗試用備戰訊號替近績波動補強。"
        elif "加強" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("improving_base", 70.0)
            note = f"{trend}，備戰力度有推進，對狀態延續屬正面訊號。"
        elif "放緩" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("slowing_base", 52.0)
            note = f"{trend}，狀態維持度要保守少少。"
        else:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("neutral_base", 60.0)
            note = "操練趨勢未見鮮明方向，按中性處理。"
            
        # 2. Raw exercise numerical multipliers
        summary = self.horse_data.get("trackwork", {}).get("summary", {})
        gallops = int(summary.get("gallops_21d", 0))
        trials = int(summary.get("trials_21d", 0))
        trotting = int(summary.get("trotting_21d", 0))
        swimming = int(summary.get("swimming_21d", 0))
        
        gallop_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("gallop_weight", 0.5)
        trial_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("trial_weight", 1.0)
        trotting_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("trotting_weight", 0.1)
        swimming_w = scoring.TRACKWORK_MICRO_WEIGHTS.get("swimming_weight", 0.05)
        
        activity_bonus = (gallops * gallop_w) + (trials * trial_w) + (trotting * trotting_w) + (swimming * swimming_w)
        
        # Apply cap and floor
        cap = scoring.TRACKWORK_MICRO_WEIGHTS.get("activity_cap", 8.0)
        floor = scoring.TRACKWORK_MICRO_WEIGHTS.get("activity_floor", -4.0)
        activity_bonus = max(floor, min(activity_bonus, cap))
        
        final_score = scoring.clip_score(base_score + activity_bonus)
        if activity_bonus > 2.0:
            note += f" (數據顯示操練特別積極 +{activity_bonus:.1f})"
        elif activity_bonus < -1.0:
            note += f" (數據顯示活躍度偏低 {activity_bonus:.1f})"
            
        return final_score, note, "trackwork_digest"

    def _ability_score(self, matrix_scores):
        if self._is_debut():
            debut_weights = {
                'trainer_signal': 0.30,
                'horse_health': 0.30,
                'race_shape': 0.20,
                'stability': 0.15,
                'class_advantage': 0.05
            }
            return sum(matrix_scores.get(key, 60.0) * weight for key, weight in debut_weights.items())
        else:
            return sum(matrix_scores[key] * weight for key, weight in MATRIX_WEIGHTS.items())

    def build_shadow_profile(self, profile_name, base_auto=None):
        if profile_name != "consistency_context":
            return None
        auto = base_auto or self.analyze_horse()
        base_features = auto.get("feature_scores", {}) if isinstance(auto, dict) else {}
        if not isinstance(base_features, dict) or not base_features:
            return None

        shadow_features = {key: clip_score(base_features.get(key, 60.0)) for key in base_features}
        shadow_score = self._candidate_consistency_shadow_score()
        applied = shadow_score is not None
        reason = "未觸發 consistency shadow，沿用主線穩定性評分。"
        if applied:
            shadow_features["consistency_score"] = clip_score(shadow_score)
            reason = "影子排序重算 consistency_score，加入輸距權重、近期回暖/回落與 margin trend。"

        matrix_scores = map_features_to_matrix_scores(shadow_features)
        ability_score = round(self._ability_score(matrix_scores), 2)
        base_ability = float(auto.get("ability_score", ability_score))
        return {
            "profile": profile_name,
            "applied": applied,
            "ability_score": ability_score,
            "ability_delta": round(ability_score - base_ability, 2),
            "grade": compute_grade(ability_score),
            "consistency_score": round(float(shadow_features.get("consistency_score", 60.0)), 2),
            "consistency_delta": round(float(shadow_features.get("consistency_score", 60.0)) - float(base_features.get("consistency_score", 60.0)), 2),
            "matrix_scores": matrix_scores,
            "reason": reason,
        }

    def _apply_mainline_context(self, feature_scores, feature_notes):
        updated = dict(feature_scores)
        notes = {}
        sources = {}

        updated, trainer_note = self._apply_trainer_signal_context(updated)
        if trainer_note:
            notes["jockey_score"] = self._append_note(feature_notes.get("jockey_score"), trainer_note)
            notes["trainer_score"] = self._append_note(feature_notes.get("trainer_score"), trainer_note)
            sources["jockey_score"] = "th01_trainer_context"
            sources["trainer_score"] = "th01_trainer_context"

        health_score, health_note = self._candidate_health_risk_score()
        if health_score is not None:
            updated["risk_score"] = clip_score(health_score)
            notes["risk_score"] = self._append_note(feature_notes.get("risk_score"), health_note)
            sources["risk_score"] = "th01_health_context"

        consistency_score = self._candidate_consistency_shadow_score()
        if consistency_score is not None:
            updated["consistency_score"] = clip_score(consistency_score)
            notes["consistency_score"] = self._append_note(
                feature_notes.get("consistency_score"),
                "已套用 CX01 consistency context，加入輸距權重、近期回暖/回落與 margin trend。",
            )
            sources["consistency_score"] = "cx01_consistency_context"

        return updated, notes, sources

    def _apply_trainer_signal_context(self, feature_scores):
        updated = dict(feature_scores)
        prior_stack = self._trainer_signal_priors()
        jockey = self._clean(self.horse_data.get("jockey"))
        trainer = self._clean(self.horse_data.get("trainer"))
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()

        jockey_adj = 0.0
        trainer_adj = 0.0
        triggers = []

        horse_history = self._current_jockey_horse_record()
        if horse_history:
            history_adj = self._trainer_history_adjustment(horse_history)
            jockey_adj += history_adj
            if history_adj:
                triggers.append("人馬歷史")

        prior = self._jockey_trainer_prior()
        if prior is None and jockey and trainer:
            prior = prior_stack.combo.get((jockey, trainer))
        combo_adj = self._trainer_combo_adjustment(prior)
        if combo_adj:
            jockey_adj += combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_jockey_share"]
            trainer_adj += combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_trainer_share"]
            triggers.append("騎練組合")

        if distance and jockey:
            distance_row = prior_stack.jockey_distance.get((jockey, distance))
            distance_adj = self._jockey_distance_adjustment(distance_row)
            jockey_adj += distance_adj
            if distance_adj:
                triggers.append("騎師同程")

        if distance and trainer:
            trainer_row = prior_stack.trainer_distance.get((trainer, distance))
            trainer_distance_adj = self._trainer_distance_adjustment(trainer_row)
            trainer_adj += trainer_distance_adj
            if trainer_distance_adj:
                triggers.append("練馬師同程")

        if self._is_jockey_changed() is True:
            change_adj = self._jockey_change_adjustment(prior_stack.jockey_change)
            jockey_adj += change_adj
            if change_adj:
                triggers.append("換騎折讓")

        if jockey_adj:
            updated["jockey_score"] = clip_score(updated.get("jockey_score", 60.0) + jockey_adj)
        if trainer_adj:
            updated["trainer_score"] = clip_score(updated.get("trainer_score", 60.0) + trainer_adj)

        if not triggers:
            return updated, ""
        note = "已套用 TH01 騎練先驗，上下文包含" + "、".join(dict.fromkeys(triggers)) + "。"
        return updated, note

    def _apply_health_only_v2(self, base_score):
        return round(clip_score(base_score), 2)

    def _apply_trainer_signal_v3(self, base_score):
        return round(clip_score(base_score), 2)

    def _candidate_health_risk_score(self):
        score = scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["base"]
        medical = self._text("medical_flags")
        weight_trend = self._text("weight_trend")
        trackwork_health = self._text("trackwork_health")
        days = parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
        weight_span = self._weight_trend_span(weight_trend)

        if "✅ 無醫療事故記錄" in medical:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_clear_bonus"]
        elif medical and medical != "N/A":
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_issue_pen"]
            if self._has_recovery_evidence():
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_recovery_bonus"]
        else:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_unknown_pen"]

        if days is not None:
            if days <= 7:
                if weight_span is not None and weight_span <= 14.0:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_stable_bonus"]
                else:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_unstable_pen"]
            elif days <= 21:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_21_bonus"]
            elif days <= 45:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_45_bonus"]
            elif days > 75:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_gt_75_pen"]

        if any(token in weight_trend for token in ("急劇變化", "急增", "急減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_sharp_change_pen"]
        elif any(token in weight_trend for token in ("顯著轉輕", "大減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_drop_pen"]
        elif any(token in weight_trend for token in ("顯著轉重", "大增")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_gain_pen"]
        elif any(token in weight_trend for token in ("微增", "微減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]

        if weight_span is not None:
            if weight_span <= 12.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_12_bonus"]
            elif weight_span <= 18.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_18_bonus"]
            elif weight_span <= 32.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_32_pen"]
            else:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_gt_32_pen"]

        if "操練放緩" in trackwork_health:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["trackwork_slowing_pen"]
        elif "risk_flags=[]" in trackwork_health or "risk_flags: []" in trackwork_health:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["trackwork_clean_bonus"]

        if "swimming=0" in trackwork_health and days is not None and days <= 21:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["swimming_zero_quick_return_pen"]
        if "blank_days=3" in trackwork_health or "blank_days=4" in trackwork_health:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["blank_days_small_pen"]

        note = "已套用 TH01 健康上下文，綜合醫療、休賽、體重波幅與晨操旗標重算風險分。"
        return clip_score(score), note

    def _candidate_consistency_shadow_score(self):
        if self._is_debut():
            return None

        detail = self._text("recent_6_detail")
        runs = self._parse_recent_runs(detail)
        if not runs:
            return None

        weights = [1.00, 0.85, 0.70, 0.55, 0.45, 0.35]
        weighted_total = sum(weights[: len(runs)])
        close_credit = 0.0
        poor_debit = 0.0
        severe_debit = 0.0

        for idx, run in enumerate(runs[:6]):
            weight = weights[idx]
            rank = run["rank"]
            margin = run["margin"]

            if rank <= 3:
                close_credit += weight
                continue
            if rank <= 5 and margin is not None and margin <= 3.0:
                close_credit += weight * 0.75
            elif rank <= 7 and margin is not None and margin <= 2.5:
                close_credit += weight * 0.40

            if rank >= 8 and margin is not None and margin >= 5.0:
                poor_debit += weight
            elif rank >= 6 and margin is not None and margin >= 7.0:
                poor_debit += weight * 0.70

            if rank >= 10 and margin is not None and margin >= 8.0:
                severe_debit += weight

        close_ratio = close_credit / weighted_total if weighted_total else 0.0
        poor_ratio = poor_debit / weighted_total if weighted_total else 0.0
        severe_ratio = severe_debit / weighted_total if weighted_total else 0.0

        score = 58.0 + close_ratio * 18.0 - poor_ratio * 14.0 - severe_ratio * 10.0
        margin_trend = self._text("margin_trend")
        if "收窄中" in margin_trend:
            score += 4.0
        elif "擴大中" in margin_trend:
            score -= 4.0
        elif "波動" in margin_trend:
            score -= 1.0

        finish_positions = [run["rank"] for run in runs[:6]]
        if len(finish_positions) >= 5:
            recent_avg = sum(finish_positions[:3]) / 3.0
            older = finish_positions[3:6]
            older_avg = sum(older) / len(older)  # was /3.0 — undercounted when only 5 runs (2 elems)
            if recent_avg + 1.0 < older_avg:
                score += 3.0
            elif recent_avg > older_avg + 1.0:
                score -= 3.0

        return clip_score(score)

    def _parse_recent_runs(self, detail):
        runs = []
        for rank_text, margin_text in re.findall(r":\s*(\d+)名\s+([^|,]+)", str(detail or "")):
            try:
                rank = int(rank_text)
            except ValueError:
                continue
            runs.append(
                {
                    "rank": rank,
                    "margin": self._margin_to_float(margin_text.strip()),
                }
            )
        return runs

    def _margin_to_float(self, value):
        text = str(value or "").strip()
        if not text or text in {"-", "--", "N/A"}:
            return None
        if "平頭馬" in text:
            return 0.0
        if "短馬頭位" in text:
            return 0.05
        if "頭位" in text:
            return 0.1
        if "頸位" in text:
            return 0.25
        if "多個馬位" in text:
            return 8.0

        total = 0.0
        matched = False
        for part in text.split("-"):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                numerator, denominator = part.split("/", 1)
                try:
                    total += float(numerator) / float(denominator)
                    matched = True
                except ValueError:
                    continue
                continue
            try:
                total += float(part)
                matched = True
            except ValueError:
                continue
        if matched:
            return total
        return None

    def _has_recovery_evidence(self):
        finishes = [int(item) for item in re.findall(r"\b\d+\b", str(self.horse_data.get("last_6_finishes") or ""))[:3]]
        if any(rank <= 3 for rank in finishes):
            return True
        finish_time_level = self._text("finish_time_adj_level")
        if "仍具競爭力" in finish_time_level or "持續快於標準" in finish_time_level:
            return True
        raw_l400 = parse_float(self._value("raw_l400"))
        return raw_l400 is not None and raw_l400 <= 23.4

    def _weight_trend_span(self, weight_trend):
        match = re.search(r"波幅(\d+(?:\.\d+)?)lb", str(weight_trend or ""))
        if match:
            return float(match.group(1))
        return None

    def _trainer_history_adjustment(self, row):
        if row["starts"] >= 2 and (row["wins"] >= 1 or row["place_rate"] >= 50.0) and row["avg_finish"] <= 5.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_strong"]
        if row["starts"] >= 3 and row["place_rate"] >= 33.0 and row["avg_finish"] <= 5.5:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_supportive"]
        if row["starts"] >= 3 and row["place_rate"] == 0.0 and row["avg_finish"] >= 7.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_zero_place"]
        if row["starts"] >= 5 and row["place_rate"] <= 20.0 and row["avg_finish"] >= 6.5:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["horse_history_weak"]
        return 0.0

    def _trainer_combo_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        if starts < 80:
            return 0.0
        if win_rate >= 14.0 or place_rate >= 36.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_elite"]
        if win_rate >= 11.0 or place_rate >= 30.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_positive"]
        if win_rate <= 7.0 and place_rate <= 23.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_negative"]
        return 0.0

    def _jockey_distance_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        if starts < 80:
            return 0.0
        if win_rate >= 15.0 or place_rate >= 40.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_elite"]
        if win_rate >= 10.0 or place_rate >= 30.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_positive"]
        if win_rate <= 6.0 and place_rate <= 22.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_distance_negative"]
        return 0.0

    def _trainer_distance_adjustment(self, row):
        if not row:
            return 0.0
        starts = float(row.get("starts", 0.0) or 0.0)
        win_rate = float(row.get("win_rate", 0.0) or 0.0)
        place_rate = float(row.get("place_rate", 0.0) or 0.0)
        if starts < 80:
            return 0.0
        if win_rate >= 12.0 or place_rate >= 34.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_elite"]
        if win_rate >= 9.0 or place_rate >= 28.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_positive"]
        if win_rate <= 5.0 and place_rate <= 20.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["trainer_distance_negative"]
        return 0.0

    def _jockey_change_adjustment(self, jockey_change_rows):
        keep = jockey_change_rows.get(False) if jockey_change_rows else None
        change = jockey_change_rows.get(True) if jockey_change_rows else None
        if not keep or not change:
            return 0.0
        if keep["win_rate"] >= change["win_rate"] + 1.0 and keep["place_rate"] >= change["place_rate"] + 3.0:
            return scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["jockey_change_negative"]
        return 0.0

    def _is_jockey_changed(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        rows = self._recent_jockey_history_rows()
        if not current_jockey or not rows:
            return None
        latest = rows[0].get("jockey", "")
        return bool(latest and latest != current_jockey)

    def _trainer_signal_priors(self):
        global _TRAINER_SIGNAL_PRIORS
        if _TRAINER_SIGNAL_PRIORS is None:
            _TRAINER_SIGNAL_PRIORS = TrainerSignalPriors()
        return _TRAINER_SIGNAL_PRIORS

    def _append_note(self, base_note, extra_note):
        base = str(base_note or "").strip()
        extra = str(extra_note or "").strip()
        if not base:
            return extra or "資料不足，中性60分。"
        if not extra:
            return base
        return base + " " + extra


    def _matrix_reasoning(self, matrix_scores, matrix, features, notes):
        specs = {
            "stability": ("狀態與穩定性", ("form_score", "consistency_score", "trackwork_trend_score")),
            "sectional": ("段速與場地適性", ("speed_score", "track_going_score")),
            "race_shape": ("檔位與走位（不含步速）", ("draw_score",)),
            "trainer_signal": ("騎練訊號", ("jockey_score", "trainer_score")),
            "horse_health": ("馬匹健康 / 新鮮感", ("risk_score", "weight_score", "confidence_score")),
            "form_line": ("賽績線", ("formline_strength_score", "margin_trend_score")),
            "class_advantage": ("級數優勢", ("class_score", "weight_score")),
        }
        reasoning = {}
        for key, (label, feature_keys) in specs.items():
            evidence = self._best_evidence(feature_keys, notes)
            score = matrix_scores[key]
            components = [
                {
                    "key": name,
                    "label": self._feature_score_label(name),
                    "score": round(features[name], 2),
                    "weight": weight,
                    "note": self._clean(notes.get(name, "資料不足，中性60分。")),
                }
                for name, weight in MATRIX_FORMULAS[key]
            ]
            reasoning[key] = {
                "label": label,
                "score": round(score, 2),
                "symbol": matrix[key],
                "tone": self._matrix_score_tone(score),
                "components": components,
                "evidence": evidence,
                "text": self._matrix_summary_text(key, label, score, features, evidence),
            }
        return reasoning

    def _score_breakdown(self, features, notes):
        return {
            key: {
                "score": round(features[key], 2),
                "note": notes.get(key, "資料不足，中性60分。"),
                "source": self.provenance.get(key, "missing_neutral"),
            }
            for key in FEATURE_KEYS
        }

    def _core_logic(self, features, matrix_scores, matrix_reasoning):
        name = self.horse_data.get("horse_name", "此駒")
        top = sorted(matrix_scores.items(), key=lambda item: item[1], reverse=True)[:2]
        low = sorted(matrix_scores.items(), key=lambda item: item[1])[:2]
        top_keys = {key for key, _score in top}
        low_keys = {key for key, _score in low}
        
        top_text = " ".join(self._core_support_sentence(key, score, features) for key, score in top)
        low_text = " ".join(self._core_risk_sentence(key, score, features) for key, score in low)
        
        include_trackwork = self._should_include_trackwork_context(top_keys, low_keys)
        context = self._context_sentence(features, top_keys, low_keys, include_trackwork)
        risk = self._risk_sentence({"trackwork_slowing"} if include_trackwork else None)
        overall = self._overall_projection_sentence(top, low, features)
        competitiveness = self._competitiveness_opening(matrix_scores, features, top, low)
        
        # More natural flowing text without robotic prefixes
        parts = [
            f"{name}{competitiveness}",
            top_text,
            f"不過要留意，{low_text}" if low_text else "",
            context,
            overall,
            risk
        ]
        
        text = " ".join(part.strip() for part in parts if part and part.strip())
        return self._normalize_prose(text)

    def _context_sentence(self, features, top_keys=None, low_keys=None, include_trackwork=True):
        top_keys = set(top_keys or ())
        low_keys = set(low_keys or ())
        bits = []
        if self._is_debut():
            bits.append("此駒屬初出馬，正式賽績空白，所以今次主要靠備戰內容同資料完整度去判斷 ready 未。")
        else:
            if "stability" not in top_keys and "stability" not in low_keys:
                bits.append(self._form_context_sentence(features))
        if "race_shape" not in top_keys and "race_shape" not in low_keys:
            bits.append(self._draw_context_sentence(features))
        if include_trackwork:
            bits.append(self._trackwork_context_sentence(features))
        return "".join(bits)

    def _risk_sentence(self, suppressed_flags=None):
        suppressed_flags = set(suppressed_flags or ())
        visible_flags = [flag for flag in self.risk_flags if flag not in suppressed_flags]
        if not visible_flags:
            return "暫未見重大紅旗，但仍要留意臨場場地及資料更新。"
        phrases = [self._risk_phrase_for_flag(flag) for flag in sorted(set(visible_flags))[:3]]
        phrases = [phrase for phrase in phrases if phrase]
        if not phrases:
            return "仍有一兩項風險未完全消化，臨場要再留意。"
        if len(phrases) == 1:
            return phrases[0]
        return "另外要留意" + "、".join(phrases[:-1]) + "，以及" + phrases[-1] + "。"

    def _normalize_reason(self, key, note):
        note = str(note or "").strip()
        if not note:
            return "資料不足，中性60分。"
        if key == "jockey_score":
            if "Elite" in note:
                self.reason_codes.append("elite_jockey_with_data_support")
                return "騎師分由結構化騎師層級給予正面支持。"
            if "Top Tier" in note:
                return "騎師分有正面層級支持。"
            return "騎師資料未見可量化加分，按中性處理。"
        if key == "trainer_score":
            if "High" in note or "Consistent" in note:
                return "練馬師分有穩定或高效率標籤支持。"
            return "練馬師資料未見可量化加分，按中性處理。"
        if key == "draw_score":
            if "Inside" in note:
                return "檔位屬內檔，檔位分正面。"
            if "Outside" in note:
                self.risk_flags.append("draw_pressure")
                return "檔位偏外或統計不利，走位容錯較低。"
            return "檔位屬中檔，影響偏中性。"
        if key == "form_score":
            if "No recent" in note or "Indeterminable" in note:
                return "近績資料不足，近績分按中性處理。"
            return "近績分由最近名次加權計算。"
        if key == "speed_score":
            if "Sectional data incomplete" in note:
                return "賽績段速資料未完整，速度分按中性處理。"
            match = re.search(r"\(([^)]+)\)", note)
            detail_text = f"（{match.group(1)}）" if match else ""
            if "Strong race sectional profile" in note:
                return f"近仗末段、能量與步速修正訊號偏強{detail_text}，速度分有明顯支持。"
            if "Positive race sectional profile" in note:
                return f"近仗 L400、能量走勢同步速修正表現正面{detail_text}，速度分有基本支持。"
            if "Fair race sectional profile" in note:
                return f"近仗段速輪廓尚算平穩{detail_text}，速度分輕微正面。"
            if "Neutral race sectional profile" in note:
                return f"近仗段速數據只屬中性{detail_text}，速度分未見額外加成。"
            if "Weak race sectional profile" in note:
                return f"近仗末段或步速修正表現偏弱{detail_text}，速度分要保守處理。"
            return self._clean(note)
        return self._clean(note)

    def _best_evidence(self, feature_keys, notes):
        for key in feature_keys:
            note = notes.get(key)
            if note and "資料不足" not in note:
                return note
        return "相關來源不足，該維度以中性或保守分處理。"

    def _form_context_sentence(self, features):
        form_score = float(features.get("form_score", 60))
        consistency_score = float(features.get("consistency_score", 60))
        if form_score >= 80 and consistency_score >= 75:
            return "近況走勢整體向上，而且唔止一場交代，呢點令基本面較實。"
        if form_score < 52 or consistency_score < 52:
            return "近期表現反覆，前列再現率未算高，所以近態信心只能保守少少。"
        return "近況有一定交代，但穩定度未算完全企穩，仍然要睇臨場節奏配合。"

    def _draw_context_sentence(self, features):
        draw_score = float(features.get("draw_score", 60))
        if draw_score >= 72:
            return "今場形勢唔差，檔位至少有助佢用比較順手嘅方式入局。"
        elif draw_score < 55:
            return "今場形勢唔算就手，檔位同走位成本都有機會限制發揮。"
        return "今場形勢大致中性，未見明顯著數，但亦未去到先天輸蝕。"

    def _trackwork_context_sentence(self, features):
        trackwork = self._trackwork_markers()
        if not any(trackwork.values()):
            return "晨操部署未見鮮明變化，今次只可作輔助參考。"
        if trackwork["classification"] == "翻案復刻":
            lead = "備戰部署帶有翻案味道，馬房似乎想用近期操練去補回正式賽績上的不足。"
        elif trackwork["classification"]:
            lead = f"備戰部署以「{trackwork['classification']}」為主，反映今次準備方向大致清晰。"
        else:
            lead = "備戰內容有一定訊號，但未去到非常鮮明。"
        if "加強" in trackwork["trend"]:
            trend = "近課節奏有推進，屬正面備戰。"
        elif "放緩" in trackwork["trend"]:
            trend = "近課節奏略為放緩，所以只能視作輔助確認。"
        else:
            trend = "近課節奏大致正常，未見特別升溫或失速。"
        if trackwork["positive"] and trackwork["positive"] != "無":
            close = "至少唔似無備而來。"
        elif trackwork["risk"] and trackwork["risk"] != "無":
            close = "但暫時未見可以單靠備戰訊號扭轉全局。"
        else:
            close = "整體只屬輔助資訊。"
        return lead + trend + close

    def _prep_score(self):
        digest = self._value("trackwork_digest")
        numbers = re.findall(r"備戰分(\d+(?:\.\d+)?)", str(digest or ""))
        return float(numbers[-1]) if numbers else 60.0

    def _current_jockey_horse_record(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        for row in self._jockey_combo_rows():
            if row["is_current"] or row["jockey"] == current_jockey:
                return {
                    "starts": row["starts"],
                    "wins": row["wins"],
                    "places": row["places"],
                    "avg_finish": row["avg_finish"],
                    "win_rate": row["win_rate"],
                    "place_rate": row["place_rate"],
                }
        return None

    def _current_declared_jockey(self):
        block = str(self._value("jockey_combo_block") or "")
        match = re.search(r"今場騎師:\s*([^\n]+)", block)
        return match.group(1).strip() if match else ""

    def _jockey_combo_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 8:
                continue
            if cols[0] in {"騎師", "------", "#", "---"}:
                continue
            if cols[0].startswith("#") or cols[0].isdigit():
                continue
            jockey_col = cols[0]
            is_current = "← 今場" in jockey_col
            jockey_name = jockey_col.replace("← 今場", "").strip()
            try:
                rows.append(
                    {
                        "jockey": jockey_name,
                        "starts": float(cols[1]),
                        "wins": float(cols[2]),
                        "places": float(cols[4]),
                        "avg_finish": float(cols[5]),
                        "win_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[6]).group(0)),
                        "place_rate": float(re.search(r"-?\d+(?:\.\d+)?", cols[7]).group(0)),
                        "is_current": is_current,
                    }
                )
            except (AttributeError, ValueError):
                continue
        return rows

    def _recent_jockey_history_rows(self):
        block = str(self._value("jockey_combo_block") or "")
        rows = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]
            if len(cols) < 5:
                continue
            if cols[0] in {"#", "---"} or cols[0].startswith("---"):
                continue
            if not re.fullmatch(r"\d+", cols[0]):
                continue
            rows.append(
                {
                    "index": int(cols[0]),
                    "date": cols[1],
                    "jockey": cols[2],
                    "finish": cols[3],
                    "note": cols[4],
                }
            )
        rows.sort(key=lambda row: row["index"])
        return rows

    def _best_jockey_for_horse(self, exclude=None):
        exclude = set(exclude or ())
        rows = [row for row in self._jockey_combo_rows() if row["jockey"] not in exclude]
        if not rows:
            return None
        return sorted(
            rows,
            key=lambda row: (
                row["wins"],
                row["places"],
                row["place_rate"],
                row["win_rate"],
                -row["avg_finish"],
                row["starts"],
            ),
            reverse=True,
        )[0]

    def _format_combo_record(self, row):
        return (
            f"{row['jockey']}×此馬 {int(row['starts'])}場 {int(row['wins'])}勝 "
            f"{int(row['places'])}上名 平均名次{row['avg_finish']:.1f} "
            f"勝率{row['win_rate']:.1f}% 位率{row['place_rate']:.1f}%"
        )

    def _trainer_signal_combo_summary(self):
        combo_block = self._clean(self._value("jockey_combo_block") or "")
        if not combo_block:
            return ""
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey() or "今場騎師")
        current_row = None
        for row in self._jockey_combo_rows():
            if row["is_current"] or row["jockey"] == current_jockey:
                current_row = row
                break
        recent_rows = self._recent_jockey_history_rows()
        latest_rider = recent_rows[0]["jockey"] if recent_rows else ""
        retained = bool(latest_rider and latest_rider == current_jockey)
        best_other = self._best_jockey_for_horse(exclude={current_jockey} if current_row else set())

        bits = []
        if current_row:
            bits.append(f"人馬組合統計方面，{self._format_combo_record(current_row)}。")
            if retained:
                bits.append("今場沿用上仗配搭。")
            elif latest_rider:
                bits.append(f"今場屬換騎，上仗由{latest_rider}執韁。")
            if best_other:
                current_edge = (
                    current_row["wins"],
                    current_row["places"],
                    current_row["place_rate"],
                    current_row["win_rate"],
                    -current_row["avg_finish"],
                    current_row["starts"],
                )
                other_edge = (
                    best_other["wins"],
                    best_other["places"],
                    best_other["place_rate"],
                    best_other["win_rate"],
                    -best_other["avg_finish"],
                    best_other["starts"],
                )
                if current_edge >= other_edge:
                    bits.append("相比其他曾策騎者，現任配搭已屬此馬較有依據的一組。")
                else:
                    bits.append(f"此馬歷來較有參考的是 {self._format_combo_record(best_other)}。")
        else:
            bits.append(f"人馬組合統計方面，{current_jockey}今場暫未有此馬歷史。")
            if latest_rider:
                bits.append(f"今場屬換騎，上仗由{latest_rider}執韁。")
            if best_other:
                bits.append(f"此馬歷來較有參考的是 {self._format_combo_record(best_other)}。")
        return self._normalize_prose("".join(bits))

    def _jockey_trainer_prior(self):
        priors = self._value("jockey_trainer_combo_prior")
        if isinstance(priors, dict):
            return priors
        return None

    def _source_for(self, name):
        return {
            "jockey_score": "jockey",
            "trainer_score": "trainer",
            "draw_score": "barrier",
            "form_score": "last_6_finishes",
            "speed_score": "race_sectional_context",
        }.get(name, "missing_neutral")

    def _value(self, key):
        if key in self.horse_data and self.horse_data.get(key) not in (None, ""):
            return self.horse_data.get(key)
        return self.data.get(key)

    def _text(self, *keys):
        return " ".join(str(self._value(key) or "") for key in keys)

    def _is_debut(self):
        return bool(self.horse_data.get("is_debut") or self.horse_data.get("debut_runner") or self.horse_data.get("career_tag") == "DEBUT")

    def _clean(self, value):
        text = str(value or "").strip()
        return "資料未完成，中性處理" if "[FILL" in text.upper() else text

    def _short(self, value, limit):
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    def _feature_label(self, key):
        return {
            "form_score": "近績",
            "speed_score": "速度",
            "class_score": "級數",
            "jockey_score": "騎師",
            "trainer_score": "練馬師",
            "draw_score": "檔位",
            "distance_score": "路程",
            "track_going_score": "場地",
            "weight_score": "負磅",
            "consistency_score": "穩定性",
            "trackwork_trend_score": "操練趨勢",
            "risk_score": "風險",
            "confidence_score": "信心",
        }[key]

    def _feature_score_label(self, key):
        return {
            "form_score": "近績分",
            "speed_score": "速度分",
            "class_score": "班次分",
            "jockey_score": "騎師分",
            "trainer_score": "練馬師分",
            "draw_score": "檔位分",
            "distance_score": "路程分",
            "track_going_score": "場地分",
            "weight_score": "負磅分",
            "consistency_score": "穩定性分",
            "trackwork_trend_score": "操練趨勢分",
            "risk_score": "風險分",
            "confidence_score": "信心分",
            "formline_strength_score": "賽績線強度分",
            "margin_trend_score": "輸距走勢分",
            "same_distance_signal_score": "同程證據分",
        }[key]

    def _matrix_score_tone(self, score):
        score = float(score)
        if score >= 80:
            return "偏強"
        if score >= 68:
            return "中上"
        if score >= 55:
            return "中性"
        if score >= 40:
            return "偏弱"
        return "明顯偏弱"

    def _matrix_summary_text(self, key, label, score, features, evidence):
        builders = {
            "stability": self._describe_stability_matrix,
            "sectional": self._describe_sectional_matrix,
            "race_shape": self._describe_race_shape_matrix,
            "trainer_signal": self._describe_trainer_signal_matrix,
            "horse_health": self._describe_horse_health_matrix,
            "form_line": self._describe_form_line_matrix,
            "class_advantage": self._describe_class_advantage_matrix,
        }
        builder = builders.get(key, self._describe_generic_matrix)
        text = builder(score, features, evidence).strip()
        return text or f"{label} 主要根據現有本地資料作保守判讀。"

    def _core_support_sentence(self, key, score, features):
        builders = {
            "stability": self._core_support_stability,
            "sectional": self._core_support_sectional,
            "race_shape": self._core_support_race_shape,
            "trainer_signal": self._core_support_trainer_signal,
            "horse_health": self._core_support_horse_health,
            "form_line": self._core_support_form_line,
            "class_advantage": self._core_support_class_advantage,
        }
        return builders.get(key, self._core_support_generic)(score, features)

    def _core_risk_sentence(self, key, score, features):
        builders = {
            "stability": self._core_risk_stability,
            "sectional": self._core_risk_sectional,
            "race_shape": self._core_risk_race_shape,
            "trainer_signal": self._core_risk_trainer_signal,
            "horse_health": self._core_risk_horse_health,
            "form_line": self._core_risk_form_line,
            "class_advantage": self._core_risk_class_advantage,
        }
        return builders.get(key, self._core_risk_generic)(score, features)

    def _core_support_stability(self, score, features):
        variants = (
            "最大賣點先在狀態與穩定性，近期表現唔係一次半次搶返來，而係持續維持到前列競爭感。",
            "近況係佢今場最重要嘅支撐，因為近期唔只交到一場，而係整體穩定度有維持。",
            "正面來源主要在近況，至少近期表現唔似偶一為之，基本競爭感係有連續性。",
        )
        if features.get("form_score", 60) >= 80 and features.get("consistency_score", 60) >= 75:
            return variants[self._variant_seed() % len(variants)]
        base = (
            "狀態與穩定性方面有基本交代，至少反映到近期仲有維持競爭力。",
            "近況未算爆燈，但整體仍然交代到一定穩定度，唔係完全靠估。",
            "狀態面至少仲有基本支撐，顯示近期表現未至於全面走樣。",
        )
        return base[self._variant_seed() % len(base)]

    def _core_support_sectional(self, score, features):
        variants = (
            "段速與場地適性屬正面板塊，反映末段走勢、速度形態同跑道適配有一定水準。",
            "速度輪廓係佢今場一個可取位，至少末段反應同步速修正後未見失守。",
            "段速面提供到實質支持，代表呢匹馬唔係單靠形勢先撐得起分數。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_support_race_shape(self, score, features):
        barrier = self.horse_data.get("barrier") or self.horse_data.get("draw") or "N/A"
        variants = (
            f"形勢上亦有可取之處，今仗排{barrier}檔，走位起步成本相對可控。",
            f"今場其中一個著數在形勢，{barrier}檔起步至少唔使先輸步位。",
            f"排{barrier}檔令佢今場入局方式較易處理，早段唔需要額外蝕太多位置。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_support_trainer_signal(self, score, features):
        combo_summary = self._trainer_signal_combo_summary()
        if combo_summary:
            return combo_summary
        jockey = self.horse_data.get("jockey", "騎師")
        trainer = self.horse_data.get("trainer", "練馬師")
        variants = (
            f"騎練訊號算站得住腳，由{jockey}操刀配合{trainer}馬房，臨場執行力有基本保證。",
            f"人馬配置係正面來源之一，{jockey}同{trainer}組合至少提供到基本執行力。",
            f"騎練層面唔算虛，{jockey}配{trainer}馬房屬可跟進配置，臨場操作有基本依靠。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_support_horse_health(self, score, features):
        variants = (
            "健康與新鮮感大致正路，起碼未見明顯消耗或備戰失衡的紅旗。",
            "體能同新鮮感暫時屬可接受範圍，未見有太大警號拖住後腿。",
            "健康面算平穩，至少未見明顯跡象顯示今場會先輸體能銜接。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_support_form_line(self, score, features):
        return self._core_form_line_support_sentence(features)

    def _core_support_class_advantage(self, score, features):
        variants = (
            "級數與負磅配套合理，今場唔似硬碰硬蝕底，基本班底可以支撐佢留在競爭圈。",
            "班底配合負磅條件算順手，起碼唔似未跑已經喺硬件上輸蝕。",
            "級數背景係有基本底氣，今場唔需要靠超水準先填補班底落差。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_support_generic(self, score, features):
        return "其中一個正面板塊有基本支持，唔需要完全靠運氣先跑得出。"

    def _core_risk_stability(self, score, features):
        variants = (
            "狀態面仍有保留，近期表現起伏未完全收窄，未必能夠穩定重複好表現。",
            "近況未算完全企穩，最大問題係好表現未必場場都複製得到。",
            "狀態延續性仍然係問號，近期表現仲帶住一定波幅。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_sectional(self, score, features):
        variants = (
            "段速與場地適性未夠銳利，若步韻一快或者要靠衝刺補數，末段反應未算有十足把握。",
            "速度面仍有隱憂，一旦臨場要靠末段硬追，反應未必夠利。",
            "段速輪廓未算 sharp，今場如果步速形勢變複雜，末段應對未必夠穩。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_race_shape(self, score, features):
        barrier = self.horse_data.get("barrier") or self.horse_data.get("draw") or "N/A"
        variants = (
            f"檔位與走位板塊偏弱，今仗排{barrier}檔未必容易慳到位，走位成本有機會偏高。",
            f"形勢面最大擔心係{barrier}檔未必容易入到理想位置，早段操作成本會上升。",
            f"排{barrier}檔令走位容錯變細，一旦早段失位，之後補救空間有限。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_trainer_signal(self, score, features):
        combo_summary = self._trainer_signal_combo_summary()
        if combo_summary:
            return self._normalize_prose(combo_summary + " 今場唔適宜將希望過份放喺單一騎練變招上。")
        variants = (
            "騎練配搭未見明顯優勢，所以唔能夠期望單靠人手變招就扭轉形勢。",
            "騎練層面未有額外加成，臨場想靠人手變招補足唔會太容易。",
            "人馬配搭只屬中性，今場唔適宜將希望過份放喺騎練操作上。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_horse_health(self, score, features):
        variants = (
            "健康與新鮮感只屬一般，休賽銜接同臨場維持度仍有少量保留。",
            "體能銜接未算完全放心，特別係臨場能否由頭到尾維持同一強度。",
            "健康面唔算大問題，但新鮮感同臨場續航仍然未去到完全無保留。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_form_line(self, score, features):
        return self._core_form_line_risk_sentence(features)

    def _core_risk_class_advantage(self, score, features):
        variants = (
            "級數優勢唔算鮮明，若對手有更完整近況，單靠班底未必頂得住。",
            "班底硬度未算突出，一旦對手近況更完整，呢邊未必夠硬食。",
            "級數面未有壓倒性，今場如果要鬥硬淨，未必有太大著數。",
        )
        return variants[self._variant_seed() % len(variants)]

    def _core_risk_generic(self, score, features):
        return "其中一個關鍵板塊未夠穩，實戰容錯率會被壓低。"

    def _overall_projection_sentence(self, top, low, features):
        support_keys = {key for key, _score in top}
        risk_keys = {key for key, _score in low}
        
        if "stability" in support_keys and "form_line" in support_keys:
            return "反映此駒近況與賽績線均到位，只要臨場唔失準，基本盤有保證。"
        if "sectional" in support_keys and "trainer_signal" in support_keys:
            return "顯示具備足夠執行力及速度感，只要跑法順手，有力交出更高水準。"
        if "race_shape" in support_keys and "class_advantage" in support_keys:
            return "勝在形勢與班底配合順手，若早段步位理想，威脅比表面更大。"
        if "sectional" in risk_keys and "race_shape" in risk_keys:
            return "換言之，今場最大隱憂在於形勢未必就手，且末段反應存疑，一旦早段蝕位較難補救。"
        if "stability" in risk_keys and "form_line" in risk_keys:
            return "即係話，今仗近況與賽績線均未夠穩，若受壓未必有第二腳回應。"
            
        support = self._matrix_hook(next(iter(support_keys)), "support") if support_keys else "基本盤"
        risk = self._matrix_hook(next(iter(risk_keys)), "risk") if risk_keys else "臨場發揮"
        
        variants = (
            f"總括而言，今場要靠{support}維持競爭力。最後能否把分數兌現，好睇{risk}頂唔頂得住。",
            f"歸根究底，核心點在於{support}可否順利落地，同時要避開{risk}拖後腿，先有機會跑返水準。",
            f"綜合睇，今場發揮關鍵在於{support}能否轉化成實際優勢，而{risk}就係最大變數。"
        )
        return variants[self._variant_seed() % len(variants)]

    def _competitiveness_opening(self, matrix_scores, features, top, low):
        ability = float(self._ability_score(matrix_scores))
        confidence = float(features.get("confidence_score", 60))
        top_key = top[0][0] if top else None
        low_key = low[0][0] if low else None
        support = self._matrix_hook(top_key, "support")
        risk_text = self._matrix_hook(low_key, "risk")
        seed = self._variant_seed()
        
        weight = self.horse_data.get("weight", "適中")
        class_text = "班底" if features.get("class_score", 60) >= 65 else "現時評分"
        
        if ability >= 72 and confidence >= 75:
            variants = (
                f"以{class_text}及負{weight}磅計，屬今場前列機會馬。最大底氣來自{support}，只要{risk_text}配合，整體競爭力甚高。",
                f"整體指標位處前列，係今場爭勝主角之一。{support}提供咗明確支撐，只要{risk_text}唔成為缺口，走勢會十分正面。",
                f"評分及數據基礎均見硬淨，屬三甲機會馬。今場最可取之處在於{support}，若{risk_text}控制得宜，勝算不俗。"
            )
            return variants[seed % len(variants)]
        if ability >= 67:
            variants = (
                f"以各項數據計，具備實際爭位權。{support}撐得住基本盤，若{risk_text}唔出錯，有力留喺爭位圈。",
                f"實力位處中上游，唔係純靠亂局先有機會。{support}足以支撐基本競爭力，但要守住位置，仍要睇{risk_text}會唔會拖後腿。",
                f"具備基本爭位條件，其中{support}係關鍵支持。只要{risk_text}唔出大問題，應有力跟住大局。"
            )
            return variants[seed % len(variants)]
        if ability >= 60:
            variants = (
                f"整體屬中游偏上、需要條件配合嘅一類。暫時靠{support}維持可爭感，不過{risk_text}會限制成績上限。",
                f"今場有一定介入空間，但未算非常穩陣。現階段主要靠{support}托住評分，如果{risk_text}處理唔好，上限會幾快見頂。",
                f"雖然唔係完全冇機會，但容錯空間較窄。眼前仍要靠{support}撐場，而{risk_text}就係最容易出錯嗰一環。"
            )
            return variants[seed % len(variants)]
        variants = (
            f"整體評估屬邊線偷位型。除非{support}完全兌現，同時{risk_text}冇再失分，否則驚喜空間有限。",
            f"今場大致只屬冷門邊線。要由{support}大幅超預期發揮，仲要避開{risk_text}帶來嘅壓力，先至有機會爆冷。",
            f"數據起步點相對較低，暫時只可寄望{support}帶來額外幫助。若{risk_text}依然構成障礙，成績幾難有突破。"
        )
        return variants[seed % len(variants)]

    def _core_form_line_support_sentence(self, features):
        strength = self._formline_strength_signal()
        trend = self._margin_trend_signal()
        highlight = self._formline_opponent_highlight()
        if strength in {"elite", "strong"} and trend == "improving":
            if highlight:
                return f"賽績線係主要支持之一，例如{highlight}，而且近期輸距走勢亦見收窄，證明唔係純粹跟強組搵位。"
            return "賽績線係主要支持之一，因為之前所處組別本身有強度，而且近期輸距走勢亦見收窄。"
        if strength in {"elite", "strong"}:
            if highlight:
                return f"賽績線有說服力，例如{highlight}，即係當時嗰條對手線其後真係有兌現。"
            return "賽績線有說服力，因為之前碰過嘅對手組合普遍唔弱，唔係普通水位下搶返來。"
        if trend == "improving":
            return "賽績線方面有回升味道，雖然對手強度未必特別突出，但自己表現走勢係向好。"
        return "賽績線方面有基本交代，但對手強度未算特別鮮明，所以只能作輔助支持。"

    def _core_form_line_risk_sentence(self, features):
        strength = self._formline_strength_signal()
        trend = self._margin_trend_signal()
        if strength in {"elite", "strong"} and trend == "worsening":
            return "賽績線雖然來自偏強對手，但自己近期未能將呢條線延續返落去，轉化能力仍有疑問。"
        if strength in {"neutral", "unknown"}:
            return "賽績線保證未算高，因為之前對手強度未有清晰證明，唔能夠單靠呢條線撐起信心。"
        if trend == "worsening":
            return "賽績線近期有降溫跡象，即使舊績唔差，近況都未見可以原樣複製。"
        return "賽績線未算完全穩陣，仍要靠其他板塊補足。"

    def _formline_opponent_highlight(self):
        context_parts = []
        formline_table = self._value("formline_table")
        recent_6_detail = self._value("recent_6_detail") or str(self.horse_data.get("last_6_finishes") or "")
        
        if isinstance(formline_table, list) and len(formline_table) > 0:
            valid_opponents = [row for row in formline_table if row.get('opponents', '未知') not in ('未知', '賽果查詢失敗')]
            if valid_opponents:
                best_opp = valid_opponents[0]
                opp_name = best_opp['opponents'].split(',')[0] if ',' in best_opp['opponents'] else best_opp['opponents']
                next_cls = best_opp.get('next_class', '-')
                next_perf = best_opp.get('next_performance', '-')
                
                opp_str = f"曾交手對手「{opp_name}」"
                if next_cls != '-' and next_perf != '-':
                    opp_str += f"(其後於{next_cls}交出{next_perf}成績)"
                context_parts.append(opp_str)
                
        margin_match = re.search(r"第1仗[^:]*:\s*\d+名\s*([^|]+)", str(recent_6_detail))
        if margin_match:
            margin_val = margin_match.group(1).strip()
            context_parts.append(f"上仗距離差為{margin_val}")
            
        if context_parts:
            return "，".join(context_parts)
            
        text = self._clean(self._value("formline_opponent_highlight") or "")
        if not text or text == "N/A":
            return ""
        return text

    def _should_include_trackwork_context(self, top_keys, low_keys):
        return "stability" not in top_keys and "stability" not in low_keys and "horse_health" not in top_keys and "horse_health" not in low_keys

    def _matrix_hook(self, key, mode):
        hooks = {
            "stability": {
                "support": "近況穩定度",
                "risk": "狀態延續性",
            },
            "sectional": {
                "support": "末段反應同速度質量",
                "risk": "末段爆發力",
            },
            "race_shape": {
                "support": "排檔同走位成本",
                "risk": "走位形勢",
            },
            "trainer_signal": {
                "support": "人馬執行力",
                "risk": "騎練加成",
            },
            "horse_health": {
                "support": "健康銜接",
                "risk": "體能維持度",
            },
            "form_line": {
                "support": "賽績線含金量",
                "risk": "賽績線轉化",
            },
            "class_advantage": {
                "support": "班底同負磅配套",
                "risk": "級數硬度",
            },
        }
        return hooks.get(key, {}).get(mode, "整體發揮")

    def _risk_phrase_for_flag(self, flag):
        mapping = {
            "trackwork_slowing": "備戰節奏略慢，臨場狀態維持度要再觀察",
            "debut_race_experience_unknown": "初出實戰感仍然係未知數",
            "draw_pressure": "排檔形勢有機會令早段走位先蝕",
            "distance_unproven": "今場路程仍未有足夠實績支持",
            "class_edge_unproven": "班底未算有壓過對手嘅把握",
            "distance_record_weak": "同程往績未足以建立信心",
            "medical_record_unknown": "健康資料未算齊全，唔可以完全放鬆",
        }
        return mapping.get(flag, "")

    def _variant_seed(self):
        name = str(self.horse_data.get("horse_name") or "")
        barrier = str(self.horse_data.get("barrier") or self.horse_data.get("draw") or "")
        return sum(ord(ch) for ch in f"{name}|{barrier}")

    def _season_record(self):
        return parse_record(self.horse_data.get("season_stats") or self._value("season_stats_line"))

    def _same_distance_record(self):
        text = self._clean(self.horse_data.get("season_stats") or self._value("season_stats_line") or "")
        match = re.search(r"同程\s*\((\d+)-(\d+)-(\d+)-(\d+)\)", text)
        if not match:
            return None
        wins, seconds, thirds, starts = (int(part) for part in match.groups())
        return {
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "starts": starts,
            "places": wins + seconds + thirds,
        }

    def _formline_strength_signal(self):
        text = self._clean(self._value("formline_strength") or "")
        if "極強" in text:
            return "elite"
        if "強" in text:
            return "strong"
        if "弱" in text:
            return "weak"
        if text and text != "N/A":
            return "neutral"
        return "unknown"

    def _margin_trend_signal(self):
        text = self._clean(self._value("margin_trend") or "")
        if "收窄中" in text:
            return "improving"
        if "擴大中" in text:
            return "worsening"
        return "flat"

    def _recent_finish_list(self):
        form = str(self.horse_data.get("last_6_finishes") or "")
        return [int(item) for item in re.findall(r"\b\d+\b", form)[:6]]

    def _recent_form_trend(self, finishes):
        if len(finishes) < 4:
            return "mixed"
        recent = finishes[:3]
        older = finishes[3:6]
        if not older:
            return "mixed"
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        if recent_avg + 1.0 < older_avg:
            return "warming"
        if recent_avg > older_avg + 1.0:
            return "cooling"
        recent_places = sum(1 for rank in recent if rank <= 3)
        older_places = sum(1 for rank in older if rank <= 3)
        if recent_places >= older_places:
            return "holding"
        return "mixed"

    def _stats_text(self, value):
        text = self._clean(value or "")
        if not text or text == "N/A":
            return text
        text = text.replace(" | ", "；").replace("|", "；")
        text = " ".join(part.strip() for part in text.split())
        return self._normalize_prose(text)

    def _normalize_prose(self, text):
        text = " ".join(str(text or "").split())
        replacements = {
            "。。": "。",
            "；。": "。",
            "，。": "。",
            " 。": "。",
            " ，": "，",
            " ；": "；",
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text.strip()

    def _describe_stability_matrix(self, score, features, evidence):
        finishes = self._recent_finish_list()
        recent_trend = self._recent_form_trend(finishes)
        trackwork = self._trackwork_markers()
        if features.get("form_score", 60) >= 78 and features.get("consistency_score", 60) >= 75:
            lead = "近期走勢保持在前列競爭圈，而且唔止一次交代，基本狀態係企得住。"
        elif features.get("form_score", 60) < 52 or features.get("consistency_score", 60) < 52:
            lead = "近期前列支撐不足，名次波幅仍然較大，狀態面未算真正回穩。"
        elif recent_trend == "warming":
            lead = "近期整體走勢有回暖跡象，雖然未到場場穩定，但狀態方向係向好。"
        elif recent_trend == "cooling":
            lead = "近期表現有少少回落，未必可以將之前較好嘅狀態原樣搬返出嚟。"
        else:
            lead = "近態有一定交代，但未去到場場穩定，整體仍屬穩中帶保留。"
        if trackwork["classification"] == "翻案復刻":
            track = "晨操摘要屬「翻案復刻」，反映團隊有意用操練訊號替正式近績翻案，但暫時未必可以完全蓋過賽績波動。"
        elif "加強" in trackwork["trend"]:
            track = f"晨操方面屬「{trackwork['classification'] or '狀態延續'}」，而且{trackwork['trend']}，顯示備戰力度有推進。"
        elif "放緩" in trackwork["trend"]:
            track = f"晨操方面屬「{trackwork['classification'] or '狀態延續'}」，但{trackwork['trend']}，所以狀態維持度仍要再觀察。"
        else:
            track = f"晨操方面屬「{trackwork['classification'] or '狀態延續'}」，整體只提供輔助確認。"
        close = self._matrix_close(score, "整體屬狀態企穩，可以視為近況支柱。", "整體屬穩中帶保留，未到無風險。", "整體反映狀態仍未完全站穩。")
        return f"{lead}{track}{close}"

    def _describe_sectional_matrix(self, score, features, evidence):
        if features.get("speed_score", 60) >= 76:
            speed = "近仗末段走勢同步速修正後表現都有明顯競爭力，速度質量屬較強一類。"
        elif features.get("speed_score", 60) >= 68:
            speed = "近仗 L400、能量走勢同步速修正表現整體正面，基本速度感未有流失。"
        elif features.get("speed_score", 60) >= 62:
            speed = "近仗段速輪廓尚算平穩，基本反應仍在，但未見特別 sharp 的加速訊號。"
        elif features.get("speed_score", 60) >= 60:
            speed = "近仗段速數據只屬中性，速度面未算失守，但亦未見明顯加分。"
        else:
            speed = "近仗末段走勢同步速修正後表現偏弱，暫未見明顯爆發感，速度面要保守處理。"
        if features.get("track_going_score", 60) >= 66:
            going = "場地/跑道資料有基本配合，唔係只靠單一末段數據支撐。"
        elif features.get("track_going_score", 60) < 60:
            going = "場地適性未見額外補強，所以呢項較難加到盡。"
        else:
            going = "場地適性未有特別加分，只能視作中性背景。"
        close = self._matrix_close(score, "整體反映段速質量有實際支撐。", "整體只屬一般，不算今場的明顯著數。", "整體反映末段爆發力仍有疑問。")
        return f"{speed}{going}{close}"

    def _describe_race_shape_matrix(self, score, features, evidence):
        barrier = self.horse_data.get("barrier") or self.horse_data.get("draw") or "N/A"
        draw_verdict = self._draw_verdict_signal()
        if features.get("draw_score", 60) >= 72:
            draw = f"今仗排{barrier}檔，檔位屬正面配置。"
        elif features.get("draw_score", 60) >= 60:
            draw = f"今仗排{barrier}檔，檔位大致中性，未算特別食虧。"
        else:
            draw = f"今仗排{barrier}檔，檔位形勢受壓，走位容錯較低。"
        if draw_verdict:
            draw += draw_verdict
        close = self._matrix_close(score, "綜合來看，今場形勢有利於發揮本身能力。", "綜合來看，形勢普通，要靠臨場發揮補足。", "綜合來看，今場走位形勢唔算舒服。")
        return f"{draw}{close}"

    def _describe_trainer_signal_matrix(self, score, features, evidence):
        jockey = self.horse_data.get("jockey", "騎師")
        trainer = self.horse_data.get("trainer", "練馬師")
        if features.get("jockey_score", 60) >= 80:
            jockey_text = f"今仗由{jockey}操刀，騎師端有明確正面層級支持。"
        elif features.get("jockey_score", 60) >= 70:
            jockey_text = f"今仗由{jockey}操刀，騎師配置算正路可靠。"
        else:
            jockey_text = f"今仗由{jockey}操刀，騎師端未見特別加分，屬中性配置。"
        if features.get("trainer_score", 60) >= 75:
            trainer_text = f"{trainer} 馬房近態或穩定度有基本支持。"
        elif features.get("trainer_score", 60) >= 68:
            trainer_text = f"{trainer} 馬房屬穩定配置，但未到強烈加分。"
        else:
            trainer_text = f"{trainer} 馬房方面未見額外優勢。"
        combo_text = self._trainer_signal_combo_summary()
        close = self._matrix_close(score, "整體騎練訊號屬可跟進級別。", "整體騎練訊號正路，但唔算單靠配搭就可以推高上限。", "整體騎練訊號偏平，驚喜要靠馬匹自己交代。")
        return f"{jockey_text}{trainer_text}{combo_text}{close}"

    def _describe_horse_health_matrix(self, score, features, evidence):
        medical = self._text("medical_flags")
        trackwork = self._trackwork_markers()
        days = parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
        if "無醫療事故" in medical:
            medical_text = "醫療欄未見明顯事故，基本健康面尚算平穩。"
        else:
            medical_text = "醫療或健康資料未算完整，所以今次健康面要保守少少。"
        if days is None:
            freshness = "休賽間隔資料不足，新鮮感只能作中性判讀。"
        elif days <= 14:
            freshness = f"休後{int(days)}日再出，轉身較快，狀態連接可以，但回氣情況要留意。"
        elif days <= 45:
            freshness = f"休後{int(days)}日再出，間隔正常，新鮮感屬合理範圍。"
        else:
            freshness = f"休後{int(days)}日再出，會有一定新鮮感，但實戰感仍要再驗證。"
        if "加強" in trackwork["trend"]:
            track = f"晨操方面{trackwork['trend']}，備戰節奏偏積極。"
        elif "放緩" in trackwork["trend"]:
            track = f"晨操方面{trackwork['trend']}，狀態維持度未算完全無保留。"
        else:
            track = "晨操節奏未見太大異常，健康面主要屬中性觀察。"
        close = self._matrix_close(score, "整體健康/新鮮感屬安心範圍。", "整體健康/新鮮感大致正常，但仍有少量保留。", "整體健康/新鮮感未算理想，臨場要多留神。")
        return f"{medical_text}{freshness}{track}{close}"

    def _describe_form_line_matrix(self, score, features, evidence):
        strength = self._formline_strength_signal()
        trend = self._margin_trend_signal()
        highlight = self._formline_opponent_highlight()
        
        if strength == "elite" and trend == "improving":
            if highlight:
                lead = f"呢條賽績線最值錢嘅地方，在於{highlight}，證明唔係純粹跟弱組搵位。"
            else:
                lead = "呢條賽績線最值錢嘅地方，在於之前所碰對手屬高強度組別，而自己近仗輸距亦見收窄，證明唔係純粹跟弱組搵位。"
        elif strength == "elite":
            if highlight:
                lead = f"呢條賽績線本身有份量，{highlight}，意味當時對手質素之後有真實延續。"
            else:
                lead = "呢條賽績線本身有份量，因為之前對手質量高，能夠跟到呢類組別已經有一定含金量。"
        elif strength == "strong" and trend == "improving":
            if highlight:
                lead = f"對手後續有實際交代，{highlight}，而自己近期走勢亦略有改善，所以賽績線唔只係紙上談兵。"
            else:
                lead = "對手強度有基本保證，而自己近期走勢亦略有改善，所以賽績線唔只係紙上談兵。"
        elif strength == "strong":
            if highlight:
                lead = f"對手組合唔弱，而且{highlight}，所以賽績線有一定可信度，只係自己近期延續性未算完全穩陣。"
            else:
                lead = "對手組合唔弱，所以賽績線有一定可信度，只係自己近期延續性未算完全穩陣。"
        elif strength in {"neutral", "unknown"} and trend == "improving":
            if highlight:
                lead = f"雖然整體對手強度未見特別鮮明，但{highlight}，令呢條賽績線仲有參考價值。"
            else:
                lead = "雖然對手強度未見特別鮮明，但自己近期走勢有回暖，令呢條賽績線仲有參考價值。"
        elif trend == "worsening":
            if highlight:
                lead = f"就算之前有可觀賽績({highlight})，近期對同類對手未見持續追近，令呢條賽績線說服力打咗折扣。"
            else:
                lead = "就算之前有可觀賽績，近期對同類對手未見持續追近，令呢條賽績線說服力打咗折扣。"
        else:
            lead = "賽績線目前只屬一般參考，因為對手強度未算突出，而自己亦未建立穩定延續性。"
            
        close = self._matrix_close(score, "整體賽績線屬可信板塊，反映呢匹馬曾經喺有份量的組別交到接近表現。", "整體賽績線有參考價值，但未去到可以單獨撐起全局。", "整體賽績線支撐不足，難以單靠過往對手線索建立信心。")
        return f"{lead}{close}"

    def _describe_class_advantage_matrix(self, score, features, evidence):
        if features.get("class_score", 60) >= 70:
            class_text = "班次 context 算穩，正式賽經驗、季內交代同評分底子都提供到支持。"
        elif features.get("class_score", 60) < 60:
            class_text = "班次 context 未算硬淨，實戰經驗或季內交代仍有缺口，級數面未見明顯著數。"
        else:
            class_text = "班次層面大致中性，基本經驗有，但未形成鮮明級數優勢。"
        if features.get("weight_score", 60) >= 68:
            weight = "負磅條件較友善，令級數優勢更容易落地。"
        elif features.get("weight_score", 60) >= 60:
            weight = "負磅大致可控，未見明顯拖低級數轉化。"
        else:
            weight = "負磅偏重，級數優勢即使存在亦要打折。"
        close = self._matrix_close(score, "整體屬班次同負磅配套合理的一類。", "整體級數感普通，要靠形勢同近態補足。", "整體級數優勢未算成立。")
        return f"{class_text}{weight}{close}"

    def _draw_verdict_signal(self):
        text = self._clean(self._value("draw_verdict") or "")
        if not text or text == "N/A":
            return ""
        if "有利" in text:
            return "本地檔位統計對呢個檔位有少量幫助，唔使一開步就先輸形勢。"
        if "不利" in text:
            return "本地檔位統計亦對呢個檔位唔算友善，跑法上要用更多操作去補。"
        if "中性" in text:
            return "本地檔位統計大致中性，真正關鍵仍然係出閘後能否搶到想要位置。"
        return ""

    def _describe_generic_matrix(self, score, features, evidence):
        return f"{evidence}{self._matrix_close(score, '整體屬正面支撐。', '整體屬中性。', '整體偏弱。')}"

    def _matrix_close(self, score, strong_text, neutral_text, weak_text):
        score = float(score)
        if score >= 75:
            return strong_text
        if score >= 58:
            return neutral_text
        return weak_text

    def _coverage_sentence(self, confidence_score):
        confidence_score = float(confidence_score)
        if confidence_score >= 80:
            return "資料覆蓋完整，今次判讀可信度較高。"
        if confidence_score >= 68:
            return "主要欄位算齊，今次判讀有一定依據。"
        return "資料未算完整，所以呢個判讀需要保守理解。"

    def _trackwork_markers(self):
        digest = self._clean(self._value("trackwork_digest") or "")
        classification = ""
        trend = ""
        positive = ""
        risk = ""
        if digest:
            classification_match = re.search(r"分類為「([^」]+)」", digest)
            trend_match = re.search(r"操練趨勢([^。；]+)", digest)
            positive_match = re.search(r"正面訊號：([^；。]+)", digest)
            risk_match = re.search(r"風險訊號：([^；。]+)", digest)
            classification = classification_match.group(1) if classification_match else ""
            trend = f"操練趨勢{trend_match.group(1)}" if trend_match else ""
            positive = positive_match.group(1).strip() if positive_match else ""
            risk = risk_match.group(1).strip() if risk_match else ""
        return {
            "classification": classification,
            "trend": trend,
            "positive": positive,
            "risk": risk,
        }

    def _matrix_dimension_label(self, key):
        labels = {
            "stability": "狀態與穩定性",
            "sectional": "段速與場地適性",
            "race_shape": "檔位與走位",
            "trainer_signal": "騎練訊號",
            "horse_health": "馬匹健康 / 新鮮感",
            "form_line": "賽績線",
            "class_advantage": "級數優勢",
        }
        return labels.get(key, key)

    def _matrix_dimension_role(self, key):
        roles = {
            "stability": "半核心",
            "sectional": "核心",
            "race_shape": "半核心",
            "trainer_signal": "核心",
            "horse_health": "輔助",
            "form_line": "輔助",
            "class_advantage": "輔助",
        }
        return roles.get(key, "輔助")

    def _grade_computation_transparency(self, matrix_scores, ability_score, grade):
        """Generate a detailed computation walkthrough for the 7D matrix.
        
        Returns a dict with textual breakdown suitable for markdown rendering.
        Weights are pulled live from the active weight set (debut vs standard)
        so the displayed 加權總分 always matches the real ability_score.
        """
        is_debut = self._is_debut()
        debut_weights = {
            "trainer_signal": 0.30,
            "horse_health": 0.30,
            "race_shape": 0.20,
            "stability": 0.15,
            "class_advantage": 0.05,
        }
        active_weights = debut_weights if is_debut else MATRIX_WEIGHTS

        dims = [
            ("stability", "狀態與穩定性", "半核心"),
            ("sectional", "段速與場地適性", "核心"),
            ("race_shape", "檔位與走位", "半核心"),
            ("trainer_signal", "騎練訊號", "核心"),
            ("horse_health", "馬匹健康 / 新鮮感", "輔助"),
            ("form_line", "賽績線", "輔助"),
            ("class_advantage", "級數優勢", "輔助"),
        ]

        lines = []
        weighted_sum = 0.0

        for key, label, role in dims:
            weight = active_weights.get(key, 0.0)
            raw_score = float(matrix_scores.get(key, 60))
            band = score_band(raw_score)
            contribution = round(raw_score * weight, 2)
            weighted_sum += contribution

            if weight == 0.0:
                tag = "初出馬豁免" if is_debut else "0% 權重（僅作風險參考）"
                lines.append(f"  - {label} [{role}]: {raw_score:.1f}分 ({tag})")
                continue

            # Build human-readable computation line
            pct = f"{weight * 100:.1f}%"
            lines.append(
                f"  - {label} [{role}]: {raw_score:.1f}分 × {pct} = {contribution:.2f} → {band}"
            )
        
        # Add health micro-adjustment note if applicable
        health_notes = []
        original_health = float(matrix_scores.get("horse_health", 60))
        # The health score already went through _apply_health_only_v2 in analyze_horse()
        # We can note that micro-adjustments were applied
        
        lines_text = "\n".join(lines)
        
        # Build summary block
        summary = (
            f"**🧮 7D 加權總分計算 (Python Auto 矩陣引擎):**\n\n"
            f"{lines_text}\n\n"
            f"**→ 加權總分 = {weighted_sum:.2f} 分 → Grade = [{grade}]**\n"
        )
        
        # Add grade threshold context
        grade_explanation = self._grade_threshold_explanation(ability_score, grade)
        if grade_explanation:
            summary += f"\n{grade_explanation}\n"
        
        # Add risk flags
        if self.risk_flags:
            flag_descriptions = []
            for flag in sorted(set(self.risk_flags)):
                desc = self._risk_phrase_for_flag(flag)
                if desc:
                    flag_descriptions.append(f"  - {desc}")
            if flag_descriptions:
                summary += f"\n**⚠️ 風險標記:**\n" + "\n".join(flag_descriptions) + "\n"
        
        return {
            "detail_lines": lines,
            "weighted_sum": round(weighted_sum, 2),
            "summary": summary,
        }
    
    def _grade_threshold_explanation(self, ability_score, grade):
        """Explain which grade threshold the score fell into."""
        thresholds = {
            "S+": "≥96分 — 壓倒性數據支持，全維度表現頂尖",
            "S": "≥92分 — 極強數據基礎，多維度顯著優勢",
            "S-": "≥88分 — 非常強勢，核心維度表現突出",
            "A+": "≥84分 — 前列競爭力，基本面紮實",
            "A": "≥80分 — 三甲競爭力，主要維度有支持",
            "A-": "≥76分 — 位置圈內，有實質競爭條件",
            "B+": "≥72分 — 中上游，具備實際爭位權",
            "B": "≥68分 — 中游偏上，需要條件配合",
            "B-": "≥64分 — 中游，基本競爭力存在",
            "C+": "≥60分 — 中下游，容錯空間較窄",
            "C": "≥56分 — 下游，需大幅超水準發揮",
            "C-": "≥52分 — 邊線，驚喜空間有限",
            "D": "≥48分 — 冷門，數據支持薄弱",
            "E": "<48分 — 數據起步點極低，難以建立信心",
        }
        explanation = thresholds.get(grade, "")
        if explanation:
            return f"**📊 Grade 定義:** {explanation}"
        return ""

    def _core_logic_transparency(self, feature_scores, matrix_scores, matrix_bands, ability_score, grade):
        """Generate a structured transparency block showing exactly what Python computed.
        
        This returns a text block that accompanies the natural-language core_logic.
        """
        dims = [
            ("stability", "狀態與穩定性", "半核心"),
            ("sectional", "段速與場地適性", "核心"),
            ("race_shape", "檔位與走位", "半核心"),
            ("trainer_signal", "騎練訊號", "核心"),
            ("horse_health", "馬匹健康 / 新鮮感", "輔助"),
            ("form_line", "賽績線", "輔助"),
            ("class_advantage", "級數優勢", "輔助"),
        ]
        
        score_lines = []
        core_strong = 0
        semi_strong = 0
        aux_strong = 0
        total_weak = 0
        
        for key, label, role in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, score_band(raw_score))
            score_lines.append(f"  - {label} [{role}]: {raw_score:.1f}分 → {band}")
            
            if band in ("✅✅", "✅"):
                if role == "核心":
                    core_strong += 1
                elif role == "半核心":
                    semi_strong += 1
                else:
                    aux_strong += 1
            if band in ("❌❌", "❌"):
                total_weak += 1
        
        scores_text = "\n".join(score_lines)
        
        # Build the transparency block
        parts = [
            "**🧮 Python 矩陣計算全記錄:**",
            "",
            "**7D 維度評分:**",
            scores_text,
            "",
            f"**統計:** 核心正面={core_strong} | 半核心正面={semi_strong} | 輔助正面={aux_strong} | 總負面={total_weak}",
            f"**7D 加權總分:** {ability_score:.1f}分",
            f"**Grade 查表:** {ability_score:.1f}分 → **[{grade}]**",
        ]
        
        # Add risk flags
        if self.risk_flags:
            flag_summary = []
            for flag in sorted(set(self.risk_flags)):
                phrase = self._risk_phrase_for_flag(flag)
                if phrase:
                    flag_summary.append(f"  - {phrase}")
            if flag_summary:
                parts.append(f"\n**⚠️ 已觸發風險標記:**")
                parts.extend(flag_summary)
        
        # Add data coverage
        coverage_text = self._data_coverage_summary(feature_scores)
        if coverage_text:
            parts.append(f"\n**📋 {coverage_text}**")
        
        return "\n".join(parts)
    
    def _data_coverage_summary(self, feature_scores):
        confidence = float(feature_scores.get("confidence_score", 60))
        if confidence >= 80:
            return "資料覆蓋完整，判讀可信度較高。"
        if confidence >= 68:
            return "主要資料欄位算齊，判讀有一定依據。"
        if confidence >= 55:
            return "資料覆蓋尚可，但部分欄位以中性處理。"
        return "資料未算完整，判讀需保守理解。"
