from engine_core import RacingEngine

class AuRacingEngine(RacingEngine):
    """
    AuRacingEngine inherits from the baseline RacingEngine (used by HKJC),
    but overrides specific rules (Speed Rating, Class, Track Condition)
    to calibrate them for Australian racing metrics.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # -------------------------------------------------------------------------
    # Overridden Methods for AU 
    # -------------------------------------------------------------------------
    
    def _formline_score(self):
        """
        Bypass HKJC formline penalties (which demand wins).
        """
        return 60, "AU賽績(無HKJC勝出要求)", "formline_au"
        
    def _consistency_score(self):
        """
        Bypass HKJC consistency penalties (which demand high top4%).
        """
        return 60, "AU穩定性(無HKJC扣分)", "consistency_au"

    def _track_score(self):
        """
        Phase 3: Track scoring using AU specific logic based on Prizemoney!
        Instead of 'Sha Tin' vs 'Happy Valley', we use prizemoney as a proxy for Venue Strength.
        """
        score = 60
        notes = []
        current_prize = float(self.race_context.get("prize") or 0)
        
        if current_prize > 0:
            entries = self._official_entries()
            highest_prize_placed = 0
            if entries:
                for e in entries:
                    pos = e.get("finish_pos")
                    prize = e.get("prizemoney", 0.0)
                    if pos and pos <= 3 and prize > highest_prize_placed:
                        highest_prize_placed = prize
            
            # If today is a Metro race (>$80k) and horse has never placed in a >$50k race
            if current_prize >= 80000:
                if highest_prize_placed == 0:
                    score -= 5
                    notes.append("缺乏賽績證明")
                elif highest_prize_placed < 50000:
                    score -= 4
                    notes.append(f"未曾於省級以上賽事入圍 (最高入圍 ${highest_prize_placed:,.0f})")
                elif highest_prize_placed < 80000:
                    score -= 2
                    notes.append(f"未曾於大都會賽事入圍 (最高入圍 ${highest_prize_placed:,.0f})")
                elif highest_prize_placed >= current_prize * 0.8:
                    score += 4
                    notes.append(f"具備同級賽道實力 (最高入圍 ${highest_prize_placed:,.0f})")
            else:
                # Provincial/Country race
                if highest_prize_placed >= current_prize * 1.5:
                    score += 4
                    notes.append(f"具備更高級別賽道實力 (最高入圍 ${highest_prize_placed:,.0f})")
                elif highest_prize_placed >= current_prize * 0.8:
                    score += 2
                    notes.append(f"具備同級賽道實力 (最高入圍 ${highest_prize_placed:,.0f})")
                    
        note_str = "；".join(notes) if notes else "賽道適應性相若"
        from engine_core import clip_score
        return clip_score(score), f"AU 賽道級別評估：{note_str}。", "track_au"

    def _speed_rating_score(self):
        """
        Phase 4: Relative speed scoring.
        Instead of absolute < 16.0s (which is HKJC), compare to the field's average.
        """
        score = 60
        notes = []
        tw_avg = self.data.get("timing_600m_avg_speed")
        tw_wet = self.data.get("timing_wet_avg_speed")
        
        # Get field averages
        field_avg = self.race_context.get("field_summary", {}).get("field_avg_tw")
        field_wet_avg = self.race_context.get("field_summary", {}).get("field_avg_tw_wet")
        
        going = str(self.race_context.get("going", "")).lower()
        is_wet = any(w in going for w in ("soft", "heavy", "黏", "爛", "軟"))
        
        if tw_avg and field_avg:
            diff = field_avg - float(tw_avg)
            if diff >= 0.5:
                score += 5
                notes.append(f"乾地段速大幅優於對手 (超 {diff:.1f}s)")
            elif diff >= 0.2:
                score += 2
                notes.append(f"乾地段速優於對手")
            elif diff <= -0.5:
                score -= 3
                notes.append(f"乾地段速遠遜對手")
                
        if is_wet and tw_wet and field_wet_avg:
            diff = field_wet_avg - float(tw_wet)
            if diff >= 0.5:
                score += 8  # Wet track premium
                notes.append(f"變化地段速特佳 (超 {diff:.1f}s)")
            elif diff >= 0.2:
                score += 4
                notes.append(f"具變化地段速優勢")
            elif diff <= -0.5:
                score -= 5
                notes.append(f"變化地段速遠遜對手")
        elif is_wet and not tw_wet:
            score -= 2
            notes.append("缺乏變化地證明")

        note_str = "；".join(notes) if notes else "段速表現與對手相若"
        from engine_core import clip_score
        return clip_score(score), f"AU 相對段速評估：{note_str}。", "sectional_au"

    def _class_weight_score(self):
        """
        Phase 3: Class transitions using AU specific logic based on Prizemoney!
        Prizemoney is the ultimate proxy for Race Class and Track Quality in AU Racing.
        """
        score = 60
        notes = []
        
        current_prize = float(self.race_context.get("prize") or 0)
        
        entries = self._official_entries()
        good_prizes = []
        
        if entries:
            # Look at recent good runs (Top 3 finishes)
            for e in entries:
                pos = e.get("finish_pos")
                prize = e.get("prizemoney", 0.0)
                if pos and pos <= 3 and prize > 0:
                    good_prizes.append(prize)
                    
            if good_prizes and current_prize > 0:
                avg_good_prize = sum(good_prizes[:3]) / min(3, len(good_prizes))
                ratio = avg_good_prize / current_prize
                
                if ratio >= 1.5:
                    score += 6
                    notes.append(f"大幅降班 (曾於 ${avg_good_prize:,.0f} 賽事入圍)")
                elif ratio >= 1.1:
                    score += 3
                    notes.append(f"降班作賽有利 (曾於 ${avg_good_prize:,.0f} 賽事入圍)")
                elif ratio <= 0.5:
                    score -= 4
                    notes.append(f"大幅升班挑戰 (最高入圍 ${avg_good_prize:,.0f})")
                elif ratio <= 0.8:
                    score -= 2
                    notes.append(f"升班作賽難度增加 (最高入圍 ${avg_good_prize:,.0f})")
                else:
                    notes.append(f"班次相若 (曾於 ${avg_good_prize:,.0f} 賽事入圍)")
            else:
                notes.append("缺乏同級入圍證明")
        
        # Fallback to LLM class_move if prizemoney parsing failed or yielded no good runs
        if score == 60:
            class_move = self.data.get("class_move") or ""
            if "↓↓" in class_move:
                score += 6
                notes.append("大幅降班作賽")
            elif "↓" in class_move:
                score += 3
                notes.append("降班作賽有利")
            elif "↑↑" in class_move:
                score -= 4
                notes.append("大幅升班挑戰")
            elif "↑" in class_move:
                score -= 2
                notes.append("升班作賽難度增加")
            
        note_str = "；".join(notes) if notes else "班次水平相若"
        from engine_core import clip_score
        return clip_score(score), f"AU 班級與升降班評估：{note_str}。", "class_au"


    def _sectional_score(self):
        """
        Bypass HKJC absolute sectional penalties.
        """
        return 60, "AU段速(無HKJC扣分)", "sectional_au"
