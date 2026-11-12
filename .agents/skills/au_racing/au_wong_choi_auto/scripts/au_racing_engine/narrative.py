"""AU 報告文字：維度判讀、證據行、優劣勢、評分透明度（由 `engine_core.RacingEngine` 搬出，EXP-20261104-02）。

`NarrativeMixin` 只係 `RacingEngine` 嘅一部分 —— 呢度嘅 method 唔會俾任何評分路徑叫（AST 呼叫圖核實），
改字眼唔會郁分數。用到嘅引擎狀態（`self.data`、`self.horse_data`、detail dict）全部喺 `engine_core` 設定。
"""
from __future__ import annotations

import re

from . import draw as _draw
from . import speed as _speed
from . import track_going as _track
from .data_prep import _record_rows
from .dimensions import DIMENSION_SPECS, LEAF_SPECS
from .matrix_mapper import MATRIX_ADVANTAGE_CUTOFF, MATRIX_FORMULAS, canonical_matrix_key
from .scoring import MATRIX_WEIGHTS, clip_score, parse_float


# 對手後續走勢字串有兩種寫法（2026-08-04 起）：
#     「出 N 次: M 勝」    —— 對手有完整往績記錄
#     「見前三 N 次: M 勝」 —— 只由對手名單推導（partial），我哋只見到佢入前三
# 兩者嘅**勝出次數都係準嘅**（我哋見到佢全部前三），所以讀「M 勝」嗰陣兩種都要接。
# 分開兩個寫法係為咗唔好講大話 —— partial 嗰批唔知佢總共出過幾多次。
#
# ⚠️ 呢個常數存在嘅原因：加咗第二種寫法之後，四處獨立嘅 regex 一齊變成
# 只認第一種，即係新增嗰批對手會**靜靜咁**被當成「冇後續」。
# 呢個 repo 已經有五次同款缺陷（見 `scraper-silent-drop-failure-mode`）。
RE_OPP_FOLLOWUP = re.compile(r"(?:出|見前三)\s*\d+\s*次:\s*(\d+)\s*勝")


_LEAF_LABELS = {spec.key: spec.label for spec in LEAF_SPECS}



