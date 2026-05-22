from scoring import BaseScorer, clip_score, parse_float

class SpeedScorer(BaseScorer):
    def _data(self):
        return self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}

    def compute(self):
        data = self._data()
        signals = 0
        strong_signals = 0
        score = 60.0
        reasons = []

        raw_l400 = parse_float(data.get("raw_l400"))
        if raw_l400 is not None:
            signals += 1
            reasons.append(f"L400={raw_l400:.2f}")
            if raw_l400 <= 22.4:
                score += 8.0
                strong_signals += 1
            elif raw_l400 <= 23.0:
                score += 5.0
                strong_signals += 1
            elif raw_l400 <= 23.6:
                score += 2.0
            elif raw_l400 >= 24.6:
                score -= 5.0
                strong_signals += 1
            elif raw_l400 >= 24.0:
                score -= 2.0

        finish_time_level = str(data.get("finish_time_adj_level") or "").strip()
        if finish_time_level:
            signals += 1
            reasons.append(f"步速修正={finish_time_level}")
            if "仍具競爭力" in finish_time_level:
                score += 8.0
                strong_signals += 1
            elif "持續快於標準" in finish_time_level:
                score += 6.0
                strong_signals += 1
            elif "略快於標準" in finish_time_level:
                score += 4.0
            elif "接近平均" in finish_time_level:
                score += 1.0
            elif "仍偏慢" in finish_time_level:
                score -= 4.0
                strong_signals += 1
            elif "明顯落後" in finish_time_level:
                score -= 8.0
                strong_signals += 1

        energy_trend = str(data.get("energy_trend") or "").strip()
        if energy_trend:
            signals += 1
            reasons.append(f"能量={energy_trend}")
            if "上升" in energy_trend and "✅" in energy_trend:
                score += 4.0
                strong_signals += 1
            elif "穩定" in energy_trend:
                score += 1.5
            elif "下降" in energy_trend and "⚠️" in energy_trend:
                score -= 4.0
                strong_signals += 1

        l400_trend = str(data.get("l400_trend") or "").strip()
        if l400_trend:
            signals += 1
            reasons.append(f"L400趨勢={l400_trend}")
            if "上升" in l400_trend and "✅" in l400_trend:
                score += 3.0
                strong_signals += 1
            elif "穩定" in l400_trend:
                score += 1.5
            elif "波動" in l400_trend:
                score -= 1.0
            elif "衰退中" in l400_trend:
                score -= 4.0
                strong_signals += 1

        engine_type = str(data.get("engine_type") or "").strip()
        if engine_type:
            signals += 1
            reasons.append(f"引擎={engine_type}")
            if "漸進加速型" in engine_type:
                score += 3.0
                strong_signals += 1
            elif "均速型" in engine_type:
                score += 1.5
            elif "混合型" in engine_type and "信心: 低" in engine_type:
                score -= 2.0
            elif "快開慢收型" in engine_type:
                score -= 2.5
                strong_signals += 1
            if "信心: 低" in engine_type:
                score -= 1.0

        distance_text = str(data.get("best_distance") or "").strip()
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()
        if distance_text and distance:
            signals += 1
            if distance_text.startswith(f"{distance}m") or f"今仗 {distance}m =" in distance_text:
                score += 1.5
                reasons.append(f"路程配合={distance}m")
            elif "未跑過" in distance_text:
                score -= 1.5
                reasons.append("路程=未跑過")

        if signals < 2:
            pdf_races = data.get("pdf_overseas_races", [])
            if pdf_races:
                ovr_score = 60.0
                ovr_reasons = []
                for r in pdf_races:
                    rank_str = str(r.get("rank", ""))
                    cls_str = str(r.get("class_level", "")).upper()
                    try:
                        rank = int(rank_str.split("/")[0]) if "/" in rank_str else int(rank_str)
                    except ValueError:
                        continue
                    
                    if rank <= 3:
                        if "G1" in cls_str or "1級" in cls_str:
                            ovr_score += 6.0
                            ovr_reasons.append("G1上名")
                        elif "G2" in cls_str or "2級" in cls_str:
                            ovr_score += 4.0
                            ovr_reasons.append("G2上名")
                        elif "G3" in cls_str or "3級" in cls_str:
                            ovr_score += 3.0
                            ovr_reasons.append("G3上名")
                        else:
                            ovr_score += 1.0
                            ovr_reasons.append("海外上名")
                
                if ovr_reasons:
                    final_score = clip_score(ovr_score)
                    return final_score, f"海外賽績速度替代指標 ({', '.join(set(ovr_reasons))})"
                    
            return 60.0, "Sectional data incomplete"

        final_score = clip_score(score)
        if final_score >= 76:
            bucket = "Strong race sectional profile"
        elif final_score >= 68:
            bucket = "Positive race sectional profile"
        elif final_score >= 62:
            bucket = "Fair race sectional profile"
        elif final_score >= 60:
            bucket = "Neutral race sectional profile"
        else:
            bucket = "Weak race sectional profile"

        signal_tag = f"signals={signals}"
        if strong_signals:
            signal_tag += f", strong={strong_signals}"
        reasons.append(signal_tag)
        return final_score, f"{bucket} ({'; '.join(reasons)})"
