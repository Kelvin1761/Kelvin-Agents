import re

with open('.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py', 'r') as f:
    code = f.read()

# 1. Update _matrix_reasoning
matrix_reasoning_old = """            "stability": self._reason_bundle(
                "stability",
                matrix_scores["stability"],
                feature_scores,
                feature_notes,
                "form_score",
                "consistency_score",
                "health_score",
            ),"""

matrix_reasoning_new = """            "stability": self._reason_bundle(
                "stability",
                matrix_scores["stability"],
                feature_scores,
                feature_notes,
                "form_score",
                "consistency_score",
            ),"""

code = code.replace(matrix_reasoning_old, matrix_reasoning_new)

# 2. Add _get_class_tier and replace _form_score
form_score_old_pattern = r'    def _form_score\(self\):.*?(?=\n    def _distance_score\(self\):)'

new_form_and_class_logic = """    def _get_class_tier(self, text):
        text = str(text).lower()
        if "group 1" in text or "g1" in text: return 1
        if "group 2" in text or "g2" in text or "group 3" in text or "g3" in text: return 2
        if "listed" in text or "lr" in text or "open" in text: return 3
        bm_match = re.search(r"bm\s*(\d+)", text)
        if bm_match:
            rating = int(bm_match.group(1))
            if rating >= 88: return 4
            if rating >= 72: return 5
            if rating >= 64: return 6
            return 7
        if "class 6" in text or "class 5" in text: return 5
        if "class 4" in text or "class 3" in text: return 6
        if "class 2" in text or "class 1" in text: return 7
        if "maiden" in text: return 8
        return 7

    def _form_score(self):
        starts = self._career_starts()
        if starts == 0:
            self.reason_codes.append("debut_form_neutral")
            return 58, "初出馬無正式賽績，近績分按保守 58 分處理。", "career_tag"
            
        entries = self._official_entries()
        if not entries:
            return 58, "缺乏正式賽績，近績分按 58 分處理。", "career_tag"

        today_class = self.race_context.get("race_class", "")
        today_tier = self._get_class_tier(today_class)
        
        total_weighted_score = 0.0
        total_applied_weights = 0.0
        notes = []
        
        for i, entry in enumerate(entries[:4]):
            place = parse_float(entry.get("placing"))
            if place is None:
                continue
                
            if place == 1: base_pts = 10
            elif place == 2: base_pts = 6
            elif place == 3: base_pts = 4
            elif place == 4: base_pts = 2
            elif place == 5: base_pts = 1
            else: base_pts = 0
            
            if i == 0: decay = 1.0
            elif i == 1: decay = 0.8
            elif i == 2: decay = 0.6
            else: decay = 0.4
            
            entry_tier = self._get_class_tier(entry.get("class", ""))
            delta = today_tier - entry_tier
            
            if delta >= 2: class_mult = 1.5
            elif delta == 1: class_mult = 1.2
            elif delta == 0: class_mult = 1.0
            elif delta == -1: class_mult = 0.7
            else: class_mult = 0.4
            
            race_score = base_pts * class_mult * decay
            total_weighted_score += race_score
            total_applied_weights += decay
            
            if place <= 5:
                if class_mult > 1.0:
                    notes.append(f"近仗曾於較強班次入前五(降班優勢 x{class_mult})")
                elif class_mult < 1.0:
                    notes.append(f"近仗曾於較弱班次入前五(升班折扣 x{class_mult})")
        
        if total_applied_weights > 0:
            avg_score = total_weighted_score / total_applied_weights
            normalized_score = 50 + (avg_score / 15.0) * 50
        else:
            normalized_score = 50
            
        score = min(100, max(0, normalized_score))
        
        if self._is_maiden_race():
            trial_count = int(parse_float(self.data.get("trial_count")) or 0)
            trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or 0)
            if trial_count >= 4 and trial_top3 >= 3:
                score += 5
                self.reason_codes.append("maiden_trial_form_proxy")
                notes.append("試閘成績優異作賽績參考")
            elif trial_count >= 3 and trial_top3 >= 2:
                score += 3
        
        note_str = "；".join(list(dict.fromkeys(notes))) if notes else "近績一般"
        return score, f"採用班次及時間加權平均計算法，{note_str}。近績分 {clip_score(score):.1f}。", "recent_form+class_weighted"
"""

code = re.sub(form_score_old_pattern, new_form_and_class_logic, code, flags=re.DOTALL)

# 3. Replace _consistency_score
consistency_score_old_pattern = r'    def _consistency_score\(self\):.*?(?=\n    def _health_score\(self\):)'

new_consistency_score_logic = """    def _consistency_score(self):
        starts = self._career_starts()
        if starts == 0:
            return 58, "初出馬以備戰完整度代替穩定樣本，跑法穩定性 58 分。", "career_tag"
            
        score = 58
        notes = []
        
        run_styles = [entry.get("run_style", "") for entry in self._official_entries()[:4] if entry.get("run_style") and entry.get("run_style") != "-"]
        if run_styles and len(set(run_styles)) == 1:
            score += 3
            notes.append("近期跑法極度連貫一致")
            
        if "穩定" in self._sectional_trends().get("pi_trend", ""):
            score += 2
            notes.append("段速及走勢維持穩定")
            
        recent = parse_recent_finishes(self.data.get("recent_form"))
        if recent:
            poor = sum(1 for x in recent[:4] if x >= 8)
            if poor >= 2 and self._forgiveness_count() >= 2:
                score += 4
                notes.append("大敗場次多具寬恕理由")
                
        repeatability = self._repeatability_brief()
        if "重覆前列交代" in repeatability or "直接對位" in repeatability:
            score += 2
            notes.append("派彩/對位具重複性")
        elif "未形成穩定交代" in repeatability:
            score -= 1
            notes.append("未見穩定交代")
            
        note_str = "；".join(notes) if notes else "未見特別跑法或表現穩定特徵"
        return score, f"{note_str}。跑法穩定性 {clip_score(score):.1f} 分。", "run_style+sectional_trend+forgiveness+repeatability"
"""

code = re.sub(consistency_score_old_pattern, new_consistency_score_logic, code, flags=re.DOTALL)

# 4. Remove _health_score
health_score_old_pattern = r'    def _health_score\(self\):.*?(?=\n    def _confidence_score\(self\):)'
code = re.sub(health_score_old_pattern, "", code, flags=re.DOTALL)

with open('.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py', 'w') as f:
    f.write(code)

print("Engine refactoring completed successfully.")
