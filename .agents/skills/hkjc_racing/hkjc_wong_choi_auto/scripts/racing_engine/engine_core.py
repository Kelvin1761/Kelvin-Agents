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
from scoring import DEBUT_MATRIX_WEIGHTS, FEATURE_KEYS, MATRIX_WEIGHTS, clip_score, compute_grade, parse_float, parse_record, score_band

_TRAINER_SIGNAL_PRIORS = None

# 班次顯示標籤（新馬賽等）——顯示用，唔影響評分
_HKJC_CLASS_DISPLAY_LABELS = {
    "GRIFFIN": "新馬賽",
    "GR": "新馬賽",
}


def _format_hkjc_class_display(value):
    text = str(value)
    for raw, display in _HKJC_CLASS_DISPLAY_LABELS.items():
        text = re.sub(rf"\b{re.escape(raw)}\b", display, text, flags=re.I)
    return text


class RacingEngine:
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

        matrix_scores = map_features_to_matrix_scores(feature_scores)
        matrix_scores["trainer_signal"] = self._apply_trainer_signal_v3(matrix_scores["trainer_signal"])
        matrix_scores["horse_health"] = self._apply_health_only_v2(matrix_scores["horse_health"])
        matrix_scores["sectional"] = self._apply_finish_time_trend(matrix_scores["sectional"])
        matrix = map_features_to_matrix(feature_scores)
        matrix["trainer_signal"] = score_band(matrix_scores["trainer_signal"])
        matrix["horse_health"] = score_band(matrix_scores["horse_health"])
        matrix["sectional"] = score_band(matrix_scores["sectional"])
        ability_score = round(self._ability_score(matrix_scores), 2)
        grade = compute_grade(ability_score)
        matrix_reasoning = self._matrix_reasoning(matrix_scores, matrix, feature_scores, feature_notes)
        score_breakdown = self._score_breakdown(feature_scores, feature_notes)
        grade_transparency = self._grade_computation_transparency(matrix_scores, ability_score, grade, feature_scores)

        return {
            "version": "HKJC_AUTO_SCORE_V2",
            "ability_score": ability_score,
            "grade": grade,
            "matrix": matrix,
            "matrix_scores": matrix_scores,
            "matrix_reasoning": matrix_reasoning,
            "core_logic": self._core_logic(feature_scores, matrix_scores, matrix_reasoning),
            "data_readout": self._data_readout(feature_scores, matrix_scores),
            "grade_transparency": grade_transparency,
            "trainer_signal_detail": self.trainer_signal_detail,
            "speed_detail": getattr(self, "speed_detail", None),
            "race_shape_detail": getattr(self, "race_shape_detail", None),
            "trackwork_read": self._trackwork_interpretation(),
            "overseas_form_read": self._overseas_form_interpretation(),
            "health_readout": self._health_readout(),
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
            notes.append("已建立賽駒")
        if starts is not None:
            if starts >= 20:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_20_bonus", 4.0)
                notes.append("經驗充足")
            elif starts <= 8:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_8_pen", -2.0)
                notes.append("樣本薄")
        if season:
            if season["places"] >= 3:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_3_bonus", 4.0)
                notes.append("季內有交代")
            elif season["places"] == 0:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_0_pen", -4.0)
                self.risk_flags.append("class_edge_unproven")
                notes.append("季內未上名")
        if same_distance and same_distance["places"] > 0:
            score += scoring.CLASS_MICRO_WEIGHTS.get("same_dist_place_bonus", 4.0)
            notes.append("同程有實績")
        elif same_distance and same_distance["starts"] > 0 and same_distance["places"] == 0:
            score += scoring.CLASS_MICRO_WEIGHTS.get("same_dist_unplaced_pen", -2.0)
            notes.append("同程未上名")
        # 短而準：分數行頭，訊號做 tag；無訊號＝各項中性
        note = f"班次分{clip_score(score):.0f}：" + ("、".join(notes) if notes else "經驗／季內／同程均中性")
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
        # 場地適性一向中性 60。原因（2026-07-10 檢討 + pit_backtest 驗證）：
        #  1. HKJC 抽取根本冇真實地面適性數據（good/soft/course record 係 AU 承襲、恒空；
        #     race_results 個 Going 欄裝錯咗班次字串）。
        #  2. 之前用 track_bias（場地偏差）＋ draw_verdict 嚟計係「方向盲」——只 grep
        #     「不利」就扣分，唔理今匹馬實際排內定排外，令排內檔（本應受惠）嘅馬喺偏內
        #     場地都照扣；而且檔位／場地偏差已由「檔位與走位」維度正正經經計算，喺呢度
        #     再扣＝同一 draw 訊號扣兩次（double deduct）。
        #  中性化後 pit_backtest 零倒退、good/champ 反而微升（draw 訊號集中喺 race_shape
        #  一處，唔再互相污染）。段速維度靠 speed_score 差異區分，場地保持 0.35 權重
        #  只作壓縮（回測最佳），唔再引入方向盲扣分。
        return scoring.TRACK_MICRO_WEIGHTS.get("neutral_base", 60.0), \
            "HKJC 未有可靠場地適性數據；檔位／場地偏差已於「檔位與走位」維度計算，此處不重複扣分，中性60分。", \
            "missing_neutral"

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

    def _is_foreign_runner(self):
        """True for a visiting international runner: has real overseas race rows
        but no HKJC form. Such horses must NOT be penalised for missing HK-only
        data (medical/coverage) — absence here is 'data N/A', not 'bad news'."""
        pdf = self.data.get("pdf_overseas_races") or self.horse_data.get("pdf_overseas_races") or []
        real = any(
            isinstance(r, dict) and any(
                str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
                for k in ("class_level", "rank", "time", "margin")
            )
            for r in pdf
        )
        if not real:
            return False
        hk_form = str(self._value("last_6_finishes") or "").strip()
        has_hk_form = hk_form not in ("", "N/A") and any(c.isdigit() for c in hk_form)
        return not has_hk_form

    def _overseas_form_interpretation(self):
        """海外往績獨立判讀（display-only）：新造馬／海外賽駒／香港樣本少嘅馬，
        海外賽績唔混入一般穩定性字句，喺呢度單獨交代含量同轉化保留。"""
        pdf = self.data.get("pdf_overseas_races") or self.horse_data.get("pdf_overseas_races") or []
        # PDF 往績表包括本會賽事：日期同近6場對到嘅 rows 係本地賽，唔係海外，剔走。
        local_dates = self._text("recent_6_detail")
        rows = []
        for r in pdf:
            if not isinstance(r, dict):
                continue
            if not any(str(r.get(k, "-")).strip() not in ("-", "", "N/A", "--")
                       for k in ("class_level", "rank", "time", "margin")):
                continue
            race_date = str(r.get("date", "")).strip()
            if race_date and race_date not in ("-", "N/A") and race_date in local_dates:
                continue
            rows.append(r)
        if not rows:
            return None
        hk_form = str(self._value("last_6_finishes") or "")
        hk_runs = len(re.findall(r"\d+", hk_form))

        ranks = []
        for r in rows:
            rank_str = str(r.get("rank", ""))
            try:
                ranks.append(int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str))
            except (TypeError, ValueError):
                continue

        def _field(r, key):
            v = str(r.get(key, "")).strip()
            return v if v not in ("", "-", "N/A", "--") else ""

        lines = []
        if ranks:
            wins = sum(1 for x in ranks if x == 1)
            top3 = sum(1 for x in ranks if x <= 3)
            lines.append(f"海外賽績{len(ranks)}仗：{wins}冠、{top3}次前三")
        else:
            lines.append(f"海外賽績{len(rows)}仗（名次資料不全）")
        # 逐仗簡表（有幾多 field 顯示幾多）
        for r in rows[:6]:
            bits = []
            if _field(r, "date"):
                bits.append(_field(r, "date"))
            if _field(r, "track_dist"):
                bits.append(f"{_field(r, 'track_dist')}m")
            if _field(r, "class_level"):
                bits.append(_field(r, "class_level"))
            rank = _field(r, "rank")
            if rank:
                bits.append(f"{rank}名" if "/" in rank else f"第{rank}名")
            if _field(r, "margin"):
                bits.append(f"輸距{_field(r, 'margin')}")
            if _field(r, "time"):
                bits.append(f"時間{_field(r, 'time')}")
            if bits:
                lines.append("・".join(bits))
        if hk_runs == 0:
            verdict = "未有香港賽績，近績判讀主要靠海外往績，可信度有限。"
        elif hk_runs < 3:
            verdict = f"香港實績僅{hk_runs}仗，近績判讀有一部分靠海外往績。"
        else:
            verdict = f"香港已有{hk_runs}仗實績，判斷以香港表現為主。"
        return {"lines": lines, "verdict": verdict}

    def _risk_score(self, features):
        score = scoring.RISK_MICRO_WEIGHTS.get("base", 68.0)
        notes = []
        medical = self._text("medical_flags")
        foreign = self._is_foreign_runner()
        if "無醫療事故" in medical:
            notes.append("醫療欄未見事故")
        elif foreign:
            # Visiting runner with no HKJC medical record — treat as neutral, not a risk.
            notes.append("海外賽駒，本會醫療欄無記錄，按中性處理")
        else:
            score += scoring.RISK_MICRO_WEIGHTS.get("medical_unknown_pen", -8.0)
            self.risk_flags.append("medical_record_unknown")
            notes.append("醫療欄資料不足")
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
        bits = [f"可用資料覆蓋{present}/{len(important_sources)}項"]
        if self._value("jockey_combo_block"):
            bonus = scoring.CONFIDENCE_MICRO_WEIGHTS.get("jockey_combo_bonus", 5.0)
            score += bonus
            bits.append(f"人馬組合檔案齊（+{bonus:.0f}）")
        if self._is_debut():
            pen = scoring.CONFIDENCE_MICRO_WEIGHTS.get("debut_pen", -4.0)
            score += pen
            bits.append(f"初出未有正式賽數據（{pen:.1f}）")
        if features.get("risk_score", 60) < 55:
            pen = scoring.CONFIDENCE_MICRO_WEIGHTS.get("high_risk_pen", -5.0)
            score += pen
            bits.append(f"風險分偏低再扣（{pen:.0f}）")
        if self._is_foreign_runner():
            # Don't dock a visiting runner for lacking HKJC-only coverage fields;
            # floor at neutral so foreign horses aren't structurally low-confidence.
            score = max(score, 60.0)
            note = f"海外賽駒，本會資料欄有限，信心分按中性floor處理為{clip_score(score):.1f}。"
            return clip_score(score), note, "data_coverage"
        note = "、".join(bits) + f"，信心分{clip_score(score):.1f}。"
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
            note = "操練訊號好過近績反映（馬房用狀態翻案部署），操練分由偏高起點計"
        elif "加強" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("improving_base", 70.0)
            note = "快操時間一課比一課快，備戰上緊"
        elif "放緩" in trend:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("slowing_base", 52.0)
            note = "快操時間趨慢，備戰力度回落，操練分要扣"
        else:
            base_score = scoring.TRACKWORK_MICRO_WEIGHTS.get("neutral_base", 60.0)
            note = "操練節奏平穩，中性處理"
            
        # 2. Raw exercise numerical multipliers
        trackwork = self.horse_data.get("trackwork")
        summary = trackwork.get("summary") if isinstance(trackwork, dict) else {}
        if not isinstance(summary, dict):
            summary = {}

        def _count(key):
            try:
                return int(float(summary.get(key, 0) or 0))
            except (TypeError, ValueError):
                return 0

        gallops = _count("gallops_21d")
        trials = _count("trials_21d")
        trotting = _count("trotting_21d")
        swimming = _count("swimming_21d")
        
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
            note += f"；操練量充足（活躍度+{activity_bonus:.1f}）"
        elif activity_bonus < -1.0:
            note += f"；操練量偏少（活躍度-{abs(activity_bonus):.1f}）"
            
        return final_score, note, "trackwork_digest"

    def _race_shape_context_score(self, features):
        draw = float(features.get("draw_score", 60))
        barrier = str(self.horse_data.get("barrier") or self.horse_data.get("draw") or "").strip()
        # 走位匹配分 + 近仗消耗分：兩場地都計、都顯示（口徑一致）。分數組合方式先分場地。
        fit_score, fit_note = self._draw_position_fit_score()
        trip_score, trip_note = self._trip_consumption_score()
        fit_why = fit_note.replace("匹配面：", "").rstrip("。")
        trip_why = trip_note.rstrip("。")
        rail = self._rail_label()
        if self._is_sha_tin_context():
            w = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
            score = clip_score(draw * w["sha_tin_draw"] + fit_score * w["sha_tin_draw_position_fit"] + trip_score * w["sha_tin_trip_consumption"])
            combine = "沙田加權 檔位55%＋走位匹配25%＋近仗消耗20%"
        else:
            delta, _items = self._race_shape_context_delta()
            score = clip_score(draw + delta)
            combine = f"跑馬地以檔位為主，走位情境微調 {delta:+.0f}"
        self.race_shape_detail = {
            "draw": round(draw, 1), "fit": round(fit_score, 1), "trip": round(trip_score, 1),
            "fit_why": fit_why, "trip_why": trip_why, "combine": combine, "rail": rail,
        }
        note = f"排{barrier}檔　{score:.0f}分" + (f"（{rail}賽道）" if rail else "")
        return score, note, "race_shape_context"

    def _rail_label(self):
        """今場賽道（A/B/C/C+3 等），顯示用。由 race_context 讀（賽前 pipeline 注入）；
        冇就回 None。唔入計分。"""
        for k in ("rail", "course_rail", "course_config"):
            v = self._clean(str(self.race_context.get(k) or ""))
            if v and v not in ("N/A", "-", ""):
                return v
        return None

    def _draw_position_fit_score(self):
        text = self._text("draw_position_fit", "position_pi", "running_style")
        weights = scoring.RACE_SHAPE_FIT_WEIGHTS
        score = weights["base"]
        details = []
        if "✅匹配" in text:
            score += weights["match_bonus"]
            details.append("檔位與跑法匹配")
        if "❌錯配" in text or "錯配!" in text:
            score += weights["mismatch_pen"]
            self.risk_flags.append("draw_position_mismatch")
            details.append("檔位與跑法有錯配")
        if "⚠️需主動切入" in text:
            score += weights["active_slot_pen"]
            self.risk_flags.append("needs_active_slotting")
            details.append("早段需要主動切入")
        if "上升軌" in text:
            score += weights["pi_up_bonus"]
            details.append("走位 PI 有上升軌")
        elif "微升" in text:
            score += weights["pi_micro_up_bonus"]
            details.append("走位 PI 微升")
        elif "衰退中" in text:
            score += weights["pi_down_pen"]
            details.append("走位 PI 衰退")
        elif "微跌" in text:
            score += weights["pi_micro_down_pen"]
            details.append("走位 PI 微跌")
        detail = "；".join(details) if details else "檔位跑法匹配未見鮮明偏差"
        return clip_score(score), f"匹配面：{detail}。"

    def _trip_consumption_score(self):
        text = self._clean(self._value("position_window") or "")
        mapping = scoring.RACE_SHAPE_TRIP_CONSUMPTION_SCORES
        scores = []
        labels = []
        for part in text.split("|")[:3]:
            part = part.strip()
            # 長標籤優先，否則「高」會搶先 match 走「極高」
            for label, score in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
                if label in part:
                    scores.append(score)
                    labels.append(label)
                    break
        if not scores:
            return 60.0, "近仗消耗未有清晰標籤，按中性處理。"
        score = sum(scores) / len(scores)
        return clip_score(score), f"近{len(scores)}仗走位消耗以{'、'.join(labels)}為主。"

    def _race_shape_context_delta(self):
        text = self._text("draw_position_fit", "position_pi", "position_window", "running_style")
        weights = scoring.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS
        delta = 0.0
        items = []  # 逐項 {factor, delta, why}
        def add(factor, d, why):
            nonlocal delta
            delta += d
            items.append({"factor": factor, "delta": round(d, 2), "why": why})
        if "✅匹配" in text:
            add("走位匹配", weights["match_bonus"], "檔位跑法匹配")
        if "❌錯配" in text or "錯配!" in text:
            self.risk_flags.append("draw_position_mismatch")
            add("走位匹配", weights["mismatch_pen"], "檔位跑法錯配")
        if "⚠️需主動切入" in text:
            self.risk_flags.append("needs_active_slotting")
            add("走位匹配", weights["active_slot_pen"], "需要主動切入")
        if "上升軌" in text:
            add("走位PI", weights["pi_up_bonus"], "走位 PI 上升")
        elif "衰退中" in text:
            add("走位PI", weights["pi_down_pen"], "走位 PI 衰退")
        if "信心: 高" in text:
            add("位置窗信心", weights["high_conf_bonus"], "位置窗信心較高")
        elif "信心: 低" in text:
            add("位置窗信心", weights["low_conf_pen"], "位置窗信心較低")
        recent = self._clean(self._value("position_window") or "").split("|")[0]
        if "低消耗" in recent:
            add("近仗消耗", weights["recent_low_consumption_bonus"], "最近走位低消耗")
        elif "極高" in recent:
            add("近仗消耗", weights["recent_extreme_consumption_pen"], "最近走位極高消耗")
        elif "高" in recent:
            add("近仗消耗", weights["recent_high_consumption_pen"], "最近走位高消耗")
        context_weights = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
        delta = max(context_weights["non_sha_tin_delta_floor"], min(context_weights["non_sha_tin_delta_cap"], delta))
        return delta, items

    def _ability_score(self, matrix_scores):
        if self._is_debut():
            return sum(matrix_scores.get(key, 60.0) * weight for key, weight in DEBUT_MATRIX_WEIGHTS.items())
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
            reason = "影子排序重算 consistency_score，加入輸距權重同近期回暖/回落。"

        matrix_scores = map_features_to_matrix_scores(shadow_features)
        # 同主線一致：重算後必須重套 finish-time trend nudge，否則 ability_delta 被污染。
        # reason_codes 係主線嗰個 list，shadow 重算唔可以 append 落去。
        saved_reason_codes = self.reason_codes
        self.reason_codes = list(saved_reason_codes)
        matrix_scores["sectional"] = self._apply_finish_time_trend(matrix_scores["sectional"])
        self.reason_codes = saved_reason_codes
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

        # 「已再參考XX調整騎練分」呢句唔append落sub note（用戶：無意義）——
        # 逐項調整已經喺「評分構成」下面逐行連證據列晒。
        updated, trainer_note = self._apply_trainer_signal_context(updated)
        if trainer_note:
            sources["jockey_score"] = "th01_trainer_context"
            sources["trainer_score"] = "th01_trainer_context"

        health_score, health_note = self._candidate_health_risk_score()
        if health_score is not None:
            updated["risk_score"] = clip_score(health_score)
            notes["risk_score"] = self._append_note(
                self._strip_embedded_score(feature_notes.get("risk_score"), "風險分"),
                f"{health_note}重算風險分{clip_score(health_score):.1f}。",
            )
            sources["risk_score"] = "th01_health_context"

        shadow = self._consistency_shadow_detail()
        if shadow is not None:
            updated["consistency_score"] = clip_score(shadow["score"])
            shift_txt = {"recovering": "，且近三仗名次好過再之前", "declining": "，但近三仗名次差過再之前"}.get(shadow["recent_shift"], "")
            notes["consistency_score"] = self._append_note(
                self._strip_embedded_score(feature_notes.get("consistency_score"), "穩定性分"),
                (
                    f"逐仗連輸距覆核：近{shadow['n']}仗有{shadow['close_runs']}仗跑近前列、"
                    f"{shadow['poor_runs']}仗明顯敗陣{shift_txt}，穩定性分定為{clip_score(shadow['score']):.1f}。"
                ),
            )
            sources["consistency_score"] = "cx01_consistency_context"

        return updated, notes, sources

    @staticmethod
    def _strip_embedded_score(note, label):
        """覆蓋分數時，將原註解入面自述嘅舊分（例：「穩定性分66分」）清走，
        避免報告出現「穩定性分 76 ← ...穩定性分66分」呢種前後對唔上。"""
        text = str(note or "").strip()
        if not text:
            return text
        text = re.sub(rf"[，,、；;]?\s*{label}[為約]?\s*\d+(?:\.\d+)?\s*分?", "", text)
        text = re.sub(r"。{2,}", "。", text).strip(" ，,、；;")
        return text

    def _apply_trainer_signal_context(self, feature_scores):
        updated = dict(feature_scores)
        prior_stack = self._trainer_signal_priors()
        jockey = self._clean(self.horse_data.get("jockey"))
        trainer = self._clean(self.horse_data.get("trainer"))
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()

        jockey_base = clip_score(updated.get("jockey_score", 60.0))
        trainer_base = clip_score(updated.get("trainer_score", 60.0))
        jockey_adj = 0.0
        trainer_adj = 0.0
        triggers = []
        adjustments = []

        # 用戶要求：凡有數據嘅因子一律顯示（±0 都寫），等每個分點嚟都睇得晒
        horse_history = self._current_jockey_horse_record()
        if horse_history:
            history_adj = self._trainer_history_adjustment(horse_history)
            jockey_adj += history_adj
            if history_adj:
                triggers.append("人馬歷史")
            adjustments.append({
                "factor": "人馬歷史",
                "target": "騎師分",
                "delta": round(history_adj, 2),
                "evidence": (
                    f"{jockey or '今場騎師'}近期策騎此馬{int(horse_history['starts'])}次："
                    f"{int(horse_history['wins'])}勝、前三率{horse_history['place_rate']:.0f}%、平均{horse_history['avg_finish']:.1f}名"
                    + ("" if history_adj else "（未達加減分門檻，不加不減）")
                ),
            })

        prior = self._jockey_trainer_prior()
        if prior is None and jockey and trainer:
            prior = prior_stack.combo.get((jockey, trainer))
        combo_adj = self._trainer_combo_adjustment(prior)
        if combo_adj:
            j_share = combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_jockey_share"]
            t_share = combo_adj * scoring.TRAINER_SIGNAL_CONTEXT_WEIGHTS["combo_trainer_share"]
            jockey_adj += j_share
            trainer_adj += t_share
            triggers.append("騎練組合")
        if prior and float(prior.get("starts", 0) or 0) >= 10:
            c_starts = int(float(prior.get("starts", 0) or 0))
            c_win = float(prior.get("win_rate", 0) or 0)
            c_place = float(prior.get("place_rate", 0) or 0)
            elite_tag = "（馬房皇牌組合）" if (c_starts >= 40 and (c_win >= 14.0 or c_place >= 36.0)) else ""
            if combo_adj:
                tail = "（騎師分攤55%／練馬師45%）"
            elif c_starts < 40:
                tail = "（樣本未夠40仗，不加不減）"
            else:
                tail = "（表現屬中游，不加不減）"
            adjustments.append({
                "factor": "騎練組合",
                "target": "騎師分/練馬師分",
                "delta": round(combo_adj, 2),
                "evidence": (
                    f"{jockey}×{trainer} 拍檔{c_starts}仗："
                    f"勝率{c_win:.1f}%、上名率{c_place:.1f}%{elite_tag}{tail}"
                ),
            })

        if distance and jockey:
            distance_row = prior_stack.jockey_distance.get((jockey, distance))
            distance_adj = self._jockey_distance_adjustment(distance_row)
            jockey_adj += distance_adj
            if distance_adj:
                triggers.append("騎師同程")
            if distance_row and float(distance_row.get("starts", 0) or 0) > 0:
                d_starts = int(float(distance_row.get("starts", 0) or 0))
                tail = "" if distance_adj else (
                    "（樣本未夠80仗，不加不減）" if d_starts < 80 else "（表現屬中游，不加不減）"
                )
                adjustments.append({
                    "factor": "騎師同程",
                    "target": "騎師分",
                    "delta": round(distance_adj, 2),
                    "evidence": (
                        f"{jockey}於{distance}米往績{d_starts}仗："
                        f"勝率{float(distance_row.get('win_rate', 0) or 0):.1f}%、上名率{float(distance_row.get('place_rate', 0) or 0):.1f}%{tail}"
                    ),
                })

        if distance and trainer:
            trainer_row = prior_stack.trainer_distance.get((trainer, distance))
            trainer_distance_adj = self._trainer_distance_adjustment(trainer_row)
            trainer_adj += trainer_distance_adj
            if trainer_distance_adj:
                triggers.append("練馬師同程")
            if trainer_row and float(trainer_row.get("starts", 0) or 0) > 0:
                t_starts = int(float(trainer_row.get("starts", 0) or 0))
                tail = "" if trainer_distance_adj else (
                    "（樣本未夠80仗，不加不減）" if t_starts < 80 else "（表現屬中游，不加不減）"
                )
                adjustments.append({
                    "factor": "練馬師同程",
                    "target": "練馬師分",
                    "delta": round(trainer_distance_adj, 2),
                    "evidence": (
                        f"{trainer}於{distance}米往績{t_starts}仗："
                        f"勝率{float(trainer_row.get('win_rate', 0) or 0):.1f}%、上名率{float(trainer_row.get('place_rate', 0) or 0):.1f}%{tail}"
                    ),
                })

        if self._is_jockey_changed() is True:
            change_adj = self._jockey_change_adjustment(prior_stack.jockey_change)
            jockey_adj += change_adj
            if change_adj:
                triggers.append("換騎")
                keep = (prior_stack.jockey_change or {}).get(False) or {}
                adjustments.append({
                    "factor": "換騎",
                    "target": "騎師分",
                    "delta": round(change_adj, 2),
                    "evidence": (
                        f"全季統計沿用原騎（勝率{float(keep.get('win_rate', 0) or 0):.1f}%）平均好過換騎，"
                        "今仗屬換騎，作小幅折讓"
                    ),
                })

        if jockey_adj:
            updated["jockey_score"] = clip_score(updated.get("jockey_score", 60.0) + jockey_adj)
        if trainer_adj:
            updated["trainer_score"] = clip_score(updated.get("trainer_score", 60.0) + trainer_adj)

        self.trainer_signal_detail = {
            "jockey_base": round(jockey_base, 2),
            "jockey_final": round(clip_score(updated.get("jockey_score", 60.0)), 2),
            "trainer_base": round(trainer_base, 2),
            "trainer_final": round(clip_score(updated.get("trainer_score", 60.0)), 2),
            "adjustments": adjustments,
        }

        if not triggers:
            return updated, ""
        note = "已再參考" + "、".join(dict.fromkeys(triggers)) + "調整騎練分。"
        return updated, note

    def _apply_health_only_v2(self, base_score):
        return round(clip_score(base_score), 2)

    def _apply_trainer_signal_v3(self, base_score):
        # 配備訊號（pit backtest 2026-07-10 驗證）：除去配備＝練馬師部署負面訊號，
        # 扣騎練訊號維度分。初戴類全部 out-of-sample NULL，維持顯示唔入分。
        gear = str(self._value("gear_change") or "")
        if "除去" in gear:
            delta = scoring.GEAR_SIGNAL_WEIGHTS["gear_removed_pen"]
            self.reason_codes.append("gear_removed")
            removed = self._gear_change_readable() or {}
            detail = getattr(self, "trainer_signal_detail", None)
            if isinstance(detail, dict):
                detail.setdefault("adjustments", []).append({
                    "factor": "除去配備",
                    "target": "騎練訊號",
                    "delta": round(delta, 2),
                    "evidence": (removed.get("value") or "今仗除去配備")
                    + "（歷史回測：除去配備平均走樣，扣3分）",
                })
            return round(clip_score(base_score + delta), 2)
        return round(clip_score(base_score), 2)

    def _apply_finish_time_trend(self, base_score):
        # ML-validated (walk-forward 18 meetings / 180 races): the finish-time
        # deviation TREND in `finish_time_block` (improving vs declining vs HKJC
        # standard) carries ranking signal that SpeedScorer ignores — it only used
        # the absolute level. Nudging the sectional dim by this trend lifted
        # min/single/top3 on the held-out split with no metric regressing.
        block = self._text("finish_time_block")
        delta = 0.0
        if "進步" in block:
            delta = scoring.FINISH_TREND_MICRO_WEIGHTS["improving"]
        elif "退步" in block:
            delta = scoring.FINISH_TREND_MICRO_WEIGHTS["declining"]
        if delta:
            self.reason_codes.append(
                "finish_time_trend_up" if delta > 0 else "finish_time_trend_down"
            )
        return round(clip_score(base_score + delta), 2)

    def _candidate_health_risk_score(self):
        score = scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["base"]
        medical = self._text("medical_flags")
        weight_trend = self._text("weight_trend")
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

        note = "已再綜合醫療紀錄、休賽日數同體重波幅，"
        return clip_score(score), note

    # 休賽日 band —— 以 15 賽日 1753 個樣本嘅分佈定門檻（中位24 / p25=18 / p75=35 / p90=49），
    # 唔用主觀數字。key=上限（含），標籤＝白話。
    _LAYOFF_BANDS = (
        (7, "急放上陣"),        # ≤7：極少（2%）
        (20, "較密間隔"),       # 8-20：低於中位
        (35, "正常間隔"),       # 21-35：主流（median 24）
        (60, "短休後復出"),     # 36-60
        (120, "較長休賽"),      # 61-120
        (10**9, "長期休養後首戰"),  # >120：長休復出
    )

    def _layoff_band(self, days):
        for hi, label in self._LAYOFF_BANDS:
            if days <= hi:
                return label
        return "長期休養後首戰"

    def _last_race_date(self):
        """由 recent_6_detail「第1仗(DD/MM/YYYY …)」抽最近一仗日期 → 中文。"""
        detail = self._text("recent_6_detail")
        m = re.search(r"第1仗\((\d{2})/(\d{2})/(\d{4})", detail)
        if not m:
            return None
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}年{int(mo)}月{int(d)}日"

    def _bodyweight_readout(self):
        """今仗排位體重 vs 上仗 → 白話（seq 新→舊，seq[0]=今仗）。
        兩個唔同概念要分清，唔好撞（用戶反映『相若又話波幅大』矛盾）：
          ① 今仗 vs 上仗（點對點）→ 相若／增／減
          ② 近仗走勢（多仗）→ 分「穩步升／跌」（單向趨勢）同「上落較大」（亂）：
             用 span vs |淨變幅| 區分——span≈淨變幅＝單向趨勢（唔算不穩），
             span 遠大於淨變幅＝真・亂上落先叫波幅大。"""
        seq = [int(x) for x in re.findall(r"\d{3,4}", self._text("weight_trend"))]
        if len(seq) < 2:
            return None
        delta = seq[0] - seq[1]           # 今 vs 上
        net = seq[0] - seq[-1]            # 今 vs 最舊（淨走勢）
        span = max(seq) - min(seq)        # 全段幅度
        a = abs(delta)
        if delta >= 15:
            word = f"體重較上仗增加{a}磅，屬明顯上升"
        elif delta >= 8:
            word = f"體重較上仗增加{a}磅，中度上升"
        elif delta >= 3:
            word = f"體重較上仗微升{a}磅"
        elif delta <= -15:
            word = f"體重較上仗下降{a}磅，屬明顯下降"
        elif delta <= -8:
            word = f"體重較上仗下降{a}磅，中度下降"
        elif delta <= -3:
            word = f"體重較上仗微降{a}磅"
        else:
            word = "體重與上仗相若"
        # 近仗走勢（只喺幅度夠大先講）：
        if span >= 19:
            erratic = span - abs(net)     # 亂度＝總幅度扣淨走勢
            if abs(net) >= 15 and erratic <= 10:
                # 單向趨勢（穩步升／跌），唔算不穩
                word += f"；近{len(seq)}仗{'穩步回升' if net > 0 else '持續轉輕'}（{seq[-1]}→{seq[0]}磅）"
            elif erratic >= 15:
                # 真・上落不定
                word += f"；近{len(seq)}仗體重上落較大（波幅{span}磅），狀態欠穩定"
        return word

    def _health_readout(self):
        """馬匹健康白話判讀（display-only）：上次出賽日期＋休賽 band＋體重＋
        傷後/長休＋長休×晨操 context。回傳 {lines, verdict}。"""
        lines = []
        days = parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
        last_date = self._last_race_date()
        if last_date and days is not None:
            band = self._layoff_band(int(days))
            lines.append(f"上次出賽：{last_date}")
            lines.append(f"距今：{int(days)}日（{band}）")
        elif days is not None:
            lines.append(f"距今：{int(days)}日（{self._layoff_band(int(days))}）")

        bw = self._bodyweight_readout()
        if bw:
            lines.append(bw)

        # 急放紅旗（display-only）：≤7日 + 上仗大敗（≥6名）。歷史此組合上名率僅
        # 6.6% vs 全體 24%（15賽日76樣本）。入分測試唔穩健（同 form 重複，過擬合），
        # 只作提示。
        l6 = re.findall(r"\d+", str(self.horse_data.get("last_6_finishes") or ""))
        if days is not None and days <= 7 and l6 and int(l6[0]) >= 6:
            lines.append(f"⚠️ 上仗大敗（{l6[0]}名）後{int(days)}日內急放，歷史此組合上名率偏低（約6.6%），須留神")

        # 傷病後復出：醫療欄有真事故（非「無事故」）＋今仗復出
        medical = self._text("medical_flags")
        has_incident = bool(medical) and "無醫療事故" not in medical and medical not in ("N/A", "")
        if has_incident:
            lines.append("醫療欄有紀錄，或屬傷病後復出，須留意復原情況")

        # 長休 × 晨操 context（#6）：長休（>60日）要睇操練夠唔夠
        tw = self._text("trackwork_digest") + self._text("trackwork_trainer")
        if days is not None and days > 60:
            strong = any(k in tw for k in ("快操", "試閘", "積極", "加強", "操練充足", "好過近績"))
            weak = any(k in tw for k in ("放緩", "偏保守", "操練量少", "操練不足"))
            if strong:
                lines.append("復出前操練量充足，狀態有支持")
            elif weak:
                lines.append("長休後操練偏保守，狀態須觀察")
            else:
                lines.append("長休復出，宜對照晨操判斷備戰")

        verdict = "；".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")
        return {"lines": lines, "verdict": verdict}

    def _candidate_consistency_shadow_score(self):
        detail = self._consistency_shadow_detail()
        return detail["score"] if detail else None

    def _consistency_shadow_detail(self):
        """逐仗連輸距重算穩定性分，並回傳可以直接寫入報告嘅事實統計
        （幾多仗貼近前列、幾多仗明顯敗陣、近三仗係咪好過之前）。"""
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
        close_runs = 0
        poor_runs = 0

        for idx, run in enumerate(runs[:6]):
            weight = weights[idx]
            rank = run["rank"]
            margin = run["margin"]

            if rank <= 3:
                close_credit += weight
                close_runs += 1
                continue
            if rank <= 5 and margin is not None and margin <= 3.0:
                close_credit += weight * 0.75
                close_runs += 1
            elif rank <= 7 and margin is not None and margin <= 2.5:
                close_credit += weight * 0.40
                close_runs += 1

            if rank >= 8 and margin is not None and margin >= 5.0:
                poor_debit += weight
                poor_runs += 1
            elif rank >= 6 and margin is not None and margin >= 7.0:
                poor_debit += weight * 0.70
                poor_runs += 1

            if rank >= 10 and margin is not None and margin >= 8.0:
                severe_debit += weight

        close_ratio = close_credit / weighted_total if weighted_total else 0.0
        poor_ratio = poor_debit / weighted_total if weighted_total else 0.0
        severe_ratio = severe_debit / weighted_total if weighted_total else 0.0

        # 輸距趨勢 nudge（收窄+4/擴大−4/波動−1）已移除：輸距本身經逐仗 close/poor
        # credit 計入，趨勢再加一次係同 form_line 重複；2026-07-08 backtest 兩邊
        # 一齊移除先零倒退（test gold/champ 反而升）。
        score = 58.0 + close_ratio * 18.0 - poor_ratio * 14.0 - severe_ratio * 10.0
        finish_positions = [run["rank"] for run in runs[:6]]
        recent_shift = ""
        if len(finish_positions) >= 5:
            recent_avg = sum(finish_positions[:3]) / 3.0
            older = finish_positions[3:6]
            older_avg = sum(older) / len(older)  # was /3.0 — undercounted when only 5 runs (2 elems)
            if recent_avg + 1.0 < older_avg:
                score += 3.0
                recent_shift = "recovering"
            elif recent_avg > older_avg + 1.0:
                score -= 3.0
                recent_shift = "declining"

        return {
            "score": clip_score(score),
            "n": len(runs[:6]),
            "close_runs": close_runs,
            "poor_runs": poor_runs,
            "recent_shift": recent_shift,
        }

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
        # Gate lowered 80→40: point-in-time backtest (18.8k runners,
        # all_race_results_master.csv) shows the jockey×trainer signal holds at
        # ≥40 starts — positive-combo top3 30.5% vs negative 18.4% (spread
        # +12.1pt vs +10.3pt at ≥80), while eligible combos rise 57→151 and
        # runner coverage ~2.6×. Lower samples (<40) start adding noise.
        if starts < 40:
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
            "sectional": ("段速表現", ("speed_score",)),
            "race_shape": ("檔位與走位情境（不含步速）", ("race_shape_context_score",)),
            "trainer_signal": ("騎練訊號", ("jockey_score", "trainer_score")),
            "horse_health": ("馬匹健康 / 新鮮感", ("risk_score", "weight_score")),
            "form_line": ("賽績線", ("formline_strength_score",)),
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
            # 矩陣後調整（例如 sectional 嘅完成時間對標趨勢 ±5）唔喺 sub分加權入面，
            # 唔寫出嚟嘅話「評分構成」加極都對唔返 header 個分 — 呢度補返一行。
            expected = clip_score(sum(clip_score(features.get(name, 60.0)) * weight
                                      for name, weight in MATRIX_FORMULAS[key]))
            diff = round(float(score) - expected, 2)
            if abs(diff) >= 0.05:
                if key == "sectional" and any(c.startswith("finish_time_trend") for c in self.reason_codes):
                    direction = "進步" if diff > 0 else "退步"
                    reasoning[key]["adjustment"] = f"完成時間對標趨勢{direction}：sub分加權後再{diff:+.1f}"
                else:
                    reasoning[key]["adjustment"] = f"矩陣後調整：sub分加權後再{diff:+.1f}"
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

    # ── 數據判讀 (structured data readout) ──────────────────────────────
    POSITIVE_TREND_WORDS = ("上升", "進步", "加強", "改善", "回升", "提升", "向好")
    NEGATIVE_TREND_WORDS = ("下降", "退步", "放緩", "回落", "轉差", "走低", "減弱")

    def _readout_band(self, trend):
        t = str(trend or "")
        if any(w in t for w in self.POSITIVE_TREND_WORDS):
            return "✅"
        if any(w in t for w in self.NEGATIVE_TREND_WORDS):
            return "⚠️"
        return "➖"

    def _trend_tail(self, text):
        """Pull the human trend label: prefer text after '趨勢:'; else last →-segment."""
        s = str(text or "")
        m = re.search(r"趨勢[:：]\s*([^|\n]+)", s)
        tail = m.group(1) if m else (s.rsplit("→", 1)[-1] if "→" in s else "")
        return re.sub(r"[📈📉🔴⚠️✅\s]+", " ", tail).strip()

    def _seq_endpoints(self, text, unit=""):
        head = re.split(r"→\s*趨勢|趨勢", str(text or ""))[0]
        nums = re.findall(r"-?\d+\.?\d*", head)
        return f"{nums[0]}→{nums[-1]}{unit}" if len(nums) >= 2 else ""

    def _rating_direction(self, text):
        """Derive rating direction from the actual numbers (the source tail label is
        unreliable — e.g. '82→90 → 降班中' is wrong; rising numbers = 評分上升)."""
        nums = re.findall(r"\d+", re.split(r"→\s*趨勢|趨勢", str(text or ""))[0])
        if len(nums) < 2:
            return ""
        first, last = int(nums[0]), int(nums[-1])
        if last - first >= 3:
            return "評分上升"
        if first - last >= 3:
            return "評分回落"
        return "評分平穩"

    def _formline_summary(self):
        """Concrete 賽績線: EVERY notable past opponent — my finish + margin that day,
        whether the opponent went on to win (form validation) and at what class move.
        Opponents that are also in today's field are flagged 同場對手."""
        table = self._value("formline_table")
        if not isinstance(table, list) or not table:
            return None

        def fin(row):
            m = re.match(r"\s*(\d+)", str(row.get("my_finish", "")))
            return int(m.group(1)) if m else 99

        def opp_name(row):
            return re.sub(r"^\[\d+\]\s*", "", str(row.get("opponents", "")).split("(")[0]).strip()

        def opp_wins(row):
            m = re.search(r":\s*(\d+)\s*勝", str(row.get("next_performance", "")))
            return int(m.group(1)) if m else 0

        def best_class_rank(text):
            ranks = [self._class_num(tok) for tok in re.split(r"[ /、,]+", str(text or "")) if tok]
            ranks = [r for r in ranks if r is not None]
            return min(ranks) if ranks else None

        today_rank = self._class_num(self.race_context.get("race_class"))
        field = set(self.race_context.get("field_horse_names") or [])
        mine = self.horse_data.get("horse_name")

        opponents = []
        for r in table:
            nm = opp_name(r)
            if not nm:
                continue
            orank = best_class_rank(r.get("next_class"))
            move = ""
            if today_rank is not None and orank is not None:
                move = "升班" if orank < today_rank else ("降班" if orank > today_rank else "同班")
            opp_text = str(r.get("opponents", ""))
            om = re.search(r"\[(\d+)\]", opp_text)
            opponents.append({
                "name": nm,
                "my_fin": fin(r),
                "my_finish_raw": str(r.get("my_finish", "")).strip(),
                "wins": opp_wins(r),
                "next_class": str(r.get("next_class", "")).strip(),
                "move": move,
                "is_field": any(f and f != mine and f in opp_text for f in field),
                "opp_fin": (1 if "頭馬" in opp_text else (int(om.group(1)) if om else None)),
                "date": str(r.get("date", "")).strip(),
            })
        validated = sum(1 for o in opponents if o["wins"] >= 1)
        return {"opponents": opponents, "validated": validated, "n": len(table)}

    def _compact_finish(self, raw):
        """'5 (-3-3/4)' → '第5負3-3/4'; '1 (...)' → '第1（勝出）'."""
        s = str(raw or "").strip()
        fm = re.match(r"\s*(\d+)", s)
        pos = fm.group(1) if fm else s
        if pos == "1":
            return "第1（勝出）"
        mm = re.search(r"\(([^)]+)\)", s)
        marg = mm.group(1).lstrip("-").strip() if mm else ""
        return f"第{pos}負{marg}" if marg else f"第{pos}"

    # HKJC 配備代號 → 港式中文（顯示用）
    _GEAR_NAMES = {
        "B": "眼罩", "BO": "單邊眼罩", "CP": "羊毛面箍", "CC": "頸箍",
        "E": "耳塞", "H": "頭罩", "P": "防沙眼罩", "PC": "半掩防沙眼罩",
        "SR": "鼻箍", "SB": "羊毛額箍", "TT": "繫舌帶", "V": "開縫眼罩",
        "VO": "單邊開縫眼罩", "XB": "交叉鼻繃",
    }

    def _gear_codes_to_names(self, text):
        parts = [c.strip() for c in str(text or "").replace("＋", "/").split("/")
                 if c.strip() and c.strip() not in ("-", "無", "N/A")]
        out = []
        for p in parts:
            code = re.sub(r"\d+$", "", p.upper()).strip()
            out.append(self._GEAR_NAMES.get(code, p))
        return out

    def _gear_change_readable(self):
        """配備變動 → 白話（戴上／除下／維持＋中文配備名）。display-only。"""
        raw = self._clean(self._value("gear_change") or "")
        if not raw or raw in ("N/A", "-"):
            return None
        m = re.search(r"上仗\s*([^→|]+?)\s*→\s*今仗\s*([^|]+)", raw)
        if not m:
            return None
        prev_names = self._gear_codes_to_names(m.group(1))
        cur_names = self._gear_codes_to_names(m.group(2))
        added = [n for n in cur_names if n not in prev_names]
        removed = [n for n in prev_names if n not in cur_names]
        bits = []
        if added:
            bits.append("戴上" + "、".join(added))
        if removed:
            bits.append("除下" + "、".join(removed))
        if bits:
            value = "；".join(bits)
            trend = "配備有變"
            band = "➖"
        else:
            value = ("維持" + "＋".join(cur_names)) if cur_names else "冇配備"
            trend = ""
            band = "➖"
        return {"value": value, "trend": trend, "band": band, "reason": raw}

    def _jockey_combo_detail(self):
        """Concrete 騎練 reason: combo record + whether jockey changed this run."""
        rows = self._jockey_combo_rows()
        cur = next((r for r in rows if r.get("jockey") and self._current_declared_jockey()
                    and r["jockey"] in self._current_declared_jockey()), None)
        if not cur and rows:
            cur = rows[0]
        # 「換騎」以近6場表逐仗判斷（上仗騎師 vs 今仗）——唔靠 digest 有冇
        # 「今場沿用」四隻字（舊 heuristic 令續配都被寫成「今仗換上」）。
        changed = self._is_jockey_changed()
        if changed is None:
            changed = bool(self._value("jockey_combo_block")) and "今場沿用" not in str(self._value("jockey_combo_block"))
        return {"row": cur, "changed": bool(changed),
                "jockey": self._clean(self._value("jockey") or ""),
                "trainer": self._clean(self._value("trainer") or "")}

    def _class_num(self, text):
        """Unified class rank — LOWER number = HIGHER class. Graded races
        (一/二/三級賽 = Group 1/2/3) and 上市賽 (Listed) rank ABOVE all 班次,
        so a horse moving from 第二班 to 三級賽 is 升班, not a same-/down-grade."""
        t = str(text or "")
        gm = re.search(r"([一二三])級賽", t)
        if gm:
            return "一二三".index(gm.group(1)) + 1          # G1=1, G2=2, G3=3
        gm = re.search(r"(?:Group|Grade|G)\s*([123])", t, re.I)
        if gm:
            return int(gm.group(1))
        if "上市賽" in t or "表列賽" in t or re.search(r"\b(?:Listed|LR)\b", t, re.I):
            return 4                                         # Listed: just below Group 3
        cm = re.search(r"第([一二三四五六七])班", t)
        if cm:
            return 10 + "一二三四五六七".index(cm.group(1))   # 第一班=10 … 第七班=16
        cm = re.search(r"C(?:lass)?\s*([1-7])", t, re.I)
        if cm:
            return 9 + int(cm.group(1))                      # C1=10 … C7=16
        return None

    def _class_label(self, text):
        """Tidy a class string for display: 'C4'→'第四班', graded kept as-is."""
        t = str(text or "").strip()
        cm = re.search(r"C(?:lass)?\s*([1-7])", t, re.I)
        if cm:
            return f"第{'一二三四五六七'[int(cm.group(1)) - 1]}班"
        return t

    def _class_move_note(self):
        """Class the horse ran last time vs today: 降班/同班/升班 (lower rank = higher class).
        Handles graded races (三級賽 etc.) which sit above all 班次."""
        today_txt = str(self.race_context.get("race_class") or "")
        today = self._class_num(today_txt)
        rd = str(self._value("recent_6_detail") or "")
        m = re.search(r"第1仗\([^)]*?([一二三]級賽|上市賽|表列賽|第[一二三四五六七]班)", rd)
        last_txt = m.group(1) if m else ""
        last = self._class_num(last_txt)
        if not (today and last):
            return ""
        move = "降班" if today > last else ("升班" if today < last else "同班")
        return f"上仗{last_txt}→今仗{self._class_label(today_txt)}（{move}）"

    def _draw_stats_note(self, draw):
        """今場此檔嘅官方 HKJC 檔位統計（racing.hkjc.com 檔位頁）。
        與評分（DrawScorer）同詳細分析（draw_verdict）同源 —— 全部讀 skeleton 一次
        resolve 好嘅 _data['draw_stats']，唔再用自家 draw_bias_stats.csv。"""
        entry = self._value("draw_stats")
        if not isinstance(entry, dict) or not entry.get("in_range"):
            return ""
        place = entry.get("place_pct")
        starts = entry.get("starts")
        if place is None or starts is None:
            return ""
        win = entry.get("win_pct")
        win_txt = f"、勝率{win:.0f}%" if isinstance(win, (int, float)) else ""
        return f"此檔歷史 上名率{place:.0f}%{win_txt}（{int(starts)}場）"



    def _recent_races_detailed(self):
        """Per-race history for the 近六場 readout: class, finishing place, 頭馬距離
        and the official rating the horse CARRIED that race. recent_6_detail and
        rating_trend are both ordered newest→oldest and align positionally
        (第1仗 ↔ rating_trend[0]), so we zip them by index."""
        rd = str(self._value("recent_6_detail") or "")
        if not rd.strip():
            return []
        rt_nums = [int(x) for x in
                   re.findall(r"\d+", re.split(r"→\s*趨勢|趨勢", str(self._value("rating_trend") or ""))[0])]
        races = []
        for seg in rd.split("|"):
            m = re.search(r"第(\d+)仗\(([^)]*)\)\s*[:：]\s*(\d+)\s*名\s*(.*)$", seg.strip())
            if not m:
                continue
            idx = int(m.group(1))
            meta = m.group(2).strip()
            dm = re.search(r"\d{2}/\d{2}/\d{4}", meta)
            date = dm.group(0) if dm else ""
            cls = meta.replace(date, "").strip()
            rating = rt_nums[idx - 1] if 1 <= idx <= len(rt_nums) else None
            races.append({"idx": idx, "date": date, "cls": cls,
                          "finish": int(m.group(3)), "margin": m.group(4).strip(),
                          "rating": rating})
        return races

    def _class_rank_note(self):
        """Average finishing place grouped by class over the available recent races
        (e.g. '三級賽 2.0名(1)、一級賽 3.5名(4)')."""
        races = self._recent_races_detailed()
        if not races:
            return ""
        buckets = {}
        for r in races:
            buckets.setdefault(r["cls"] or "未知", []).append(r["finish"])
        # order by class strength (graded above 班次)
        def keyf(item):
            n = self._class_num(item[0])
            return n if n is not None else 99
        parts = [f"{cls} 平均{sum(v)/len(v):.1f}名（{len(v)}場）"
                 for cls, v in sorted(buckets.items(), key=keyf)]
        return " ｜ ".join(parts)

    def _predicted_style(self):
        """Parse the pre-computed running_style ('後上 | 信心: 高 | 依據: …') into a
        tactical label the punter cares about (前置／守好位／守中／後上) plus the WHY.
        Reference only — never enters the rating matrix."""
        raw = str(self._value("running_style") or "").strip()
        if not raw or raw in ("N/A", "-", "--"):
            return None
        parts = [p.strip() for p in raw.split("|")]
        style_cn = parts[0] if parts else ""
        conf, basis = "", ""
        for p in parts[1:]:
            seg = p.split("：", 1)[-1].split(":", 1)[-1].strip()
            if "信心" in p:
                conf = seg
            elif "依據" in p:
                basis = seg
        label_map = {"前領": "前置", "跟前": "守好位", "中段": "守中",
                     "後上": "後上", "靈活": "靈活（隨步速）"}
        label = label_map.get(style_cn, style_cn)
        if not label:
            return None
        # Prefer the compact 近6仗 走位 breakdown (e.g. "5場守好位、1場後上") over the
        # verbose per-race "近1仗評語顯示…" basis.
        breakdown = str(self._value("style_breakdown_6") or "").strip()
        basis = f"近6仗 {breakdown}" if breakdown else basis
        return {"label": label, "conf": conf, "basis": basis}

    def _data_readout(self, features, matrix_scores):
        """Structured, fully-Chinese 數據判讀 rows: each = label/value/trend/band(/reason).
        Feeds both the .md report and the dashboard preview. Skips absent data."""
        rows = []

        def add(label, value, trend, band=None, reason=""):
            value = str(value or "").strip()
            trend = str(trend or "").strip()
            if value or trend:
                rows.append({"label": label, "value": value, "trend": trend,
                             "band": band or self._readout_band(trend), "reason": reason})

        def present(v):
            return v is not None and str(v).strip() not in ("", "N/A", "-", "--", "數據不可用")

        # 段速表現：一句總結（優勢／中性／劣勢＋理據），取代舊「段速趨勢」端點行；
        # 同 7D 段速判讀共用 _speed_verdict，口徑一致。
        if str(self._value("raw_l400") or "").strip() or str(self._value("l400_trend") or "").strip():
            v = self._speed_verdict(features, sectional_score=matrix_scores.get("sectional"))
            add("段速表現", v["label"], v["why"], band=v["band"])
        energy = self._value("energy_trend")
        if present(energy):
            # Show the source 趨勢 LABEL (a model assessment that out-predicts naive
            # endpoint direction — confirmed by ML), without the raw endpoints, which
            # can look contradictory (e.g. '99→90 → 上升'). Keeps display consistent
            # with how speed.py scores energy.
            etail = self._trend_tail(energy)
            # Only surface energy when it is actually rising/falling — a "穩定" row
            # carries no signal, so skip it (user feedback).
            if "上升" in etail:
                add("能量趨勢", "", "能量上升", band="✅")
            elif "下降" in etail:
                add("能量趨勢", "", "能量下降", band="⚠️")
        ftb = self._value("finish_time_block")
        if present(ftb):
            # 趨勢箭嘴喺抽取檔用 emoji（📈進步／📉退步／📊平穩）表達，早期格式先用中文；
            # 兩者都認，先前淨 grep 中文令呢行幾乎永遠顯示「平穩」（BUG A 顯示修正）。
            s = str(ftb)
            if "📈" in s or "進步" in s:
                tr = "進步中"
            elif "📉" in s or "退步" in s:
                tr = "退步中"
            else:
                tr = "平穩"
            # 「趨勢」= 近幾仗完成時間對標準嘅方向（改善／退步），有別於速度分講嘅
            # 絕對水平（快／慢）——並排時唔會被誤讀成矛盾。
            add("完成時間趨勢", "對標準", tr)
        rt = self._value("rating_trend")
        cur = self._value("current_rating")
        chg = self._value("rating_change")  # authoritative 評分+/- from the racecard
        if present(rt) or present(cur):
            cls_note = self._class_move_note()
            # rating history numbers, ordered newest→oldest (rt_nums[0] = last race)
            rt_nums = ([int(x) for x in
                        re.findall(r"\d+", re.split(r"→\s*趨勢|趨勢", str(rt))[0])]
                       if present(rt) else [])
            cur_int = None
            if present(cur):
                try:
                    cur_int = int(float(cur))
                except (TypeError, ValueError):
                    cur_int = None
            # previous-race rating: prefer the authoritative 評分+/- delta, else
            # the newest history value (rt_nums[0]).
            chg_int = None
            if present(chg):
                try:
                    chg_int = int(float(chg))
                except (TypeError, ValueError):
                    chg_int = None
            if cur_int is not None and chg_int is not None:
                last_rt = cur_int - chg_int
            else:
                last_rt = rt_nums[0] if rt_nums else None
            # rating range: prefer 近三季 (profile) high/low + 季初評分; else recent pool
            ss = self._value("rating_season_start")
            hi3, lo3 = self._value("rating_high_3s"), self._value("rating_low_3s")
            range_bits = []
            if ss is not None:
                try:
                    range_bits.append(f"季初評分{int(float(ss))}")
                except (TypeError, ValueError):
                    pass
            if hi3 is not None and lo3 is not None:
                try:
                    range_bits.append(f"近三季最高{int(float(hi3))}·最低{int(float(lo3))}")
                except (TypeError, ValueError):
                    pass
            if range_bits:
                range_txt = "；".join(range_bits)
            else:
                pool = list(rt_nums) + ([cur_int] if cur_int is not None else [])
                range_txt = f"近{len(rt_nums)}仗評分區間{min(pool)}-{max(pool)}分" if rt_nums else ""
            # today vs last-race rating → 加分/減分
            delta_txt, delta_tag = "", ""
            if cur_int is not None and last_rt is not None:
                d = cur_int - last_rt
                if d > 0:
                    delta_txt, delta_tag = f"今仗{cur_int}分、較上仗{last_rt}分 +{d}（加分）", f"+{d} 加分"
                elif d < 0:
                    delta_txt, delta_tag = f"今仗{cur_int}分、較上仗{last_rt}分 {d}（減分）", f"{d} 減分"
                else:
                    delta_txt, delta_tag = f"今仗{cur_int}分、與上仗持平（{last_rt}分）", "與上仗持平"
            elif cur_int is not None:
                delta_txt = f"今仗官方評分{cur_int}"
            reason = "；".join([p for p in (cls_note, delta_txt, range_txt) if p])
            cmove = "降班" if "降班" in cls_note else ("升班" if "升班" in cls_note else "")
            value = f"今仗{cur_int}分" if cur_int is not None else self._seq_endpoints(rt)
            # 評分／班次走勢係 handicapping 情境（降班、評分變動），但 rating 唔入
            # 評分（實測入分會 regress）——故一律中性 ➖，避免標 ✅ 令人以為有加分。
            add("評分走勢", value, cmove or delta_tag, band="➖", reason=reason)
        # (走位動量 row removed — low signal, per user feedback)
        # 休賽：上次出賽日期 + 距今日數 + band（數據門檻）
        days = parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
        if days is not None and days > 0:
            band = self._layoff_band(int(days))
            last_date = self._last_race_date()
            val = f"距今{int(days)}日" + (f"（上次{last_date}）" if last_date else "")
            # 正常休息唔係 edge：只有風險 band（急放／長休）標 ⚠️，其餘中性 ➖，冇 ✅
            add("休賽", val, band,
                band="⚠️" if band in ("較長休賽", "長期休養後首戰", "急放上陣") else "➖")
        # 體重狀態：整句白話（今仗vs上仗 ＋ 近仗走勢），唔拆開避免「相若／波幅大」讀落矛盾。
        bw = self._bodyweight_readout()
        if bw:
            concerning = any(k in bw for k in ("明顯上升", "明顯下降", "上落較大", "狀態欠穩定"))
            add("體重狀態", bw, "", band="⚠️" if concerning else "➖")
        eng = self._value("engine_type")
        if present(eng):
            add("段速型態", str(eng).split("|")[0].strip(), "")
        bd = self._value("best_distance")
        if present(bd):
            m = re.search(r"今仗\s*(\d+m)\s*=\s*(\d+)場\s*\(([\d\-]+)\)", str(bd))
            if m:
                dist, n, rec = m.group(1), m.group(2), m.group(3)
                parts = [int(x) for x in rec.split("-")]
                rband = "✅" if parts and parts[0] > 0 else ("➖" if sum(parts[1:]) > 0 else "⚠️")
                add("今仗路程", dist, "", band=rband,
                    reason=f"同程往績 {n}場（{parts[0]}冠/{(parts[1] if len(parts)>1 else 0)}亞/{(parts[2] if len(parts)>2 else 0)}季）")
            else:
                add("今仗路程", str(bd).split("|")[0].strip(), "")
        last6 = self._value("last_6_finishes")
        if present(last6):
            # Enrich with per-race 班次 / 名次 / 頭馬距離 / 當時評分 + 各班平均名次.
            races = self._recent_races_detailed()
            detail = ""
            if races:
                segs = []
                for r in races:
                    bits = [r["cls"], f"{r['finish']}名"]
                    if r["margin"]:
                        bits.append(r["margin"])
                    if r["rating"] is not None:
                        bits.append(f"評{r['rating']}")
                    segs.append("·".join(b for b in bits if b))
                detail = " ｜ ".join(segs)
            # 各班平均名次 now lives in its own 班次表現 section (see below).
            add("近六場", str(last6).strip(), "", reason=detail)
        draw = self._value("barrier") or self._value("draw")
        if present(draw):
            add("檔位", f"{str(draw).strip()}檔", "", reason=self._draw_stats_note(draw))
        # 預測跑法 — tactical position read (前置／守好位／守中／後上). Reference only:
        # explicitly NOT in the rating matrix; explains the WHY (recent runs, jockey change).
        ps = self._predicted_style()
        if ps:
            why = []
            if ps["basis"]:
                why.append(ps["basis"])
            # Jockey-change note is authoritative (set only on a REAL change vs last
            # start, with the new rider's prior style on this horse). No note ⇒ no change.
            jcn = self._value("jockey_change_note")
            if jcn:
                why.append(str(jcn))
            add("預測跑法", ps["label"],
                f"信心{ps['conf']}" if ps["conf"] else "",
                band="➖", reason="；".join(why))
        # 騎練 + 晨操 use matrix bands / digests already computed
        ts = matrix_scores.get("trainer_signal", 60)
        jc = self._jockey_combo_detail()
        jt = f"{jc['jockey']}／{jc['trainer']}".strip("／")
        row = jc.get("row")
        jscore = features.get("jockey_score", 60)
        parts_r = []
        # 換騎先講「換上」；續配用返續配講法（用戶：同一騎師唔好寫換上）
        if jc.get("changed"):
            parts_r.append(f"今仗轉用上格騎師{jc['jockey']}" if jscore >= 75 else f"今仗換上{jc['jockey']}")
        elif jc.get("jockey"):
            parts_r.append(f"續配{jc['jockey']}")
        if row and row.get("starts", 0) >= 1:
            wins, places, avg = int(row.get("wins", 0)), int(row.get("places", 0)), row.get("avg_finish", 0)
            rec = f"{int(row['starts'])}仗{wins}勝{places}上名、平均{avg:.1f}名"
            if wins > 0 or avg <= 4.5:
                parts_r.append(f"與此馬 {rec}（人馬合拍）")
            else:
                parts_r.append(f"惟與此馬 {rec}")
        # 騎練組合全埠統計（有入分：騎練組合調整因子）＋皇牌組合 tag
        combo_prior = self._jockey_trainer_prior()
        if combo_prior is None and jc.get("jockey") and jc.get("trainer"):
            combo_prior = self._trainer_signal_priors().combo.get((jc["jockey"], jc["trainer"]))
        trend_txt = "強訊號" if ts >= 70 else ("偏弱" if ts < 55 else "中性")
        if combo_prior and float(combo_prior.get("starts", 0) or 0) >= 10:
            c_starts = int(float(combo_prior.get("starts", 0) or 0))
            c_win = float(combo_prior.get("win_rate", 0) or 0)
            c_place = float(combo_prior.get("place_rate", 0) or 0)
            combo_txt = f"拍檔{c_starts}仗勝率{c_win:.0f}%、上名率{c_place:.0f}%"
            if c_starts >= 40 and (c_win >= 14.0 or c_place >= 36.0):
                combo_txt += "（馬房皇牌組合）"
                trend_txt = "皇牌組合"
            parts_r.append(combo_txt)
        jreason = "，".join(parts_r)
        add("騎練組合", jt, trend_txt,
            band="✅" if ts >= 70 else ("⚠️" if ts < 55 else "➖"), reason=jreason)
        fl = self._formline_summary()
        if fl and fl.get("opponents"):
            opps = fl["opponents"]
            # Surface every meaningful opponent: today's rivals (同場對手) first, then the
            # rest of the validated ones (opponents that went on to win). Order: field
            # rivals → most subsequent wins → my best finish.
            cand = [o for o in opps if o["is_field"] or o["wins"] >= 1] or opps[:1]
            # dedupe by opponent name (a rival can beat me in several of my past races);
            # keep the strongest instance: field-rival > more subsequent wins > my best finish
            byname = {}
            for o in cand:
                e = byname.get(o["name"])
                if e is None or (o["is_field"], o["wins"], -o["my_fin"]) > (e["is_field"], e["wins"], -e["my_fin"]):
                    byname[o["name"]] = o
            shown = sorted(byname.values(), key=lambda o: (not o["is_field"], -o["wins"], o["my_fin"]))[:4]
            field_n = sum(1 for o in shown if o["is_field"])
            mine = self.horse_data.get("horse_name", "本駒")
            lines = []
            for o in shown:
                fin_c = self._compact_finish(o["my_finish_raw"])
                tag = "⭐同場對手" if o["is_field"] else ""
                if o["wins"] >= 1:
                    cls = o["next_class"]
                    won = (f"{o['name']}其後{o['move']}（{cls}）再勝{o['wins']}場" if o["move"]
                           else f"{o['name']}其後於{cls}再勝{o['wins']}場")
                else:
                    won = f"{o['name']}其後未再勝"
                meet = (f"當日{mine}{fin_c}、{o['name']}第{o['opp_fin']}" if o["is_field"] and o["opp_fin"]
                        else f"當日{mine}{fin_c}")
                lines.append(f"{tag}「{o['name']}」{meet}，{won}".lstrip())
            trend = (f"同場對手{field_n}駒" if field_n else
                     ("對手已驗證" if fl["validated"] >= 1 else "對手未驗證"))
            add("賽績線", f"近{fl['n']}仗", trend,
                band="✅" if (field_n or fl["validated"] >= 1) else "➖",
                reason=" ｜ ".join(lines))
        # 班次表現 — average finishing place grouped by class (own section).
        # Prefer the 近三季 profile-derived breakdown; fall back to recent races.
        cls_perf = self._value("class_perf_3s") or self._class_rank_note()
        if cls_perf:
            add("班次表現", _format_hkjc_class_display(cls_perf), "", band="➖")
        # 配備變動 — 初戴類顯示用（曾測試入分：out-of-sample NULL）；
        # 除去配備已入分（騎練訊號 −3，見 _apply_trainer_signal_v3），band 標 ⚠️
        gear_read = self._gear_change_readable()
        if gear_read:
            removed_scored = "gear_removed" in self.reason_codes
            # reason 用白話 value（唔用 raw gear_change，佢含 ASCII pipe 會漏入
            # core_logic 觸發 NLG-002 假陽性）
            add("配備變動", gear_read["value"],
                gear_read["trend"] + ("，騎練訊號 −3分" if removed_scored else ""),
                band=("⚠️" if removed_scored else gear_read["band"]),
                reason=gear_read["value"])
        # 晨操 row 同晨操分析／狀態與穩定性共用 _trackwork_pattern 呢個單一判定，
        # 呢度只出 pattern 標籤＋賽日騎師參與＋一句原因；原始課數留返晨操分析度睇。
        tw_pattern = self._trackwork_pattern()
        if tw_pattern:
            jockey_txt = "賽日騎師有參與操練" if tw_pattern["jockey_in"] else "賽日騎師未有參與操練"
            add("晨操", tw_pattern["label"], jockey_txt,
                band=tw_pattern["band"], reason=tw_pattern["reason"])
        return rows

    DIM_LABELS = {
        "stability": "穩定性", "sectional": "段速", "race_shape": "形勢檔位",
        "trainer_signal": "騎練訊號", "horse_health": "健康新鮮", "form_line": "賽績線",
        "class_advantage": "班次優勢",
    }

    def _core_logic(self, features, matrix_scores, matrix_reasoning):
        """Reason-giving verdict. Each strong/weak factor is explained with its
        CONCRETE driver (combo names, jockey change, named opponent, segment
        numbers, rating direction) — neutral factors are skipped, no filler verdict."""
        name = self.horse_data.get("horse_name", "此駒")
        readout = self._data_readout(features, matrix_scores)

        def describe(r):
            # prefer the concrete reason; else label + trend/value
            if r.get("reason"):
                return r["reason"]
            detail = r["trend"] or r["value"]
            return f"{r['label']}{detail}".replace("　", "")

        pos = [r for r in readout if r["band"] == "✅"]
        neg = [r for r in readout if r["band"] == "⚠️"]

        # Always-present concrete framing: overall score + strongest/weakest dim.
        ordered = sorted(matrix_scores.items(), key=lambda kv: kv[1], reverse=True)
        top_dim = self.DIM_LABELS.get(ordered[0][0], ordered[0][0])
        low_dim = self.DIM_LABELS.get(ordered[-1][0], ordered[-1][0])
        ability = self._ability_score(matrix_scores)
        sents = [f"{name}今仗七維綜合戰力 {ability:.1f} 分，當中以{top_dim}（{ordered[0][1]:.0f}）為最強一環、"
                 f"{low_dim}（{ordered[-1][1]:.0f}）相對最弱。"]
        if pos:
            sents.append("優勢在於" + "；".join(describe(r) for r in pos[:3]) + "。")
        if neg:
            sents.append("要留意" + "；".join(describe(r) for r in neg[:3]) + "。")
        if not pos and not neg:
            sents.append("各項數據趨勢偏中性，暫未見鮮明強弱訊號，臨場節奏與形勢將係關鍵。")
        if self._is_debut():
            sents.append("初出馬無正式賽績，以上以備戰及試閘數據作背景參考，須臨場驗證。")
        # 保險：清走任何殘餘 ASCII pipe（raw 欄漏入會觸發 NLG-002 假陽性）；
        # 全形「｜」係賽績線敘述分隔，保留。
        return self._normalize_prose("".join(sents)).replace(" | ", "；").replace("|", "；")



    def _normalize_reason(self, key, note):
        note = str(note or "").strip()
        if not note:
            return "資料不足，中性60分。"
        if key == "jockey_score":
            jockey = self._clean(self.horse_data.get("jockey", "")) or "今場騎師"
            if "實績評分" in note:
                # 連續實績評分（兩季 master stats），reason 已係完整中文，掛名就得
                return f"{jockey}{note}。"
            if "Elite" in note:
                self.reason_codes.append("elite_jockey_with_data_support")
                return f"{jockey}屬頭馬季常客級（Elite）騎師，基礎85分起計。"
            if "Top Tier" in note:
                return f"{jockey}屬上格（Top Tier）騎師，基礎75分起計。"
            if "Positive" in note:
                return f"{jockey}屬正面層級騎師，基礎70分起計。"
            if "Overseas" in note and "G1" in note:
                return f"{jockey}為海外騎師，有G1級往績，基礎85分起計。"
            if "Overseas" in note:
                return f"{jockey}為海外騎師，按海外基準70分起計。"
            return f"{jockey}未列入特別加分層級，基礎60分中性起計。"
        if key == "trainer_score":
            trainer = self._clean(self.horse_data.get("trainer", "")) or "今場練馬師"
            if "實績評分" in note:
                return f"{trainer}{note}。"
            if "High" in note:
                return f"{trainer}屬高效率馬房，基礎80分起計。"
            if "Consistent" in note:
                return f"{trainer}屬穩定馬房，基礎75分起計。"
            if "Supported" in note:
                return f"{trainer}屬正面層級馬房，基礎70分起計。"
            if "Overseas" in note and "G1" in note:
                return f"{trainer}為海外練馬師，有G1級往績，基礎85分起計。"
            if "Overseas" in note and ("G2" in note or "G3" in note):
                return f"{trainer}為海外練馬師，有G2/G3級往績，基礎75分起計。"
            if "Aligns" in note:
                return f"{trainer}為海外練馬師，按同行騎師層級對齊處理。"
            if "Overseas" in note:
                return f"{trainer}為海外練馬師，按海外基準70分起計。"
            return f"{trainer}未列入特別加分層級，屬一般馬房，基礎60分中性起計。"
        if key == "draw_score":
            # DrawScorer 只用位置先驗（實證檔位統計經回測屬淨負累，只留顯示）。
            barrier = str(self.horse_data.get("barrier") or self.horse_data.get("draw") or "").strip()
            if "Invalid" in note:
                return "檔位資料不全，檔位分按中性處理。"
            dist = str(self.race_context.get("distance") or "")
            is_straight = "1000" in dist and self._is_sha_tin_context()
            try:
                dn = int(barrier)
            except (TypeError, ValueError):
                dn = None
            if dn is None:
                return "檔位按位置先驗計分。"
            if is_straight:
                pos = "高檔（直路賽有利）" if dn >= 8 else ("中檔" if dn >= 5 else "低檔（直路賽相對食虧）")
                return f"排{dn}檔；沙田1000米直路以高檔較著數，此檔屬{pos}，按位置先驗計分。"
            pos = "內檔（彎路賽著數位）" if dn <= 4 else ("中檔" if dn <= 8 else "外檔（彎路賽要蝕位）")
            return f"排{dn}檔；彎路賽以內檔較著數，此檔屬{pos}，按位置先驗計分。"
        if key == "form_score":
            if "No recent" in note or "Indeterminable" in note:
                return "近績資料不足，近績分按中性處理。"
            # FormScorer now emits a specific Chinese note (finishes + top3/win counts) — pass through.
            return note
        if key == "speed_score":
            # 一句定性收結即可——逐項 L400／步速修正／能量／引擎／路程 嘅加減分
            # 已喺報告「速度分＝基準60 + 逐項訊號」明細度全部列晒，唔喺度重複塞細節。
            if "Sectional data incomplete" in note:
                return "賽績段速資料未完整，速度分按中性處理。"
            if "Strong race sectional profile" in note:
                return "末段訊號偏強（逐項見下）。"
            if "Positive race sectional profile" in note:
                return "末段表現正面（逐項見下）。"
            if "Fair race sectional profile" in note:
                return "段速尚算平穩（逐項見下）。"
            if "Neutral race sectional profile" in note:
                return "段速只屬中性（逐項見下）。"
            if "Weak race sectional profile" in note:
                return "末段表現偏弱（逐項見下）。"
            return self._clean(note)
        return self._clean(note)

    def _best_evidence(self, feature_keys, notes):
        for key in feature_keys:
            note = notes.get(key)
            if note and "資料不足" not in note:
                return note
        return "相關來源不足，該維度以中性或保守分處理。"




    def _prep_score(self):
        digest = self._value("trackwork_digest")
        numbers = re.findall(r"備戰分(\d+(?:\.\d+)?)", str(digest or ""))
        return float(numbers[-1]) if numbers else 60.0

    def _current_jockey_horse_record(self):
        current_jockey = self._clean(self.horse_data.get("jockey", "") or self._current_declared_jockey())
        # SCORING uses the RECENCY window (current jockey's rides within the
        # horse's most recent races, i.e. the 近6場 history table) rather than the
        # full-career combo table. Point-in-time backtest over 16.8k runners shows
        # recency is the stronger predictor (corr 0.129 vs full-career 0.124;
        # strong-bucket top3 38.1% vs 36.4%). The full table is DISPLAY only.
        recent = self._recent_jockey_horse_record(current_jockey)
        if recent is not None:
            return recent
        if self._recent_jockey_history_rows():
            # Recency table present but current jockey absent → no recent signal.
            return None
        # Legacy fallback: no 近6場 table → use full combo table row.
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

    def _recent_jockey_horse_record(self, current_jockey):
        """Current jockey's record over the horse's recent races (近6場 table).

        Returns None when no recency table exists (caller decides fallback) or
        when the current jockey has no completed run in that window.
        """
        rows = self._recent_jockey_history_rows()
        if not rows:
            return None
        finishes = []
        for row in rows:
            if self._clean(row["jockey"]) != current_jockey:
                continue
            match = re.search(r"\d+", str(row["finish"]))
            if not match:
                continue
            value = int(match.group(0))
            if value > 0:
                finishes.append(value)
        if not finishes:
            return None
        starts = len(finishes)
        wins = sum(1 for f in finishes if f == 1)
        shows = sum(1 for f in finishes if f <= 3)
        places = sum(1 for f in finishes if f <= 2)
        return {
            "starts": float(starts),
            "wins": float(wins),
            "places": float(places),
            "avg_finish": round(sum(finishes) / starts, 1),
            "win_rate": round(wins / starts * 100, 1),
            "place_rate": round(shows / starts * 100, 1),
        }

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

    def _is_sha_tin_context(self):
        value = self.race_context.get("venue") or self.race_context.get("course") or self.race_context.get("racecourse") or ""
        text = str(value)
        return text in {"ST", "Sha Tin", "ShaTin", "沙田"} or "沙田" in text or "ShaTin" in text or "Sha Tin" in text

    def _clean(self, value):
        text = str(value or "").strip()
        return "資料未完成，中性處理" if "[FILL" in text.upper() else text



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
            "race_shape_context_score": "檔位走位情境分",
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























    def _formline_proximity_note(self):
        """Display-only. Surfaces the strongest 'ran CLOSE to a rival who later
        validated' evidence from formline_table — the genuinely predictive angle
        (proximity to validated strong-group rivals) that the formline STRENGTH
        SCORE ignores (it only counts opponents who later won, not how close the
        horse finished to them). Purely narrative; does not affect any score."""
        table = self._value("formline_table")
        if not isinstance(table, list):
            return ""
        STRONG = ("超強組", "強組")
        best = None
        for row in table:
            if not isinstance(row, dict):
                continue
            strength = str(row.get("strength") or "")
            if not any(s in strength for s in STRONG):
                continue
            m = re.match(r"\s*(\d+)", str(row.get("my_finish") or ""))
            if not m:
                continue
            fin = int(m.group(1))
            if fin > 3:  # only genuine "ran close" evidence
                continue
            perf = str(row.get("next_performance") or "")
            wm = re.search(r"(\d+)\s*勝", perf)
            wins = int(wm.group(1)) if wm else 0
            if wins < 1:  # rival must have validated the form later
                continue
            opp = re.sub(r"^\[\d+\]\s*", "", str(row.get("opponents") or "").split(",")[0])
            opp = opp.replace("(頭馬)", "").strip()
            next_cls = "／".join(str(row.get("next_class") or "").split())
            sm = re.search(r"出\s*(\d+)\s*次", perf)
            starts = int(sm.group(1)) if sm else 0
            grp = "超強組" if "超強組" in strength else "強組"
            key = (1 if grp == "超強組" else 0, -fin, wins)
            phrase = f"當時喺{grp}賽事以第{fin}名貼近對手「{opp}」"
            if next_cls and next_cls != "-" and starts:
                phrase += f"，該對手其後於{next_cls}出賽{starts}次贏{wins}場"
            phrase += "，證明貼得到呢類已兌現嘅對手"
            if best is None or key > best[0]:
                best = (key, phrase)
        return best[1] if best else ""

    def _formline_opponent_highlight(self):
        context_parts = []
        formline_table = self._value("formline_table")
        recent_6_detail = self._value("recent_6_detail") or str(self.horse_data.get("last_6_finishes") or "")

        proximity = self._formline_proximity_note()
        if proximity:
            context_parts.append(proximity)

        if not proximity and isinstance(formline_table, list) and len(formline_table) > 0:
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
                
        # 距離差註腳只喺冇 proximity 主句時先加——否則會插入主句中間打斷語意
        margin_match = re.search(r"第1仗[^:]*:\s*\d+名\s*([^|]+)", str(recent_6_detail))
        if margin_match and not proximity:
            margin_val = margin_match.group(1).strip()
            context_parts.append(f"上仗距離差為{margin_val}")
            
        if context_parts:
            return "，".join(context_parts)
            
        text = self._clean(self._value("formline_opponent_highlight") or "")
        if not text or text == "N/A":
            return ""
        return text



    def _risk_phrase_for_flag(self, flag):
        mapping = {
            "debut_race_experience_unknown": "初出實戰感仍然係未知數",
            "draw_pressure": "排檔形勢有機會令早段走位先蝕",
            "distance_unproven": "今場路程仍未有足夠實績支持",
            "class_edge_unproven": "班底未算有壓過對手嘅把握",
            "distance_record_weak": "同程往績未足以建立信心",
            "medical_record_unknown": "健康資料未算齊全，唔可以完全放鬆",
        }
        return mapping.get(flag, "")


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

    def _score_close(self, score):
        """判讀統一收尾：個分對總分係咩意義（界線同 band 符號一致：70/55）。"""
        score = float(score)
        if score >= 70:
            return f" → {score:.0f}分，加分位。"
        if score >= 55:
            return f" → {score:.0f}分，中性。"
        return f" → {score:.0f}分，拖累位。"

    def _describe_stability_matrix(self, score, features, evidence):
        finishes = self._recent_finish_list()
        recent_trend = self._recent_form_trend(finishes)
        seq = "-".join(str(f) for f in finishes[:6])
        seq_txt = f"近{min(len(finishes), 6)}仗 {seq}：" if seq else ""

        # 1) 名次面
        if features.get("form_score", 60) >= 78 and features.get("consistency_score", 60) >= 75:
            lead = f"{seq_txt}場場前列，狀態實在"
        elif features.get("form_score", 60) < 52 or features.get("consistency_score", 60) < 52:
            lead = f"{seq_txt}名次反覆，前列支撐不足"
        elif recent_trend == "warming":
            lead = f"{seq_txt}近三仗轉好，回勇中"
        elif recent_trend == "cooling":
            lead = f"{seq_txt}近三仗轉差，回落中"
        else:
            lead = f"{seq_txt}有交代，未算穩定"

        # 2) 輸距面（同穩定性分覆核同一組事實）
        shadow = self._consistency_shadow_detail()
        margin_txt = ""
        if shadow and shadow["n"] >= 3:
            if shadow["poor_runs"] == 0 and shadow["close_runs"] >= max(2, shadow["n"] - 2):
                margin_txt = "；輸距冇大敗，敗仗都貼近"
            elif shadow["poor_runs"] >= 2:
                margin_txt = f"；{shadow['poor_runs']}仗大敗（輸5個馬位以上）"
            elif shadow["poor_runs"] == 1:
                margin_txt = "；1仗大敗，其餘輸幅可接受"

        # 3) 晨操同賽績夾唔夾（統一 _trackwork_pattern）
        pattern = self._trackwork_pattern()
        if pattern is None:
            track = "；晨操資料不足"
        else:
            label = pattern["label"]
            if label == "操練好過近績":
                track = "；晨操好過近績，有翻身條件"
            elif label in ("轉強", "操練積極") and recent_trend == "cooling":
                track = f"；晨操{label}但近績回落，訊號矛盾，以賽績為準"
            elif label in ("轉強", "操練積極"):
                track = f"；晨操{label}，同近績同向"
            elif label == "操練放緩":
                track = "；晨操放緩，狀態冇額外佐證"
            elif label in ("轉弱", "操練偏少"):
                track = f"；晨操{label}，延續要打折扣"
            else:
                track = "；晨操中性"
        return f"{lead}{margin_txt}{track}{self._score_close(score)}"

    def _speed_verdict(self, features, sectional_score=None):
        """段速表現總結：優勢／中性／劣勢＋主要理據。band 直接由「最終 sectional
        維度分」（已含完成時間趨勢 nudge）經 score_band 判定，令判讀 emoji 同
        7D 逐項拆解嘅維度 emoji 100% 對齊——避免「原始速度分優勢但維度中性」矛盾。
        理據仍列 speed_detail 實際加減分。"""
        sp = float(sectional_score) if sectional_score is not None else float(features.get("speed_score", 60))
        detail = self.speed_detail if isinstance(self.speed_detail, list) else []
        pos = sorted([d for d in detail if float(d.get("delta", 0) or 0) > 0],
                     key=lambda x: -float(x["delta"]))
        neg = sorted([d for d in detail if float(d.get("delta", 0) or 0) < 0],
                     key=lambda x: float(x["delta"]))
        band = score_band(sp)
        label = "優勢" if band in ("✅", "✅✅") else ("中性" if band == "➖" else "劣勢")
        bits = [f"{d['why']}(+{float(d['delta']):.1f})" for d in pos[:2]]
        bits += [f"{d['why']}({float(d['delta']):.1f})" for d in neg[:1]]
        why = "、".join(bits) if bits else "各項段速訊號中性"
        return {"label": label, "band": band, "why": why, "score": sp}

    def _describe_sectional_matrix(self, score, features, evidence):
        # 判讀由 speed_detail 實際加減分砌出，band 用最終維度分（同拆解 emoji 對齊）。
        v = self._speed_verdict(features, sectional_score=score)
        l400 = self._seq_endpoints(self._value("l400_trend"), "s")
        l400_txt = f"L400 {l400}；" if l400 else ""
        return f"{l400_txt}段速{v['label']}：{v['why']}{self._score_close(score)}"

    def _describe_race_shape_matrix(self, score, features, evidence):
        barrier = self.horse_data.get("barrier") or self.horse_data.get("draw") or "N/A"
        draw_verdict = self._draw_verdict_signal()
        ps = self._predicted_style()
        style_txt = f"，預計{ps['label']}" if ps else ""
        if features.get("draw_score", 60) >= 72:
            draw = f"排{barrier}檔{style_txt}：著數位，有得揀位"
        elif features.get("draw_score", 60) >= 60:
            draw = f"排{barrier}檔{style_txt}：檔位中性，睇出閘搶位"
        else:
            draw = f"排{barrier}檔{style_txt}：檔位受壓，走位容錯低"
        if draw_verdict:
            draw += draw_verdict
        return f"{draw}{self._score_close(score)}"

    def _describe_trainer_signal_matrix(self, score, features, evidence):
        jockey = self.horse_data.get("jockey", "騎師")
        trainer = self.horse_data.get("trainer", "練馬師")
        detail = self.trainer_signal_detail or {}
        adjs = detail.get("adjustments") or []
        jf = float(features.get("jockey_score", 60))
        tf = float(features.get("trainer_score", 60))
        jw = "強" if jf >= 75 else ("中上" if jf >= 65 else ("一般" if jf >= 58 else "弱"))
        # 練馬師實績評分天然壓縮（全埠 58-65 左右），門檻相應收窄
        tw = "強" if tf >= 63 else ("有支持" if tf >= 61 else ("一般" if tf >= 58 else "弱"))
        short = {
            "人馬歷史": ("人馬合拍", "人馬紀錄差"),
            "騎練組合": ("組合合拍", "組合唔夾"),
            "騎師同程": ("同程數強", "同程數弱"),
            "練馬師同程": ("馬房同程強", "馬房同程弱"),
            "換騎": ("", "換騎微扣"),
        }
        pos = [short.get(a["factor"], (a["factor"], ""))[0] for a in adjs if a.get("delta", 0) > 0]
        neg = [short.get(a["factor"], ("", a["factor"]))[1] for a in adjs if a.get("delta", 0) < 0]
        pos = [x for x in dict.fromkeys(pos) if x]
        neg = [x for x in dict.fromkeys(neg) if x]
        extras = ""
        if pos:
            extras += "；" + "、".join(pos)
        if neg:
            extras += "；" + "、".join(neg)
        return f"{jockey}（{jw}）配{trainer}（{tw}）{extras}{self._score_close(score)}"

    def _describe_horse_health_matrix(self, score, features, evidence):
        # 晨操敘述已統一歸 stability（狀態與穩定性）獨家負責，健康維度只講醫療／休賽／體重。
        medical = self._text("medical_flags")
        days = parse_float(self._value("days_since_last") or self.horse_data.get("days_since_last"))
        wt = self._text("weight_trend")
        span = self._weight_trend_span(wt)
        medical_text = "醫療乾淨" if "無醫療事故" in medical else "醫療資料未齊，保守處理"
        if days is None:
            freshness = "；休賽間隔不明"
        elif days <= 14:
            freshness = f"；休後{int(days)}日快出，回氣要留意"
        elif days <= 45:
            freshness = f"；休後{int(days)}日，間隔正常"
        else:
            freshness = f"；休後{int(days)}日，實戰感成疑"
        if span is not None:
            weight_txt = f"；體重波幅{span:.0f}lb正常" if span <= 14 else f"；體重波幅{span:.0f}lb偏大"
        else:
            weight_txt = ""
        return f"{medical_text}{freshness}{weight_txt}{self._score_close(score)}"

    def _describe_form_line_matrix(self, score, features, evidence):
        strength = self._formline_strength_signal()
        highlight = self._formline_opponent_highlight()
        if strength == "elite":
            lead = "對手層面高，含金量高"
        elif strength == "strong":
            lead = "對手唔弱，有可信度"
        elif strength == "weak":
            lead = "對手支持唔夠，含金量偏弱"
        else:
            lead = "對手強度一般"
        hl = f"；{highlight}" if highlight else ""
        fl = self._formline_summary()
        frank = ""
        if fl and fl.get("n"):
            v, n = fl["validated"], fl["n"]
            if v >= 2:
                frank = f"；兌現度高（{v}/{n}仗對手其後再贏）"
            elif v == 1:
                frank = f"；有基本背書（1/{n}仗對手再贏）"
            else:
                frank = f"；未有賽果背書（0/{n}仗對手再贏）"
        return f"{lead}{hl}{frank}{self._score_close(score)}"

    def _describe_class_advantage_matrix(self, score, features, evidence):
        move = self._class_move_note()
        move_txt = ""
        if "降班" in move:
            move_txt = f"{move}：對手淺咗，實際著數；"
        elif "升班" in move:
            move_txt = f"{move}：過往交代要打折；"
        elif move:
            move_txt = f"{move}；"
        if features.get("class_score", 60) >= 70:
            class_text = "班次底子穩"
        elif features.get("class_score", 60) < 60:
            class_text = "班次底子未夠硬"
        else:
            class_text = "班次背景中性"
        if features.get("weight_score", 60) >= 68:
            weight = "；負磅友善"
        elif features.get("weight_score", 60) >= 60:
            weight = "；負磅可控"
        else:
            weight = "；負磅偏重"
        return f"{move_txt}{class_text}{weight}{self._score_close(score)}"

    def _draw_verdict_signal(self):
        text = self._clean(self._value("draw_verdict") or "")
        if not text or text == "N/A":
            return ""
        if "有利" in text:
            return "；本地檔位統計偏有利"
        if "不利" in text:
            return "；本地檔位統計唔友善"
        return ""

    def _describe_generic_matrix(self, score, features, evidence):
        return str(evidence or "").strip()


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

    # 已知晨操訊號 → 實戰意義（揀馬用語，唔係機械覆述）
    def _trackwork_pattern(self):
        """晨操 pattern 嘅單一判定來源 — 數據判讀、晨操分析、狀態與穩定性判讀共用，
        保證三度講嘅係同一個結論。label ∈ {轉強, 操練積極, 中性, 操練放緩, 轉弱}。
        reason 係一句白話、唔含原始課數（課數只喺晨操分析度展示）。"""
        digest = self._clean(self._value("trackwork_digest") or "")
        if not digest:
            return None
        markers = self._trackwork_markers()
        m = re.search(r"快操(\d+)課.*?試閘(\d+)課.*?踱步(\d+)課.*?游水(\d+)課", digest)
        gallops = trials = trotting = swimming = None
        if m:
            gallops, trials, trotting, swimming = (int(x) for x in m.groups())
        trend = markers["trend"]
        positive = markers["positive"] or ""
        jockey_in = "賽日騎師" in positive or "賽日騎師" in digest
        trainer_in = "練馬師親自" in positive
        # digest 三個分（維持/備戰/復刻）好少落 55 以下——一落即係真警號，
        # 用嚟將表面「放緩/中性」降級做「轉弱」，補返負面分辨力
        # （07-08 樣本：全場平均 75-77 分，<55 只有個位數）。
        digest_scores = {}
        for score_label in ("維持分", "備戰分", "復刻分"):
            sm = re.search(score_label + r"(\d+(?:\.\d+)?)", digest)
            if sm:
                digest_scores[score_label] = float(sm.group(1))
        weak_scores = [k for k, v in digest_scores.items() if v < 55]
        # 標籤同計分方向一致（計分都係「翻案復刻」優先，先到 trend）：
        # 操練好過近績＝正面翻身訊號，唔好同單純「放緩」撈亂。
        if markers["classification"] == "翻案復刻":
            label, band = "操練好過近績", "✅"
            reason = "近績麻麻但操練有力，有翻身條件"
        elif "加強" in trend:
            label, band = "轉強", "✅"
            reason = "快操時間一課比一課快"
        elif "放緩" in trend:
            if weak_scores or (gallops is not None and gallops <= 2):
                label, band = "轉弱", "⚠️"
                reason = "快操時間趨慢，備戰指標亦偏低" if weak_scores else "快操時間趨慢，課數亦少"
            else:
                label, band = "操練放緩", "➖"
                reason = "快操時間趨慢"
        elif weak_scores:
            label, band = "轉弱", "⚠️"
            reason = "備戰指標偏低（" + "、".join(weak_scores) + "不足55）"
        elif gallops is not None and gallops >= 5:
            # 全場快操眾數係4課；4課只係大隊平均，5課以上先算積極
            label, band = "操練積極", "✅"
            reason = "快操課數多過大隊平均"
        elif gallops is not None and gallops <= 1 and (swimming or 0) >= 10:
            label, band = "操練偏少", "⚠️"
            reason = "實地快操少，以游水踱步為主"
        else:
            label, band = "中性", "➖"
            reason = "操練量同節奏屬大隊正常水平"
        return {
            "label": label,
            "band": band,
            "reason": reason,
            "jockey_in": jockey_in,
            "trainer_in": trainer_in,
            "classification": markers["classification"],
            "counts": {"gallops": gallops, "trials": trials, "trotting": trotting, "swimming": swimming},
        }

    _TRACKWORK_SIGNAL_MEANINGS = {
        "賽日騎師有參與操練": "賽日騎師有落場操——出擊部署",
        "練馬師親自操練": "練馬師親自操練——馬房重視",
        "操練加壓超近績": "操練力度好過近績",
        "操練穩定持續": "操練規律持續，節奏正常",
        "初出備戰完備": "初出備戰工夫足",
        "操練放緩": "操練力度回落",
    }

    def _trackwork_interpretation(self):
        """晨操判讀（display-only）：將 digest 原文轉化成揀馬可用嘅判讀 —
        備戰量夠唔夠、趨勢代表乜、邊啲訊號係出擊部署、三個分數點解讀。
        原始 digest 全文仍保留喺 stability 維度嘅數據錨點，可對照追溯。"""
        digest = self._clean(self._value("trackwork_digest") or "")
        if not digest:
            return None
        markers = self._trackwork_markers()
        m = re.search(r"快操(\d+)課.*?試閘(\d+)課.*?踱步(\d+)課.*?游水(\d+)課", digest)
        gallops = trials = trotting = swimming = None
        if m:
            gallops, trials, trotting, swimming = (int(x) for x in m.groups())
        blank_m = re.search(r"空白日(\d+)日", digest)
        blank = int(blank_m.group(1)) if blank_m else None
        scores = {}
        for label in ("維持分", "備戰分", "復刻分"):
            sm = re.search(label + r"(\d+(?:\.\d+)?)", digest)
            if sm:
                scores[label] = float(sm.group(1))

        lines = []

        # 1. 備戰量 — 課數點解讀
        if gallops is not None:
            vol = f"近21日快操{gallops}課、試閘{trials}課、踱步{trotting}課、游水{swimming}課"
            # 呢行只講「工作量」；快慢方向由下面統一 pattern 講，避免兩行打架
            # 4課快操＝大隊眾數，只算正常；5課以上先叫充足
            if gallops >= 5:
                read = "工作量充足，多過大隊平均"
            elif gallops >= 2:
                read = "工作量正常（大隊水平）"
            elif (swimming or 0) >= 10:
                read = "實地操練少，游水為主"
            else:
                read = "操練量偏少"
            if trials:
                read += "，有試閘"
            lines.append(f"{vol} → {read}")
        if blank is not None and blank >= 5:
            lines.append(f"空白日{blank}日偏多，慎防中間有小狀況")

        # 2. 趨勢 — 用 _trackwork_pattern 嘅統一判定（同數據判讀、穩定性判讀一致）
        pattern = self._trackwork_pattern()
        if pattern:
            lines.append(f"操練 pattern：**{pattern['label']}** — {pattern['reason']}")

        # 3. 訊號 — 逐個翻譯成實戰意義
        for raw in [s.strip() for s in re.split(r"[、,]", markers["positive"] or "") if s.strip() and s.strip() != "無"]:
            lines.append("✅ " + self._TRACKWORK_SIGNAL_MEANINGS.get(raw, f"{raw}（正面訊號）"))
        for raw in [s.strip() for s in re.split(r"[、,]", markers["risk"] or "") if s.strip() and s.strip() != "無"]:
            if raw == "操練放緩":
                continue  # pattern 行已講，唔重複
            lines.append("⚠️ " + self._TRACKWORK_SIGNAL_MEANINGS.get(raw, f"{raw}（風險訊號）"))

        # 4. 三個備戰指標 — 用白話名＋評語，唔好淨掉個內部分數名出嚟
        #    維持分＝近期狀態帶到今仗嘅把握；備戰分＝今仗操課做得齊唔齊；
        #    復刻分＝重現自己最佳表現嘅機會。
        if scores:
            def _score_word(v):
                if v >= 80:
                    return "高"
                if v >= 70:
                    return "唔錯"
                if v >= 60:
                    return "一般"
                if v >= 50:
                    return "偏低"
                return "差"
            rename = {"維持分": "狀態延續力", "備戰分": "備戰完整度", "復刻分": "重現最佳狀態機會"}
            bits = [
                f"{rename[k]} {scores[k]:.0f}（{_score_word(scores[k])}）"
                for k in ("維持分", "備戰分", "復刻分") if k in scores
            ]
            score_line = "／".join(bits)
            weakest = min(scores, key=scores.get)
            if scores[weakest] < 55:
                score_line += f" — {rename[weakest]}偏低係主要扣分位"
            elif min(scores.values()) >= 70:
                score_line += " — 三項齊上70，備戰無短板"
            lines.append(score_line)

        # 5. 判讀 — 一句短結論（原因喺上面 pattern 行已講，唔重複）
        if pattern is None:
            verdict = "資料有限，作輔助參考"
        elif pattern["label"] == "操練好過近績":
            verdict = "操練好過近績，留意翻身可能"
        elif pattern["label"] in ("轉強", "操練積極"):
            verdict = f"{pattern['label']}，狀態有備戰支持"
        elif pattern["label"] in ("轉弱", "操練偏少"):
            verdict = f"{pattern['label']}，狀態延續存疑"
        elif pattern["label"] == "操練放緩":
            verdict = "操練放緩，以正式賽績為準"
        else:
            verdict = "中性，冇特別訊號"

        return {"lines": lines, "verdict": verdict}



    def _grade_computation_transparency(self, matrix_scores, ability_score, grade, feature_scores=None):
        """The ONE scoring-summary block: a 7D contribution table (score × weight
        = contribution), the weighted total + grade, reference scores that sit
        outside the 7D formula, and triggered risk flags. Weights are pulled live
        from the active weight set (debut vs standard) so the displayed 加權總分
        always matches the real ability_score."""
        is_debut = self._is_debut()
        active_weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS

        dims = [
            ("stability", "狀態與穩定性"),
            ("trainer_signal", "騎練訊號"),
            ("sectional", "段速表現"),
            ("race_shape", "檔位與走位"),
            ("horse_health", "馬匹健康 / 新鮮感"),
            ("form_line", "賽績線"),
            ("class_advantage", "級數優勢"),
        ]

        rows = []
        lines = []
        weighted_sum = 0.0

        for key, label in dims:
            weight = active_weights.get(key, 0.0)
            raw_score = float(matrix_scores.get(key, 60))
            band = score_band(raw_score)
            contribution = round(raw_score * weight, 2)
            weighted_sum += contribution
            rows.append({"key": key, "label": label, "score": round(raw_score, 2),
                         "weight": weight, "contribution": contribution, "band": band})
            if weight == 0.0:
                tag = "初出馬豁免" if is_debut else "0%（僅作參考）"
                lines.append(f"| {label} | {raw_score:.1f} | {tag} | — | {band} |")
            else:
                lines.append(f"| {label} | {raw_score:.1f} | {weight * 100:.1f}% | {contribution:.2f} | {band} |")

        table = "\n".join([
            "| 維度 | 得分 | 權重 | 貢獻 | 判定 |",
            "|:---|---:|---:|---:|:---:|",
            *lines,
        ])
        summary = (
            f"{table}\n\n"
            f"**→ 加權總分 = {weighted_sum:.2f} 分 → 評級 [{grade}]**"
        )

        grade_explanation = self._grade_threshold_explanation(ability_score, grade)
        if grade_explanation:
            summary += f"\n{grade_explanation}"

        # Reference scores that exist but do NOT enter the 7D weighted formula —
        # shown so nothing that was computed is hidden from the report.
        if feature_scores:
            ref_bits = []
            dist = feature_scores.get("distance_score")
            if isinstance(dist, (int, float)):
                ref_bits.append(f"路程分 {float(dist):.1f}")
            draw = feature_scores.get("draw_score")
            if isinstance(draw, (int, float)):
                ref_bits.append(f"檔位分 {float(draw):.1f}（經檔位走位情境入分）")
            if ref_bits:
                summary += "\n**📎 參考分（不直接入7D公式）：** " + "、".join(ref_bits)
            coverage_text = self._data_coverage_summary(feature_scores)
            if coverage_text:
                summary += f"\n**📋 {coverage_text}**"

        if self.risk_flags:
            flag_descriptions = []
            for flag in sorted(set(self.risk_flags)):
                desc = self._risk_phrase_for_flag(flag)
                if desc:
                    flag_descriptions.append(f"  - {desc}")
            if flag_descriptions:
                summary += "\n\n**⚠️ 已觸發風險標記:**\n" + "\n".join(flag_descriptions)

        return {
            "detail_lines": lines,
            "rows": rows,
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
            return f"**📊 評級定義：** {explanation}"
        return ""

    def _data_coverage_summary(self, feature_scores):
        confidence = float(feature_scores.get("confidence_score", 60))
        if confidence >= 80:
            return "資料覆蓋完整，判讀可信度較高。"
        if confidence >= 68:
            return "主要資料欄位算齊，判讀有一定依據。"
        if confidence >= 55:
            return "資料覆蓋尚可，但部分欄位以中性處理。"
        return "資料未算完整，判讀需保守理解。"
