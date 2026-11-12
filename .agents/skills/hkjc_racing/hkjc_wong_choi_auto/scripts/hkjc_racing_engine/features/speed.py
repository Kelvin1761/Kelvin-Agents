import re
from hkjc_racing_engine import scoring
from hkjc_racing_engine.scoring import BaseScorer, clip_score, parse_float

def first_section_delta(min_delta):
    """近 6 仗最快第一段（Δ1 對標準，負 = 快）→ 段速分加減。None = 冇證據。"""
    m = parse_float(min_delta)
    if m is None:
        return None, ""
    w = scoring.SPEED_MICRO_WEIGHTS
    if m < -0.3:
        return w["first_section_fast_bonus"], "第一段曾快過標準 >0.3s"
    if m < 0:
        return w["first_section_quick_bonus"], "第一段曾快過標準"
    if m < 0.3:
        return 0.0, "第一段接近標準"
    if m < 0.6:
        return w["first_section_slowish_pen"], "第一段偏慢"
    return w["first_section_slow_pen"], "第一段明顯慢"


def l400_weight_adjustment(data):
    """上仗 L400 換算到今仗負磅（EXP-20261112-13）。返回 None（唔換算）或 dict：
    raw、adjusted（2 位小數，入分用）、shift、weight_diff、coef、distance、last_weight、today_weight。
    要上仗 L400 同 Logic `raw_l400` 對得上（≤0.02s），先確定係同一仗。"""
    if not getattr(scoring, "L400_WEIGHT_ADJUST", False) or not isinstance(data, dict):
        return None
    raw = parse_float(data.get("raw_l400"))
    last = data.get("l400_last_run")
    today = data.get("formguide_today_weight")
    if raw is None or not isinstance(last, dict) or today in (None, ""):
        return None
    l4, last_w, dist = parse_float(last.get("l400")), last.get("weight"), last.get("distance")
    if l4 is None or last_w in (None, "") or not dist or abs(l4 - raw) > 0.02:
        return None
    coef = scoring.l400_weight_seconds_per_lb(dist)
    diff = int(today) - int(last_w)
    adjusted = float(f"{raw + coef * diff:.2f}")
    return {"raw": raw, "adjusted": adjusted, "shift": round(adjusted - raw, 2), "weight_diff": diff, "coef": coef,
            "distance": int(dist), "last_weight": int(last_w), "today_weight": int(today)}


# 現行「步速修正等級」其實係近 3 仗平均輸頭馬秒數（馬位 × 0.17 秒；inject_hkjc_fact_anchors V5.1
# 扣「頭馬對標準偏差」之後剩低嘅就係輸頭馬距離）。等級字串由上游產生（入分照用關鍵字），顯示改用啱嘅名。
MARGIN_LEVEL_TEXT = (
    ("仍具競爭力", "輸頭馬少（平均 < 0.3 秒）"),
    ("接近平均", "輸頭馬中等（0.3–0.8 秒）"),
    ("仍偏慢", "輸頭馬偏多（0.8–1.3 秒）"),
    ("明顯落後", "輸頭馬多（≥ 1.3 秒）"),
)


def margin_level_display(level_text):
    """「⚠️ 步速修正後仍偏慢 (近 3 仗修正平均: +1.23s)」→「⚠️ 輸頭馬偏多（0.8–1.3 秒）(近 3 仗平均輸頭馬 1.23 秒)」。"""
    text = str(level_text or "").strip()
    if not text:
        return ""
    icon = re.match(r"^([✅⚠️❌➖️\s]*)", text).group(1).strip()
    words = next((label for key, label in MARGIN_LEVEL_TEXT if key in text), text.lstrip("✅⚠️❌➖️ ").strip())
    m = re.search(r"近\s*(\d+)\s*仗修正平均[:：]\s*([+-]?\d+(?:\.\d+)?)s", text)
    tail = f" (近 {m.group(1)} 仗平均輸頭馬 {abs(float(m.group(2))):.2f} 秒)" if m else ""
    return f"{icon} {words}{tail}".strip()


def margin_series_display(series_text):
    """步速修正偏差串 =「輸頭馬秒數」串：唔郁數字，剷走「步速修正」字眼。"""
    text = str(series_text or "").replace("步速修正偏差", "輸頭馬秒數").strip()
    return re.sub(r"\+(\d)", r"\1", text)      # 輸頭馬秒數唔會係負數，唔使「+」


def l400_weight_display(data):
    """報告／dashboard 一行：上仗 L400 點樣換算到今仗負磅。冇換算返空字串。"""
    adj = l400_weight_adjustment(data)
    if not adj:
        return ""
    # 唔用「→」：dashboard 會將含箭咀嘅行當走勢串解析。
    if adj["weight_diff"] == 0:
        change = "同上仗一樣負磅，唔使換算"
    else:
        change = (f"{'重' if adj['weight_diff'] > 0 else '輕'} {abs(adj['weight_diff'])} 磅 × {adj['coef']:.3f} 秒"
                  f" ＝ {adj['shift']:+.2f}s")
    return (f"上仗 {adj['raw']:.2f}s（{adj['distance']}m 負 {adj['last_weight']} 磅）；今仗負 {adj['today_weight']} 磅，"
            f"{change}；入分用 {adj['adjusted']:.2f}s")


