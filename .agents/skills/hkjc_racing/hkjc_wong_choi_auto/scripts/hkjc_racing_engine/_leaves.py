"""Leaf scores: every 0–100 sub-score that feeds a 9D dimension, plus the
jockey/trainer context adjustments and the composite (`_ability_score`).
"""
import re

from . import scoring
from .rail_draw_context import rail_draw_context_adjustment
from .scoring import (CENTRED_MATRIX_WEIGHTS, DEBUT_MATRIX_WEIGHTS, MATRIX_WEIGHTS, clip_score, parse_float)



_CONSUMPTION_VALUE = re.compile(r"消耗=([^,，|\s]+)")


def _consumption_label(part, mapping):
    """`消耗=中低消耗` → "中低"（mapping key）；冇標籤／未知 → None.

    以前用 `label in part` 長標籤優先：「低消耗」比「中低」長，所以 1,169 個
    「中低消耗」全部當咗「低消耗」（70 而唔係 66）。而家只睇「消耗=」後面個值，
    用前綴對，長優先（「極高」先過「高」）。EXP-20261018-05，§7。
    """
    match = _CONSUMPTION_VALUE.search(str(part or ""))
    if not match:
        return None
    value = match.group(1)
    for label in sorted(mapping, key=len, reverse=True):
        if value == label or value.startswith(label):
            return label
    return None


def _calc_line(base, items, final):
    """「60 ＋ 有香港出賽紀錄 +4 − 樣本薄 2 ＝ 62」—— 報告用嘅計法字串（純顯示）。"""
    parts = [f"{base:g}"]
    for label, delta in items:
        if delta:
            parts.append(f"{'＋' if delta > 0 else '−'} {label} {abs(delta):g}")
    return " ".join(parts) + f" ＝ {final:.1f}"