class NarrativeMixin:
    def _matrix_reasoning(self, matrix_scores, feature_scores, feature_notes):
        return {
            spec.key: self._reason_bundle(
                spec.key,
                (matrix_scores.get(spec.key, spec.reasoning_score_default)
                 if spec.reasoning_score_default is not None else matrix_scores[spec.key]),
                feature_scores,
                feature_notes,
                *(spec.reasoning_components or tuple(key for key, _ in spec.leaves)),
            )
            for spec in DIMENSION_SPECS if spec.shown_in_report
        }

    def _reason_bundle(self, key, score, feature_scores, feature_notes, *component_keys):
        label = self._matrix_label(key)
        # 有啲 component 係純 context（矩陣公式內權重 = 0）—— 例如 級數分（2026-07-29
        # 退出）同 負磅分（2026-08-01 退出）。之前佢哋同真·計分項排一齊、格式一模
        # 一樣，讀者見到「級數分 60、負磅分 60」就自然當成「呢個維度全部都係 60，
        # 純噪音」。標明出嚼，維度分數點嚟先睇得明。
        scoring_leaves = {
            name for name, _weight in MATRIX_FORMULAS.get(canonical_matrix_key(key), ())
        }
        return {
            "label": label,
            "score": round(clip_score(score), 2),
            "tone": self._matrix_summary(key, score),
            "text": self._describe_matrix(key, score, feature_scores),
            "components": [
                {
                    "key": component_key,
                    "label": self._feature_label(component_key),
                    "score": round(feature_scores.get(component_key, 60), 2),
                    "note": str(feature_notes.get(component_key, "")).strip(),
                    "in_ranking": component_key in scoring_leaves,
                }
                for component_key in component_keys
            ],
            "anchors": self._matrix_anchor_lines(key),
        }

    def _describe_matrix(self, key, score, feature_scores):
        describers = {
            "stability": self._describe_stability_matrix,
            "pace_perf": self._describe_pace_perf_matrix,
            "race_shape": self._describe_race_shape_matrix,
            "jockey_trainer": self._describe_jockey_trainer_matrix,
            "class_weight": self._describe_class_weight_matrix,
            "track": self._describe_track_matrix,
            "form_line": self._describe_form_line_matrix,
            "preparation": self._describe_preparation_matrix,
        }
        describer = describers.get(key)
        if describer:
            return describer(score, feature_scores)
        return self._matrix_summary(key, score)

    def _describe_pace_perf_matrix(self, score, feature_scores):
        """Source-aware L600 evidence plus runner-level PI interpretation."""
        pace = feature_scores.get("pace_figure_score", 60)
        sec = feature_scores.get("sectional_score", 60)
        pd = getattr(self, "pace_figure_detail", {}) or {}
        pf_source = str(pd.get("source") or "unknown")
        individual_pf = pf_source.startswith("racenet_")
        has_pf = pd.get("state") == "ok"
        has_pi = bool(self._sectional_breakdown().get("has_pi"))

        if has_pf and individual_pf and pace >= 72:
            verdict = "逐駒 L600 benchmark 快過場均，個體速度證據偏強。"
        elif has_pf and individual_pf and pace <= 48:
            verdict = "逐駒 L600 benchmark 明顯慢過場均，個體速度證據偏弱。"
        elif has_pf and individual_pf:
            verdict = "逐駒 L600 benchmark 接近場均，個體速度證據中性。"
        elif has_pf and pace >= 72:
            verdict = "往績所處賽事末段環境快過場均——反映過往速度考驗，唔等於本駒個體末段。"
        elif has_pf and pace <= 48:
            verdict = "往績賽事末段環境明顯慢過場均，速度考驗旁證偏弱。"
        elif has_pf and pace <= 56:
            verdict = "往績賽事末段環境略慢過場均，速度考驗旁證冇著數。"
        elif has_pf:
            verdict = "往績賽事末段環境貼近場均，呢項旁證中性。"
        elif has_pi:
            verdict = "冇 L600 環境數據，只有 PI 位置增益作旁證，呢一格參考價值有限。"
        else:
            verdict = "段速證據不足，呢一格唔好過份解讀。"

        # 門檻對應段速分階梯（60 = 冇增益證據、75 = PI 優秀、81 = PI 極佳），
        # 2026-08-01 中性化之後重新對位（舊尺 45/55/60 喺新尺永遠唔會觸發）。
        cross = ""
        if has_pf and has_pi:
            if individual_pf and pace >= 68 and sec >= 75:
                cross = "逐駒 benchmark 同 PI 升位方向一致，個體速度證據較完整。"
            elif individual_pf and pace >= 68:
                cross = "逐駒 benchmark 偏快但 PI 平平，速度有數據、兌現度仍要保守。"
            elif individual_pf and sec >= 75:
                cross = "PI 升位靚但逐駒 benchmark 未見優勢，後勁證據未完全一致。"
            elif pace >= 68 and sec >= 75:
                cross = "快末段賽事背景下仍有 PI 升位，個體後勁旁證較完整。"
            elif pace >= 68 and sec <= 63:
                cross = "只係往績賽事末段快、PI 升位平平，唔可以當成本駒自己快。"
            elif pace < 56 and sec >= 75:
                cross = "PI 升位靚但往績賽事末段環境偏慢，位置增益要保守解讀。"

        evidence_name = "逐駒 benchmark" if individual_pf else "L600 環境"
        conf = (f"強（{evidence_name} {int(pd.get('runs') or 0)} 場）" if has_pf
                else "中（只有 PI 位置增益）" if has_pi
                else "弱（只餘試閘／無數據）")
        return " ".join(x for x in (verdict, cross, f"速度背景證據信心：{conf}。") if x)

    def _describe_stability_matrix(self, score, feature_scores):
        recent = str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()
        status = self._status_cycle_display() or "狀態週期未明"
        trend = self._deduped_trend_summary() or "近況輪廓未算鮮明"
        latest_note = self._latest_official_note_brief()
        forgiveness = self._forgiveness_brief()
        repeatability = self._repeatability_brief()
        # 缺料時直接省略該子句，唔好輸出「狀態週期未明」「輪廓未算鮮明」呢類佔位話
        status_known = bool(status) and "未明" not in status
        trend_known = bool(trend) and "未算鮮明" not in trend
        if self._career_starts() == 0:
            opener = "此駒正式賽樣本仍薄，呢一格主要靠備戰完整度、試閘交代同狀態週期去判備戰程度。"
        elif recent:
            opener = f"近績 {recent}"
            if status_known:
                opener += f"，處於{status}階段"
            if trend_known:
                opener += f"，走勢大致呈「{trend}」"
            opener += "。"
        elif status_known:
            opener = f"正式近績樣本有限，穩定性主要依賴 {status} 週期定位判斷。"
        else:
            opener = "正式近績樣本有限，穩定性主要靠試閘同備戰資料判斷。"

        quality_score = feature_scores.get(
            "performance_quality_score",
            feature_scores.get("consistency_score", 60),
        )
        if feature_scores["form_score"] >= 72 and quality_score >= 68:
            assessment = "連仗交出接近表現證明戰鬥力企穩，唔係單靠一場偶發水準撐起，具備堅實嘅爭勝底氣。"
        elif feature_scores["form_score"] <= 58 or quality_score <= 58:
            assessment = "近態未算企得好穩，評分上仍然要留低少少問號。"
        else:
            assessment = "近況有啲底，但未到可以完全放膽追捧嘅絕對穩定期。"

        if latest_note:
            assessment += f" 上仗備註：{latest_note}。"
        if forgiveness:
            assessment += f" 寬恕條件：{forgiveness}。"
        if repeatability:
            assessment += f" 同類設置下，{repeatability}。"

        return " ".join(part for part in (opener, assessment) if part)

    def _describe_race_shape_matrix(self, score, feature_scores):
        """一句檔位（同入綜合分嘅大場次檔位分一致）＋預期跑法。"""
        style = self._running_style()
        style_parts = [p.strip() for p in str(style).split("/")]
        if len(style_parts) > 1 and len(set(style_parts)) == 1:
            style = style_parts[0]
        barrier = self.horse_data.get("barrier")
        e = _draw.explain(barrier, self._field_summary().get("barriers"), self._straight_course())
        if not e["applies"]:
            draw_v = f"排 {barrier} 檔（{e['reason']}）"
        elif e["adj"] >= 0.5:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬內檔，有利（{e['adj']:+.1f}）"
        elif e["adj"] <= -0.5:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬外檔，蝕位（{e['adj']:+.1f}）"
        else:
            draw_v = f"排 {barrier} 檔，{e['n']} 匹入面屬中間（{e['adj']:+.1f}）"
        if style:
            draw_v += f"，預期「{style}」跑法"
        return draw_v + "。"

    def _describe_jockey_trainer_matrix(self, score, feature_scores):
        jockey = self._clean_identity(self.horse_data.get("jockey")) or "騎師資料未明"
        trainer = self._clean_identity(self.horse_data.get("trainer")) or "練馬師資料未明"

        # 判讀短而狠（2026-07-11 Phase C）：一句定調 → 最強訊號/主要扣分各一句，
        # 唔重覆逐項明細（明細喺評分構成 detail 攤開）。
        fit = feature_scores["jockey_horse_fit_score"]
        j_s = feature_scores["jockey_score"]
        t_s = feature_scores["trainer_score"]
        adjs = (self.jt_fit_detail or {}).get("adjustments") or []
        top_pos = max((a for a in adjs if a.get("delta", 0) > 0),
                      key=lambda a: a["delta"], default=None)
        top_neg = min((a for a in adjs if a.get("delta", 0) < 0),
                      key=lambda a: a["delta"], default=None)
        combo = f"由 {jockey} 配 {trainer}。"
        if fit >= 74:
            assessment = "騎練部署積極，人馬熟習度同備戰方向一致——有出擊意圖嘅配置。"
        elif fit <= 55 or (top_neg and top_neg.get("delta", 0) <= -3):
            assessment = "人馬部署有保留位，注碼上唔好當佢係主動出擊。"
        elif j_s >= 68 and t_s >= 66:
            assessment = "騎練有牌面，但同呢匹馬未見專屬默契。"
        elif j_s <= 58 and t_s <= 58:
            assessment = "騎練牌面平平，呢一格幫唔到手，要靠馬匹自己交代。"
        else:
            assessment = "人馬配置中性，未見明顯部署訊號。"
        if top_pos:
            assessment += f" 最強訊號：{top_pos['factor']}（{top_pos['delta']:+.1f}）。"
        if top_neg:
            assessment += f" 主要扣分：{top_neg['factor']}（{top_neg['delta']:+.1f}）。"
        # 歷來配套/最佳配搭/換騎/同場樣本等原始證據已喺數據錨點逐行列出，判讀唔重覆。
        return " ".join(part for part in (combo, assessment) if part)

    def _describe_class_weight_matrix(self, score, feature_scores):
        """一句今場班次／負磅 → 一句能力對位結論。逐項計法喺評分構成 detail 攤開。"""
        class_move = self._class_move_display()
        weight = parse_float(self.horse_data.get("weight"))
        cs = feature_scores["class_score"]
        rs = feature_scores["rating_score"]

        head = f"今仗 {self._race_class_text()}"
        if weight is not None:
            head += f"，負 {weight:.1f}kg{self._weight_allowance_suffix()}"
        if "降班" in class_move:
            head += "，今場班次較上仗低"
        elif "升班" in class_move:
            head += "，今場班次較上仗高"
        head += "。"

        # 維度 = 0.70 評分分 + 0.15 級數分（class_rating）；負磅分只做顯示。
        if rs >= 66:
            verdict = "官方讓磅分對位高過場均，能力面有實質支持。"
        elif rs <= 54:
            verdict = "官方讓磅分對位低過場均，能力面要靠其他維度補。"
        else:
            verdict = "能力對位貼近場均，未見明顯阻力亦未見甜頭。"
        if cs <= 56:
            verdict += f" 級數分 {cs:.0f} 偏低。"
        elif cs >= 65:
            verdict += f" 級數分 {cs:.0f} 偏高。"
        return head + " " + verdict

    def _describe_track_matrix(self, score, feature_scores):
        """短而狠：場地/地狀適應一句定調 ＋（濕地）風險一句。逐項計法喺評分構成攤開。"""
        ts = feature_scores["track_score"]
        wet_state = self._wet_state()
        if ts >= 70:
            verdict = "同場/今日地狀有實績支持，場地唔會成為絆腳石。"
        elif ts <= 54:
            verdict = "場地/地狀往績未見支持，發揮要打折睇。"
        elif not any(_track.track_score(self._track_records(), self._today_going())[1:]):
            verdict = "冇同場／今日地況往績，場地分維持中性。"
        else:
            verdict = "場地適應有基礎，應付到今日地狀。"
        if wet_state in {"soft7plus", "heavy"} and not self._has_verified_wet_place():
            verdict += " 爛地實績未經驗證（唔扣分：未跑過濕地嘅馬實測只差 −1.2pp）。"
        return verdict

    def _describe_form_line_matrix(self, score, feature_scores):
        formline = self._formline_level() or "賽績線摘要未明"
        latest_formal = self._latest_record_summary("正式")
        headwinner = self._formline_headwinner()
        followup = self._formline_followup_brief()

        # 純參考維度：權重 0，唔入綜合戰力分／排名（已 ML 驗證無上位訊號）。
        tag = "（僅供參考，不計入排名）"
        if feature_scores["formline_score"] >= 72:
            assessment = f"賽績線屬「{formline}」級別，對手線有強勁承接{tag}。"
        elif feature_scores["formline_score"] <= 56:
            assessment = f"賽績線級別評為「{formline}」，對手後續支持力弱{tag}。"
        else:
            assessment = f"賽績線屬「{formline}」級別，對手線有一定參考價值{tag}。"

        # 兌現度（franking）一句總結：對手其後有冇再贏，係條線可唔可信嘅關鍵
        all_rows = self._formline_rows()
        # 只計有效行（跳過查冊失敗嘅延續行），同數據錨點嘅明細表口徑一致
        rows = [r for r in all_rows
                if not (str(r.get("date", "")).strip() in {"查冊失敗", "-", ""} and not str(r.get("opponent", "")).strip())]
        frank = ""
        if rows:
            wins = 0
            failed = 0
            for row in rows:
                nr = str(row.get("next_result", ""))
                m = RE_OPP_FOLLOWUP.search(nr)
                if m and int(m.group(1)) > 0:
                    wins += 1
                if "查冊失敗" in nr:
                    failed += 1
            if wins >= 2:
                frank = f"兌現度高：{len(rows)} 個對手當中 {wins} 個其後再勝，條線已受賽果驗證。"
            elif wins == 1:
                frank = f"{len(rows)} 個對手當中有 1 個其後再勝，條線有基本背書。"
            elif failed == len(rows):
                frank = f"{len(rows)} 個對手嘅後續查冊失敗，兌現度暫時無法驗證。"
            else:
                frank = f"{len(rows)} 個對手其後未有再勝，條線暫未有賽果背書。"

        details = []
        if headwinner:
            details.append(f"曾直接交手嘅頭馬：{headwinner}。")
        # 最近正式賽果同對手後續摘要已喺「數據」錨點列出，判讀唔重覆

        return " ".join(part for part in (assessment, frank, " ".join(details)) if part)

    def _speed_evidence_brief(self):
        """L600 環境分每一仗用咗乜（speed.evidence）：賽事 L600 對基準、輸距、本駒估算、權重。"""
        metrics = self._pf_metrics() or {}
        source = str((metrics.get("pf_aggregates") or {}).get("source") or "")
        parts = []
        for run in _speed.evidence(metrics.get("pf_runs") or [], source):
            where = " ".join(str(x) for x in (run["date"], run.get("venue"),
                                               f"{run['distance']}m" if run.get("distance") else None) if x)
            if run["own"] is not None:
                body = f"賽事 {run['race']:+.2f}s、輸 {float(run['margin']):.1f}L → 本駒 {run['own']:+.2f}s"
            else:
                body = f"賽事 {run['race']:+.2f}s"
            parts.append(f"{where}：{body}（×{run['weight']:.2f}）")
        return "；".join(parts)

    def _matrix_anchor_lines(self, key):
        if key == "stability":
            return self._anchor_lines(
                ("近績序列", str(self.data.get("recent_form") or self.horse_data.get("recent_form") or "").strip()),
                ("Last 10 / 警告", str(self.data.get("warning_line") or self.data.get("last10_raw") or "").strip()),
                ("狀態週期", self._status_cycle_display()),
                ("趨勢總評", self._deduped_trend_summary()),
                ("寬恕因素", self._forgiveness_brief()),
                ("上仗註腳", self._latest_official_note_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
                ("試閘交代", self._trial_summary_text()),
            )
        if key == "pace_perf":
            # 逐項計法已喺評分構成 detail 攤開，錨點只留原始證據
            return self._anchor_lines(
                ("逐仗證據（新→舊，負數＝快過基準）", self._speed_evidence_brief()),
                ("近段 PI 走勢", self._sectional_trend_brief()),
                ("試閘交代", self._trial_summary_text()),
            )
        if key == "race_shape":
            # 跑法資訊合併成一條（標籤＋信心），唔再分開出 跑法信心／style evidence／預計走法；
            # 戰術劇本明確標示係「跑法×檔位模板」，唔係實測 trip。
            return self._anchor_lines(
                ("預期跑法", self._run_style_brief()),
                ("近仗 Settled Pattern", self._recent_settled_pattern_brief()),
                ("賽道幾何配套", self._track_fit_brief()),
                ("戰術劇本（跑法×檔位推演·非實測）", self._tactical_scenario_text()),
            )
        if key == "jockey_trainer":
            return self._anchor_lines(
                ("Section內部權重", self._jockey_trainer_weights_text()),
                ("騎師 / 練馬師", self._jockey_trainer_pair_text()),
                ("人馬歷史", self._current_jockey_history_brief()),
                ("上仗正式賽騎師", self._latest_official_jockey_brief()),
                ("歷來最佳配搭", self._best_jockey_history_brief()),
                ("今場 vs 歷來最佳", self._current_vs_best_jockey_brief()),
                ("換騎訊號", self._jockey_change_signal()),
                ("同場騎練組合", self._track_combo_brief()),
                ("馬房場館履歷", self._trainer_track_brief()),
                ("已知合作騎師", self._known_jockeys_brief()),
                ("試閘交代", self._trial_summary_text()),
                ("狀態週期", self._status_cycle_display()),
                ("首次/二次上陣往績", str(self.data.get("stage_stats_line") or "").strip()),
            )
        if key == "class_weight":
            return self._anchor_lines(
                ("今場班次", self._race_class_text()),
                ("班次變動", self._class_move_display()),
                ("官方 Rating", self._horse_rating_text()),
                ("Rating 對位", self._field_rating_brief()),
                ("負磅", self._weight_text()),
                ("場內磅差", self._field_weight_brief()),
                ("生涯背景", str(self.data.get("career_record_line") or "").strip()),
                ("上仗結果(Racecard)", str(self.data.get("last_finish_line") or "").strip()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        if key == "track":
            return self._anchor_lines(
                ("場地/路線紀錄", str(self.data.get("track_record_line") or "").strip()),
                ("地狀分拆", str(self.data.get("going_stats_line") or "").strip()),
                ("今場掛牌", self._today_going()),
                ("濕地血統", self._wet_bloodline_signal()),
                ("今日場地偏差", self._meeting_bias_brief()),
                ("賽道幾何", self._track_geometry_brief()),
                ("路段提示", self._track_distance_note_brief()),
                ("跑法/檔位配套", self._track_fit_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        if key == "preparation":
            ts = getattr(self, "trial_speed_detail", None) or {}
            return self._anchor_lines(
                ("試閘交代", self._trial_summary_text()),
                ("試閘密度加分", "、".join(f"{a['factor']} {a['delta']:+.2f}（{a['evidence']}）"
                                        for a in self.preparation_parts)),
                ("試閘 L600", "" if ts.get("raw") is None else
                 f"本駒 {ts['raw']:+.2f} 秒，同場 {ts.get('field_count', 0)} 匹均值 {ts.get('mean'):+.2f} 秒"
                 if ts.get("mean") is not None else f"本駒 {ts['raw']:+.2f} 秒（同場可比少過 3 匹）"),
                ("狀態週期", self._status_cycle_display()),
            )
        if key == "form_line":
            return self._anchor_lines(
                ("賽績線級別", self._formline_level()),
                ("頭馬", self._formline_headwinner()),
                ("對手後續摘要", self._formline_followup_brief()),
                ("最近正式賽果", self._latest_record_summary("正式")),
            )
        return []

    def _describe_preparation_matrix(self, score, feature_scores):
        """一句講試閘密度同試閘速度各自點計（EXP-20261104-01：以前冇判讀，dashboard 只見罐頭句）。"""
        parts = self.preparation_parts
        dens = ("試閘密度：" + "、".join(f"{a['factor']}（{a['delta']:+.1f}）" for a in parts)) if parts \
            else "試閘密度未見加分（試閘課數或前列次數唔夠）"
        ts = getattr(self, "trial_speed_detail", None) or {}
        ts_score = feature_scores.get("trial_speed_score", 60)
        if not ts.get("applies", True):
            speed = "正式賽已有 6 場或以上，試閘速度唔計"
        elif ts.get("z") is None:
            speed = "試閘 L600 數據唔夠，試閘速度中性"
        else:
            speed = f"試閘 L600 {'快過' if ts['z'] < 0 else '慢過'}同場（試閘 L600 分 {ts_score:.1f}）"
        return f"{dens}；{speed}。"

    def _anchor_lines(self, *items):
        lines = []
        for label, value in items:
            text = str(value or "").strip()
            if text:
                lines.append(f"{label}: {text}")
        return lines

    def _matrix_label(self, key):
        from .dimensions import MATRIX_LABELS
        if key in MATRIX_LABELS:
            return MATRIX_LABELS[key]
        return {
            "stability": "近績穩定性",
            "pace_perf": "速度考驗背景",
            # 舊 key 保留畀歷史 Logic 檔顯示
            "sectional": "段速與引擎",
            "pace_figure": "往績賽事 L600 環境",
            "race_shape": "檔位形勢",
            "jockey_trainer": "騎練訊號",
            "class_level": "級數門檻",
            "weight_pressure": "負磅壓力",
            "class_weight": "官方評分對位",
            "track": "場地與地況適性",
            "form_line": "賽績線",
            "preparation": "試閘備戰",
        }.get(key, key)

    def _feature_label(self, key):
        """leaf 中文名一律由 `dimensions.LEAF_SPECS` 攞（唯一真源；以前手抄漏咗三個新 leaf）。"""
        return _LEAF_LABELS.get(key, key)

    def _matrix_summary(self, key, score):
        label = self._matrix_label(key)
        if score >= 74:
            return f"{label} 係今場其中一條主要支柱"
        if score >= 68:
            return f"{label} 屬正面支撐範圍"
        if score <= 55:
            return f"{label} 仍然係主要保留位"
        return f"{label} 暫時只算中性參考"

    def _au_grade_computation_transparency(self, matrix_scores, matrix_bands, feature_scores,
                                           base_7d_score, ability_score, grade,
                                           feature_notes=None, wet_form_feature=0.0,
                                           class_proof_feature=0.0, full_time_speed_feature=0.0,
                                           draw_feature=0.0):
        """Generate the six-dimension ranking walkthrough.

        ``base_7d_score`` is retained as a legacy archive field name.  The live
        ranking registry has six dimensions; ``form_line`` is report-only.
        """
        # 舊「核心/半核心/輔助」角色標籤已死（同實際權重脫節，輸出表亦唔再印）；
        # 直接用 _matrix_label ＋ 實際權重，權重百分比先係唯一真相。
        dims = [(key, self._matrix_label(key), float(MATRIX_WEIGHTS.get(key, 0.0))) for key in MATRIX_WEIGHTS]
        rows = []
        lines = []
        weighted_sum = 0.0
        for key, label, weight in dims:
            raw_score = float(matrix_scores.get(key, 60))
            band = matrix_bands.get(key, "➖")
            contribution = round((raw_score - 60.0) * weight, 2)
            weighted_sum += contribution
            rows.append({"key": key, "label": label, "score": round(raw_score, 2),
                         "weight": weight, "contribution": contribution, "band": band})
            # 拿走 [核心/半核心/輔助] 標籤：權重百分比已經表達咗重要性，標籤多餘。
            lines.append(f"| {label} | {raw_score:.1f} | {weight:.4f} | {contribution:+.2f} | {band} |")
        table = "\n".join([
            "| 維度 | 得分 | 合成係數 | 相對60分的貢獻 | 判定 |",
            "|:---|---:|---:|---:|:---:|",
            *lines,
        ])
        # 每個 overlay 屬於一個維度嘅題目（renderer.OVERLAYS）。濕地往績調整同場地維度用同一批
        # 軟／重地往績（EXP-20261113-21：兩份都要留 —— 剷任何一份 Gold 都跌），所以要擺埋一齊
        # 睇：「呢匹馬場地／地況總共攞幾多」。純顯示，唔改任何分數。
        overlay_values = {"track": ("濕地往績調整", wet_form_feature),
                          "class_weight": ("高班實績證明", class_proof_feature),
                          "pace_perf": ("逐駒全程速度", full_time_speed_feature),
                          "race_shape": ("大場次檔位", draw_feature)}
        contrib = {row["key"]: row["contribution"] for row in rows}
        grouped = []
        for key, (olabel, value) in overlay_values.items():
            value = float(value or 0.0)
            if abs(value) < 0.005:
                continue
            if key not in contrib:   # 冇六維係數（檔位形勢）：成份都係個調整
                grouped.append(f"{self._matrix_label(key)} {value:+.2f}（全部來自{olabel}）")
                continue
            dim = contrib[key]
            grouped.append(f"{self._matrix_label(key)} {dim + value:+.2f}"
                           f"（維度 {dim:+.2f} ＋ {olabel} {value:+.2f}）")
        group_line = ("\n**🧩 按維度合計（維度貢獻＋屬於佢嘅調整）：** " + "；".join(grouped) + "\n"
                      if grouped else "")
        summary = (
            f"{table}\n{group_line}\n"
            f"**→ 60 ＋ 各項貢獻 = {base_7d_score:.2f} 分；"
            f"濕地往績調整 {float(wet_form_feature):+.2f}；"
            f"高班實績證明 {float(class_proof_feature):+.2f}；"
            f"逐駒全程速度 {float(full_time_speed_feature):+.4f}；"
            f"大場次檔位 {float(draw_feature):+.2f}；"
            f"綜合戰力分 = {ability_score:.2f} 分 → Grade = [{grade}]**"
        )
        # 有計但唔直接入六維公式嘅分數 — 一併展示，唔收埋
        ref_bits = []
        # confidence_score 計嘅係資料錨點數目（30 ＋ 4×有值欄位…），唔係預測信心 → 叫「資料覆蓋分」。
        for ref_key, ref_label in (("distance_score", "路程分"), ("confidence_score", "資料覆蓋分")):
            val = feature_scores.get(ref_key)
            if isinstance(val, (int, float)):
                ref_bits.append(f"{ref_label} {float(val):.1f}")

        # 備戰完整度分 2026-08-21 實測（300 場）：場內 SD **0.89**，19% 嘅馬恰好 60.0。
        # 佢自己每項調整只有 ±0.3..±2.0 分，而 band 界線喺 55 / 70 —— 即係呢個數字
        # 數學上永遠出唔到 ➖ 以外，印出嚟等於冇資訊。但佢個 note（「近績有獸醫/
        # 健康疑點」「久休 N 日而缺少試閘時間支撐」）係真有料嘅。
        # 所以：唔再印個無意義嘅數，改為只喺真有訊號觸發時出佢講咗咩。
        health = feature_scores.get("health_score")
        if isinstance(health, (int, float)) and abs(float(health) - 60.0) >= 1.0:
            note = str((feature_notes or {}).get("health_score") or "").strip()
            # note 形如「近績有獸醫/健康疑點；久休 120 日…。健康/備戰分 56.0。」
            # 只要最前面嗰段講原因嘅字，唔要尾巴嗰個分數。
            reason = note.split("。")[0].strip(" ；")
            skip = ("未見明確健康或備戰扣分訊號", "")
            if reason and reason not in skip:
                direction = "⚠️" if float(health) < 60.0 else "＋"
                # health_score 唯一輸入係距上仗日數 → 叫「出賽間隔」，唔好叫「備戰」。
                ref_bits.append(f"出賽間隔 {direction}{reason}")
        if ref_bits:
            from .dimensions import ranking_dimension_numeral
            summary += f"\n**📎 參考分（不直接入{ranking_dimension_numeral(MATRIX_WEIGHTS)}維公式）：** " + "、".join(ref_bits)
        if self.risk_flags:
            flag_descriptions = []
            for flag in sorted(set(self.risk_flags)):
                desc = self._au_risk_flag_description(flag)
                if desc:
                    flag_descriptions.append(f"  - {desc}")
            if flag_descriptions:
                summary += "\n\n**⚠️ 風險標記:**\n" + "\n".join(flag_descriptions)
        return {"detail_lines": lines, "rows": rows, "weighted_sum": round(weighted_sum, 2), "summary": summary}

    def _jockey_trainer_weights_text(self):
        """由 MATRIX_FORMULAS 生成，唔好再寫死（舊字串 28/20/52 同真公式 33/29/38 唔一樣）。"""
        names = {"jockey_score": "騎師", "trainer_score": "練馬師", "jockey_horse_fit_score": "人馬配搭"}
        parts = MATRIX_FORMULAS.get("jockey_trainer") or ()
        total = sum(float(w) for _, w in parts) or 1.0
        return " / ".join(f"{names.get(k, k)} {float(w) / total:.1%}" for k, w in parts)

    def _au_risk_flag_description(self, flag):
        mapping = {
            "form_flattered": "近仗有場次名次好睇但實際居後半或輸超過 5 個馬位（只作標示，不入分）",
            "high_consumption_load": "近仗走位消耗偏高，末段續航能力要再觀察",
            "top_weight": "頂磅環境要自己讓人，發揮要求更高",
            "pace_burn_risk": "若早段互燒，末段有機會先消耗後失速",
            "distance_unproven": "路程仍未正式證明，末端續航力未可完全信任",
            "debut_form_neutral": "初出馬缺正式賽經驗，變數自然較大",
            "debut_distance_unproven": "初出馬未經路程實戰驗證",
            "trial_no_recent_top3": "近三課有名次嘅試閘全部未入前三，備戰交代偏弱",
            "surface_transfer_unverified": "近仗包含另一種跑道；草地與合成跑道成績不能直接等同",
        }
        return mapping.get(flag, flag)

    def _status_cycle_display(self):
        inferred = self._preparation_cycle().get('label')
        if inferred:
            return inferred
        value = self._status_cycle_text()
        return {
            "First-up": "久休復出",
            "Second-up": "二出",
            "Third-up": "第三仗",
            "Deep Prep": "長期作戰期",
        }.get(value, value)

    def _deduped_trend_summary(self):
        trend = str(self.horse_data.get("trend_summary") or "").strip()
        status = self._status_cycle_display() or ""
        if not trend:
            return ""
        compact_trend = trend.replace("休後復出", "久休復出").replace("長休復出", "久休復出")
        if status and (compact_trend == status or compact_trend in status or status in compact_trend):
            return ""
        return trend

    def _running_style(self):
        text = str(self.data.get("running_style_line") or "").strip()
        if not text or any(token in text for token in self.UNMEASURED_STYLES):
            return ""
        return text

    def _predicted_style(self):
        """Tactical position read (前置／守好位／守中／後上) + the WHY, for the 數據判讀.
        Reference only — never enters the rating matrix. Uses the pre-computed
        running_style_line / tactical_plan; WHY comes from the race scenario."""
        raw = self._running_style()
        token = ""
        for cand in ("前領", "前置", "居中前", "跟前", "守好位", "中後", "後上",
                     "守中", "中段", "居中"):
            if cand in str(raw):
                token = cand
                break
        if not token:
            return None
        label_map = {"前領": "前置", "前置": "前置", "居中前": "守好位", "跟前": "守好位",
                     "守好位": "守好位", "中後": "後上", "後上": "後上",
                     "守中": "守中", "中段": "守中", "居中": "守中"}
        label = label_map.get(token, token)
        conf = re.sub(r"^.*?[:：]", "", self._style_confidence()).strip() or self._style_confidence().strip()
        why_bits = []
        scenario = self._tactical_scenario_text()
        if scenario:
            why_bits.append(scenario)
        else:
            shape = self._recent_settled_pattern_brief()
            if shape:
                why_bits.append(f"近仗走位：{shape}")
        return {"label": label, "conf": conf, "why": "；".join(why_bits)}

    def _latest_official_note_brief(self):
        latest = self._official_entries()[0] if self._official_entries() else {}
        flags = self._entry_note_flags(latest)
        parts = []
        if flags["positive"]:
            parts.append(" / ".join(flags["positive"][:3]))
        if flags["negative"]:
            parts.append("風險: " + " / ".join(flags["negative"][:2]))
        return "；".join(parts)

    def _latest_official_jockey_formal_wins(self):
        return int(parse_float(self.data.get("latest_official_jockey_formal_wins")) or 0)

    def _track_combo_brief(self):
        stats = self._current_track_combo_stats()
        venue = self._current_venue_name()
        if not stats or not venue:
            return ""
        place_rate = stats.get("place_rate", 0.0) * 100
        return f"{venue} 同場騎練 {stats.get('runs', 0)} 次，{stats.get('wins', 0)} 勝 {stats.get('places', 0)} 次上名，上名率 {place_rate:.0f}%"

    def _trainer_track_brief(self):
        stats = self._trainer_track_stats()
        venue = self._current_venue_name()
        if not stats or not venue:
            return ""
        place_rate = stats.get("place_rate", 0.0) * 100
        return f"{venue} 場館下馬房累積 {stats.get('runs', 0)} 次，{stats.get('wins', 0)} 勝 {stats.get('places', 0)} 次上名，上名率 {place_rate:.0f}%"

    def _best_formal_jockey_places(self):
        return int(parse_float(self.data.get("best_formal_jockey_places")) or 0)

    def _best_formal_jockey_wins(self):
        return int(parse_float(self.data.get("best_formal_jockey_wins")) or 0)

    def _best_jockey_history_brief(self):
        direct = str(self.data.get("best_jockey_history_line") or "").strip()
        if direct:
            return direct
        jockey = self._best_formal_jockey()
        rides = self._best_formal_jockey_rides()
        places = self._best_formal_jockey_places()
        wins = self._best_formal_jockey_wins()
        if not jockey or not rides:
            return ""
        if wins > 0:
            return f"{jockey} 曾策 {rides} 次，錄得 {wins} 勝 {places} 入位，為此馬歷來最有依據的配搭"
        if places > 0:
            return f"{jockey} 曾策 {rides} 次，錄得 {places} 次上名，配搭有一定穩定性"
        return f"{jockey} 曾策 {rides} 次，數據偏弱"

    def _known_jockeys_brief(self):
        return str(self.data.get("known_jockeys_line") or "").strip()

    def _latest_official_jockey_brief(self):
        latest = self._latest_official_jockey()
        rides = self._latest_official_jockey_formal_rides()
        places = self._latest_official_jockey_formal_places()
        wins = self._latest_official_jockey_formal_wins()
        if not latest:
            return ""
        if not rides:
            return latest
        return f"{latest} 曾策正式賽 {rides} 次，{wins} 勝 {places} 上名"

    def _sire_line(self):
        return str(self.data.get("sire_line") or "").strip()

    def _wet_bloodline_signal(self):
        sire = self._sire_line()
        if not sire:
            return ""
        positive = ("So You Think", "Savabeel", "Dundeel", "Tavistock")
        negative = ("Snitzel", "Rubick")
        if any(token in sire for token in positive):
            return "濕地血統偏正面"
        if any(token in sire for token in negative):
            return "濕地血統偏保留"
        return ""

    def _track_geometry_brief(self):
        profile = self._track_profile()
        venue = str(profile.get("venue") or self._meeting_intelligence().get("venue") or "").strip()
        parts = []
        if venue:
            parts.append(venue)
        straight_m = int(parse_float(profile.get("straight_m")) or 0)
        circumference_m = int(parse_float(profile.get("circumference_m")) or 0)
        dims = []
        if circumference_m:
            dims.append(f"周長 {circumference_m}m")
        if straight_m:
            dims.append(f"直路 {straight_m}m")
        if dims:
            parts.append(" / ".join(dims))
        traits = []
        for item in profile.get("key_traits") or []:
            clean = str(item).strip()
            if not clean:
                continue
            clean = clean.replace("Tight-turning 急彎賽道", "急彎賽道")
            clean = clean.replace("On-Pace BIAS 前領偏差", "前置偏差")
            clean = clean.replace("On-Pace Bias 前領偏差", "前置偏差")
            traits.append(clean)
        if traits:
            parts.append(" / ".join(traits[:2]))
        if len(parts) <= 1:
            # 淨係得場地名 = 呢個場地冇任何幾何資料。報一個孤零零嘅名等於話
            # 「有資料」，所以直接唔出呢行（`_anchor_lines` 會 drop 空字串）。
            return ""
        return " | ".join(parts)

    def _track_distance_note_brief(self):
        return str(self._track_context().get("distance_note") or "").strip()

    def _track_fit_brief(self):
        context = self._track_context()
        style = self._running_style()
        barrier = parse_float(self.horse_data.get("barrier"))
        bits = []
        if context.get("front_bias"):
            if any(token in style for token in ("前", "跟前", "居中前")):
                bits.append("跑法同偏前置場地輪廓相對對位")
            elif any(token in style for token in ("後", "中後")):
                bits.append("跑法要克服偏前置場地輪廓")
        if barrier is not None:
            if context.get("inside_advantage") and barrier <= 4:
                bits.append("內檔可放大省位價值")
            elif context.get("outside_penalty") and barrier >= 9:
                bits.append("外檔仍有額外走位成本")
        if context.get("short_straight") and any(token in style for token in ("後", "中後", "後上")):
            bits.append("短直路令後追 timing 更緊")
        if not bits and context.get("fair_track"):
            bits.append("場地整體偏公平，主要睇自身適性")
        return "；".join(bits)

    def _has_verified_wet_place(self):
        return _track.has_wet_place(self._track_records())

    def _run_style_brief(self):
        """單一 canonical 跑法顯示：clean 標籤（前置／守好位／守中／後上）＋信心。
        取代舊有分散嘅 跑法信心 / style evidence / 預計走法 三條重覆欄位，
        亦統一咗之前三個函數各自俾出唔同字串嘅問題。"""
        ps = self._predicted_style()
        if ps and ps.get("label"):
            label, conf = ps["label"], (ps.get("conf") or "")
        else:
            label = self._running_style().strip()
            conf = re.sub(r"^.*?[:：]", "", self._style_confidence()).strip()
        if not label:
            return ""
        return f"{label}（信心{conf}）" if conf else label

    def _formguide_shape_stats(self):
        if self._formguide_shape_cache is not None:
            return self._formguide_shape_cache
        stats = {
            "settled_pattern": str(self.data.get("recent_settled_pattern_line") or "").strip(),
            "pos400_pattern": str(self.data.get("recent_400_pattern_line") or "").strip(),
            "consensus_bucket": str(self.data.get("recent_shape_consensus") or "").strip(),
            "consensus_count": int(parse_float(self.data.get("recent_shape_consensus_count")) or 0),
            "entropy": int(parse_float(self.data.get("recent_shape_entropy")) or 0),
            "front_count": int(parse_float(self.data.get("recent_shape_front_count")) or 0),
            "mid_count": int(parse_float(self.data.get("recent_shape_mid_count")) or 0),
            "back_count": int(parse_float(self.data.get("recent_shape_back_count")) or 0),
            "inside_count": int(parse_float(self.data.get("recent_shape_inside_count")) or 0),
            "wide_no_cover_count": int(parse_float(self.data.get("recent_shape_wide_no_cover_count")) or 0),
            "early_work_count": int(parse_float(self.data.get("recent_shape_early_work_count")) or 0),
            "summary_line": str(self.data.get("recent_shape_summary_line") or "").strip(),
        }
        self._formguide_shape_cache = stats
        return stats

    def _recent_settled_pattern_brief(self):
        stats = self._formguide_shape_stats()
        parts = []
        if stats["settled_pattern"]:
            parts.append(f"Settled {stats['settled_pattern']}")
        if stats["summary_line"]:
            parts.append(stats["summary_line"])
        return "；".join(parts)

    def _trial_summary_text(self):
        trial_count = int(parse_float(self.data.get("trial_count")) or len(self._trial_places()))
        trial_top3 = int(parse_float(self.data.get("trial_top3_count")) or sum(1 for place in self._trial_places() if place <= 3))
        if trial_count <= 0:
            return ""
        return f"共 {trial_count} 次試閘，其中 {trial_top3} 次跑入前三"

    def _field_weight_delta(self):
        weight = parse_float(self.horse_data.get("weight"))
        field = self._field_summary()
        if weight is None or not field:
            return {}
        max_weight = parse_float(field.get("max_weight"))
        avg_weight = parse_float(field.get("avg_weight"))
        min_weight = parse_float(field.get("min_weight"))
        return {
            # `to_top` keeps the field-minus-horse convention because its label
            # spells the direction out ("較頂磅**輕** X kg").
            "to_top": (max_weight - weight) if max_weight is not None else None,
            # `to_avg` was ALSO field-minus-horse, but it is rendered with a bare
            # signed label ("較場均 +X kg") which reads as the horse's deviation —
            # so every sign was printed backwards.  2026-08-22 Randwick R1 made it
            # self-contradictory on one row: Call Me Sassy carried 52.0kg in a field
            # averaging 56.41kg and topped at 60.0kg, and the report said
            # "較頂磅輕 8.0kg；較場均 **+4.4kg**" — 8kg below the top weight yet
            # somehow 4.4kg above the average.  Gunroom (59.0kg) printed "-2.6kg"
            # when it was carrying 2.59kg MORE than the field.
            # Horse-minus-field, matching `_field_rating_delta` directly below and
            # `to_bottom` in this same dict.  Display-only: the sole consumer is
            # `_field_weight_brief`, and `weight_score` left the ranking matrix on
            # 2026-07-30, so no score moves.
            "to_avg": (weight - avg_weight) if avg_weight is not None else None,
            "to_bottom": (weight - min_weight) if min_weight is not None else None,
        }

    def _weight_allowance_suffix(self):
        """`（見習減 1.5kg，實負 59.5kg）`／`（超磅 0.5kg，實負 53.5kg）`；冇調整回空字串。"""
        allowance = parse_float(self.horse_data.get("jockey_allowance_kg")) or 0.0
        carried = parse_float(self.horse_data.get("carried_weight"))
        if not allowance or carried is None:
            return ""
        label = "見習減" if allowance < 0 else "超磅"
        return f"（{label} {abs(allowance):g}kg，實負 {carried:.1f}kg）"

    def _weight_text(self):
        # `weight` = 分配負磅；騎師調整只喺後綴顯示。
        weight = parse_float(self.horse_data.get("weight"))
        if weight is None:
            return ""
        return f"{weight:.1f}kg{self._weight_allowance_suffix()}"

    def _field_weight_brief(self):
        delta = self._field_weight_delta()
        if delta.get("to_top") is None:
            return ""
        parts = []
        if delta["to_top"] is not None:
            parts.append(f"較頂磅輕 {delta['to_top']:.1f}kg")
        if delta.get("to_avg") is not None:
            sign = "+" if delta["to_avg"] > 0 else ""
            parts.append(f"較場均 {sign}{delta['to_avg']:.1f}kg")
        return "；".join(parts)

    def _horse_rating_text(self):
        rating = self._horse_rating()
        return f"{rating:.1f}" if rating is not None else ""

    def _field_rating_delta(self):
        rating = self._horse_rating()
        field = self._field_summary()
        if rating is None or not field:
            return {}
        avg_rating = parse_float(field.get("avg_rating"))
        top3_cutoff = parse_float(field.get("top3_rating_cutoff"))
        rating_stdev = parse_float(field.get("rating_stdev"))
        return {
            "to_avg": (rating - avg_rating) if avg_rating is not None else None,
            "to_top3": (rating - top3_cutoff) if top3_cutoff is not None else None,
            "stdev": rating_stdev if rating_stdev is not None else None,
        }

    def _field_rating_brief(self):
        delta = self._field_rating_delta()
        rating = self._horse_rating()
        if rating is None:
            return ""
        parts = [f"今場評分 {rating:.1f}"]
        if delta.get("to_avg") is not None:
            sign = "+" if delta["to_avg"] > 0 else ""
            parts.append(f"較場均 {sign}{delta['to_avg']:.1f}")
        if delta.get("to_top3") is not None:
            if delta["to_top3"] >= 0:
                parts.append("已達場內前三 rating 門檻")
            else:
                parts.append(f"離前三 rating 門檻差 {abs(delta['to_top3']):.1f}")
        return "；".join(parts)

    def _l400_text(self):
        l400 = parse_float(self.horse_data.get("raw_l400") or self.data.get("raw_l400"))
        if l400 is None:
            return ""
        return f"{l400:.2f} 秒"

    def _jockey_trainer_pair_text(self):
        jockey = self._clean_identity(self.horse_data.get("jockey"))
        trainer = self._clean_identity(self.horse_data.get("trainer"))
        if jockey and trainer:
            return f"{jockey} / {trainer}"
        return jockey or trainer

    @staticmethod
    def _clean_trend_label(raw):
        # 顯示用：剝走 bleed 入趨勢標籤嘅 L400 子句 / 重覆「→ 趨勢:」，scoring cache 不受影響。
        first = re.split(r"\s*[-–—]\s*L400|L400 PI|；", str(raw or ""))[0]
        return first.strip() or "未明"

    def _sectional_trend_brief(self):
        # 只出一條 PI 序列（定位→終點）＋趨勢；舊版同時印 PI 同 L400 PI 兩條近乎一樣嘅序列，重覆。
        trends = self._sectional_trends()
        values = trends.get("pi_values") or trends.get("l400_values")
        raw = trends.get("pi_trend") if trends.get("pi_values") else trends.get("l400_trend")
        if not values:
            return ""
        seq = ", ".join(str(int(v)) if float(v).is_integer() else str(v) for v in values)
        return f"PI {seq}（{self._clean_trend_label(raw)}）"

    def _formline_followup_brief(self):
        rows = self._formline_rows()
        if not rows:
            return ""
        wins = 0
        for row in rows:
            result = row.get("next_result", "")
            match = RE_OPP_FOLLOWUP.search(result)
            if match and int(match.group(1)) > 0:
                wins += 1
        if wins == 0:
            return "對手後續暫未見明顯贏馬延續"
        counts = self._formline_followup_counts()
        parts = []
        if counts["higher"] > 0:
            parts.append(f"當中 {counts['higher']} 匹對手其後升上更高班出賽，對手成色有正面指標")
        if counts["same"] > 0:
            parts.append(f"{counts['same']} 匹對手其後繼續同班角逐，對手線有基本延續")
        if counts["lower"] > 0:
            parts.append(f"{counts['lower']} 匹對手其後要降班出賽，支持力度較有限")
        if not parts:
            parts.append(f"對手後續有 {wins} 匹再贏")
        parts.append(f"合共 {wins} 匹具後續交代")
        return "；".join(parts)

    def _formline_level(self):
        text = str(self.data.get("formline_line") or "").strip()
        text = text.replace("✅", "").replace("⚠️", "").strip()
        if self._formline_rows() and ("無資料" in text or "未有出賽" in text):
            return "待驗證 (有對手線，未有後續承接)"
        if self._formline_rows() and self._is_misleading_formline_headline(text):
            return self._formline_inferred_level() or text
        # 上游「強組比例 a/b」嘅 a 係分數加總（超強 2、強 1、中 0.5），唔係「幾多個強組」，
        # 可以大過 b（AU 標籤審計 2026-11-13 #2）。顯示改講真意思；Facts 原文唔郁。
        return re.sub(r"強組比例[:：]\s*([\d.]+/\d+)", r"對手強度分 \1，超強2·強1·中0.5", text)

    def _formline_support_text(self, support, valid):
        if valid <= 0:
            return "0/0"
        support_text = str(int(support)) if float(support).is_integer() else f"{support:.1f}"
        return f"{support_text}/{valid}"

    def _formline_inferred_level(self):
        signal = self._formline_inferred_signal()
        if not signal:
            return ""
        if signal == "neutral":
            return "待驗證 (有對手線，未有後續承接)"
        support, valid = self._formline_support_summary()
        label_map = {
            "elite": "極強",
            "strong": "強",
            "medium_strong": "中強",
            "medium_weak": "中弱",
            "weak": "❌ 弱",
        }
        return f"{label_map.get(signal, '待驗證')} (承接分: {self._formline_support_text(support, valid)})"

    def _latest_record_summary(self, record_type="正式"):
        for cols in _record_rows(self.facts_section):
            kind = cols[1]
            is_trial = "試閘" in kind
            if record_type == "正式" and is_trial:
                continue
            if record_type == "試閘" and not is_trial:
                continue
            return self._record_row_summary(cols)
        return ""

    def _record_row_summary(self, cols):
        kind = cols[1]
        date = cols[2]
        venue = cols[3]
        distance = cols[4]
        going = cols[5]
        barrier = cols[6]
        placing = cols[7]
        trajectory = cols[9] if len(cols) > 9 else ""
        parts = [date, venue, distance, f"場地 {going}"]
        if barrier and barrier != "-":
            parts.append(f"檔位 {barrier}")
        parts.append(f"名次 {placing}")
        if trajectory and trajectory != "-":
            parts.append(f"走勢 {trajectory}")
        if "試閘" in kind:
            parts.insert(0, "試閘")
        return " | ".join(parts)

    def _advantages(self, feature_scores, matrix_scores):
        # 2026-08-01：門檻統一到 MATRIX_ADVANTAGE_CUTOFF。維度尺正規化之前，
        # 每個維度嘅 spread 差幾倍，所以呢啲 magic number 各自係對住唔同尺磨出嚟
        # ——`jockey_trainer >= 72`（舊上限 73.8）同 `class_weight >= 68`（舊上限
        # 69.5）實際上幾乎永遠唔會 fire。而家七個維度同一把尺，一個門檻就夠。
        cut = MATRIX_ADVANTAGE_CUTOFF
        items = []
        if matrix_scores.get("pace_perf", 60) >= cut:
            if feature_scores["distance_score"] >= 72:
                items.append("曾應付較快末段賽事環境，路程配套亦有支持")
            else:
                items.append("往績速度考驗背景唔差，但唔當成本駒個體末段實測")
        if matrix_scores["jockey_trainer"] >= cut:
            trainer = self._clean_identity(self.horse_data.get("trainer")) or "馬房"
            items.append(f"{trainer} 呢邊嘅部署訊號偏正面，人馬配搭有基本支持")
        if matrix_scores["track"] >= cut:
            items.append("場地或場館適性有實際證據，唔係紙上談兵")
        if matrix_scores["stability"] >= cut:
            items.append("近期交代密度夠，狀態線唔算飄")
        if matrix_scores.get("race_shape", 60) >= cut:
            items.append("檔位同步速形勢配腳，走位有本錢")
        if matrix_scores.get("class_weight", 60) >= cut:
            items.append("班次同負磅未見吃力，發揮門檻唔高")
        if self._forgiveness_count() >= 2:
            items.append("近仗至少有一兩場蝕位或受阻，紙面名次可能低估真身")
        if self._formline_followup_counts()["higher"] > 0:
            items.append("對手後續升班仲交到貨，賽績線唔薄")
        return items[:3] or ["整體結構平均，未見特別爆點，但亦唔算有明顯穿崩位"]

    def _au_readout_band(self, trend):
        t = str(trend or "")
        if any(w in t for w in ("上升", "進步", "加強", "改善", "受捧", "合拍", "已驗證", "升級")):
            return "✅"
        if any(w in t for w in ("下降", "退步", "放緩", "回落", "受冷", "轉差", "未驗證")):
            return "⚠️"
        return "➖"

    def _data_readout(self, feature_scores, matrix_scores):
        """Structured, fully-Chinese 數據判讀 rows for AU (label/value/trend/band/reason).
        Feeds the report + dashboard. Mirrors the HKJC readout using AU data lines."""
        rows = []

        def add(label, value, trend, band=None, reason=""):
            value = str(value or "").strip()
            trend = str(trend or "").strip()
            if value or trend:
                rows.append({"label": label, "value": value, "trend": trend,
                             "band": band or self._au_readout_band(trend), "reason": reason})

        def present(v):
            return v is not None and str(v).strip() not in ("", "N/A", "-", "--")

        d = self.data
        rf = d.get("recent_form") or self.horse_data.get("recent_form")
        if present(rf):
            add("近績", str(rf).strip(), "")
        l4 = self._l400_text()
        if l4:
            add("段速", l4, "")
        et = str(d.get("engine_type_line") or "")
        if present(et):
            m = re.search(r"（([^）]+)）|\(([^)]+)\)", et)  # keep the Chinese type, drop 'Type A/B'
            add("段速型態", (m.group(1) or m.group(2)) if m else et, "")
        dp = str(d.get("distance_profile_line") or "")
        # only the clean "今仗 1717m: …" segment; skip the messy "今仗 | ≥2000m" form
        m = re.search(r"今仗\s*\d+\s*m[：:]?\s*[^|（(]+", dp)
        if m:
            seg = m.group(0).strip(" -：:")
            band = "✅" if "✅" in m.group(0) else ("⚠️" if "⚠️" in m.group(0) else "➖")
            seg = re.sub(r"[✅⚠️]", "", seg).strip()
            add("今仗路程", seg, "", band=band)
        cm = self._class_move_today()
        if present(cm):
            cm_s = str(cm).strip()
            cband = "✅" if "降班" in cm_s else ("➖" if "升班" in cm_s else "➖")
            add("班次走向", cm_s, "", band=cband)
        # 檔位 + running-position bucket (AU has no per-barrier historical table,
        # so show the position bucket, not fabricated stats).
        bar = self.horse_data.get("barrier")
        if bar not in (None, "", 0):
            try:
                bn = int(bar)
                bucket = "內檔" if bn <= 4 else ("中檔" if bn <= 8 else ("外檔" if bn <= 12 else "極外檔"))
                add("檔位", f"{bn}檔", bucket, band="✅" if bn <= 4 else ("⚠️" if bn >= 13 else "➖"))
            except (TypeError, ValueError):
                pass
        # 預測跑法 — tactical position read (前置／守好位／守中／後上). Reference only:
        # explicitly NOT in the rating matrix. 戰術劇本（race scenario）只喺「檔位形勢」
        # 7D 維度出一次，呢度唔再塞落 reason，避免同一段劇本重覆四次。
        ps = self._predicted_style()
        if ps:
            add("預測跑法", ps["label"],
                f"信心{ps['conf']}" if ps["conf"] else "",
                band="➖")
        counts = self._formline_followup_counts()
        opp = self._formline_headwinner() if hasattr(self, "_formline_headwinner") else ""
        validated = counts["higher"] + counts["same"] + counts["lower"]
        field = set(self.race_context.get("field_horse_names") or []) if isinstance(getattr(self, "race_context", None), dict) else set()
        mine = self.horse_data.get("horse_name")
        h2h = sorted({nm for r in self._formline_rows() for nm in field
                      if nm and nm != mine and nm in str(r.get("opponent", ""))})
        if h2h:
            add("賽績線", "重遇" + "、".join(h2h), "曾交手", band="✅",
                reason=f"今場重遇曾交手對手{'、'.join(h2h)}")
        elif validated or opp:
            cls_bits = []
            if counts["higher"]:
                cls_bits.append(f"{counts['higher']}匹其後升班出賽")
            if counts["same"]:
                cls_bits.append(f"{counts['same']}匹同班出賽")
            if counts["lower"]:
                cls_bits.append(f"{counts['lower']}匹降班出賽")
            head = f"曾交手頭馬「{opp}」" if opp else "近仗對手線"
            add("賽績線", f"曾鬥頭馬「{opp}」" if opp else "近仗對手",
                "對手線有延續" if validated else "對手未驗證",
                band="✅" if validated else "➖",
                reason="；".join([head] + cls_bits) if cls_bits else head)
        mt = d.get("current_market_trend")
        if present(mt):
            band = "✅" if "受捧" in str(mt) else ("⚠️" if "受冷" in str(mt) else "➖")
            add("市場走勢", str(mt).strip(), "", band=band)
        gs = str(d.get("going_stats_line") or "")
        if present(gs):
            add("場地往績", gs.split("|")[0].strip(), "")
        cur = self._clean_identity(self.horse_data.get("jockey"))
        cur_line = str(d.get("current_jockey_history_line") or "")
        best_line = str(d.get("best_jockey_history_line") or "")
        if cur:
            up = best_line and cur and cur not in best_line  # today's rider ≠ the best historical one
            add("騎師", cur, "", reason=cur_line[:48] or None)
            if up and present(best_line):
                add("騎師往績", "", "最佳拍檔非今仗", band="➖", reason=best_line[:48])
        return rows

    def _core_logic(self, feature_scores, matrix_scores, advantages, disadvantages):
        """Data-grounded verdict: six ranking dimensions, then actual
        strengths and concerns (reusing the already-specific advantages/disadvantages).
        Drops the generic '做主軸 / 保留型 / 走勢未算鮮明' filler."""
        name = self.horse_data.get("horse_name", "此駒")
        # ``matrix_scores`` also carries report-only ``form_line`` for archive and
        # renderer compatibility.  It must never be described as the strongest or
        # weakest *ranking* dimension now that the live registry is six-dimensional.
        ordered = sorted(
            ((key, matrix_scores.get(key, 60.0)) for key in MATRIX_WEIGHTS),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top_dim = self._matrix_label(ordered[0][0])
        low_dim = self._matrix_label(ordered[-1][0])
        from .dimensions import ranking_dimension_numeral
        sents = [f"{name}今場{ranking_dimension_numeral(MATRIX_WEIGHTS)}個排名維度以{top_dim}（{ordered[0][1]:.0f}）最強、{low_dim}（{ordered[-1][1]:.0f}）最弱。"]
        real_adv = [a for a in (advantages or []) if "整體結構平均" not in a]
        real_dis = [d for d in (disadvantages or []) if "主要變數仍然係臨場步速" not in d]
        if real_adv:
            sents.append("優勢在於" + "；".join(real_adv[:3]) + "。")
        if real_dis:
            sents.append("要留意" + "；".join(real_dis[:3]) + "。")
        if "surface_transfer_unverified" in self.risk_flags:
            sents.append(self.form_detail.get("surface_transfer_note", ""))
        if not real_adv and not real_dis:
            sents.append("整體結構平均，未見特別爆點亦無明顯穿崩，臨場步速與形勢將係關鍵。")
        if self._career_starts() == 0:
            sents.append("初出馬正式賽績空白，以上以備戰及試閘數據作背景參考，須臨場驗證。")
        return re.sub(r"\s{2,}", " ", "".join(sents)).strip()

    def _forgiveness_brief(self):
        count = self._forgiveness_count()
        if count <= 0:
            return ""
        latest_flag = ""
        for entry in self._official_entries()[:4]:
            forgiveness = str(entry.get("forgiveness") or "").strip()
            if forgiveness and forgiveness not in {"[-]", "[需判定]"}:
                latest_flag = forgiveness
                break
        if latest_flag:
            return f"近四仗有 {count} 次可作寬恕，最近焦點為 {latest_flag}"
        return f"近四仗有 {count} 次可作寬恕"