def std_pace_display(data):
    """對馬會標準（EXP-20261112-09 定義）—— 只顯示，唔入分；forward shadow `std_pace_shadow` 判入唔入分。"""
    pace = (data or {}).get("std_pace") if isinstance(data, dict) else None
    if not isinstance(pace, dict) or pace.get("p2") is None:
        return ""
    return (f"近 {pace.get('n')} 仗加權：對標準 {float(pace['p0']):+.2f}s｜扣步速 {float(pace['p1']):+.2f}s｜"
            f"再換算今仗負磅 {float(pace['p2']):+.2f}s（越細越快；未入分，forward 觀察中）")


class SpeedScorer(BaseScorer):
    def _data(self):
        return self.horse_data.get("_data", {}) if isinstance(self.horse_data.get("_data"), dict) else {}

    def compute(self):
        score, note = self._compute_core()
        # 最快第一段（EXP-20261016-52/53，Kelvin 2026-10-16 決定上線，未證實）：喺所有返回路徑之後加，
        # 唔計入 signals —— 同 A/B arm 一模一樣，排名可以同 arm 逐場對數。
        m = self._data().get("first_section_min_delta")
        delta, why = first_section_delta(m)
        if delta is None:
            return score, note
        self.detail = list(getattr(self, "detail", []) or []) + [
            {"factor": "頭段速度", "value": f"{float(m):+.2f}s", "delta": round(delta, 2), "why": why}]
        return clip_score(score + delta), note

    def _compute_core(self):
        data = self._data()
        signals = 0
        strong_signals = 0
        score = 60.0
        reasons = []
        # 逐項結構化明細（同騎練訊號一致）：每個訊號 factor / 原始值 / ±分 / 白話
        self.detail = []

        def add(factor, value, delta, why):
            score_ref[0] += delta
            self.detail.append({"factor": factor, "value": value, "delta": round(delta, 2), "why": why})
        score_ref = [score]  # 用 list 令內層 add 可改到

        raw_l400 = parse_float(data.get("raw_l400"))
        weight_adj = l400_weight_adjustment(data)
        if raw_l400 is not None:
            signals += 1
            reasons.append(f"L400={raw_l400:.2f}")
            if weight_adj:
                # 入分用換算到今仗負磅之後嘅 L400；顯示保留原始值同換算過程。
                reasons.append(f"負磅換算L400={weight_adj['adjusted']:.2f}")
                raw_l400 = weight_adj["adjusted"]
            shown = (f"{raw_l400:.2f}s，上仗 {weight_adj['raw']:.2f}s 按負磅換算 {weight_adj['shift']:+.2f}s"
                     if weight_adj and weight_adj["shift"] else f"{raw_l400:.2f}s")
            if raw_l400 <= 22.4:
                add("L400 絕對值", shown, scoring.SPEED_MICRO_WEIGHTS.get("l400_22_4_bonus", 8.0), "末段極快（≤22.4s）")
                strong_signals += 1
            elif raw_l400 <= 23.0:
                add("L400 絕對值", shown, scoring.SPEED_MICRO_WEIGHTS.get("l400_23_0_bonus", 5.0), "末段快（≤23.0s）")
                strong_signals += 1
            elif raw_l400 <= 23.6:
                add("L400 絕對值", shown, scoring.SPEED_MICRO_WEIGHTS.get("l400_23_6_bonus", 2.0), "末段偏快（≤23.6s）")
            elif raw_l400 >= 24.6:
                add("L400 絕對值", shown, scoring.SPEED_MICRO_WEIGHTS.get("l400_24_6_pen", -5.0), "末段慢（≥24.6s）")
                strong_signals += 1
            elif raw_l400 >= 24.0:
                add("L400 絕對值", shown, scoring.SPEED_MICRO_WEIGHTS.get("l400_24_0_pen", -2.0), "末段偏慢（≥24.0s）")
            else:
                add("L400 絕對值", shown, 0.0, "末段一般（23.6–24.0s）")

        finish_time_level = str(data.get("finish_time_adj_level") or "").strip()
        if finish_time_level:
            signals += 1
            reasons.append(f"輸頭馬差距={finish_time_level}")
            lvl = finish_time_level.lstrip("✅⚠️❌➖ ").strip()
            m_avg = re.search(r"近\s*(\d+)\s*仗修正平均[:：]\s*([+-]?\d+(?:\.\d+)?)s", finish_time_level)
            lvl = f"近 {m_avg.group(1)} 仗平均 {abs(float(m_avg.group(2))):.2f} 秒" if m_avg else lvl
            if "仍具競爭力" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_competitive_bonus", 8.0), "輸頭馬少（< 0.3 秒）")
                strong_signals += 1
            elif "持續快於標準" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_faster_bonus", 6.0), "持續快於標準")
                strong_signals += 1
            elif "略快於標準" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_slightly_faster_bonus", 4.0), "略快於標準")
            elif "接近平均" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_avg_bonus", 1.0), "輸頭馬中等（0.3–0.8 秒）")
            elif "仍偏慢" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_slow_pen", -4.0), "輸頭馬偏多（0.8–1.3 秒）")
                strong_signals += 1
            elif "明顯落後" in finish_time_level:
                add("輸頭馬差距", lvl, scoring.SPEED_MICRO_WEIGHTS.get("finish_far_behind_pen", -8.0), "輸頭馬多（≥ 1.3 秒）")
                strong_signals += 1

        energy_trend = str(data.get("energy_trend") or "").strip()
        if energy_trend:
            signals += 1
            reasons.append(f"能量={energy_trend}")
            etail = energy_trend.split("趨勢:")[-1].strip() if "趨勢" in energy_trend else energy_trend
            # NOTE: scoring intentionally keys on the source 趨勢 LABEL, not the raw
            # first-vs-last numbers (ML-tested; numbers REGRESSED). Do not "fix".
            if "上升" in energy_trend and "✅" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_up_bonus", 4.0), "能量上升")
                strong_signals += 1
            elif "穩定" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_steady_bonus", 1.5), "能量穩定")
            elif "下降" in energy_trend and "⚠️" in energy_trend:
                add("能量趨勢", etail, scoring.SPEED_MICRO_WEIGHTS.get("energy_down_pen", -4.0), "能量下降")
                strong_signals += 1

        l400_trend = str(data.get("l400_trend") or "").strip()
        if l400_trend:
            signals += 1
            reasons.append(f"L400趨勢={l400_trend}")
            ltail = l400_trend.split("趨勢:")[-1].strip() if "趨勢" in l400_trend else l400_trend
            if "上升" in l400_trend and "✅" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_up_bonus", 3.0), "末段速度走勢改善")
                strong_signals += 1
            elif "穩定" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_steady_bonus", 1.5), "末段速度平穩")
            elif "波動" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_fluctuate_pen", -1.0), "末段速度波動")
            elif "衰退中" in l400_trend:
                add("L400 趨勢", ltail, scoring.SPEED_MICRO_WEIGHTS.get("l400_trend_decline_pen", -4.0), "末段速度衰退")
                strong_signals += 1

        engine_type = str(data.get("engine_type") or "").strip()
        if engine_type:
            signals += 1
            reasons.append(f"引擎={engine_type}")
            etype = engine_type.split("|")[0].strip()
            if "漸進加速型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_progressive_bonus", 3.0), "漸進加速型")
                strong_signals += 1
            elif "均速型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_steady_bonus", 1.5), "均速型")
            elif "混合型" in engine_type and "信心: 低" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_mixed_low_conf_pen", -2.0), "混合型＋低信心")
            elif "快開慢收型" in engine_type:
                add("引擎型態", etype, scoring.SPEED_MICRO_WEIGHTS.get("engine_fast_slow_pen", -2.5), "快開慢收型")
                strong_signals += 1
            if "信心: 低" in engine_type:
                add("引擎信心", "低", scoring.SPEED_MICRO_WEIGHTS.get("engine_low_conf_pen", -1.0), "剖面樣本不足")

        distance_text = str(data.get("best_distance") or "").strip()
        distance = str(self.race_context.get("distance") or "").replace("m", "").strip()
        if distance_text and distance:
            signals += 1
            if distance_text.startswith(f"{distance}m") or f"今仗 {distance}m =" in distance_text:
                add("路程配合", f"{distance}m", scoring.SPEED_MICRO_WEIGHTS.get("dist_match_bonus", 1.5), "今程有往績")
                reasons.append(f"路程配合={distance}m")
            elif "未跑過" in distance_text:
                add("路程配合", f"{distance}m 未跑過", scoring.SPEED_MICRO_WEIGHTS.get("dist_unproven_pen", -1.5), "今程未有往績")
                reasons.append("路程=未跑過")

        score = score_ref[0]

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
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g1_bonus", 6.0)
                            ovr_reasons.append("G1上名")
                        elif "G2" in cls_str or "2級" in cls_str:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g2_bonus", 4.0)
                            ovr_reasons.append("G2上名")
                        elif "G3" in cls_str or "3級" in cls_str:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_g3_bonus", 3.0)
                            ovr_reasons.append("G3上名")
                        else:
                            ovr_score += scoring.SPEED_MICRO_WEIGHTS.get("overseas_place_bonus", 1.0)
                            ovr_reasons.append("海外上名")
                
                if ovr_reasons:
                    final_score = clip_score(ovr_score)
                    self.detail = [{"factor": "海外賽績替代", "value": "、".join(set(ovr_reasons)),
                                    "delta": round(final_score - 60.0, 2), "why": "本地段速資料不足，用海外上名替代"}]
                    return final_score, f"海外賽績速度替代指標 ({', '.join(set(ovr_reasons))})"

            self.detail = [{"factor": "資料不足", "value": f"有效訊號 {signals}/6", "delta": 0.0,
                            "why": "本地段速資料不足兩項，速度分中性60"}]
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