class LeafScores:
    def _set_calc(self, key, text):
        """逐個分項嘅計法字串（純顯示，報告「計法」行），唔影響分數。"""
        if text:
            self.__dict__.setdefault("leaf_calc", {})[key] = text

    def _class_score(self, _features):
        if self._is_debut():
            self.reason_codes.append("debut_class_unknown")
            return 60, "初出馬未有正式賽績，經驗與季內分暫按中性60分。", "career_tag"
        score = 60
        notes = []
        items = []
        starts = parse_float(self._value("career_race_starts") or self.horse_data.get("career_race_starts"))
        season = self._season_record()
        career_tag = self._clean(self._value("career_tag") or self.horse_data.get("career_tag") or "")
        if career_tag == "ESTABLISHED":
            score += scoring.CLASS_MICRO_WEIGHTS.get("established_bonus", 4.0)
            notes.append("有香港出賽紀錄")
            items.append(("有香港出賽紀錄", scoring.CLASS_MICRO_WEIGHTS.get("established_bonus", 4.0)))
        if starts is not None:
            if starts >= 20:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_20_bonus", 4.0)
                notes.append("經驗充足")
                items.append((f"出賽 {starts:.0f} 次（≥20）", scoring.CLASS_MICRO_WEIGHTS.get("starts_20_bonus", 4.0)))
            elif starts <= 8:
                score += scoring.CLASS_MICRO_WEIGHTS.get("starts_8_pen", -2.0)
                notes.append("樣本薄")
                items.append((f"出賽 {starts:.0f} 次（≤8）", scoring.CLASS_MICRO_WEIGHTS.get("starts_8_pen", -2.0)))
        # A new season's 0-0-0-0 is no evidence, not an unsuccessful campaign.
        if season and season["starts"] > 0:
            if season["places"] >= 3:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_3_bonus", 4.0)
                notes.append("季內有交代")
                items.append((f"季內上名 {season['places']} 次（≥3）", scoring.CLASS_MICRO_WEIGHTS.get("season_place_3_bonus", 4.0)))
            elif season["places"] == 0:
                score += scoring.CLASS_MICRO_WEIGHTS.get("season_place_0_pen", -4.0)
                items.append((f"季內 {season['starts']} 戰未上名", scoring.CLASS_MICRO_WEIGHTS.get("season_place_0_pen", -4.0)))
                self.risk_flags.append("class_edge_unproven")
                notes.append("季內未上名")
        # 短而準：分數行頭，訊號做 tag；無訊號＝各項中性
        self._set_calc("class_score", _calc_line(60, items, clip_score(score)))
        note = f"經驗與季內分{clip_score(score):.0f}：" + ("、".join(notes) if notes else "經驗／季內均中性")
        return clip_score(score), note, "career_context"

    def _distance_suitability_adjustment(self, features, matrix_scores):
        """Keep V1 live and calculate surface-specific V2 as a shadow.

        New Logic carries a PIT within-horse residual: target-distance form
        minus the same horse's all-distance form on the same surface.  Older
        Logic has no V2 payload and therefore exposes no shadow.  The official
        adjustment remains the exact V1 migration, preserving reproducibility
        while new meetings collect genuinely unseen V2 outcomes.
        """
        neutral = {
            "raw_adjustment": 0.0,
            "signal": "neutral",
            "same_distance_starts": 0,
            "same_distance_places": 0,
            "note": "同程未有可入分實績，路程適性調整為0。",
        }
        if self._is_debut():
            neutral["signal"] = "debut_neutral"
            neutral["note"] = "初出馬未有同程正式賽績，路程適性調整為0。"
            return neutral

        v2 = self._distance_suitability_v2_component()
        v2_shadow = None
        if v2["available"]:
            profile = scoring.DISTANCE_SUITABILITY_V2_PROFILES[v2["surface"]]
            weight = float(profile["weight"])
            cap = float(profile["cap"])
            component = 60.0 + max(-cap, min(cap, float(v2["score"]) - 60.0))
            base_raw = float(self._ability_score(matrix_scores))
            candidate_raw = (1.0 - weight) * base_raw + weight * component
            adjustment = round(candidate_raw - base_raw, 6)
            v2_shadow = {
                "candidate_raw_adjustment": adjustment,
                "status": "prospective_shadow_pending_primary_gate",
                "score": round(float(v2["score"]), 2),
                "surface": v2["surface"],
                "source": v2["source"],
                "target_effective_n": v2["target_effective_n"],
                "surface_effective_n": v2["surface_effective_n"],
                "profile": dict(profile),
                "component_score": round(component, 2),
            }

        # V1 remains official until the prospective V2 primary gate passes.
        record = self._same_distance_record()
        if not record or record["starts"] <= 0:
            if v2_shadow is not None:
                neutral["v2_shadow"] = v2_shadow
            return neutral
        placed = record["places"] > 0
        signal = "same_distance_placed" if placed else "same_distance_unplaced"
        note = ("同程有上名實績，獨立路程適性調整為正面。" if placed
                else "同程已有樣本但未上名，獨立路程適性調整為負面。")
        raw_adjustment = scoring.DISTANCE_SUITABILITY_RAW[signal]
        output = {
            "raw_adjustment": raw_adjustment,
            "signal": signal,
            "same_distance_starts": int(record["starts"]),
            "same_distance_places": int(record["places"]),
            "note": note,
        }
        if v2_shadow is not None:
            output["v2_shadow"] = v2_shadow
        return output

    def _distance_score(self, _features):
        best_distance = self._value("best_distance")
        distance = str(self.race_context.get("distance") or "")
        # 同程往績一定要由「同程 (…)」讀。舊 code 用 parse_record(text) 掃第一個
        # 四元組，而 season_stats 個字串係「季內 (…) | 同程 (…) | 同場同程 (…)」
        # ——第一個係**季內**，所以路程分一路用緊季內成績做同程證據。09-06 全場
        # 季內 (0-0-0-0)（新季），六匹馬全部跌落「樣本有限 66 分」。
        record = self._same_distance_record()
        best_text = self._clean(best_distance or "")
        distance_token = distance.replace("m", "").strip()
        direct_match = best_text.startswith(f"{distance_token}m") or best_text.startswith(distance)
        # `season_stats` is now rebuilt from complete point-in-time history.
        # It must outrank the legacy `best_distance` sentence, which can still
        # say "未跑過" when the older six-run summary omitted earlier starts.
        if record and record["starts"] > 0:
            if record["places"] > 0:
                return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_place_base", 72.0), \
                    "完整歷史顯示同程已有上名紀錄，路程適性評為72分。", "season_stats"
            self.risk_flags.append("distance_record_weak")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("same_dist_unplaced_base", 54.0), \
                "完整歷史顯示同程有樣本但未見上名支持，路程分54分。", "season_stats"
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
                return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_place_base", 72.0), "路程資料見今仗距離及上名紀錄，路程適性評為72分。", "best_distance"
            return scoring.DISTANCE_MICRO_WEIGHTS.get("direct_match_small_sample_base", 66.0), "最佳路程欄與今仗距離吻合，但樣本有限，路程分66分。", "best_distance"
        if self._is_debut():
            self.reason_codes.append("debut_distance_unproven")
            return scoring.DISTANCE_MICRO_WEIGHTS.get("debut_base", 58.0), "初出馬未經今仗路程實戰驗證，路程分保守58分。", "career_tag"
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
            "policy_neutral"

    def _weight_score(self, _features):
        # 負磅分只計讓磅官嘅負磅（EXP-20261010-04）。馬匹體重趨勢係健康訊號，已經喺
        # risk_score 計，所以唔再重複計。
        # 負磅分讀嘅係讓磅官嘅意見，所以用**宣佈負磅**（排位表負磅，未扣見習減磅）。
        # 見習減磅係騎師嘅減磅，唔係讓磅官對匹馬嘅評價（EXP-20261029-30，§7：
        # Gold +0.29pp、Good +0.58pp，冇一個分層負）。Logic `weight` 係實際負磅
        # （已扣減磅，EXP-20261018-06），冇 `declared_weight` 時用「實際＋減磅」還原。
        # EXP-20261111-10：直接讀官方評分距全場最高評分幾多分，唔再由負磅推返評分。
        # 讓磅賽入面兩者幾乎一樣；分別喺頂磅 135 唔係 133、同埋冇馬負到 132 嘅場次。
        gap = parse_float(self._value("rating_gap"))
        if gap is not None:
            self._set_calc("weight_score", f"官方評分距全場最高 {gap:.0f} 分：≤{scoring.WEIGHT_RATING_GAP_HEAVY:g} 分 → 70；"
                                           f"≥{scoring.WEIGHT_RATING_GAP_LIGHT:g} 分 → 54；其餘 64")
            rating = self._value("current_rating")
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("base", 64.0)
            note = (f"官方評分{rating}，距全場最高{gap:.0f}分，屬中游，讓磅官冇特別意見，"
                    f"官方評分分{score:.0f}分。")
            if gap >= scoring.WEIGHT_RATING_GAP_LIGHT:
                score = scoring.WEIGHT_MICRO_WEIGHTS.get("light_weight_base", 54.0)
                note = (f"官方評分{rating}，距全場最高{gap:.0f}分 —— 讓磅官睇低佢（輕磅），"
                        f"官方評分分{score:.0f}分。")
            elif gap <= scoring.WEIGHT_RATING_GAP_HEAVY:
                score = scoring.WEIGHT_MICRO_WEIGHTS.get("heavy_weight_base", 70.0)
                note = (f"官方評分{rating}，全場最高或只差{gap:.0f}分 —— 讓磅官視佢為全場最好嘅馬，"
                        f"而實測讓磅官每 1 分評分只加約 0.39 kg 負磅（慣例 0.5 kg），官方評分分{score:.0f}分。")
            return clip_score(score), note, "rating_gap"
        weight = parse_float(self._value("weight_carried") or self._value("weight"))
        if weight is None:
            return 60, "評分同負磅資料都不足，官方評分分60分。", "missing_neutral"
        allowance = parse_float(self._value("jockey_allowance")) or 0.0
        declared = parse_float(self._value("declared_weight"))
        carried = declared if declared is not None else weight + allowance
        claim = f"（見習減磅 {allowance:.0f}，實際負磅 {carried - allowance:.0f}）" if allowance else ""
        score = scoring.WEIGHT_MICRO_WEIGHTS.get("base", 64.0)
        note = f"今仗宣佈負磅{carried:.0f}磅{claim}，屬中游負磅，讓磅官冇特別意見，官方評分分{score:.0f}分。"
        if carried <= scoring.WEIGHT_DECLARED_LIGHT:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("light_weight_base", 54.0)
            note = (f"今仗宣佈負磅{carried:.0f}磅{claim}較輕 —— 負磅係讓磅官嘅評分，輕磅即係"
                    f"官方評分低，官方評分分{score:.0f}分。")
        elif carried >= scoring.WEIGHT_DECLARED_HEAVY:
            score = scoring.WEIGHT_MICRO_WEIGHTS.get("heavy_weight_base", 70.0)
            note = (f"今仗宣佈負磅{carried:.0f}磅{claim}屬頂磅 —— 讓磅官視佢為全場最好嘅馬，"
                    f"而實測讓磅官每 1 分評分只加約 0.39 kg 負磅（慣例 0.5 kg），"
                    f"官方評分分{score:.0f}分。")
        return clip_score(score), note, "weight_carried"

    def _consistency_score(self, features):
        form = str(self.horse_data.get("last_6_finishes") or "")
        finishes = [int(item) for item in re.findall(r"\b\d+\b", form)[:6]]
        if self._is_debut():
            prep = self._prep_score()
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_base", 58.0) + (prep - 60) * scoring.CONSISTENCY_MICRO_WEIGHTS.get("debut_prep_mult", 0.35)
            note = f"初出馬以晨操備戰穩定性代替正式近績，備戰分{prep:.0f}，上名／大敗紀錄分{score:.1f}。"
            return score, note, "trackwork_digest"
        if len(finishes) >= 3:
            places = sum(1 for rank in finishes if 1 <= rank <= 3)
            poor = sum(1 for rank in finishes if rank >= 8)
            score = scoring.CONSISTENCY_MICRO_WEIGHTS.get("base", 58.0) + places * scoring.CONSISTENCY_MICRO_WEIGHTS.get("place_mult", 7.0) - poor * scoring.CONSISTENCY_MICRO_WEIGHTS.get("poor_mult", 5.0)
            note = f"近{len(finishes)}仗有{places}次前三、{poor}次八名或以後，上名／大敗紀錄分{clip_score(score):.1f}。"
            self._set_calc("consistency_score", f"58 ＋ 7 × 前三 {places} 次 − 5 × 八名或以後 {poor} 次 ＝ {clip_score(score):.1f}")
            return score, note, "last_6_finishes"
        if features.get("form_score", 60) >= 70:
            return scoring.CONSISTENCY_MICRO_WEIGHTS.get("good_form_base", 66.0), "近績樣本少但名次訊號正面，上名／大敗紀錄分66分。", "last_6_finishes"
        return scoring.CONSISTENCY_MICRO_WEIGHTS.get("neutral_base", 60.0), "近績樣本不足，上名／大敗紀錄分60分。", "missing_neutral"

    def _risk_score(self, features):
        """馬匹健康 leaf（`risk_score`）＝醫療＋休賽日數＋體重（`_candidate_health_risk_score`）。

        以前呢度先計一個「風險篩查分」（醫療／初出／檔位壓力／路程未證），寫入
        `risk_score`，之後 `_apply_mainline_context` 一定用健康分覆蓋 —— 篩查分由來冇入過
        任何維度（2026-10-19 公式審查）。而家直接回傳健康分；篩查只留低 risk_flags、
        說明文字，同埋 `confidence_score` 嘅「篩查分 < 55」扣分。輸出 bit-identical。
        """
        screen_score, screen_note = self._risk_screen(features)
        self._risk_screen_score = screen_score
        health_score, health_note = self._candidate_health_risk_score()
        # 說明只講真正入分嘅嘢（2026-11-05）。舊版前面接住篩查說明（「檔位分偏低、
        # 同程紀錄未見上名」），但篩查分由來冇入風險分，令人以為檔位同同程會扣健康分。
        note = f"{self._risk_medical_note()}；{health_note}重算健康分{clip_score(health_score):.1f}。"
        return clip_score(health_score), note, "th01_health_context"

    def _risk_medical_note(self):
        """風險分醫療部分嘅來源：賽事短評關鍵字（入分）＋賽會傷患記錄（未入分）。"""
        medical = self._text("medical_flags")
        official = self._official_medical_records()
        if "無醫療事故" in medical and official and scoring.OFFICIAL_INJURY_SCORING == "off":
            return "賽事短評未見事故；⚠️ 賽會傷患記錄有紀錄（未入分，見健康解讀）"
        if "無醫療事故" in medical:
            return "賽事短評未見事故"
        if self._is_foreign_runner() and not medical:
            return "海外賽駒，本會醫療欄無記錄，按中性處理"
        if medical and medical != "N/A":
            return "賽事短評有醫療事故紀錄"
        return "醫療欄資料不足"

    def _risk_screen(self, features):
        """風險篩查：只產生 risk_flags、說明同 confidence 用嘅篩查分，唔入分。"""
        score = scoring.RISK_SCREEN_WEIGHTS.get("base", 68.0)
        notes = []
        medical = self._text("medical_flags")
        foreign = self._is_foreign_runner()
        if "無醫療事故" in medical:
            notes.append("醫療欄未見事故")
        elif foreign:
            # Visiting runner with no HKJC medical record — treat as neutral, not a risk.
            notes.append("海外賽駒，本會醫療欄無記錄，按中性處理")
        else:
            score += scoring.RISK_SCREEN_WEIGHTS.get("medical_unknown_pen", -8.0)
            self.risk_flags.append("medical_record_unknown")
            notes.append("醫療欄資料不足")
        if self._is_debut():
            score += scoring.RISK_SCREEN_WEIGHTS.get("debut_pen", -5.0)
            self.risk_flags.append("debut_race_experience_unknown")
            notes.append("初出缺正式賽經驗")
        if features.get("draw_score", 60) < 55:
            score += scoring.RISK_SCREEN_WEIGHTS.get("draw_pressure_pen", -5.0)
            self.risk_flags.append("draw_pressure")
            notes.append("檔位分偏低")
        if features.get("distance_score", 60) < 58:
            score += scoring.RISK_SCREEN_WEIGHTS.get("distance_unproven_pen", -4.0)
            record = self._same_distance_record()
            if record and record["starts"] > 0:
                if "distance_record_weak" not in self.risk_flags:
                    self.risk_flags.append("distance_record_weak")
                notes.append("同程紀錄未見上名")
            else:
                self.risk_flags.append("distance_unproven")
                notes.append("路程證明不足")
        return clip_score(score), "、".join(notes) + f"，健康分{clip_score(score):.1f}。"

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
        if getattr(self, "_risk_screen_score", 60.0) < 55:
            pen = scoring.CONFIDENCE_MICRO_WEIGHTS.get("high_risk_pen", -5.0)
            score += pen
            bits.append(f"健康分偏低再扣（{pen:.0f}）")
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
        label_cn = {"elite": "極強", "strong": "強", "weak": "弱", "neutral": "中", "unknown": "未有資料"}[signal]
        calc_items = [(f"對手之後跑過高過今仗班次（有贏馬）{higher_count} 匹（每匹 3 分）", higher_count * 3),
                      (f"同班再贏 {same_count} 匹（每匹 1 分）", same_count), (f"低班再贏 {lower_count} 匹（每匹 1 分）", -lower_count)]
        calc_text = _calc_line(score, calc_items, clip_score(score + bonus)).replace(f"{score:g}", f"賽績線「{label_cn}」{score:g}", 1)
        if bonus == 8 and higher_count * 3 + same_count - lower_count > 8:
            calc_text += "（加分上限 +8）"
        self._set_calc("formline_strength_score", calc_text)
        if higher_count:
            note_map[signal] += f" 對手之後有{higher_count}匹跑過高過今仗嘅班次（有贏馬），含金量可再上調。"
        elif same_count and not lower_count:
            note_map[signal] += f" 對手後續有{same_count}匹於同班再贏，證明基本線索有兌現。"
        elif lower_count and not higher_count:
            note_map[signal] += " 對手後續主要在較低班再贏，提升幅度只宜保守。"
        final = clip_score(score + bonus)
        # 「碰過強敵」要今馬自己跑得埋堆先算數：若所有賽績線往績都冇跑近過
        # （≤6名兼落後≤5個馬位＝competitive ratio 0，例：次次被拋離十幾個馬位），
        # 則封頂 60——面對強陣但每次大敗，唔應照當高含金量。
        # pit 驗證（FL2_zero_cap）：good +0.7、champ +0.6、TEST 零變、零回退。
        fl = self._formline_summary()
        if fl and fl.get("opponents") and final > 60:
            ops = fl["opponents"]
            if not any(o["competitive"] for o in ops):
                final = 60.0
                note_map[signal] = "曾碰強陣但今馬每仗都跑唔近（大敗收場），賽績線含金量存疑，按中性60分。"
                self._set_calc("formline_strength_score", calc_text + " → 但每仗都跑唔近（≤6名兼輸≤5個馬位一次都冇），封頂 60")
        return final, note_map[signal], "formline_strength"

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
        if scoring.TRACKWORK_SCORING != "on":
            return 60.0, "晨操退出排名（EXP-20261029-02），只作顯示參考", "trackwork_digest"
        trackwork = self._trackwork_markers()
        classification = trackwork["classification"]
        trend = trackwork["trend"]

        # 「加強／放緩」係抽取層用第一課同最後一課快操嘅完成時間比出嚟（extract_trackwork.classify_trend）。
        # 快操路程唔一（完成時間 26–85 秒），首尾相差 >4 秒嗰 38% 其實係比緊唔同路程，
        # 但全部都被標咗加強／放緩（EXP-20261018-11，§7）。呢類唔計趨勢。
        raw = self.horse_data.get("trackwork")
        raw_summary = raw.get("summary") if isinstance(raw, dict) else {}
        times = raw_summary.get("gallop_times") if isinstance(raw_summary, dict) else None
        if (("加強" in trend or "放緩" in trend) and isinstance(times, list) and len(times) >= 2
                and all(isinstance(t, (int, float)) for t in (times[0], times[-1]))
                and abs(float(times[-1]) - float(times[0])) > 4.0):
            trend = "操練趨勢未明（首尾快操唔同路程，唔比較）"

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

        # 四個計數都 ≥ 0，所以活躍度只有 0 → 上限；以前嘅 −4 下限同「操練量偏少」
        # 句子永遠觸發唔到（2026-10-19 公式審查剷走）。
        cap = scoring.TRACKWORK_MICRO_WEIGHTS.get("activity_cap", 8.0)
        activity_bonus = min(activity_bonus, cap)

        final_score = scoring.clip_score(base_score + activity_bonus)
        if activity_bonus > 2.0:
            note += f"；操練量充足（活躍度+{activity_bonus:.1f}）"

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
        is_sha_tin = self._is_sha_tin_context()
        if is_sha_tin:
            w = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
            score = clip_score(draw * w["sha_tin_draw"] + fit_score * w["sha_tin_draw_position_fit"] + trip_score * w["sha_tin_trip_consumption"])
            combine = "沙田加權 檔位55%＋走位匹配25%＋近仗消耗20%"
        else:
            delta, _items = self._race_shape_context_delta()
            score = clip_score(draw + delta)
            combine = f"跑馬地以檔位為主，走位情境微調 {delta:+.0f}"
        surface = None
        live_profile = "sha_tin_legacy" if is_sha_tin else "legacy_v2"
        # 跑馬地非初出馬：檔位＋個別谷草性能（EXP-20260929-01，2026-10-27 review 確認保留）。
        # 跑馬地初出馬冇谷草往績，用上面嘅檔位＋走位情境微調。
        if self._is_happy_valley_context() and not self._is_debut():
            surface = self._surface_performance_shadow_component()
            gain = scoring.HAPPY_VALLEY_RACE_SHAPE_V3_SURFACE_GAIN
            score = clip_score(draw + gain * (float(surface["score"]) - 60.0))
            live_profile = "v3_surface"
            combine = "跑馬地實驗主線：檔位＋個別谷草性能；歷史匹配／近仗消耗不入分"
        # 顯示用：講清楚邊幾項真係入分、點樣加出 leaf 分（2026-11-05：報告列咗
        # 三個分但冇講點加，跑馬地真正入分嘅谷草性能反而冇印）。唔郁計分。
        if live_profile == "v3_surface":
            surface_score = float(surface["score"])
            formula = (f"檔位分 {draw:.1f} + {gain:.2f} × (谷草性能 {surface_score:.1f} − 60) "
                       f"= {score:.1f}")
            surface_why = (f"有效樣本 {float(surface.get('effective_n', 0) or 0):.1f} 仗"
                           if surface.get("available") else "冇可用紀錄，按中性 60")
            terms = [
                {"label": "檔位分", "score": draw, "scored": True, "why": ""},
                {"label": "個別谷草性能", "score": surface_score, "scored": True, "why": surface_why},
                {"label": "走位匹配分", "score": fit_score, "scored": False, "why": fit_why},
                {"label": "近仗消耗分", "score": trip_score, "scored": False, "why": trip_why},
            ]
        elif is_sha_tin:
            formula = (f"檔位分 {draw:.1f}×{w['sha_tin_draw']:.0%} + 走位匹配分 {fit_score:.1f}×"
                       f"{w['sha_tin_draw_position_fit']:.0%} + 近仗消耗分 {trip_score:.1f}×"
                       f"{w['sha_tin_trip_consumption']:.0%} = {score:.1f}")
            terms = [
                {"label": "檔位分", "score": draw, "scored": True, "why": ""},
                {"label": "走位匹配分", "score": fit_score, "scored": True, "why": fit_why},
                {"label": "近仗消耗分", "score": trip_score, "scored": True, "why": trip_why},
            ]
        else:
            formula = f"檔位分 {draw:.1f} + 走位情境微調 {delta:+.1f} = {score:.1f}"
            terms = [
                {"label": "檔位分", "score": draw, "scored": True, "why": ""},
                {"label": "走位匹配分", "score": fit_score, "scored": False, "why": fit_why},
                {"label": "近仗消耗分", "score": trip_score, "scored": False, "why": trip_why},
            ]
        self.race_shape_detail = {
            "formula": formula,
            "terms": [dict(t, score=round(float(t["score"]), 1)) for t in terms],
            "draw": round(draw, 1), "fit": round(fit_score, 1), "trip": round(trip_score, 1),
            "fit_why": fit_why, "trip_why": trip_why, "combine": combine, "rail": rail,
            "live_profile": live_profile,
            "surface_performance": surface,
            "field_tempo": "withheld_insufficient_reliability" if live_profile == "v3_surface" else None,
            "rail_draw_context": self._live_rail_draw_context(),
        }
        note = f"排{barrier}檔" + (f"（{rail}賽道）" if rail else "") + "，計法見下"
        return score, note, "race_shape_context"

    def _live_rail_draw_context(self):
        source = rail_draw_context_adjustment(
            self.race_context or {},
            self.horse_data.get("barrier") or self.horse_data.get("draw"),
        )
        if self._is_debut():
            source = dict(source)
            source["applied"] = False
            source["adjustment"] = 0.0
            source["reason"] = "debut_formula_locked"
        return source

    def _draw_position_fit_score(self):
        # `running_style` was a next-race positional forecast.  Recent HV
        # validation was only ~44-46% accurate, so it must not influence the
        # score.  Keep only observed historical lane/draw fit and position PI.
        text = self._text("draw_position_fit", "position_pi")
        weights = scoring.RACE_SHAPE_FIT_WEIGHTS
        score = weights["base"]
        details = []
        if "✅匹配" in text:
            score += weights["match_bonus"]
            details.append("檔位與歷史走位匹配")
        if "❌錯配" in text or "錯配!" in text:
            score += weights["mismatch_pen"]
            self.risk_flags.append("draw_position_mismatch")
            details.append("檔位與歷史走位有錯配")
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
        detail = "；".join(details) if details else "歷史檔位走位未見鮮明偏差"
        return clip_score(score), f"歷史匹配面：{detail}。"

    def _trip_consumption_score(self):
        text = self._clean(self._value("position_window") or "")
        mapping = scoring.RACE_SHAPE_TRIP_CONSUMPTION_SCORES
        scores = []
        labels = []
        for part in text.split("|")[:3]:
            label = _consumption_label(part, mapping)
            if label is not None:
                scores.append(mapping[label])
                labels.append(label)
        if not scores:
            return 60.0, "近仗消耗未有清晰標籤，按中性處理。"
        score = sum(scores) / len(scores)
        return clip_score(score), f"近{len(scores)}仗走位消耗以{'、'.join(labels)}為主。"

    def _race_shape_context_delta(self):
        # Do not use the low-accuracy next-race running-style forecast.  The
        # remaining inputs are all observations from completed prior races.
        text = self._text("draw_position_fit", "position_pi")
        weights = scoring.RACE_SHAPE_CONTEXT_DELTA_WEIGHTS
        delta = 0.0
        items = []  # 逐項 {factor, delta, why}
        def add(factor, d, why):
            nonlocal delta
            delta += d
            items.append({"factor": factor, "delta": round(d, 2), "why": why})
        if "✅匹配" in text:
            add("歷史走位匹配", weights["match_bonus"], "檔位與歷史走位匹配")
        if "❌錯配" in text or "錯配!" in text:
            self.risk_flags.append("draw_position_mismatch")
            add("歷史走位匹配", weights["mismatch_pen"], "檔位與歷史走位錯配")
        if "⚠️需主動切入" in text:
            self.risk_flags.append("needs_active_slotting")
            add("走位匹配", weights["active_slot_pen"], "需要主動切入")
        if "上升軌" in text:
            add("走位PI（追前位數）", weights["pi_up_bonus"], "近仗追前位數上升")
        elif "衰退中" in text:
            add("走位PI（追前位數）", weights["pi_down_pen"], "近仗追前位數下降")
        recent = _consumption_label(
            self._clean(self._value("position_window") or "").split("|")[0],
            scoring.RACE_SHAPE_TRIP_CONSUMPTION_SCORES,
        )
        if recent == "低消耗":
            add("近仗消耗", weights["recent_low_consumption_bonus"], "最近走位低消耗")
        elif recent == "極高":
            add("近仗消耗", weights["recent_extreme_consumption_pen"], "最近走位極高消耗")
        elif recent == "高":
            add("近仗消耗", weights["recent_high_consumption_pen"], "最近走位高消耗")
        context_weights = scoring.RACE_SHAPE_CONTEXT_WEIGHTS
        delta = max(context_weights["non_sha_tin_delta_floor"], min(context_weights["non_sha_tin_delta_cap"], delta))
        return delta, items

    def _ability_score(self, matrix_scores):
        if self._is_debut():
            base = sum(matrix_scores.get(key, 60.0) * weight for key, weight in DEBUT_MATRIX_WEIGHTS.items())
        else:
            base = sum(matrix_scores[key] * weight for key, weight in MATRIX_WEIGHTS.items())
        # Centred dimensions (同程表現) add weight × (score − 60); debut runners
        # have no same-distance record so their term is 0 by construction.
        return base + sum(
            weight * (float(matrix_scores.get(key, 60.0)) - 60.0)
            for key, weight in CENTRED_MATRIX_WEIGHTS.items()
        )

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

        shadow = self._consistency_from_runs()
        if shadow is not None:
            updated["consistency_score"] = clip_score(shadow["score"])
            self._set_calc("consistency_score", shadow["calc"])
            shift_txt = {"recovering": "，且近三仗名次好過再之前", "declining": "，但近三仗名次差過再之前"}.get(shadow["recent_shift"], "")
            notes["consistency_score"] = self._append_note(
                self._strip_embedded_score(feature_notes.get("consistency_score"), "上名／大敗紀錄分"),
                (
                    f"逐仗連輸距覆核：近{shadow['n']}仗有{shadow['close_runs']}仗跑近前列、"
                    f"{shadow['poor_runs']}仗明顯敗陣{shift_txt}，上名／大敗紀錄分定為{clip_score(shadow['score']):.1f}。"
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

        if self._is_jockey_changed() is True and not self._is_top_jockey_upgrade_exempt():
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



    def _candidate_health_risk_score(self):
        base = scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["base"]
        score = base
        items = []
        medical = self._text("medical_flags")
        weight_trend = self._text("weight_trend")
        days = self._days_since_last()
        weight_span = self._weight_trend_span(weight_trend)

        # 官方傷患記錄（EXP-20261020-02）：預設 "off" 唔入分；A/B arm 先開。
        mode = scoring.OFFICIAL_INJURY_SCORING
        official = bool(self._official_medical_records()) and "✅ 無醫療事故記錄" in medical
        if official and mode == "issue":
            medical = "官方傷患記錄"   # 當作醫療事故，行下面 −12（有康復證據 +6）
        if "✅ 無醫療事故記錄" in medical and official and mode == "no_clear":
            pass                      # 唔再俾「醫療清白」+2
        elif "✅ 無醫療事故記錄" in medical:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_clear_bonus"]; items.append(("醫療紀錄乾淨", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_clear_bonus"]))
        elif medical and medical != "N/A":
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_issue_pen"]; items.append(("有醫療事故紀錄", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_issue_pen"]))
            if self._has_recovery_evidence():
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_recovery_bonus"]; items.append(("有康復證據", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_recovery_bonus"]))
        else:
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_unknown_pen"]; items.append(("醫療資料不明", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["medical_unknown_pen"]))

        if days is not None:
            if days <= 7:
                if weight_span is not None and weight_span <= 14.0:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_stable_bonus"]; items.append((f"休 {days:.0f} 日（≤7，體重穩）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_stable_bonus"]))
                else:
                    score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_unstable_pen"]; items.append((f"休 {days:.0f} 日（≤7，體重唔穩）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_7_unstable_pen"]))
            elif days <= 21:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_21_bonus"]; items.append((f"休 {days:.0f} 日（8–21）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_21_bonus"]))
            elif days <= 45:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_45_bonus"]; items.append((f"休 {days:.0f} 日（22–45）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_le_45_bonus"]))
            elif days > 75:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_gt_75_pen"]; items.append((f"休 {days:.0f} 日（>75）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["days_gt_75_pen"]))

        if any(token in weight_trend for token in ("急劇變化", "急增", "急減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_sharp_change_pen"]; items.append(("體重急劇變化", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_sharp_change_pen"]))
        elif any(token in weight_trend for token in ("顯著轉輕", "大減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_drop_pen"]; items.append(("體重顯著轉輕", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_drop_pen"]))
        elif any(token in weight_trend for token in ("顯著轉重", "大增")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_gain_pen"]; items.append(("體重顯著轉重", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_gain_pen"]))
        elif any(token in weight_trend for token in ("微增", "微減")):
            score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]; items.append(("體重微增／微減", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["weight_micro_bonus"]))

        if weight_span is not None:
            if weight_span <= 12.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_12_bonus"]; items.append((f"體重波幅 {weight_span:.0f} 磅（≤12）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_12_bonus"]))
            elif weight_span <= 18.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_18_bonus"]; items.append((f"體重波幅 {weight_span:.0f} 磅（≤18）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_18_bonus"]))
            elif weight_span <= 32.0:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_32_pen"]; items.append((f"體重波幅 {weight_span:.0f} 磅（≤32）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_le_32_pen"]))
            else:
                score += scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_gt_32_pen"]; items.append((f"體重波幅 {weight_span:.0f} 磅（>32）", scoring.HORSE_HEALTH_CONTEXT_WEIGHTS["span_gt_32_pen"]))

        note = "已再綜合醫療紀錄、休賽日數同體重波幅，"
        self._set_calc("risk_score", _calc_line(base, items, clip_score(score)))
        return clip_score(score), note


    def _consistency_from_runs(self):
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

            if 1 <= rank <= 3:
                close_credit += weight
                close_runs += 1
                continue
            if 1 <= rank <= 5 and margin is not None and margin <= 3.0:
                close_credit += weight * 0.75
                close_runs += 1
            elif 1 <= rank <= 7 and margin is not None and margin <= 2.5:
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

        shift_pts = 3.0 if recent_shift == "recovering" else (-3.0 if recent_shift == "declining" else 0.0)
        calc = (f"58 ＋ 18 × 跑近前列比例 {close_ratio:.2f} − 14 × 明顯敗陣比例 {poor_ratio:.2f} − 10 × 大敗比例 {severe_ratio:.2f}"
                + (f" {'＋' if shift_pts > 0 else '−'} 近三仗{'好過' if shift_pts > 0 else '差過'}之前 3" if shift_pts else "")
                + f" ＝ {clip_score(score):.1f}（近仗權重 1.00／0.85／0.70／0.55／0.45／0.35；跑近前列＝前三，或前五輸≤3 個馬位、前七輸≤2.5 個馬位；"
                  "明顯敗陣＝八名後輸≥5 個馬位，或六名後輸≥7 個馬位；大敗＝十名後輸≥8 個馬位）")
        return {
            "score": clip_score(score),
            "calc": calc,
            "n": len(runs[:6]),
            "close_runs": close_runs,
            "poor_runs": poor_runs,
            "recent_shift": recent_shift,
        }

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

    def _is_top_jockey_upgrade_exempt(self):
        """EXP-20261027-13 arm B switch: no change penalty when moving to a top-6 jockey."""
        if not scoring.JOCKEY_CHANGE_SKIP_TOP_UPGRADE:
            return False
        from hkjc_racing_engine import overlays

        return bool(overlays.evaluate_overlays(self)["top_jockey_upgrade"]["value"])

    def _append_note(self, base_note, extra_note):
        base = str(base_note or "").strip()
        extra = str(extra_note or "").strip()
        if not base:
            return extra or "資料不足，中性60分。"
        if not extra:
            return base
        return base + " " + extra
