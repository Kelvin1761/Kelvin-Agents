import re

with open('.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py', 'r') as f:
    code = f.read()

new_sectional_breakdown = """    def _sectional_breakdown(self):
        if self._sectional_breakdown_cache is not None:
            return self._sectional_breakdown_cache
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_float(latest_entry.get("placing")) if latest_entry else None
        recent_top4 = sum(1 for entry in entries[:3] if (parse_float(entry.get("placing")) or 99) <= 4)
        forgiveness_count = self._forgiveness_count()

        total_score = 40.0
        notes = ["基礎分 40 分"]

        # 1. Average PI (Max 25)
        pi_from_entries = []
        for entry in entries:
            pi_val = parse_float(entry.get("pi"))
            if pi_val is not None:
                pi_from_entries.append(pi_val)

        if not pi_from_entries:
            tw_trial = self.data.get("timing_trial_600m_avg_speed")
            if tw_trial and tw_trial > 0:
                trial_l600 = 600.0 / tw_trial
                if trial_l600 <= 33.5:
                    total_score += 40
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 極速補償 (+40)")
                elif trial_l600 <= 34.0:
                    total_score += 25
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 優秀補償 (+25)")
                elif trial_l600 <= 34.8:
                    total_score += 10
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 合格補償 (+10)")
                else:
                    notes.append(f"初出/無紀錄馬: 試閘 L600 ({trial_l600:.1f}s) 偏慢 (0)")
            else:
                notes.append("缺乏正式 L400 數據及試閘時間 (0)")
        else:
            recent_pi = sum(pi_from_entries[:2]) / len(pi_from_entries[:2]) if len(pi_from_entries) >= 1 else pi_from_entries[0]
            avg_pi = sum(pi_from_entries) / len(pi_from_entries)
            max_pi = max(pi_from_entries)

            if avg_pi >= 4.0:
                total_score += 25
                notes.append("平均 L400 PI 極佳 (+25)")
            elif avg_pi >= 2.0:
                total_score += 15
                notes.append("平均 L400 PI 優秀 (+15)")
            elif avg_pi >= 0.0:
                total_score += 5
                notes.append("平均 L400 PI 達標 (+5)")
            else:
                notes.append("平均 L400 PI 為負，缺乏後勁 (0)")

            # 2. Distance-Adjusted L600 Peak (Max 15)
            tw_best = self.data.get("timing_600m_best_speed")
            if tw_best and tw_best > 0:
                best_l600 = 600.0 / tw_best
                race_dist = self._distance_from_text(self.race_context.get("distance", ""))
                if race_dist and race_dist >= 600:
                    std_l600 = _lookup_standard_l600(self._current_venue_name(), race_dist)
                    if std_l600 and std_l600 > 0:
                        delta = best_l600 - std_l600
                        if delta <= -0.6:
                            total_score += 15
                            notes.append(f"最佳 L600 ({best_l600:.2f}s vs 標準 {std_l600:.2f}s) 突破路程極限 (+15)")
                        elif delta <= -0.3:
                            total_score += 5
                            notes.append(f"最佳 L600 ({best_l600:.2f}s) 達該路程優秀級別 (+5)")
                        else:
                            notes.append(f"最佳 L600 ({best_l600:.2f}s) 未見路程極速優勢 (0)")

            # 3. Trend & Peak PI (Max 10)
            if max_pi >= 6.0:
                total_score += 5
                notes.append("生涯曾交出頂峰級別 PI 爆發 (+5)")
            if recent_pi > avg_pi + 2.0:
                total_score += 5
                notes.append("近期 PI 呈現強烈上升軌 (+5)")
            elif recent_pi < avg_pi - 3.0:
                total_score = max(0, total_score - 10)
                notes.append("近期 PI 嚴重退步 (-10)")

            # 4. Realization & Forgiveness (Max 10)
            if avg_pi > 0 and recent_top4 > 0:
                total_score += 10
                notes.append("高 PI 成功兌現為前列成績 (+10)")
            elif avg_pi > 2.0 and forgiveness_count >= 1:
                total_score += 5
                notes.append("高 PI 未兌現但有受阻/寬恕背景 (+5)")

        total_score = min(100.0, max(0.0, total_score))
        
        self._sectional_breakdown_cache = {
            "score": total_score,
            "notes": "；".join(notes) if notes else "-",
            "label": "Base 40 + PI/L600 累加"
        }
        return self._sectional_breakdown_cache"""

pattern1 = r'    def _sectional_breakdown\(self\):.*?(?=\n    def _sectional_score\(self\):)'
code = re.sub(pattern1, new_sectional_breakdown, code, flags=re.DOTALL)

with open('.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py', 'w') as f:
    f.write(code)

print("Update complete")
