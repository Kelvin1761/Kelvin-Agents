import re
from pathlib import Path

engine_file = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py")
content = engine_file.read_text(encoding="utf-8")

# 1. We need to extract the logic of `_speed_rating_score` body.
speed_match = re.search(r"def _speed_rating_score\(self\):(.*?)(?:\n\s*def _micro_rank_bonus)", content, re.DOTALL)
if not speed_match:
    print("Could not find _speed_rating_score")
    exit(1)

speed_body = speed_match.group(1)

# We want to transform the variable names in speed_body:
# `score` -> `l600_score`, `notes` -> `l600_notes`
speed_body = speed_body.replace('return 60, "Sixth-Hundred 數據樣本不足，速評以中性 60 分處理。", "timing_data"', 'l600_notes.append("Sixth-Hundred 數據樣本不足，速評中性")')
speed_body = speed_body.replace("score =", "l600_score =")
speed_body = speed_body.replace("score +=", "l600_score +=")
speed_body = speed_body.replace("score -=", "l600_score -=")
speed_body = speed_body.replace("notes.append", "l600_notes.append")

# Remove the return statement at the end of speed_body
speed_body = re.sub(r"        return l600_score, f\".*?\", \"timing_data\"\n", "", speed_body)

# 2. Extract `formal_score` logic from `_sectional_breakdown`
formal_match = re.search(r"(        formal_score = 60.*?formal_score = clip_score\(formal_score\))", content, re.DOTALL)
formal_logic = formal_match.group(1) if formal_match else ""

# 3. Build the new `_sectional_breakdown`
new_breakdown = f"""    def _sectional_breakdown(self):
        if self._sectional_breakdown_cache is not None:
            return self._sectional_breakdown_cache
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {{}}
        latest_place = parse_float(latest_entry.get("placing")) if latest_entry else None
        latest_flags = self._entry_note_flags(latest_entry) if latest_entry else {{"positive": [], "negative": []}}
        recent_top3 = sum(1 for entry in entries[:3] if (parse_float(entry.get("placing")) or 99) <= 3)
        forgiveness_count = self._forgiveness_count()
        l400 = parse_float(self.horse_data.get("raw_l400") or self.data.get("raw_l400"))
        fast_sectionals = sum(1 for entry in entries[:4] if any(token in entry.get("sectional_quality", "") for token in ("極快", "較快")))
        
{formal_logic}

        # L600 Speed logic merged from _speed_rating_score
{speed_body}

        l600_score = clip_score(l600_score)

        weights = {{
            "formal_sectional": 0.50,
            "l600_speed": 0.50,
        }}
        final_score = clip_score(
            formal_score * weights["formal_sectional"]
            + l600_score * weights["l600_speed"]
        )
        self._sectional_breakdown_cache = {{
            "score": final_score,
            "weights": weights,
            "formal_sectional": {{"score": formal_score, "notes": formal_notes}},
            "l600_speed": {{"score": l600_score, "notes": l600_notes}},
        }}
        return self._sectional_breakdown_cache
"""

# Replace the old `_sectional_breakdown`
content = re.sub(r"    def _sectional_breakdown\(self\):.*?(?=    def _sectional_score\(self\):)", lambda m: new_breakdown, content, flags=re.DOTALL)

# 4. Modify `_sectional_score`
new_sectional_score = """    def _sectional_score(self):
        target_line = str(self.data.get("target_distance_line") or "")
        entries = self._official_entries()
        latest_entry = entries[0] if entries else {}
        latest_place = parse_float(latest_entry.get("placing")) if latest_entry else None
        latest_flags = self._entry_note_flags(latest_entry) if latest_entry else {"positive": [], "negative": []}
        race_bucket = self._race_class_bucket()
        wet_state = self._wet_state()
        recent_top3 = sum(1 for entry in entries[:3] if (parse_float(entry.get("placing")) or 99) <= 3)
        breakdown = self._sectional_breakdown()
        score = breakdown["score"]
        notes = []
        notes.append(
            "段速內部按 正式賽段速 50% / L600 實速表現 50% 匯總"
        )
        for key, label in (
            ("formal_sectional", "正式賽段速"),
            ("l600_speed", "L600 實速"),
        ):
            component = breakdown[key]
            if component["notes"]:
                notes.append(f"{label} {component['score']:.1f} 分（{' / '.join(component['notes'][:2])}）")
            else:
                notes.append(f"{label} {component['score']:.1f} 分")
        if entries and latest_flags["positive"] and latest_place is not None and latest_place <= 4:
            notes.append("上仗直路受阻/蝕位，裸名次未完全反映輸出")
        if "← 今仗 ❌" in target_line:
            notes.append("今仗路程本身仍要再驗證，段速投射唔可過份放大")
        if (
            race_bucket in {"bm58", "bm72"}
            and self._field_size_bucket() == "Field 9-12"
            and wet_state not in {"soft56", "soft7plus", "heavy"}
            and recent_top3 == 0
            and latest_place is not None
            and latest_place >= 5
        ):
            notes.append("中型好地場唔會單憑段速亮點就當成穩定入位本錢")

        return score, "；".join(notes) + f"。段速分 {clip_score(score):.1f}。" if notes else "段速實證有限，段速分中性處理。", "engine_line+sectional_trend+record_table+pf_metrics+formguide_notes"
"""
content = re.sub(r"    def _sectional_score\(self\):.*?(?=    def _pace_map_score\(self\):)", lambda m: new_sectional_score, content, flags=re.DOTALL)

# 5. Remove `_speed_rating_score`
content = re.sub(r"    def _speed_rating_score\(self\):.*?(?=    def _micro_rank_bonus\(self, matrix_scores, feature_scores\):)", "", content, flags=re.DOTALL)

# 6. Remove `speed_performance` from `_matrix_reasoning`
content = re.sub(r"            \"speed_performance\": self\._reason_bundle\([\s\S]*?\"sectional_score\",\n            \),\n", "", content)

# 7. Update weights in `_au_grade_computation_transparency`
content = content.replace('("sectional", "段速與引擎", "核心", 0.20)', '("sectional", "段速與引擎", "核心", 0.30)')
content = re.sub(r"            \(\"speed_performance\", \"實速表現\", \"核心\", 0\.10\),\n", "", content)

# 8. Update `_grade_components_list`
content = content.replace('("sectional", "段速與引擎", "核心"),', '("sectional", "段速與引擎", "核心"),')
content = re.sub(r"            \(\"speed_performance\", \"實速表現\", \"核心\"\),\n", "", content)

# Write back
engine_file.write_text(content, encoding="utf-8")
print("Refactoring applied successfully.")
