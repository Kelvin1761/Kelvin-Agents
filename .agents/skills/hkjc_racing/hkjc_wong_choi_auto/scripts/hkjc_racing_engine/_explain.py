"""Explanations: readouts, per-dimension prose and grade transparency.

Display only — nothing here may change a score (see display-only-changes-leak-into-ranking).
"""
import re
from datetime import date

from .matrix_mapper import (
    DEBUT_MATRIX_FORMULAS,
    MATRIX_FORMULAS,
)
from . import dimensions
from .scoring import (CENTRED_MATRIX_WEIGHTS, DEBUT_MATRIX_WEIGHTS, FEATURE_KEYS, MATRIX_WEIGHTS, clip_score, score_band, to_dimension_display,
                      to_display_scale)


# Frozen prospective candidates from EXP-20260928-09.  These weights never
# replace MATRIX_WEIGHTS: they live only inside `shadow_profiles`, so the
# official ranking and run contract remain bit-for-bit mainline.
_CN_COUNT = {7: "七", 8: "八", 9: "九", 10: "十", 11: "十一", 12: "十二"}

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


class Explanations:
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
        # 長休之後，「回來重咗」實測係**正面**訊號，唔係警號。
        # 16,959 個有上仗體重嘅 runner-start：
        #   長休 >75 日：重咗(>+5lb) − 輕咗(<-5lb) 上名率 **+7.9pp, 95% CI [+2.1, +13.7]**
        #   短休 ≤75 日：同一個對比 −0.6pp, CI [-2.5, +1.2]（跨零＝冇訊號）
        # 所以「明顯上升」加 ⚠️ 喺長休復出馬身上係講反話（2026-09-06 R3 嘉應高昇
        # 休 133 日、回來 +29 磅，落喺實測最好嗰批，但報告寫「狀態欠穩定」）。
        # ⚠️ 計分冇改 —— 剷／改嗰四個變幅項五個 arm 全部過唔到 primary
        #    （EXP-20260904-08）。呢度只係唔再叫個讀者睇錯方向。
        days = self._days_since_last()
        if days is not None and days > 75 and delta >= 8:
            word += (f"（註：長休{int(days)}日後回來體重增加，實測係正面訊號 "
                     f"——長休組重咗嘅上名率高過輕咗嘅 +7.9pp）")
        return word

    def _official_injury_lines(self):
        """賽會傷患記錄頁白話（display-only），最新一條行先。"""
        race_day = str((self.race_context or {}).get("race_date") or "")
        lines = []
        for rec in sorted(self._official_injury_records(), key=lambda r: r.get("incident_date") or "", reverse=True):
            inc = rec.get("incident_date") or "日期不明"
            passed = rec.get("passed_date")
            gap = ""
            if race_day and inc[:4].isdigit():
                try:
                    gap = f"，距今 {(date.fromisoformat(race_day[:10]) - date.fromisoformat(inc)).days} 日"
                except ValueError:
                    gap = ""
            tail = f"；{passed} 通過檢驗" if passed else ""
            # 「季終時年屆八歲或以上」係年齡例行檢查，唔係傷患；計分分類唔郁
            # （官方傷患 B1 forward 測試用緊），只係顯示唔再加 ⚠️。
            if rec.get("performance_only"):
                tag = "賽會覆檢"
            elif re.search(r"年屆\S*歲", str(rec.get("detail") or "")):
                tag = "賽會年齡例行檢查"
            else:
                tag = "賽會傷患記錄"
            lines.append(f"{tag}：{inc} {rec.get('detail', '')}{gap}{tail}")
        return lines

    def _health_readout(self):
        """馬匹健康白話判讀（display-only）：上次出賽日期＋休賽 band＋體重＋
        傷後/長休＋長休×晨操 context。回傳 {lines, verdict}。"""
        lines = []
        days = self._days_since_last()
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

        # 官方傷患記錄頁（2026-10-20）：兩仗之間嘅手術／受傷，賽事短評唔會有
        for official_line in self._official_injury_lines():
            lines.append(f"⚠️ {official_line}" if "傷患" in official_line else official_line)

        # 傷病後復出：醫療欄有真事故（非「無事故」）＋今仗復出
        medical = self._text("medical_flags")
        has_incident = bool(medical) and "無醫療事故" not in medical and medical not in ("N/A", "")
        if has_incident:
            lines.append("醫療欄有紀錄，或屬傷病後復出，須留意復原情況")

        # 長休 × 晨操 context（#6）：長休（>60日）要睇操練夠唔夠
        # 以前 strong = 「快操」或「試閘」出現 —— 但每份摘要都有「近#日快操#課、試閘#課」
        # 模板字，所以長休馬一律印「操練量充足」（897 匹只有 1 匹兩樣都係 0）。
        # 而家睇實際課數（EXP-20261018-10，純顯示，唔入分）。
        tw = self._text("trackwork_digest") + self._text("trackwork_trainer")
        if days is not None and days > 60:
            counts = re.search(r"近(\d+)日快操(\d+)課、試閘(\d+)課", tw)
            gallops = int(counts.group(2)) if counts else None
            trials = int(counts.group(3)) if counts else None
            seen = f"（近{counts.group(1)}日快操{gallops}課、試閘{trials}課）" if counts else ""
            slowing = any(k in tw for k in ("放緩", "偏保守", "操練量少", "操練不足"))
            enough = bool(counts) and ((gallops >= 3 and trials >= 1) or gallops >= 5)
            light = bool(counts) and gallops <= 2 and trials == 0
            if enough and not slowing:
                lines.append(f"復出前操練量充足{seen}，狀態有支持")
            elif enough:
                lines.append(f"復出前有實際操練{seen}，但近期操練趨勢放緩，狀態須觀察")
            elif light or slowing:
                lines.append(f"長休後操練偏保守{seen}，狀態須觀察")
            else:
                lines.append(f"長休復出{seen}，宜對照晨操判斷備戰")

        verdict = "；".join(lines[1:]) if len(lines) > 1 else (lines[0] if lines else "")
        return {"lines": lines, "verdict": verdict}

    def _matrix_reasoning(self, matrix_scores, matrix, features, notes, matrix_scores_display=None):
        # Keys, order and leaves come from dimensions.py; only the wording of
        # this section's headings differs from the registry label.
        heading = {"race_shape": "檔位與走位情境（不含步速）"}
        specs = {
            key: (heading.get(key, spec.label), tuple(name for name, _w in MATRIX_FORMULAS[key]))
            for key, spec in ((spec.key, spec) for spec in dimensions.DIMENSIONS)
        }
        reasoning = {}
        # 初出馬級數優勢嘅班次／負磅份額唔同（見 dimensions._PRE_MERGE）。
        formulas = DEBUT_MATRIX_FORMULAS if self._is_debut() else MATRIX_FORMULAS
        for key, (label, feature_keys) in specs.items():
            evidence = self._best_evidence(feature_keys, notes)
            # `score` = 顯示尺（讀者睇嘅、band 用嘅）；`score_raw` = 原始尺
            # （sub 分加權真正加出嚟嘅數，同綜合分嘅輸入）。兩個都要寫出嚟，
            # 唔然「評分構成」加極都對唔返 header 個分。
            raw = matrix_scores[key]
            score = (matrix_scores_display or {}).get(key, raw)
            components = [
                {
                    "key": name,
                    "label": self._feature_score_label(name),
                    "score": round(features[name], 2),
                    "weight": weight,
                    "note": self._clean(notes.get(name, "資料不足，中性60分。")),
                }
                for name, weight in formulas[key]
            ]
            reasoning[key] = {
                "label": label,
                "score": round(score, 2),
                "score_raw": round(raw, 2),
                "symbol": matrix[key],
                "tone": self._matrix_score_tone(score),
                "components": components,
                "evidence": evidence,
                "text": self._matrix_summary_text(key, label, score, features, evidence),
            }
            # 矩陣後調整唔喺 sub分加權入面，
            # 唔寫出嚟嘅話「評分構成」加極都對唔返 header 個分 — 呢度補返一行。
            expected = clip_score(sum(clip_score(features.get(name, 60.0)) * weight
                                      for name, weight in formulas[key]))
            diff = round(float(raw) - expected, 2)
            if abs(diff) >= 0.05:
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
        days = self._days_since_last()
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
            # 長休後回來重咗係正面訊號（見 _bodyweight_readout），所以嗰句
            # 帶住「實測係正面訊號」嘅時候唔好再亮 ⚠️。
            concerning = (any(k in bw for k in ("明顯上升", "明顯下降", "上落較大", "狀態欠穩定"))
                          and "實測係正面訊號" not in bw)
            add("體重狀態", bw, "", band="⚠️" if concerning else "➖")
        eng = self._value("engine_type")
        if present(eng):
            add("段速型態", str(eng).split("|")[0].strip(), "")
        bd = self._value("best_distance")
        if present(bd):
            m = re.search(r"今仗\s*(\d+m)\s*=\s*(\d+)場\s*\(([\d\-]+)\)", str(bd))
            if m:
                dist, n, rec = m.group(1), m.group(2), m.group(3)
                # 抽取層寫嘅係（勝-亞季-未上名），見 inject_hkjc_fact_anchors.compute_distance_aptitude。
                # 舊版當咗「冠/亞/季」印，又將未上名當上名（全敗唔會亮 ⚠️）。
                wins, placed, unplaced = ([int(x) for x in rec.split("-")] + [0, 0, 0])[:3]
                rband = "✅" if wins > 0 else ("➖" if placed > 0 else "⚠️")
                add("今仗路程", dist, "", band=rband,
                    reason=f"同程往績 {n}場（{wins}勝、{placed}次亞季、{unplaced}次未上名）")
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
        # 預測跑法已移除：近兩次跑馬地驗證只有約 44-46% 命中，唔再將
        # 「前置／守中／後上」包裝成今仗預測。歷史實際走位仍保留喺 race-shape 證據。
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
            # 驗證對手要「今馬當日跑得埋堆」(competitive) 先surface；同場對手照顯示
            # （相關），但唔當已驗證。跑第13負十幾個馬位嗰啲唔會再誤當賽績線兌現。
            cand = [o for o in opps if o["is_field"] or (o["wins"] >= 1 and o["competitive"])] or opps[:1]
            byname = {}
            for o in cand:
                e = byname.get(o["name"])
                if e is None or (o["is_field"], o["wins"], -o["my_fin"]) > (e["is_field"], e["wins"], -e["my_fin"]):
                    byname[o["name"]] = o
            shown = sorted(byname.values(), key=lambda o: (not o["is_field"], -o["wins"], o["my_fin"]))[:4]
            field_n = sum(1 for o in shown if o["is_field"])
            comp_field = sum(1 for o in shown if o["is_field"] and o["competitive"])
            mine = self.horse_data.get("horse_name", "本駒")
            lines = []
            for o in shown:
                fin_c = self._compact_finish(o["my_finish_raw"])
                tag = "⭐同場對手" if o["is_field"] else ""
                # 已驗證只計「跑得埋堆」嗰啲；跑唔近就寫實況（曾同場但落後多）
                if o["wins"] >= 1 and o["competitive"]:
                    cls = o["next_class"]
                    won = (f"{o['name']}其後{o['move']}（{cls}）再勝{o['wins']}場" if o["move"]
                           else f"{o['name']}其後於{cls}再勝{o['wins']}場")
                elif o["wins"] >= 1:
                    won = f"{o['name']}其後再勝但當日跑唔近（僅供參考）"
                else:
                    won = f"{o['name']}其後未再勝"
                meet = (f"當日{mine}{fin_c}、{o['name']}第{o['opp_fin']}" if o["is_field"] and o["opp_fin"]
                        else f"當日{mine}{fin_c}")
                lines.append(f"{tag}「{o['name']}」{meet}，{won}".lstrip())
            has_evidence = fl["validated"] >= 1 or comp_field >= 1
            trend = (f"同場對手{field_n}駒" if field_n else
                     ("對手已驗證" if fl["validated"] >= 1 else "近仗未跑近已兌現對手"))
            add("賽績線", f"近{fl['n']}仗", trend,
                band="✅" if has_evidence else "➖",
                reason=" ｜ ".join(lines))
        # 班次表現 — average finishing place grouped by class (own section).
        # Prefer the 近三季 profile-derived breakdown; fall back to recent races.
        cls_perf = self._value("class_perf_3s") or self._class_rank_note()
        if cls_perf:
            add("班次表現", _format_hkjc_class_display(cls_perf), "", band="➖")
        # 配備變動 — 只做顯示（初戴 out-of-sample NULL；除去 −3 已剷走，EXP-20261010-05）
        gear_read = self._gear_change_readable()
        if gear_read:
            # reason 用白話 value（唔用 raw gear_change，佢含 ASCII pipe 會漏入
            # core_logic 觸發 NLG-002 假陽性）
            add("配備變動", gear_read["value"], gear_read["trend"],
                band=gear_read["band"], reason=gear_read["value"])
        # 晨操 row 同晨操分析／狀態與穩定性共用 _trackwork_pattern 呢個單一判定，
        # 呢度只出 pattern 標籤＋賽日騎師參與＋一句原因；原始課數留返晨操分析度睇。
        tw_pattern = self._trackwork_pattern()
        if tw_pattern:
            jockey_txt = "賽日騎師有參與操練" if tw_pattern["jockey_in"] else "賽日騎師未有參與操練"
            add("晨操", tw_pattern["label"], jockey_txt,
                band=tw_pattern["band"], reason=tw_pattern["reason"])
        return rows

    DIM_LABELS = dimensions.short_labels()

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
        ability = to_display_scale(self._ability_score(matrix_scores))
        sents = [f"{name}今仗{_CN_COUNT.get(len(dimensions.DIMENSIONS), len(dimensions.DIMENSIONS))}維綜合戰力 {ability:.1f} 分，當中以{top_dim}（{ordered[0][1]:.0f}）為最強一環、"
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

    def _format_combo_record(self, row):
        return (
            f"{row['jockey']}×此馬 {int(row['starts'])}場 {int(row['wins'])}勝 "
            f"{int(row['places'])}上名 平均名次{row['avg_finish']:.1f} "
            f"勝率{row['win_rate']:.1f}% 位率{row['place_rate']:.1f}%"
        )


    _TIMELINE_TYPES = {"gallop": "快操", "trial": "試閘"}

    def _trackwork_timeline(self):
        """Structured 21-day trackwork for the dashboard (display only, not scored).

        Kelvin 2026-10-10: show trackwork in detail. Every gallop and barrier trial
        is listed with time, splits, rider and gear; easy work (trotting,
        swimming) is summarised; consecutive days at 從化 collapse into one stay.
        """
        trackwork = self.horse_data.get("trackwork")
        if not isinstance(trackwork, dict):
            return None
        entries = [e for e in trackwork.get("entries") or [] if isinstance(e, dict)]
        summary = trackwork.get("summary") or {}
        digest = trackwork.get("stability_digest") or {}
        rows = []
        for entry in sorted(entries, key=lambda e: str(e.get("date") or ""), reverse=True):
            kind = self._TIMELINE_TYPES.get(str(entry.get("type") or ""))
            if not kind:
                continue
            rows.append({
                "date": str(entry.get("date") or ""),
                "type": kind,
                "location": str(entry.get("location") or ""),
                "time": entry.get("final_time"),
                "sectionals": list(entry.get("sectionals") or []),
                "rider": str(entry.get("rider_role") or entry.get("rider") or ""),
                "gear": str(entry.get("gear") or ""),
                "detail": str(entry.get("details") or ""),
            })
        conghua = sorted({str(e.get("date") or "") for e in entries if "從化" in str(e.get("location") or "")})
        stay = {"from": conghua[0], "to": conghua[-1], "days": len(conghua)} if conghua else None
        trend = {"improving": "轉快", "easing": "放緩", "steady": "平穩"}.get(
            str(summary.get("gallop_time_trend") or ""), str(summary.get("gallop_time_trend") or ""))
        return {
            "window_days": summary.get("window_days", 21),
            "gallops": summary.get("gallops_21d", 0),
            "trials": summary.get("trials_21d", 0),
            "trotting": summary.get("trotting_21d", 0),
            "swimming": summary.get("swimming_21d", 0),
            "gallop_trend": trend,
            "race_jockey_involved": bool(summary.get("race_jockey_involved")),
            "readiness": digest.get("readiness_score"),
            "maintenance": digest.get("maintenance_score"),
            "conghua_stay": stay,
            "work": rows[:12],
        }

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
            "distance_fit_score": "同程表現分",
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

    def _describe_trackwork_matrix(self, score, features, evidence):
        """晨操（9D 獨立維度）：沿用晨操分嘅判讀；冇料就明講中性。"""
        text = self._clean(evidence) if evidence else ""
        if len(text) >= 12:
            return text
        return f"近 21 日晨操資料有限，晨操分 {float(features.get('trackwork_trend_score', 60.0)):.0f}，按中性處理。"

    def _distance_fit_note(self, detail):
        """同程表現分（leaf）嘅評分構成說明：有紀錄就講紀錄同貢獻，冇就講中性原因。"""
        starts = int(detail.get("same_distance_starts", 0) or 0)
        places = int(detail.get("same_distance_places", 0) or 0)
        adjustment = float(detail.get("raw_adjustment", 0.0) or 0.0)
        if starts:
            return f"今仗路程 {starts} 戰 {places} 次上名，原始分貢獻 {adjustment:+.2f}。"
        return self._clean(detail.get("note", "")) or "今仗路程未有正式往績，同程表現按中性 60 處理。"

    def _describe_distance_fit_matrix(self, score, features, evidence):
        """同程表現（9D centred 維度）：今仗路程有冇上名實績。"""
        detail = getattr(self, "distance_suitability_adjustment", {}) or {}
        starts = int(detail.get("same_distance_starts", 0) or 0)
        places = int(detail.get("same_distance_places", 0) or 0)
        note = self._clean(detail.get("note", ""))
        if starts:
            return f"今仗路程 {starts} 戰 {places} 次上名：{note or '按同程實績調整。'}"
        return note if len(note) >= 12 else "今仗路程未有正式往績，同程表現按中性 60 處理。"

    def _matrix_summary_text(self, key, label, score, features, evidence):
        builders = {
            "stability": self._describe_stability_matrix,
            "sectional": self._describe_sectional_matrix,
            "race_shape": self._describe_race_shape_matrix,
            "trainer_signal": self._describe_trainer_signal_matrix,
            "horse_health": self._describe_horse_health_matrix,
            "form_line": self._describe_form_line_matrix,
            "class_advantage": self._describe_class_advantage_matrix,
            "trackwork": self._describe_trackwork_matrix,
            "distance_fit": self._describe_distance_fit_matrix,
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

    def _margin_trend_display(self):
        """由 recent_6_detail 重算「頭馬距離趨勢」，帶符號。

        Logic 個 `_data.margin_trend` 係抽取層寫落去嘅，而抽取層一直當每個距離
        都係「落後頭馬幾多」——贏馬嗰欄其實係**贏出距離**。所以六戰六勝嘅
        嘉應高昇印住「4-1/4→…→2-3/4 → 📉擴大中」，而同場真連敗嗰匹反而讀
        「收窄中」。抽取層已修（`scrape_hkjc_horse_profile.compute_margin_trend`），
        但**已經存喺 Logic 嘅字串補唔返**，所以呢度用 recent_6_detail（有名次
        又有距離）自己重算，蓋過個舊字串。

        `margin_trend_score` 2026-07-08 已剔出 7D 計分，所以呢個係報告層修正。
        """
        races = self._recent_races_detailed()
        pairs = [(r["finish"], self._parse_margin_length(r["margin"])) for r in races]
        pairs = [(f, m) for f, m in pairs if m is not None]
        if len(pairs) < 3:
            return None
        seq = " → ".join(f"勝{r['margin']}" if r["finish"] == 1 else r["margin"]
                         for r in races if self._parse_margin_length(r["margin"]) is not None)
        signed = [(-m if f == 1 else m) for f, m in pairs]
        if all(x < 0 for x in signed):
            return f"{seq} → 📈連勝中"
        recent = signed[:3]
        older = signed[3:6]
        delta = (sum(recent) / len(recent)) - (sum(older) / len(older)) if older else 0.0
        if delta < -0.5:
            return f"{seq} → 📈收窄中"
        if delta > 0.5:
            return f"{seq} → 📉擴大中"
        return f"{seq} → 📊波動"

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
        recent_places = sum(1 for rank in recent if 1 <= rank <= 3)
        older_places = sum(1 for rank in older if 1 <= rank <= 3)
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
        shadow = self._consistency_from_runs()
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
        # Display context only: one medically abnormal run can drive several
        # correlated speed penalties. Do not silently erase it from scoring.
        medical = self._text("medical_flags")
        latest_incident = re.search(r"第1仗\s*[:：]\s*(⚠️[^;；\n]+)", medical)
        context = ""
        if latest_incident:
            context = (
                f"；上仗有醫療異常紀錄（{latest_incident.group(1).strip()}）。"
                "該仗段速與趨勢可能同受一次異常影響，不能視作多次獨立能力下滑；"
                "復出風險須另看醫療與覆檢資料"
            )
        return f"{l400_txt}段速{v['label']}：{v['why']}{self._score_close(score)}{context}"

    def _describe_race_shape_matrix(self, score, features, evidence):
        barrier = self.horse_data.get("barrier") or self.horse_data.get("draw") or "N/A"
        draw_verdict = self._draw_verdict_signal()
        if features.get("draw_score", 60) >= 72:
            draw = f"排{barrier}檔：著數位，有得揀位"
        elif features.get("draw_score", 60) >= 60:
            draw = f"排{barrier}檔：檔位中性，睇出閘搶位"
        else:
            draw = f"排{barrier}檔：檔位受壓，走位容錯低"
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
        days = self._days_since_last()
        wt = self._text("weight_trend")
        span = self._weight_trend_span(wt)
        # 年齡例行檢查唔係傷患（見 _official_injury_lines），唔好喺判讀度當傷患講。
        official = [r for r in self._official_medical_records()
                    if not re.search(r"年屆\S*歲", str(r.get("detail") or ""))]
        if "無醫療事故" in medical and official:
            latest = max(official, key=lambda r: r.get("incident_date") or "")
            medical_text = (f"賽事短評未見事故，但賽會傷患記錄有 {latest.get('incident_date')} "
                            f"{latest.get('detail', '')}，須核對復原情況")
        elif "無醫療事故" in medical:
            medical_text = "醫療乾淨"
        elif medical and medical != "N/A":
            medical_text = "有歷史醫療異常紀錄，須核對復原及覆檢情況；紀錄本身不代表目前仍患病"
        else:
            medical_text = "醫療資料未齊，保守處理"
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
        # 2026-11-05：負磅分已搬去級數優勢，呢格只剩風險分，唔使再解釋負磅。
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
        weight_score = float(features.get("weight_score", 60))
        if weight_score >= 68:
            weight = "；讓磅官高評（頂磅）"
        elif weight_score >= 60:
            weight = "；讓磅官評價中游"
        else:
            weight = "；讓磅官評價偏低（輕磅）"
        # 講清楚呢個維度實際上係邊個 sub 分推動。`class_score` 場內幾乎冇變化
        # （實測全日 120 匹只有 52.5–62.0），所以場內排位差不多完全由負磅決定。
        #
        # 2026-09-04 EXP-20260904-09 之後方向已經調轉：負磅係讓磅官對馬匹能力
        # 嘅意見，所以場內 ρ(官方評分, weight_score) 而家係**正**嘅。頂磅馬呢一格
        # 高分，係因為全場公認佢最好，而且讓磅官抹得唔夠（0.389 分/kg vs 慣例 0.5）。
        #
        # ⚠️ 「級數優勢」呢個名同呢一格實際量嘅嘢唔完全對得上，而呢點量過：
        # 「本駒喺今仗班次或更高嘅上名率」場內 AUC 0.6337，但輸畀唔限班次嘅
        # 0.6418，喺班次條件真係改到嘢嗰 12.3% 更加係 −0.0385；「跌級／升級」
        # 四個分層上名率 29.0/31.6/30.4/32.4%、AUC 0.4662–0.5192。
        # 即係香港班次制度嘅設計目的（抹平級數優勢）真係做到 —— 剩返嘅資訊
        # 就係讓磅官抹得唔夠嗰個殘差，而嗰個已經由 weight_score 捉住。
        driver = ""
        if abs(weight_score - 60.0) >= 4.0:
            side = "拉高" if weight_score > 60 else "拉低"
            driver = f"（呢格場內主要由讓磅官負磅{side}，唔係班次底子）"
        return f"{move_txt}{class_text}{weight}{driver}{self._score_close(score)}"

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
        """The ONE scoring-summary block: the matrix contribution table (score × weight
        = contribution), the weighted total + grade, reference scores that sit
        outside the 7D formula, and triggered risk flags. Weights are pulled live
        from the active weight set (debut vs standard) so the displayed 加權總分
        always matches the real ability_score."""
        is_debut = self._is_debut()
        active_weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS

        table_label = {"race_shape": "檔位與走位"}
        dims = [(spec.key, table_label.get(spec.key, spec.label)) for spec in dimensions.DIMENSIONS]

        rows = []
        lines = []
        weighted_sum = 0.0

        # 兩個尺一定要同時印。原始尺係真正嘅算式（分 × 權重 = 貢獻），顯示尺係
        # 讀者同 band 用嘅。只印原始尺就會出現「69.4 ➖」同「76.7 ✅」並排咁
        # 讀落好似亂判 —— 其實係兩個維度嘅原始尺根本唔同刻度。
        for key, label in dims:
            centred = key in CENTRED_MATRIX_WEIGHTS and not is_debut
            weight = CENTRED_MATRIX_WEIGHTS[key] if centred else active_weights.get(key, 0.0)
            raw_score = float(matrix_scores.get(key, 60))
            disp_score = float(to_dimension_display(key, raw_score))
            band = score_band(disp_score)
            # Centred dimensions add weight × (score − 60) on top (see dimensions.py).
            contribution = round(weight * (raw_score - 60.0) if centred else raw_score * weight, 2)
            weighted_sum += contribution
            rows.append({"key": key, "label": label,
                         "score": round(disp_score, 2),
                         "score_raw": round(raw_score, 2),
                         "weight": weight, "contribution": contribution, "band": band})
            if centred:
                lines.append(f"| {label} | {disp_score:.1f} | {raw_score:.1f} | "
                             f"{weight * 100:.1f}%（以 60 為中心） | {contribution:+.2f} | {band} |")
            elif weight == 0.0:
                tag = "初出馬豁免" if is_debut else "0%（僅作參考）"
                lines.append(f"| {label} | {disp_score:.1f} | {raw_score:.1f} | {tag} | — | {band} |")
            else:
                lines.append(f"| {label} | {disp_score:.1f} | {raw_score:.1f} | "
                             f"{weight * 100:.1f}% | {contribution:.2f} | {band} |")

        table = "\n".join([
            "| 維度 | 維度分（顯示尺） | 原始分 | 權重 | 貢獻 | 判定 |",
            "|:---|---:|---:|---:|---:|:---:|",
            *lines,
        ])
        # 表格逐行印嘅係維度加權貢獻，加起身係**原始**加權總分（實測全距 50–77）。
        # `ability_score` 係顯示尺，所以兩個數字要一齊印，唔然讀者會以為表格加錯。
        matrix_weighted_sum = weighted_sum
        # 同程表現已經係表入面一行（centred 維度），唔再另外加一次。
        distance_adjustment = getattr(self, "distance_suitability_adjustment", {})
        distance_raw = float(distance_adjustment.get("raw_adjustment", 0.0) or 0.0)
        summary = (
            f"{table}\n\n"
            f"**→ {len(dimensions.DIMENSIONS)}D 維度加權總和（原始總分）= {weighted_sum:.2f} 分"
            f"（原始尺，實測全場分佈 50–77）**\n"
            f"**→ 換算顯示尺 = {ability_score:.1f} 分 → 評級 [{grade}]**"
        )

        grade_explanation = self._grade_threshold_explanation(ability_score, grade)
        if grade_explanation:
            summary += f"\n{grade_explanation}"

        # Reference scores that do not enter the 7D weighted matrix.  The
        # same-distance record now enters only through the explicitly displayed
        # capped adjustment above; distance_score remains a diagnostic scale.
        if feature_scores:
            ref_bits = []
            dist = feature_scores.get("distance_score")
            if isinstance(dist, (int, float)):
                ref_bits.append(f"路程分 {float(dist):.1f}（診斷參考；同程實績另經獨立調整入分）")
            draw = feature_scores.get("draw_score")
            if isinstance(draw, (int, float)):
                ref_bits.append(f"檔位分 {float(draw):.1f}（經檔位走位情境入分）")
            if ref_bits:
                summary += f"\n**📎 參考分（不直接入{len(dimensions.DIMENSIONS)}D公式）：** " + "、".join(ref_bits)
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
            "matrix_weighted_sum": round(matrix_weighted_sum, 2),
            "distance_suitability_adjustment": round(distance_raw, 2),
            "weighted_sum": round(weighted_sum, 2),
            "summary": summary,
        }

    def _grade_threshold_explanation(self, ability_score, grade):
        """Explain which grade threshold the score fell into."""
        # 括號係實測百分位（3,438 個 runner / 274 場，2026-04-12→2026-09-06）。
        # 加咗百分位係為咗個等級講得出「幾罕有」——之前 A 到 S+ 六級喺實際分佈
        # 上面係空嘅，讀者冇辦法知道 B+ 其實已經係全場最高分。
        thresholds = {
            "S+": "≥96分 — 壓倒性數據支持，全維度表現頂尖（實測 0.0%，兩季未出現過）",
            "S": "≥92分 — 極強數據基礎，多維度顯著優勢（全體最高 0.2%）",
            "S-": "≥88分 — 非常強勢，核心維度表現突出（全體最高 0.8%）",
            "A+": "≥84分 — 前列競爭力，基本面紮實（全體最高 1.9%）",
            "A": "≥80分 — 三甲競爭力，主要維度有支持（全體最高 5.3%）",
            "A-": "≥76分 — 位置圈內，有實質競爭條件（全體最高 11.7%）",
            "B+": "≥72分 — 中上游，具備實際爭位權（全體最高 21.1%）",
            "B": "≥68分 — 中游偏上，需要條件配合（全體最高 34.4%）",
            "B-": "≥64分 — 中游，基本競爭力存在（全體最高 50.0%，即中位馬）",
            "C+": "≥60分 — 中下游，容錯空間較窄",
            "C": "≥56分 — 下游，需大幅超水準發揮",
            "C-": "≥52分 — 邊線，驚喜空間有限",
            "D": "≥48分 — 冷門，數據支持薄弱（全體最低 12.6%）",
            "E": "<48分 — 數據起步點極低，難以建立信心（全體最低 5.5%）",
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
